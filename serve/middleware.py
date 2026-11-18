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
        endpoint = request.url.path

        try:
            response = await call_next(request)
        except Exception:
            # An unhandled error becomes a 500 above this middleware: still count and log it.
            self._record(request, request_id, endpoint, 500, time.perf_counter() - t0)
            raise
        finally:
            # Always release the gauge, otherwise one exception inflates it forever.
            ACTIVE_REQUESTS.dec()

        self._record(request, request_id, endpoint, response.status_code, time.perf_counter() - t0)
        response.headers['X-Request-ID'] = request_id
        return response

    @staticmethod
    def _record(request: Request, request_id: str, endpoint: str, status: int, elapsed: float):
        REQUEST_COUNT.labels(endpoint=endpoint, status=str(status)).inc()
        LATENCY.labels(endpoint=endpoint).observe(elapsed)
        print(json.dumps({
            'request_id': request_id,
            'method': request.method,
            'path': endpoint,
            'status': status,
            'duration_ms': round(elapsed * 1000, 1),
        }), file=sys.stdout)
