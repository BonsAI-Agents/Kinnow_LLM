"""
Rule lookup (retrieval) for Kinnow answers.

The fine-tuned model learns the style of an answer but not every section number, form name and
due date. This module finds the most relevant reviewed Q&A notes for a question, so the server can
hand them to the model as reference text before it answers.

No extra dependencies: BM25 over a small JSONL knowledge file (data/knowledge/kb.jsonl, built by
scripts/build_kb.py from the reviewed training data, without refusal rows).
"""

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


_default: Retriever | None = None


def load_retriever(path: str | Path = DEFAULT_KB_PATH) -> Retriever:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
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


def with_notes(question: str, hits: list[dict]) -> str:
    """The user turn with reference notes in front. Unchanged when nothing was found."""
    if not hits:
        return question
    return f"{format_notes(hits)}\n\nQuestion: {question}"
