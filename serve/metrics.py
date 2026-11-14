"""Prometheus metrics for the Kinnow API server."""

from prometheus_client import Counter, Histogram, Gauge

REQUEST_COUNT = Counter(
    'kinnow_requests_total',
    'Total requests received',
    ['endpoint', 'status'],
)

BLOCK_COUNT = Counter(
    'kinnow_blocks_total',
    'Total requests blocked by guardrails',
    ['layer', 'reason'],
)

LATENCY = Histogram(
    'kinnow_request_duration_seconds',
    'End-to-end request latency',
    ['endpoint'],
    buckets=[0.1, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0],
)

MODEL_LATENCY = Histogram(
    'kinnow_model_duration_seconds',
    'Model inference latency only',
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 4.0],
)

ACTIVE_REQUESTS = Gauge(
    'kinnow_active_requests',
    'Currently in-flight requests',
)

OOS_RATE = Counter(
    'kinnow_oos_queries_total',
    'Out-of-scope queries blocked by classifier',
)

FEEDBACK_COUNT = Counter(
    'kinnow_feedback_total',
    'User feedback submissions',
    ['rating'],
)
