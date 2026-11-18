"""Health and readiness endpoints."""

import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from serve import version
from serve.redis_client import get_redis
from serve.vllm_client import get_client
from serve.circuit_breaker import get_circuit_breaker

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    model_version: str
    uptime_seconds: float


@router.get('/health', response_model=HealthResponse)
async def health():
    """Liveness probe: returns 200 if the process is alive (plan section 11a)."""
    return {
        'status': 'ok',
        'model_version': version.MODEL_VERSION,
        'uptime_seconds': round(time.time() - version.START_TIME, 1),
    }


@router.get('/ready')
async def ready():
    """
    Readiness probe: returns 200 only when all dependencies are reachable.
    K8s will stop sending traffic if this returns non-200.
    """
    checks = {}
    ok = True

    # Redis
    try:
        await get_redis().ping()
        checks['redis'] = 'ok'
    except Exception as e:
        checks['redis'] = f'error: {e}'
        ok = False

    # vLLM
    try:
        resp = await get_client().get('/health')
        checks['vllm'] = 'ok' if resp.status_code == 200 else f'status {resp.status_code}'
        if resp.status_code != 200:
            ok = False
    except Exception as e:
        checks['vllm'] = f'error: {e}'
        ok = False

    # Circuit breaker
    cb = get_circuit_breaker()
    checks['circuit_breaker'] = cb.state.value
    if cb.is_open:
        ok = False

    return JSONResponse(
        status_code=200 if ok else 503,
        content={'status': 'ready' if ok else 'not_ready', 'checks': checks},
    )
