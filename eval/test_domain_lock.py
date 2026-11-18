"""
Domain-lock adversarial suite (plan section 21h).

Checks that the guardrails (Layer 4 injection defence + Layer 2 classifier) block
out-of-scope and injection queries and let legitimate ERP queries through. No model
is involved, so it is fast and runs in CI. Every case must pass: any failure blocks
deployment (exit code 1).

Cases live in eval/domain_lock_cases.jsonl:
    {"query": "...", "expected": "blocked" | "passed", "category": "..."}

Usage:
    python eval/test_domain_lock.py
    python eval/test_domain_lock.py --cases path/to/cases.jsonl
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from guardrails.layer4_injection import sanitize_input, detect_injection  # noqa: E402
from guardrails.layer2_classifier import classify_query  # noqa: E402


def load_centroids() -> str:
    """Load data/centroids.npz exactly like serve/app.py does. Returns the mode label."""
    import os
    from guardrails.layer2_classifier import set_domain_centroids, load_centroids
    path = Path(os.getenv("CENTROIDS_PATH", str(ROOT / "data" / "centroids.npz")))
    if path.exists():
        centroids = load_centroids(path)
        set_domain_centroids(centroids)
        return f"embedding + keyword ({len(centroids)} domain centroids)"
    return "KEYWORD-ONLY (no centroids; run scripts/build_centroids.py, the server uses centroids)"


def judge(query: str) -> str:
    """Returns 'blocked', 'clarify' or 'passed' for what the guardrails would do with this query."""
    q = sanitize_input(query)
    is_injection, _ = detect_injection(q)
    if is_injection:
        return "blocked"
    decision = classify_query(q).get("decision", "pass")
    if decision == "block":
        return "blocked"
    if decision == "clarify":
        return "clarify"
    return "passed"


def run_suite(cases: list) -> dict:
    res = {"pass": 0, "fail": 0, "failures": [], "by_category": defaultdict(lambda: [0, 0])}
    for tc in cases:
        got = judge(tc["query"])
        ok = got == tc["expected"]  # 'clarify' never counts as blocked or passed
        res["by_category"][tc["category"]][0 if ok else 1] += 1
        if ok:
            res["pass"] += 1
        else:
            res["fail"] += 1
            res["failures"].append({"query": tc["query"], "expected": tc["expected"], "got": got,
                                    "category": tc["category"]})
    total = len(cases)
    res["total"] = total
    res["score"] = res["pass"] / total if total else 0.0
    res["deployment_gate"] = total > 0 and res["fail"] == 0
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=str(ROOT / "eval" / "domain_lock_cases.jsonl"))
    args = ap.parse_args()

    with open(args.cases, encoding="utf-8") as f:
        cases = [json.loads(l) for l in f if l.strip()]
    mode = load_centroids()
    res = run_suite(cases)

    print(f"\n{'=' * 60}\n  Domain-lock suite: {res['pass']}/{res['total']} passed ({res['score']:.1%})\n  classifier mode: {mode}\n{'=' * 60}")
    for cat, (ok, bad) in sorted(res["by_category"].items()):
        print(f"  {cat:<28} {ok:>3} ok  {bad:>3} failed")
    if res["failures"]:
        print(f"\n  Failures ({len(res['failures'])}):")
        for f in res["failures"]:
            print(f"   - [{f['category']}] expected {f['expected']}, got {f['got']}: {f['query'][:90]}")

    out = ROOT / "eval" / "results"
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "domain_lock.json", "w", encoding="utf-8") as f:
        json.dump({**{k: v for k, v in res.items() if k != "by_category"},
                   "by_category": {k: {"ok": v[0], "failed": v[1]} for k, v in res["by_category"].items()}},
                  f, ensure_ascii=False, indent=1)

    print("\n  " + ("PASSED, deployment gate open" if res["deployment_gate"] else "FAILED, deployment blocked"))
    sys.exit(0 if res["deployment_gate"] else 1)


if __name__ == "__main__":
    main()
