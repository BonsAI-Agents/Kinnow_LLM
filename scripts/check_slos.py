"""
Canary SLO checker — called by CI during canary deploy.
Queries Prometheus to verify p95 latency and error rate are within SLO.

Usage:
    python scripts/check_slos.py --prometheus-url http://prometheus:9090

Exits 0 if SLOs pass, 1 if any SLO is violated.
"""

import argparse
import sys
import time
import urllib.request
import urllib.parse
import json

# SLO thresholds (must match monitoring/alerts.yml)
P95_LATENCY_SLO = 2.0   # seconds
ERROR_RATE_SLO = 0.01   # 1%

QUERIES = {
    'p95_latency': (
        'histogram_quantile(0.95, '
        'sum(rate(kinnow_request_duration_seconds_bucket[5m])) by (le))'
    ),
    'error_rate': (
        'sum(rate(kinnow_requests_total{status=~"5.."}[5m])) / '
        'sum(rate(kinnow_requests_total[5m]))'
    ),
}


def query_prometheus(base_url: str, promql: str) -> float | None:
    encoded = urllib.parse.urlencode({'query': promql})
    url = f"{base_url.rstrip('/')}/api/v1/query?{encoded}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
        results = data.get('data', {}).get('result', [])
        if not results:
            return None
        return float(results[0]['value'][1])
    except Exception as exc:
        print(f"  ERROR querying Prometheus: {exc}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prometheus-url', required=True)
    parser.add_argument('--retries', type=int, default=3,
                        help='Number of retries if Prometheus not ready')
    args = parser.parse_args()

    violations = []

    for attempt in range(args.retries):
        print(f"SLO check attempt {attempt + 1}/{args.retries}…")

        p95 = query_prometheus(args.prometheus_url, QUERIES['p95_latency'])
        err = query_prometheus(args.prometheus_url, QUERIES['error_rate'])

        if p95 is None and err is None:
            if attempt < args.retries - 1:
                print("  Prometheus not ready, retrying in 10s…")
                time.sleep(10)
                continue
            print("  Could not reach Prometheus after all retries — failing safe.")
            sys.exit(1)

        violations = []

        if p95 is not None:
            status = "PASS" if p95 <= P95_LATENCY_SLO else "FAIL"
            print(f"  p95 latency: {p95:.3f}s  (SLO ≤ {P95_LATENCY_SLO}s)  [{status}]")
            if p95 > P95_LATENCY_SLO:
                violations.append(f"p95 latency {p95:.3f}s > {P95_LATENCY_SLO}s SLO")

        if err is not None:
            status = "PASS" if err <= ERROR_RATE_SLO else "FAIL"
            print(f"  error rate:  {err:.4%}  (SLO ≤ {ERROR_RATE_SLO:.0%})  [{status}]")
            if err > ERROR_RATE_SLO:
                violations.append(f"error rate {err:.4%} > {ERROR_RATE_SLO:.0%} SLO")

        break

    if violations:
        print("\nSLO VIOLATIONS — rolling back canary:")
        for v in violations:
            print(f"  ✗ {v}")
        sys.exit(1)

    print("\nAll SLOs passed — promoting to production.")
    sys.exit(0)


if __name__ == '__main__':
    main()
