"""
POST /v1/feedback — thumbs-up / thumbs-down on a model response.
Thumbs-down entries queue to Redis for human review (data flywheel, Section 24).
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel, field_validator
from serve.redis_client import feedback_push
from serve.metrics import FEEDBACK_COUNT

router = APIRouter()


class FeedbackRequest(BaseModel):
    session_id: str
    query: str
    response: str
    rating: str  # 'up' or 'down'

    @field_validator('rating')
    @classmethod
    def rating_must_be_valid(cls, v):
        if v not in ('up', 'down'):
            raise ValueError("rating must be 'up' or 'down'")
        return v

    @field_validator('query', 'response')
    @classmethod
    def not_empty(cls, v):
        if not v.strip():
            raise ValueError("field must not be empty")
        return v[:2000]  # truncate to guard against abuse


@router.post('/v1/feedback')
async def submit_feedback(payload: FeedbackRequest, request: Request):
    FEEDBACK_COUNT.labels(rating=payload.rating).inc()

    if payload.rating == 'down':
        await feedback_push(
            user_id=payload.session_id,
            query=payload.query,
            response=payload.response,
            rating=payload.rating,
        )

    return {'status': 'received', 'rating': payload.rating}
