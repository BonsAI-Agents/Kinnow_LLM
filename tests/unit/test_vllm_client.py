"""Unit tests for serve/vllm_client.py using httpx's mock transport (no real model server)."""

import json

import httpx
import pytest
from prometheus_client import REGISTRY

from serve import vllm_client

MESSAGES = [{"role": "system", "content": "sys"}, {"role": "user", "content": "GST rate?"}]


def install_client(monkeypatch, handler):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://vllm.test")
    monkeypatch.setattr(vllm_client, "_client", client)
    return client


def completion(text="18% under SAC 998314"):
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": text}}]})


class TestGenerate:
    async def test_returns_the_assistant_text(self, monkeypatch):
        install_client(monkeypatch, lambda request: completion("hello"))
        assert await vllm_client.generate(MESSAGES) == "hello"

    async def test_sends_the_expected_openai_payload(self, monkeypatch):
        captured = {}

        def handler(request: httpx.Request):
            captured["path"] = request.url.path
            captured["body"] = json.loads(request.content)
            return completion()

        install_client(monkeypatch, handler)
        await vllm_client.generate(MESSAGES, max_tokens=64)
        body = captured["body"]
        assert captured["path"] == "/v1/chat/completions"
        assert body["messages"] == MESSAGES
        assert body["max_tokens"] == 64
        assert body["model"] == vllm_client.MODEL_NAME
        assert body["stream"] is False
        assert body["temperature"] == vllm_client.DEFAULT_TEMPERATURE
        assert body["top_p"] == vllm_client.DEFAULT_TOP_P

    async def test_default_max_tokens(self, monkeypatch):
        captured = {}

        def handler(request):
            captured["max_tokens"] = json.loads(request.content)["max_tokens"]
            return completion()

        install_client(monkeypatch, handler)
        await vllm_client.generate(MESSAGES)
        assert captured["max_tokens"] == vllm_client.DEFAULT_MAX_TOKENS

    async def test_records_model_latency(self, monkeypatch):
        install_client(monkeypatch, lambda request: completion())
        before = REGISTRY.get_sample_value("kinnow_model_duration_seconds_count") or 0
        await vllm_client.generate(MESSAGES)
        assert REGISTRY.get_sample_value("kinnow_model_duration_seconds_count") == before + 1

    async def test_http_error_status_raises(self, monkeypatch):
        install_client(monkeypatch, lambda request: httpx.Response(500, text="boom"))
        with pytest.raises(httpx.HTTPStatusError):
            await vllm_client.generate(MESSAGES)

    async def test_connection_failure_raises(self, monkeypatch):
        def handler(request):
            raise httpx.ConnectError("refused")

        install_client(monkeypatch, handler)
        with pytest.raises(httpx.ConnectError):
            await vllm_client.generate(MESSAGES)

    async def test_empty_choices_is_an_error(self, monkeypatch):
        install_client(monkeypatch, lambda request: httpx.Response(200, json={"choices": []}))
        with pytest.raises(ValueError, match="empty choices"):
            await vllm_client.generate(MESSAGES)

    async def test_failed_call_does_not_record_latency(self, monkeypatch):
        install_client(monkeypatch, lambda request: httpx.Response(503))
        before = REGISTRY.get_sample_value("kinnow_model_duration_seconds_count") or 0
        with pytest.raises(httpx.HTTPStatusError):
            await vllm_client.generate(MESSAGES)
        assert (REGISTRY.get_sample_value("kinnow_model_duration_seconds_count") or 0) == before


class TestLifecycle:
    def test_get_client_before_init_raises(self):
        with pytest.raises(RuntimeError, match="not initialized"):
            vllm_client.get_client()

    async def test_init_creates_a_client_with_the_configured_base_url_and_timeout(self):
        await vllm_client.init_vllm_client()
        try:
            client = vllm_client.get_client()
            assert str(client.base_url).rstrip("/") == vllm_client.VLLM_BASE_URL.rstrip("/")
            assert client.timeout.read == 30.0
        finally:
            await vllm_client.close_vllm_client()

    async def test_close_closes_the_client(self, monkeypatch):
        client = install_client(monkeypatch, lambda request: completion())
        await vllm_client.close_vllm_client()
        assert client.is_closed

    async def test_close_without_client_is_a_noop(self):
        await vllm_client.close_vllm_client()
