"""The request sent to vLLM must disable Qwen3 thinking, matching how the model was trained."""

import asyncio

import httpx

from serve import vllm_client


def test_generate_sends_enable_thinking_false(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    async def run():
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://vllm")
        monkeypatch.setattr(vllm_client, "_client", client)
        try:
            return await vllm_client.generate([{"role": "user", "content": "hi"}])
        finally:
            await client.aclose()

    assert asyncio.run(run()) == "ok"
    assert seen["body"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert seen["body"]["messages"] == [{"role": "user", "content": "hi"}]
