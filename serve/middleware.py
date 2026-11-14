"""
Request middleware:
- Injects a unique request ID into every request
- Structured JSON logging for every request/response
- Tracks active request count (Prometheus gauge)
"""

import time
import uuid
import json
import sys
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from serve.metrics import REQUEST_COUNT, LATENCY, ACTIVE_REQUESTS


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        ACTIVE_REQUESTS.inc()
        t0 = time.perf_counter()

        response = await call_next(request)

        elapsed = time.perf_counter() - t0
        ACTIVE_REQUESTS.dec()

        endpoint = request.url.path
        status = str(response.status_code)

        REQUEST_COUNT.labels(endpoint=endpoint, status=status).inc()
        LATENCY.labels(endpoint=endpoint).observe(elapsed)

        log = {
            'request_id': request_id,
            'method': request.method,
            'path': endpoint,
            'status': response.status_code,
            'duration_ms': round(elapsed * 1000, 1),
        }
        print(json.dumps(log), file=sys.stdout)

        response.headers['X-Request-ID'] = request_id
        return response
