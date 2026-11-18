"""The privacy-safe request log (plan 13a), the /metrics guard (plan 11b/20d) and the request store."""

import json

import pytest

from serve import redis_client
from serve.internal_only import InternalOnly, PROXY_HEADERS
from serve.request_log import log_request, user_hash

FIELDS = dict(request_id="r1", session_id="s1", user_hash="abc", query_chars=42, category="GST",
              guardrail=None, guardrail_layer=None, model="kinnow-v1", response_chars=120,
              latency_ms=15, flags=[])


class TestRequestLog:
    def test_writes_one_json_line_with_exactly_the_plan_fields(self, capsys):
        log_request(**FIELDS)
        line = capsys.readouterr().out.strip()
        entry = json.loads(line)
        assert "\n" not in line
        assert set(entry) == {"event", "ts", "request_id", "session_id", "user_hash", "query_chars", "category",
                              "guardrail", "guardrail_layer", "model", "response_chars", "latency_ms", "flags"}
        assert entry["event"] == "chat" and entry["query_chars"] == 42 and entry["latency_ms"] == 15

    def test_timestamp_is_utc_iso_8601(self, capsys):
        log_request(**FIELDS)
        ts = json.loads(capsys.readouterr().out)["ts"]
        assert ts.endswith("+00:00") and "T" in ts

    def test_the_function_cannot_be_given_text_to_log(self):
        """There is no parameter for query or response text, so it cannot leak by mistake."""
        with pytest.raises(TypeError):
            log_request(**FIELDS, query="My PAN is ABCDE1234F")
        with pytest.raises(TypeError):
            log_request(**FIELDS, response="some answer")

    def test_user_hash_is_stable_short_and_hides_the_id(self):
        h = user_hash("owner", "priya@example.com")
        assert h == user_hash("owner", "priya@example.com") and len(h) == 16
        assert "priya" not in h and "owner" not in h

    def test_user_hash_differs_by_user_and_by_owner(self):
        assert user_hash("o", "alice") != user_hash("o", "bob")
        assert user_hash("o1", "alice") != user_hash("o2", "alice")

    def test_user_hash_matches_what_the_pipeline_logs(self):
        from guardrails.pipeline import anonymise
        assert user_hash("owner", "alice") == anonymise("owner:alice")


class TestInternalOnlyGuard:
    async def call(self, headers):
        sent = []

        async def inner(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"metrics"})

        async def send(message):
            sent.append(message)

        scope = {"type": "http", "headers": [(k.encode(), v.encode()) for k, v in headers.items()]}
        await InternalOnly(inner)(scope, None, send)
        return sent[0]["status"], b"".join(m.get("body", b"") for m in sent[1:])

    async def test_requests_without_proxy_headers_reach_the_metrics_app(self):
        assert await self.call({"host": "10.0.0.5:8000", "user-agent": "Prometheus/2.x"}) == (200, b"metrics")

    @pytest.mark.parametrize("header", sorted(h.decode() for h in PROXY_HEADERS))
    async def test_any_proxy_header_means_the_request_came_from_outside(self, header):
        status, body = await self.call({header: "203.0.113.9"})
        assert status == 404 and body == b"Not Found"

    async def test_header_names_are_matched_case_insensitively(self):
        assert (await self.call({"X-FORWARDED-FOR": "203.0.113.9"}))[0] == 404

    async def test_non_http_scopes_pass_through(self):
        called = []

        async def inner(scope, receive, send):
            called.append(scope["type"])

        await InternalOnly(inner)({"type": "lifespan"}, None, None)
        assert called == ["lifespan"]


class TestRequestStore:
    async def test_roundtrip(self, fake_redis):
        await redis_client.request_set("owner", "req-1", {"query": "q", "response": "r", "session_id": "s"})
        assert await redis_client.request_get("owner", "req-1") == {"query": "q", "response": "r", "session_id": "s"}

    async def test_expires_after_an_hour_by_default(self, fake_redis):
        await redis_client.request_set("owner", "req-1", {})
        assert fake_redis.ttls["request:owner:req-1"] == 3600

    async def test_unknown_request_is_none(self, fake_redis):
        assert await redis_client.request_get("owner", "nope") is None

    async def test_one_owner_cannot_read_anothers_request(self, fake_redis):
        await redis_client.request_set("alice", "req-1", {"query": "secret"})
        assert await redis_client.request_get("bob", "req-1") is None

    async def test_feedback_push_carries_extra_fields(self, fake_redis):
        await redis_client.feedback_push("u", "q", "r", 1, request_id="req-1", comment="bad", text_expired=False)
        event = json.loads(fake_redis.lists["feedback:queue"][0])
        assert event == {"user_id": "u", "query": "q", "response": "r", "rating": 1,
                         "request_id": "req-1", "comment": "bad", "text_expired": False}
