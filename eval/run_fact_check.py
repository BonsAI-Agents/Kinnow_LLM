"""
Fact check: one question per claim in data/tejas_review/FACTS_TO_VERIFY.md (eval/fact_checks.jsonl).

A claim passes when the answer has every word in `all_of`, at least one word from each `any_of` group,
and nothing from `must_not` (a stale or wrong figure). The facts file is the source of truth here: it is
Tejas's list, not yet checked by a CA. If the file changes, change eval/fact_checks.jsonl to match.

    python eval/run_fact_check.py --notes-only            # no model, no GPU: do the notes contain each fact?
    python eval/run_fact_check.py --self-test             # check the claim file against its own references
    python eval/run_fact_check.py --model-id Qwen/Qwen2.5-7B-Instruct --adapter models/sft_qwen25_v2 --rag 4

Exit code 1 when any claim fails (so it can gate a release).
"""

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

from run_full_eval import normalize_text, Responder  # noqa: E402

CLAIMS = ROOT / "eval" / "fact_checks.jsonl"
OUT = ROOT / "eval" / "results" / "fact_check.json"


def load_claims() -> list[dict]:
    with open(CLAIMS, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def check(text: str, claim: dict) -> dict:
    t = normalize_text(text)
    missing = [w for w in claim["all_of"] if normalize_text(w) not in t]
    missing += [" / ".join(g) for g in claim["any_of"] if not any(normalize_text(w) in t for w in g)]
    stale = [w for w in claim["must_not"] if normalize_text(w) in t]
    return {"passed": not missing and not stale, "missing": missing, "stale": stale}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-id")
    ap.add_argument("--adapter")
    ap.add_argument("--rag", type=int, default=0)
    ap.add_argument("--hybrid", action="store_true")
    ap.add_argument("--calc", action="store_true")
    ap.add_argument("--cite", action="store_true")
    ap.add_argument("--max-new-tokens", type=int, default=200)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--notes-only", action="store_true", help="only check the retrieved notes, no model")
    args = ap.parse_args()
    if not (args.self_test or args.notes_only or args.model_id):
        ap.error("give --model-id, --self-test or --notes-only")

    claims = load_claims()
    k = args.rag or 4

    from guardrails.retrieval import load_retriever
    retriever = load_retriever(hybrid=args.hybrid) if (args.notes_only or args.rag) else None

    responder = None
    if not args.notes_only:
        responder = Responder(SimpleNamespace(self_test=args.self_test, responses=None, model_id=args.model_id,
                                              adapter=args.adapter, max_new_tokens=args.max_new_tokens,
                                              rag=args.rag, hybrid=args.hybrid, calc=args.calc, cite=args.cite))

    rows = []
    for c in claims:
        row = {"id": c["id"], "source": c["source"], "tag": c.get("tag", ""), "question": c["question"]}
        if retriever:
            notes = " ".join(h["prompt"] + " " + h["completion"] for h in retriever.search(c["question"], k=k))
            n = check(notes, {**c, "must_not": []})   # stale words may appear in a note ("was 15,000"), so only look for the fact
            row["notes_ok"], row["notes_missing"] = n["passed"], n["missing"]
        if responder:
            text = responder.respond(c["question"], [], c["question"], c["reference"])
            m = check(text, c)
            row.update(answer_ok=m["passed"], answer_missing=m["missing"], answer_stale=m["stale"], answer=text)
        rows.append(row)

    total = len(rows)
    print(f"\n{'=' * 60}\n  Fact check: {total} claims from FACTS_TO_VERIFY.md\n{'=' * 60}")
    if retriever:
        ok = sum(r["notes_ok"] for r in rows)
        print(f"  notes contain the fact (top {k}) : {ok}/{total}  ({round(100 * ok / total)}%)")
    failed = []
    if responder:
        ok = sum(r["answer_ok"] for r in rows)
        label = "self-test" if args.self_test else "answers follow the facts"
        print(f"  {label:<31}: {ok}/{total}  ({round(100 * ok / total)}%)")
        failed = [r for r in rows if not r["answer_ok"]]
    elif retriever:
        failed = [r for r in rows if not r["notes_ok"]]
    for r in failed:
        why = r.get("answer_missing", r.get("notes_missing"))
        stale = r.get("answer_stale") or []
        print(f"   - {r['id']:<16} {r['tag']:<12} missing {why}" + (f" STALE {stale}" if stale else ""))
    if responder and retriever:
        print(f"  claims whose notes had the fact but the answer did not: "
              f"{sum(1 for r in rows if r['notes_ok'] and not r['answer_ok'])}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
