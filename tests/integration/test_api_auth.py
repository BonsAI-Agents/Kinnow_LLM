"""
Authentication and session isolation through the running app (serve/auth.py wired into the routes).
"""

import httpx
import pytest
from fastapi.testclient import TestClient

import serve.app as appmod
from guardrails.pipeline import KinnowGuardrailPipeline
from serve import vllm_client
from serve.auth import owner_id
from serve.routes import chat as chat_routes
from tests.conftest import TEST_API_KEY

GOOD_REPLY = (
    "The GST rate on restaurant services is 5% under SAC code 996331. "
    "Input tax credit is not available on this. File GSTR-3B by 20th of next month."
)
IN_SCOPE = "Explain GST filing in GSTR-3B for my invoice"
SECOND_KEY = "second-client-key"


async def _noop():
    return None


def bearer(key):
    return {"Authorization": f"Bearer {key}"}


@pytest.fixture
def seen_messages():
    return []


@pytest.fixture
def app_client(monkeypatch, fake_redis, tmp_path, seen_messages):
    """The running app with two accepted keys (primary plus a rotation key), no default auth header."""
    monkeypatch.setenv("API_KEY_NEW", SECOND_KEY)
    for name in ("init_redis", "close_redis", "init_vllm_client", "close_vllm_client"):
        monkeypatch.setattr(appmod, name, _noop)
    monkeypatch.setattr(appmod, "CENTROIDS_PATH", str(tmp_path / "missing.npy"))

    async def model_fn(messages):
        seen_messages.append(messages)
        return GOOD_REPLY

    with TestClient(appmod.app) as c:
        chat_routes.set_pipeline(KinnowGuardrailPipeline(model_fn=model_fn))
        yield c


PROTECTED = [
    ("/v1/chat", {"message": IN_SCOPE}),
    ("/v1/feedback", {"session_id": "s", "query": "q", "response": "r", "rating": "up"}),
]


class TestAuthentication:
    @pytest.mark.parametrize("path,body", PROTECTED)
    def test_protected_endpoints_reject_requests_without_a_key(self, app_client, path, body):
        r = app_client.post(path, json=body)
        assert r.status_code == 401
        assert r.headers["WWW-Authenticate"] == "Bearer"

    @pytest.mark.parametrize("path,body", PROTECTED)
    def test_protected_endpoints_reject_a_wrong_key(self, app_client, path, body):
        assert app_client.post(path, json=body, headers=bearer("not-the-key")).status_code == 401

    @pytest.mark.parametrize("path,body", PROTECTED)
    def test_both_the_primary_and_the_rotation_key_are_accepted(self, app_client, path, body):
        for key in (TEST_API_KEY, SECOND_KEY):
            assert app_client.post(path, json=body, headers=bearer(key)).status_code == 200

    def test_rejected_chat_request_never_touches_redis_or_the_model(self, app_client, fake_redis, seen_messages):
        app_client.post("/v1/chat", json={"message": IN_SCOPE})
        assert fake_redis.store == {} and seen_messages == []

    def test_probes_and_metrics_stay_open(self, app_client, monkeypatch):
        monkeypatch.setattr(
            vllm_client, "_client",
            httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)), base_url="http://vllm.test"),
        )
        assert app_client.get("/health").status_code == 200
        assert app_client.get("/ready").status_code == 200
        assert app_client.get("/metrics/").status_code == 200

    def test_the_app_refuses_to_start_without_an_api_key(self, monkeypatch, fake_redis):
        monkeypatch.delenv("API_KEY_PROD")
        for name in ("init_redis", "close_redis", "init_vllm_client", "close_vllm_client"):
            monkeypatch.setattr(appmod, name, _noop)
        with pytest.raises(RuntimeError, match="API_KEY_PROD"):
            with TestClient(appmod.app):
                pass


