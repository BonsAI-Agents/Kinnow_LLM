"""
Async vLLM client — wraps the vLLM OpenAI-compatible HTTP API.
The vLLM server runs as a separate process (see serve/start_vllm.sh).
"""

import os
import time
import httpx
from serve.metrics import MODEL_LATENCY

VLLM_BASE_URL = os.getenv('VLLM_BASE_URL', 'http://localhost:8001')
MODEL_NAME = os.getenv('MODEL_NAME', 'kinnow-v1')

# Generation defaults (Section 11)
DEFAULT_MAX_TOKENS = 512
DEFAULT_TEMPERATURE = 0.1   # low = deterministic, good for factual ERP answers
DEFAULT_TOP_P = 0.9

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    if _client is None:
        raise RuntimeError("vLLM client not initialized. Call init_vllm_client() at startup.")
    return _client


async def init_vllm_client():
    global _client
    _client = httpx.AsyncClient(
        base_url=VLLM_BASE_URL,
        timeout=httpx.Timeout(30.0),
    )


async def close_vllm_client():
    if _client:
        await _client.aclose()


async def generate(messages: list[dict], max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
    """
    Send messages to vLLM and return the assistant's text response.
    Raises httpx.HTTPError on failure (caught by circuit breaker in pipeline).
    """
    client = get_client()
    t0 = time.perf_counter()

    resp = await client.post('/v1/chat/completions', json={
        'model': MODEL_NAME,
        'messages': messages,
        'max_tokens': max_tokens,
        'temperature': DEFAULT_TEMPERATURE,
        'top_p': DEFAULT_TOP_P,
        'stream': False,
    })
    resp.raise_for_status()

    elapsed = time.perf_counter() - t0
    MODEL_LATENCY.observe(elapsed)

    data = resp.json()
    choices = data.get('choices', [])
    if not choices:
        raise ValueError(f"vLLM returned empty choices list (model={MODEL_NAME})")
    return choices[0]['message']['content']
