"""Re-score saved answers with the strict and the lenient scorer, side by side. No model needed.

Usage: python scripts/rescore.py path/to/<label>_full.json [--show]
Prints per topic: strict score, lenient score, and (with --show) the questions the lenient scorer rescues.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
from lenient import evaluate  # noqa: E402


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    data = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    rows = data["golden"]
    tot = defaultdict(lambda: [0, 0, 0])
    rescued, lost = [], []
    for r in rows:
        strict = bool(r["passed"])
        lenient = evaluate(r["response"], r["must_contain"], r.get("must_not_contain"))["passed"]
        for key in (r["category"], "ALL"):
            tot[key][0] += 1
            tot[key][1] += strict
            tot[key][2] += lenient
        if lenient and not strict:
            rescued.append(r)
        if strict and not lenient:
            lost.append(r)
    print(f"{'topic':10s} {'n':>4s} {'strict':>8s} {'lenient':>8s}")
    for key, (n, s, l) in sorted(tot.items()):
        print(f"{key:10s} {n:4d} {100 * s / n:7.1f}% {100 * l / n:7.1f}%")
    print(f"\nrescued by the lenient scorer: {len(rescued)}   lost: {len(lost)}")
    if "--show" in sys.argv:
        for r in rescued:
            print("  +", r["category"], r["tag"], r["must_contain"])
        for r in lost:
            print("  -", r["category"], r["tag"], r["must_contain"])


if __name__ == "__main__":
    main()