class TestSessionIsolation:
    SESSION = "shared-session-id"

    def send(self, client, key, message):
        return client.post("/v1/chat", json={"session_id": self.SESSION, "message": message}, headers=bearer(key))

    def test_one_key_cannot_read_anothers_history_by_guessing_the_session_id(self, app_client, seen_messages):
        self.send(app_client, TEST_API_KEY, "Explain GST filing in GSTR-3B for my confidential invoice 4471")
        self.send(app_client, SECOND_KEY, "Explain GST filing in GSTR-1 for my invoice")
        assert not any("confidential invoice 4471" in m["content"] for m in seen_messages[1])

    def test_the_same_key_still_gets_its_own_history_back(self, app_client, seen_messages):
        first = "Explain GST filing in GSTR-3B for my invoice"
        self.send(app_client, TEST_API_KEY, first)
        self.send(app_client, TEST_API_KEY, "Explain GST filing in GSTR-1 for my invoice")
        assert any(m["content"] == first for m in seen_messages[1])

    def test_sessions_are_stored_under_the_owner_namespace(self, app_client, fake_redis):
        self.send(app_client, TEST_API_KEY, IN_SCOPE)
        self.send(app_client, SECOND_KEY, IN_SCOPE)
        assert f"session:{owner_id(TEST_API_KEY)}:{self.SESSION}" in fake_redis.store
        assert f"session:{owner_id(SECOND_KEY)}:{self.SESSION}" in fake_redis.store
        assert f"session:{self.SESSION}" not in fake_redis.store

    def test_rate_limit_state_is_separate_per_key(self, app_client):
        """One key exhausting its off-topic allowance must not rate-limit another key's same session id."""
        for _ in range(10):
            self.send(app_client, TEST_API_KEY, "What is the weather in Mumbai today?")
        limited = self.send(app_client, TEST_API_KEY, "What is the weather in Mumbai today?").json()
        assert limited["block_reason"] == "rate_limited"
        other = self.send(app_client, SECOND_KEY, IN_SCOPE).json()
        assert other["blocked"] is False


class TestRateLimitIsSharedThroughRedis:
    """The app builds its pipeline with the Redis limiter, so replicas share the off-topic counter."""

    def test_the_app_pipeline_uses_the_redis_limiter(self, monkeypatch, fake_redis, tmp_path):
        from serve.rate_limiter import RedisRateLimiter
        for name in ("init_redis", "close_redis", "init_vllm_client", "close_vllm_client"):
            monkeypatch.setattr(appmod, name, _noop)
        monkeypatch.setattr(appmod, "CENTROIDS_PATH", str(tmp_path / "missing.npy"))
        with TestClient(appmod.app) as c:
            assert isinstance(chat_routes.get_pipeline()._limiter, RedisRateLimiter)
            c.post("/v1/chat", json={"session_id": "s1", "message": "What is the weather in Mumbai today?"},
                   headers=bearer(TEST_API_KEY))
        assert f"rl:oos:count:{owner_id(TEST_API_KEY)}:s1" in fake_redis.store

    def test_ten_off_topic_questions_limit_the_caller_through_redis(self, monkeypatch, fake_redis, tmp_path):
        for name in ("init_redis", "close_redis", "init_vllm_client", "close_vllm_client"):
            monkeypatch.setattr(appmod, name, _noop)
        monkeypatch.setattr(appmod, "CENTROIDS_PATH", str(tmp_path / "missing.npy"))
        with TestClient(appmod.app) as c:
            for _ in range(10):
                c.post("/v1/chat", json={"session_id": "s1", "message": "What is the weather in Mumbai today?"},
                       headers=bearer(TEST_API_KEY))
            r = c.post("/v1/chat", json={"session_id": "s1", "message": "What is the weather in Mumbai today?"},
                       headers=bearer(TEST_API_KEY))
        assert r.json()["block_reason"] == "rate_limited"
        assert f"rl:oos:limited:{owner_id(TEST_API_KEY)}:s1" in fake_redis.store
