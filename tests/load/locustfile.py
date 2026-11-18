"""
Load test for Kinnow ERP LLM API.
Target: 21 req/sec sustained, p95 < 2s, over 10 minutes.

Run:
    locust -f tests/load/locustfile.py --host http://localhost:8000 \
           --users 50 --spawn-rate 5 --run-time 10m --headless
"""

import os
import uuid
from locust import HttpUser, task, between, events
from tests.load.scenarios import weighted_query, random_erp


class KinnowUser(HttpUser):
    wait_time = between(0.5, 2.0)  # 0.5–2s between requests per user

    def on_start(self):
        self.session_id = str(uuid.uuid4())
        self.user_id = f'load-{uuid.uuid4().hex[:8]}'
        self.last_request_id = None
        # The endpoints require authentication: pass a key the server accepts (API_KEY_PROD / API_KEY_NEW).
        api_key = os.environ.get('API_KEY', '')
        if not api_key:
            raise SystemExit('Set the API_KEY environment variable to a key the server accepts.')
        self.client.headers.update({'Authorization': f'Bearer {api_key}'})

    @task(7)
    def chat_erp(self):
        """ERP query — should pass through and get a response."""
        self._chat(random_erp())

    @task(3)
    def chat_mixed(self):
        """Weighted mix including OOS and injection — most should be blocked fast."""
        self._chat(weighted_query())

    @task(1)
    def feedback(self):
        """Submit a thumbs-down feedback."""
        if not self.last_request_id:
            return
        self.client.post('/v1/feedback', json={
            'user_id': self.user_id,
            'session_id': self.session_id,
            'request_id': self.last_request_id,
            'rating': 1,
        }, name='/v1/feedback')

    def _chat(self, message: str):
        with self.client.post(
            '/v1/chat',
            json={'user_id': self.user_id, 'session_id': self.session_id, 'message': message},
            name='/v1/chat',
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                self.last_request_id = resp.json().get('request_id')
                resp.success()
            elif resp.status_code == 429:
                resp.success()  # the per-user limit (20/min) is expected under load
            elif resp.status_code == 503:
                resp.failure("Circuit breaker open or service unavailable")
            else:
                resp.failure(f"Unexpected status {resp.status_code}")


@events.quitting.add_listener
def on_quitting(environment, **kwargs):
    """Fail the run if p95 > 2s or error rate > 1%."""
    stats = environment.stats.total
    if stats.num_requests == 0:
        return

    error_rate = stats.num_failures / stats.num_requests
    p95 = stats.get_response_time_percentile(0.95) / 1000  # ms → s

    print(f"\nLoad test summary:")
    print(f"  Total requests : {stats.num_requests}")
    print(f"  Error rate     : {error_rate:.2%}")
    print(f"  p95 latency    : {p95:.2f}s")

    if p95 > 2.0:
        print(f"  FAILED: p95 {p95:.2f}s exceeds 2s SLO")
        environment.process_exit_code = 1
    elif error_rate > 0.01:
        print(f"  FAILED: error rate {error_rate:.2%} exceeds 1% SLO")
        environment.process_exit_code = 1
    else:
        print("  PASSED ✓")
