"""
Rule lookup (retrieval) for Kinnow answers.

The fine-tuned model learns the style of an answer but not every section number, form name and
due date. This module finds the most relevant reviewed Q&A notes for a question, so the server can
hand them to the model as reference text before it answers.

No extra dependencies: BM25 over a small JSONL knowledge file (data/knowledge/kb.jsonl, built by
scripts/build_kb.py from the reviewed training data, without refusal rows).
"""

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

DEFAULT_KB_PATH = "data/knowledge/kb.jsonl"

_STOP = frozenset(
    "a an and are as at be by can do does for from how i if in is it its my of on or our so that the "
    "their then there this to was we what when where which who why will with you your should must "
    "has have had not no yes".split()
)
# Kept whole, so "50(3)", "rfd-11" and "cmp-08" match as written
_TOKEN = re.compile(r"[a-z0-9]+(?:[-./()][a-z0-9]+)*\)?")


def tokenize(text: str) -> list[str]:
    tokens = []
    for t in _TOKEN.findall(text.lower()):
        if t in _STOP:
            continue
        tokens.append(t)
        # also index the pieces, so "gstr-9" is found by "gstr" and "9", and "17(2)" by "17"
        parts = [p for p in re.split(r"[-./()]", t) if p]
        if len(parts) > 1:
            tokens.extend(p for p in parts if p not in _STOP)
    return tokens


class Retriever:
    def __init__(self, rows: list[dict], k1: float = 1.5, b: float = 0.75):
        self.rows = rows
        self.k1, self.b = k1, b
        self.docs = [Counter(tokenize(r["prompt"] + " " + r["completion"])) for r in rows]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg_len = (sum(self.lengths) / len(self.lengths)) if self.lengths else 1.0
        df = Counter()
        for d in self.docs:
            df.update(d.keys())
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def search(self, query: str, k: int = 3, min_score: float = 0.0) -> list[dict]:
        q = Counter(tokenize(query))
        scored = []
        for i, d in enumerate(self.docs):
            s, norm = 0.0, self.k1 * (1 - self.b + self.b * self.lengths[i] / self.avg_len)
            for t in q:
                f = d.get(t)
                if f:
                    s += self.idf[t] * f * (self.k1 + 1) / (f + norm)
            if s > min_score:
                scored.append((s, i))
        scored.sort(reverse=True)
        return [{**self.rows[i], "score": round(s, 3)} for s, i in scored[:k]]


class HybridRetriever(Retriever):
    """BM25 plus embedding similarity, merged by reciprocal rank fusion.

    Word matching misses paraphrases ("unpaid supplier" vs "vendor not paid"); embeddings miss exact
    section and form numbers. Together they put the needed note in the top 4 more often (measured on
    the eval's required terms: 64% -> 70%). Needs sentence-transformers (already used by Layer 2).
    Note embeddings are cached next to the knowledge file, keyed by its content."""

    MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    def __init__(self, rows: list[dict], cache_path: str | Path | None = None, depth: int = 30, **kw):
        super().__init__(rows, **kw)
        import numpy as np
        from sentence_transformers import SentenceTransformer
        self._np = np
        self.depth = depth
        self.model = SentenceTransformer(self.MODEL)
        docs = [r["prompt"] + " " + r["completion"] for r in rows]
        key = hashlib.sha1("\n".join(docs).encode("utf-8")).hexdigest()[:12]
        cache = Path(str(cache_path) + f".{key}.npy") if cache_path else None
        if cache and cache.exists():
            self.emb = np.load(cache)
        else:
            self.emb = self.model.encode(docs, batch_size=64, normalize_embeddings=True, show_progress_bar=False)
            if cache:
                np.save(cache, self.emb)
        self._pos = {id(r): i for i, r in enumerate(rows)}

    def search(self, query: str, k: int = 3, min_score: float = 0.0) -> list[dict]:
        np = self._np
        sims = self.emb @ self.model.encode([query], normalize_embeddings=True)[0]
        fused: dict[int, float] = {}
        bm_hits = super().search(query, k=self.depth, min_score=min_score)
        text_to_i = {(r["prompt"], r["completion"]): i for i, r in enumerate(self.rows)}
        bm_score: dict[int, float] = {}
        for rank, h in enumerate(bm_hits):
            i = text_to_i[(h["prompt"], h["completion"])]
            fused[i] = fused.get(i, 0.0) + 1.0 / (60 + rank)
            bm_score[i] = h["score"]
        for rank, i in enumerate(np.argsort(-sims)[: self.depth]):
            i = int(i)
            fused[i] = fused.get(i, 0.0) + 1.0 / (60 + rank)
        top = sorted(fused, key=lambda i: -fused[i])[:k]
        return [{**self.rows[i], "score": round(fused[i], 5), "bm25": bm_score.get(i, 0.0)} for i in top]


_default: Retriever | None = None


def load_retriever(path: str | Path = DEFAULT_KB_PATH, hybrid: bool = False) -> Retriever:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    if hybrid:
        return HybridRetriever(rows, cache_path=path)
    return Retriever(rows)


def get_retriever(path: str | Path = DEFAULT_KB_PATH) -> Retriever | None:
    """Shared retriever; None when the knowledge file is missing (the server then runs without it)."""
    global _default
    if _default is None:
        if not Path(path).exists():
            return None
        _default = load_retriever(path)
    return _default


def format_notes(hits: list[dict]) -> str:
    """Reference text placed ahead of the question."""
    lines = [f"- Q: {h['prompt']}\n  A: {h['completion']}" for h in hits]
    return ("Reference notes from Kinnow's reviewed rules. Use them if they apply to the question; "
            "ignore them if they do not.\n" + "\n".join(lines))




def with_notes(question: str, hits: list[dict], computed: str | None = None) -> str:
    """The user turn with reference notes (and the system's own working, if any) in front.
    Unchanged when there is nothing to add."""
    parts = []
    if hits:
        parts.append(format_notes(hits))
    if computed:
        parts.append("Computed by the system (use these exact figures in your answer): " + computed)
    if not parts:
        return question
    return "\n\n".join(parts) + f"\n\nQuestion: {question}"


# ---------- citation line ----------

_SECTION = re.compile(r"\bSections? \d+[A-Z]{0,2}(?:\([0-9A-Za-z]+\))*")
_RULE = re.compile(r"\bRules? \d+[A-Z]{0,2}(?:\([0-9A-Za-z]+\))*")
_FORM = re.compile(r"\b(?:Form [0-9]{1,3}[A-Z]?|GSTR-[0-9][A-Z]?|CMP-\d+|ITC-\d+|RFD-\d+|DRC-\d+|GST [A-Z]+-\d+)\b")


def sources_line(hits: list[dict], max_refs: int = 5, rel: float = 0.6) -> str:
    """'Sources: Section 16(2)(aa), Rule 37, GSTR-2B' taken from the notes the lookup found.

    Only citations that actually appear in the top notes (and only notes scoring close to the best one)
    are used, so nothing is invented. Empty when the notes cite nothing."""
    if not hits:
        return ""
    def strength(h):
        return h.get("bm25", h.get("score", 0)) or 0

    top = strength(hits[0])
    refs: list[str] = []
    for h in hits[:2]:
        if top and strength(h) < rel * top:
            continue
        for pat in (_SECTION, _RULE, _FORM):
            for m in pat.findall(h["completion"]):
                m = m.replace("Sections ", "Section ").replace("Rules ", "Rule ")
                if m not in refs:
                    refs.append(m)
    return ("Sources: " + ", ".join(refs[:max_refs]) + ".") if refs else ""
