"""
POST /v1/chat: main chat endpoint (contract: plan section 11a).
Runs the full guardrail pipeline → vLLM → output validator → response.
"""

import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from guardrails.pipeline import KinnowGuardrailPipeline, GUARDRAIL_BY_REASON
from serve.auth import require_api_key
from serve.metrics import OOS_RATE, BLOCK_COUNT, RATE_LIMITED
from serve.rate_limit import get_request_limiter
from serve.redis_client import session_get, session_set, request_set
from serve.request_log import log_request, user_hash
from serve import version

router = APIRouter()

# Pipeline is initialized at app startup (see app.py)
_pipeline: KinnowGuardrailPipeline | None = None


def set_pipeline(pipeline: KinnowGuardrailPipeline):
    global _pipeline
    _pipeline = pipeline


def get_pipeline() -> KinnowGuardrailPipeline:
    if _pipeline is None:
        raise RuntimeError("Pipeline not initialized")
    return _pipeline


class ChatRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128, description="Unique user identifier")
    session_id: str = Field(..., min_length=1, max_length=128, description="Conversation session ID")
    message: str = Field(..., min_length=1, max_length=2000, description="User's message")
    context_window: Optional[list[dict]] = Field(
        default=None, description="Previous turns (optional and ignored: the server manages history)")

    @field_validator('message')
    @classmethod
    def message_not_blank(cls, v):
        if not v.strip():
            raise ValueError("message must not be empty")
        return v


class ChatResponse(BaseModel):
    response: str
    blocked: bool
    category_detected: Optional[str] = None
    guardrail_triggered: Optional[str] = None
    latency_ms: int
    session_id: str
    model_version: str
    request_id: str


@router.post('/v1/chat', response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request, owner: str = Depends(require_api_key)):
    t0 = time.perf_counter()
    request_id = getattr(request.state, 'request_id', 'unknown')
    session_id = payload.session_id

    # Per-user rate limit (plan section 11a): 20 a minute, 500 a day
    limit = await get_request_limiter().check(owner, payload.user_id)
    if not limit.allowed:
        RATE_LIMITED.labels(scope=limit.scope).inc()
        raise HTTPException(status_code=429, detail="Rate limit exceeded",
                            headers={'Retry-After': str(limit.retry_after)})

    # Load conversation history from Redis
    history = await session_get(session_id, owner)

    try:
        result = await get_pipeline().process(
            query=payload.message,
            history=history,
            user_id=f'{owner}:{payload.user_id}',    # off-topic limiter and logs are per key and user
        )
    except RuntimeError as e:
        err_msg = str(e)
        if 'circuit_open' in err_msg:
            raise HTTPException(status_code=503, detail=err_msg)
        raise HTTPException(status_code=500, detail="internal_error")

    # Record block / clarification metrics (a clarification is not "blocked" but is a guardrail
    # outcome that must be visible too)
    if result.get('block_reason'):
        reason = result['block_reason']
        BLOCK_COUNT.labels(layer=_layer_from_reason(reason), reason=reason).inc()
        if reason == 'oos_query':
            OOS_RATE.inc()

    # Update session history with new turn (only on successful model call)
    if not result['blocked'] and result.get('messages_sent'):
        history.append({'role': 'user', 'content': payload.message})
        history.append({'role': 'assistant', 'content': result['response']})
        await session_set(session_id, history[-12:], owner=owner)  # keep last 6 pairs

    # Remember this exchange for an hour so a thumbs-down (including on a wrongful refusal) can
    # be reviewed without the client resending the text. Same retention as the session history.
    await request_set(owner, request_id, {
        'session_id': session_id,
        'query': payload.message,
        'response': result['response'],
    })

    latency_ms = int((time.perf_counter() - t0) * 1000)
    log_request(
        request_id=request_id,
        session_id=session_id,
        user_hash=user_hash(owner, payload.user_id),
        query_chars=len(payload.message),
        category=result.get('category_detected'),
        guardrail=result.get('guardrail_triggered'),
        guardrail_layer=result.get('guardrail_layer'),
        model=version.MODEL_VERSION,
        response_chars=len(result['response']),
        latency_ms=latency_ms,
        flags=result.get('flags', []),
    )

    return ChatResponse(
        response=result['response'],
        blocked=result['blocked'],
        category_detected=result.get('category_detected'),
        guardrail_triggered=result.get('guardrail_triggered'),
        latency_ms=latency_ms,
        session_id=session_id,
        model_version=version.MODEL_VERSION,
        request_id=request_id,
    )


def _layer_from_reason(reason: str) -> str:
    return GUARDRAIL_BY_REASON.get(reason, ('unknown', 'unknown'))[1]
