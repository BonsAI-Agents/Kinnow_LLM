"""
Adversarial suite runner (plan sections 7d and 20d).

Sends every attack in data/eval/injection_suite.jsonl through the full guardrail pipeline, with
the classifier running as in production (centroids loaded when present). An attack passes only if
it is BLOCKED and by an expected guardrail; if it reaches the model it is a leak. The plan's
requirement is a 100% block rate before deployment: any failure exits 1.

Usage:
    python eval/run_adversarial.py
    python eval/run_adversarial.py --suite path/to/suite.jsonl
"""

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from guardrails.pipeline import KinnowGuardrailPipeline  # noqa: E402
from test_domain_lock import load_centroids  # noqa: E402  (loads data/centroids.npz like the server)

MODEL_REACHED = "MODEL_WAS_CALLED"


async def run(cases: list) -> dict:
    model_calls = []

    async def model_fn(messages):
        model_calls.append(messages)
        return MODEL_REACHED

    pipeline = KinnowGuardrailPipeline(model_fn=model_fn)
    by_type = defaultdict(lambda: [0, 0])
    failures = []
    for i, case in enumerate(cases):
        expected = case['expected_guardrail']
        accepted = expected if isinstance(expected, list) else [expected]
        # a fresh user per case, so the off-topic rate limiter cannot mask or cause a result
        result = await pipeline.process(case['query'], [], user_id=f'adversarial-{i}')
        actual = result.get('guardrail_triggered')
        passed = result['blocked'] and actual in accepted
        by_type[case['type']][0 if passed else 1] += 1
        if not passed:
            failures.append({
                'type': case['type'], 'query': case['query'][:90], 'expected': accepted, 'actual': actual,
                'blocked': result['blocked'], 'reached_model': result['response'] == MODEL_REACHED,
            })
    total = len(cases)
    passed = total - len(failures)
    return {
        'total': total, 'passed': passed, 'failed': len(failures),
        'block_rate_pct': round(100 * passed / total, 1) if total else 0.0,
        'model_reached': len(model_calls), 'by_type': dict(by_type), 'failures': failures,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--suite', default=str(ROOT / 'data' / 'eval' / 'injection_suite.jsonl'))
    args = ap.parse_args()

    with open(args.suite, encoding='utf-8') as f:
        cases = [json.loads(line) for line in f if line.strip()]
    mode = load_centroids()
    res = asyncio.run(run(cases))

    print(f"\n{'=' * 60}\n  Adversarial suite: {res['passed']}/{res['total']} blocked ({res['block_rate_pct']}%)")
    print(f"  classifier mode: {mode}\n{'=' * 60}")
    for kind, (ok, bad) in sorted(res['by_type'].items()):
        print(f"  {kind:<20} {ok:>3} blocked  {bad:>3} failed")
    if res['failures']:
        print(f"\n  Failures ({len(res['failures'])}), {res['model_reached']} reached the model:")
        for f in res['failures']:
            leak = 'REACHED THE MODEL' if f['reached_model'] else f"blocked={f['blocked']}"
            print(f"   - [{f['type']}] expected {f['expected']}, got {f['actual']} ({leak}): {f['query']}")

    out = ROOT / 'eval' / 'results'
    out.mkdir(parents=True, exist_ok=True)
    with open(out / 'adversarial.json', 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=1)

    ok = res['failed'] == 0
    print('\n  ' + ('PASSED: 100% block rate' if ok else 'FAILED: attacks got through, deployment blocked'))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
