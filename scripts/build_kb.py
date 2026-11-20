"""
Build the rule-lookup knowledge file from the reviewed training data.

    python scripts/build_kb.py                      # data/v2_training/raw.jsonl -> data/knowledge/kb.jsonl

Refusal rows are left out (they hold no facts). Rows held for CA review are not in raw.jsonl, so they
stay out too. Questions that also appear in the eval files are left out, so the eval stays a fair test.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data/v2_training/raw.jsonl"
OUT = ROOT / "data/knowledge/kb.jsonl"
EVAL_FILES = [ROOT / "eval/golden_set.jsonl", ROOT / "eval/hindi_eval_30.jsonl", ROOT / "eval/multiturn_eval_20.jsonl"]


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
    return 0


if __name__ == "__main__":
    sys.exit(main())
