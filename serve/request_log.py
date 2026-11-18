"""
Structured, privacy-safe request log (plan section 13a).

One JSON line per chat request, with metadata only. The raw query and response text are NEVER
logged, and neither is the raw user id: only lengths, the detected category, which guardrail
fired, timing and flags. `user_hash` is stable, so one user's requests can be correlated
without identifying them.
"""

import json
import sys
from datetime import datetime, timezone

from guardrails.pipeline import anonymise


def user_hash(owner: str, user_id: str) -> str:
    """Same value the pipeline logs for this user, so the two log lines can be joined."""
    return anonymise(f'{owner}:{user_id}')


def log_request(*, request_id: str, session_id: str, user_hash: str, query_chars: int,
                category: str | None, guardrail: str | None, guardrail_layer: str | None,
                model: str, response_chars: int, latency_ms: int, flags: list[str]) -> None:
    record = {
        'event': 'chat',
        'ts': datetime.now(timezone.utc).isoformat(),
        'request_id': request_id,
        'session_id': session_id,
        'user_hash': user_hash,
        'query_chars': query_chars,
        'category': category,
        'guardrail': guardrail,
        'guardrail_layer': guardrail_layer,
        'model': model,
        'response_chars': response_chars,
        'latency_ms': latency_ms,
        'flags': flags,
    }
    print(json.dumps(record), file=sys.stdout)
