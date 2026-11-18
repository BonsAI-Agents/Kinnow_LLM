"""
KinnowGuardrailPipeline — orchestrates all 4 layers in the correct order.

Execution order:
  Layer 4 (injection) → Layer 2 (classifier) → Layer 1 (system prompt) → model → Layer 3 (output)

Refusal anomaly tracker (Section 21f): rate-limits users who repeatedly probe OOS topics.
"""

from .layer4_injection import sanitize_input, detect_injection
from .layer2_classifier import classify_query
from .layer1_system_prompt import build_messages, sanitize_history
from .layer3_output_validator import validate_output_v2
from .rate_limit import InMemoryRateLimiter, OOS_BLOCK_THRESHOLD

# Default limiter: in-process and bounded. The API passes a Redis-backed one so the limit is
# shared across replicas (serve/rate_limiter.py).
_default_limiter = InMemoryRateLimiter()


def reset_oos_tracker() -> None:
    """Clear the default limiter's state. Call in test setup to avoid inter-test pollution."""
    _default_limiter.reset()


REFUSAL_RESPONSE = (
    "I'm Kinnow's ERP assistant. I can only help with GST, payroll, "
    "invoice matching, and ERP operations. What ERP topic can I help you with?"
)

INJECTION_RESPONSE = (
    "I'm Kinnow's ERP assistant and I cannot change my role or answer outside my scope."
)

RATE_LIMIT_RESPONSE = (
    "You've sent many off-topic questions. Please wait a few minutes before trying again."
)

OUTPUT_INVALID_RESPONSE = (
    "I encountered an issue generating a valid response. Please rephrase your question."
)


class KinnowGuardrailPipeline:
    """
    Stateless pipeline class. Instantiate once at app startup.
    Pass a `model_fn` callable: fn(messages: list[dict]) -> str
    """

    def __init__(self, model_fn, rate_limiter=None):
        self.model_fn = model_fn
        self._limiter = rate_limiter or _default_limiter

    async def process(self, query: str, history: list[dict], user_id: str = 'anonymous') -> dict:
        """
        Full guardrail pipeline. Returns response dict:
        {
            'response': str,
            'blocked': bool,
            'block_reason': str | None,
            'messages_sent': list[dict] | None   # only when model was called
        }
        """
        # --- Layer 4: Injection detection (runs first, cheapest) ---
        query = sanitize_input(query)
        is_injection, matched = detect_injection(query)
        if is_injection:
            self._log_security('injection_blocked', user_id, matched)
            return self._blocked_response(INJECTION_RESPONSE, 'injection')

        # --- Refusal anomaly check (Section 21f) ---
        if await self._limiter.is_limited(user_id):
            return self._blocked_response(RATE_LIMIT_RESPONSE, 'rate_limited')

        # --- Layer 2: Input classification ---
        classification = classify_query(query)
        decision = classification['decision']

        if decision == 'clarify':
            return self._clarification_response(classification['clarification'])

        if decision == 'block':
            if await self._limiter.record(user_id):
                self._log_security('rate_limit_applied', user_id, f'{OOS_BLOCK_THRESHOLD} OOS in window')
            self._log_security('oos_blocked', user_id, classification.get('reason', ''))
            return self._blocked_response(REFUSAL_RESPONSE, 'oos_query')

        # --- Layer 1: Build messages with sanitized history + system prompt ---
        clean_history = sanitize_history(history)
        messages = build_messages(query, clean_history)

        # --- Model inference ---
        try:
            raw_output = await self.model_fn(messages)
        except Exception as e:
            if 'circuit_open' in str(e):
                # Model known to be down: let the API answer 503 (plan section 23) instead of
                # presenting a generic "rephrase your question" reply.
                raise
            self._log_event('model_error', {'user_id': user_id, 'error': str(e)})
            return self._blocked_response(OUTPUT_INVALID_RESPONSE, 'model_error')

        # --- Layer 3: Output validation ---
        validation = validate_output_v2(raw_output)
        if not validation['valid']:
            self._log_event('output_invalid', {
                'user_id': user_id,
                'issues': validation['issues'],
            })
            if any('oos_response' in issue for issue in validation['issues']):
                return self._blocked_response(REFUSAL_RESPONSE, 'oos_output')
            if any('pii_detected' in issue for issue in validation['issues']):
                return self._blocked_response(OUTPUT_INVALID_RESPONSE, 'pii_in_output')
            if any(issue in ('output_too_short', 'output_too_long') for issue in validation['issues']):
                # Empty or runaway generations are model failures, not answers.
                return self._blocked_response(OUTPUT_INVALID_RESPONSE, 'output_length')
            if any('invalid_gst_rate' in issue for issue in validation['issues']):
                # Return response but append a caveat
                caveat = ("\n\n*Note: Please verify GST rates with the official GSTN portal "
                          "or a Chartered Accountant before filing.*")
                return self._success_response(raw_output + caveat, messages)

        return self._success_response(raw_output, messages)

    # --- Response builders ---

    def _blocked_response(self, message: str, reason: str) -> dict:
        return {
            'response': message,
            'blocked': True,
            'block_reason': reason,
            'messages_sent': None,
        }

    def _clarification_response(self, message: str) -> dict:
        return {
            'response': message,
            'blocked': False,
            'block_reason': 'clarification_requested',
            'messages_sent': None,
        }

    def _success_response(self, text: str, messages: list[dict]) -> dict:
        return {
            'response': text,
            'blocked': False,
            'block_reason': None,
            'messages_sent': messages,
        }

    # --- Logging ---

    def _log_event(self, event_type: str, payload: dict) -> None:
        import json
        import sys
        print(json.dumps({'event': event_type, **payload}), file=sys.stderr)

    def _log_security(self, event_type: str, user_id: str, detail: str) -> None:
        import json
        import sys
        print(json.dumps({
            'level': 'SECURITY',
            'event': event_type,
            'user_id': user_id,
            'detail': detail,
        }), file=sys.stderr)
