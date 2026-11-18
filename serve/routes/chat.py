"""
POST /v1/chat — main chat endpoint.
Runs the full guardrail pipeline → vLLM → output validator → response.
"""

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, field_validator

from guardrails.pipeline import KinnowGuardrailPipeline
from serve.redis_client import session_get, session_set
from serve.metrics import OOS_RATE, BLOCK_COUNT

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
    session_id: str = 'anonymous'
    message: str

    @field_validator('message')
    @classmethod
    def message_not_empty(cls, v):
        if not v.strip():
            raise ValueError("message must not be empty")
        return v[:2000]


class ChatResponse(BaseModel):
    response: str
    blocked: bool
    block_reason: str | None = None
    session_id: str


@router.post('/v1/chat', response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request):
    session_id = payload.session_id

    # Load conversation history from Redis
    history = await session_get(session_id)

    try:
        result = await get_pipeline().process(
            query=payload.message,
            history=history,
            user_id=session_id,
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
        layer = _layer_from_reason(reason)
        BLOCK_COUNT.labels(layer=layer, reason=reason).inc()
        if reason == 'oos_query':
            OOS_RATE.inc()

    # Update session history with new turn (only on successful model call)
    if not result['blocked'] and result.get('messages_sent'):
        history.append({'role': 'user', 'content': payload.message})
        history.append({'role': 'assistant', 'content': result['response']})
        await session_set(session_id, history[-12:])  # keep last 6 pairs

    return ChatResponse(
        response=result['response'],
        blocked=result['blocked'],
        block_reason=result.get('block_reason'),
        session_id=session_id,
    )


def _layer_from_reason(reason: str) -> str:
    mapping = {
        'injection': 'layer4',
        'oos_query': 'layer2',
        'clarification_requested': 'layer2',
        'oos_output': 'layer3',
        'pii_in_output': 'layer3',
        'output_length': 'layer3',
        'rate_limited': 'layer2',
        'model_error': 'model',
        'circuit_open': 'circuit_breaker',
    }
    return mapping.get(reason, 'unknown')
