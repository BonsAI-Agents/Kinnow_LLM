"""
POST /v1/feedback: rate a response (contract: plan section 11a).

The client sends the request_id from the chat response and a 1-5 rating (1 = thumbs down,
5 = thumbs up). A rating of 1 or 2 queues the exchange for human review (plan sections 13e and
24, the data flywheel). The text for the review item comes from the server's one-hour record of
the request, so clients never resend (and the plan never logs) user text. If that record has
expired, or the request id is not this key's, the item is queued without text and marked.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from serve.auth import require_api_key
from serve.metrics import FEEDBACK_COUNT
from serve.redis_client import feedback_push, request_get
from serve.request_log import user_hash

router = APIRouter(dependencies=[Depends(require_api_key)])


class FeedbackRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    session_id: str = Field(..., min_length=1, max_length=128)
    request_id: str = Field(..., min_length=1, max_length=64,
                            description="The request_id from the ChatResponse being rated")
    rating: int = Field(..., ge=1, le=5, description="1 = thumbs down, 5 = thumbs up")
    comment: Optional[str] = Field(default=None, max_length=500)


def _label(rating: int) -> str:
    return 'down' if rating <= 2 else ('up' if rating >= 4 else 'neutral')


@router.post('/v1/feedback', status_code=204)
async def submit_feedback(payload: FeedbackRequest, request: Request,
                          owner: str = Depends(require_api_key)):
    FEEDBACK_COUNT.labels(rating=_label(payload.rating)).inc()

    if payload.rating <= 2:
        stored = await request_get(owner, payload.request_id)
        extra = {
            'session_id': payload.session_id,
            'request_id': payload.request_id,
            'comment': payload.comment,
            'text_expired': stored is None,
        }
        await feedback_push(
            user_id=user_hash(owner, payload.user_id),
            query=(stored or {}).get('query', ''),
            response=(stored or {}).get('response', ''),
            rating=payload.rating,
            **extra,
        )

    return Response(status_code=204)
