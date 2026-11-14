"""
Load test for Kinnow ERP LLM API.
Target: 21 req/sec sustained, p95 < 2s, over 10 minutes.

Run:
    locust -f tests/load/locustfile.py --host http://localhost:8000 \
           --users 50 --spawn-rate 5 --run-time 10m --headless
"""

import uuid
from locust import HttpUser, task, between, events
from tests.load.scenarios import weighted_query, random_erp


class KinnowUser(HttpUser):
    wait_time = between(0.5, 2.0)  # 0.5–2s between requests per user

    def on_start(self):
        self.session_id = str(uuid.uuid4())

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
        self.client.post('/v1/feedback', json={
            'session_id': self.session_id,
            'query': random_erp(),
            'response': 'Some model response.',
            'rating': 'down',
        }, name='/v1/feedback')

    def _chat(self, message: str):
        with self.client.post(
            '/v1/chat',
            json={'session_id': self.session_id, 'message': message},
            name='/v1/chat',
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
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
