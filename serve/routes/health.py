"""Health and readiness endpoints."""

from fastapi import APIRouter
from serve.redis_client import get_redis
from serve.vllm_client import get_client
from serve.circuit_breaker import get_circuit_breaker

router = APIRouter()


@router.get('/health')
async def health():
    """Liveness probe — returns 200 if the process is alive."""
    return {'status': 'ok'}


@router.get('/ready')
async def ready():
    """
    Readiness probe — returns 200 only when all dependencies are reachable.
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

    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=200 if ok else 503,
        content={'status': 'ready' if ok else 'not_ready', 'checks': checks},
    )
