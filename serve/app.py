"""
Kinnow ERP LLM — FastAPI application entrypoint.

Startup sequence:
  1. Connect Redis
  2. Connect vLLM client
  3. Set up the per-user request rate limiter
  4. Load domain centroids from data/centroids.npz and warm the embedding model
  5. Initialize guardrail pipeline
  6. Register routes

Run locally:
    uvicorn serve.app:app --host 0.0.0.0 --port 8000 --workers 1
"""

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from prometheus_client import make_asgi_app

from serve.auth import load_api_keys
from serve.redis_client import init_redis, close_redis, get_redis
from serve.rate_limiter import RedisRateLimiter
from serve.rate_limit import RequestRateLimiter, set_request_limiter
from serve.internal_only import InternalOnly
from serve.vllm_client import init_vllm_client, close_vllm_client, generate
from serve.middleware import RequestLoggingMiddleware
from serve.routes.chat import router as chat_router, set_pipeline
from serve.routes.health import router as health_router
from serve.routes.feedback import router as feedback_router
from serve.circuit_breaker import get_circuit_breaker
from guardrails.pipeline import KinnowGuardrailPipeline
from guardrails.layer2_classifier import set_domain_centroids, load_centroids, load_embedding_model


CENTROIDS_PATH = os.getenv('CENTROIDS_PATH', 'data/centroids.npz')


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    print("Starting Kinnow ERP LLM API server…")

    print(f"  ✓ API keys loaded ({load_api_keys()})")

    await init_redis()
    print("  ✓ Redis connected")

    # Per-user request limit (20 a minute, 500 a day by default), counted in Redis
    set_request_limiter(RequestRateLimiter(get_redis))

    await init_vllm_client()
    print("  ✓ vLLM client ready")

    # Load domain centroids if available
    centroids_file = Path(CENTROIDS_PATH)
    if centroids_file.exists():
        centroids = load_centroids(centroids_file)
        set_domain_centroids(centroids)
        print(f"  ✓ Centroids loaded ({len(centroids)} domains)")
        # Load the embedding model now, not on the first request that reaches it (several seconds of
        # latency, and a failed load would surface as user-facing errors). A failure here stops the
        # server from becoming ready instead.
        await asyncio.to_thread(load_embedding_model)
        print("  ✓ Embedding model loaded")
    else:
        print(f"  ⚠ Centroids not found at {CENTROIDS_PATH} — classifier runs keyword-only mode")

    # Build guardrail pipeline with async vLLM model function
    cb = get_circuit_breaker()

    async def model_fn(messages):
        return await cb.call(generate(messages))

    # Off-topic rate-limit state lives in Redis so every replica enforces the same limit.
    pipeline = KinnowGuardrailPipeline(model_fn=model_fn, rate_limiter=RedisRateLimiter(get_redis))
    set_pipeline(pipeline)
    print("  ✓ Guardrail pipeline initialized")
    print("  → Server ready\n")

    yield

    # --- Shutdown ---
    await close_redis()
    await close_vllm_client()
    print("Server shut down.")


app = FastAPI(
    title="Kinnow ERP LLM API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(RequestLoggingMiddleware)

# Routes
app.include_router(health_router)
app.include_router(chat_router)
app.include_router(feedback_router)

# Prometheus metrics endpoint
# (internal only: see serve/internal_only.py)
metrics_app = InternalOnly(make_asgi_app())
app.mount("/metrics", metrics_app)
