"""
Build the rule-lookup knowledge file from the reviewed training data.

    python scripts/build_kb.py                      # data/v2_training/raw.jsonl -> data/knowledge/kb.jsonl
    python scripts/build_kb.py --embed              # also precompute the note embeddings the hybrid lookup uses
                                                    # (about 4 minutes on CPU; the server then starts fast and the
                                                    # data folder can be mounted read-only)

Refusal rows and the generated calculation rows are left out (no facts to look up). Rows held for CA review are not in raw.jsonl, so they
stay out too. Rows in data/knowledge_extra/checklist_notes.jsonl (facts from Tejas's checklist that the training data lacks) are added.
Questions that also appear in the eval files are left out, so the eval stays a fair test.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data/v2_training/raw.jsonl"
OUT = ROOT / "data/knowledge/kb.jsonl"
EXTRA = ROOT / "data/knowledge_extra/checklist_notes.jsonl"   # facts from FACTS_TO_VERIFY.md that the training data lacks
EVAL_FILES = [ROOT / "eval/golden_set.jsonl", ROOT / "eval/hindi_eval_30.jsonl", ROOT / "eval/multiturn_eval_20.jsonl"]
NOTES = ROOT / "data/tejas/new_v3/kb_notes_verified.jsonl"   # short rule notes from Tejas's batch 15, checked one by one


def note_rows(entries: list[dict]) -> list[dict]:
    """Turn knowledge notes {domain, topic, note, citation} into lookup rows. The citation goes into the text so the
    Sources line can quote it."""
    rows = []
    for e in entries:
        topic, note = (e.get("topic") or "").strip(), (e.get("note") or "").strip()
        if not topic or not note:
            continue
        cite = (e.get("citation") or "").strip()
        rows.append({"domain": e.get("domain") or "GST", "prompt": topic,
                     "completion": note + (f" Reference: {cite}." if cite else "")})
    return rows


sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_calc_rows import generate as generate_calc_rows  # noqa: E402


def norm(s: str) -> str:
    return re.sub(r"\W+", " ", s.lower()).strip()


def load(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def eval_questions() -> set[str]:
    qs = set()
    for p in EVAL_FILES:
        if not p.exists():
            continue
        for r in load(p):
            for key in ("question", "prompt"):
                if r.get(key):
                    qs.add(norm(r[key]))
            for t in r.get("turns", []):
                if isinstance(t, dict) and t.get("content"):
                    qs.add(norm(t["content"]))
    return qs


def main() -> int:
    rows = [r for r in load(SRC) if r.get("domain") != "REFUSAL" and r.get("prompt") and r.get("completion")]
    if EXTRA.exists():
        rows += [r for r in load(EXTRA) if r.get("prompt") and r.get("completion")]
    if NOTES.exists():
        rows += note_rows(load(NOTES))
    # Generated calculation rows are for training only. As notes they crowd out the fact notes: a question
    # about the composition limit then retrieves worked composition examples instead of the limit itself.
    generated = {norm(g["prompt"]) for g in generate_calc_rows(42)}
    rows = [r for r in rows if norm(r["prompt"]) not in generated]
    eval_qs = eval_questions()
    leaked = [r for r in rows if norm(r["prompt"]) in eval_qs]
    rows = [r for r in rows if norm(r["prompt"]) not in eval_qs]
    print(f"left out {len(leaked)} rows whose question is also in the eval files")
    seen, kept = set(), []
    for r in rows:
        key = norm(r["prompt"])
        if key in seen:
            continue
        seen.add(key)
        kept.append({"domain": r["domain"], "prompt": r["prompt"], "completion": r["completion"]})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for r in kept:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(kept)} notes written to {OUT.relative_to(ROOT)}")
    if "--embed" in sys.argv:
        sys.path.insert(0, str(ROOT))
        from guardrails.retrieval import HybridRetriever
        HybridRetriever(kept, cache_path=OUT)          # writes data/knowledge/kb.jsonl.<key>.npy
        print("note embeddings cached next to the knowledge file")
    return 0


if __name__ == "__main__":
    sys.exit(main())
