"""
KinnowGuardrailPipeline — orchestrates all 4 layers in the correct order.

Execution order:
  Layer 4 (injection) → Layer 2 (classifier) → Layer 1 (system prompt) → model → Layer 3 (output)

Refusal anomaly tracker (Section 21f): rate-limits users who repeatedly probe OOS topics.
"""

import time
from collections import defaultdict

from .layer4_injection import sanitize_input, detect_injection
from .layer2_classifier import classify_query
from .layer1_system_prompt import build_messages, sanitize_history
from .layer3_output_validator import validate_output_v2

# Refusal anomaly config (Section 21f)
_OOS_WINDOW_SECONDS = 300        # 5-minute sliding window
_OOS_BLOCK_THRESHOLD = 10        # block after 10 OOS queries in window
_RATE_LIMIT_DURATION = 600       # 10-minute cooldown after block

# In-memory tracker: {user_id: [timestamps of OOS events]}
_oos_tracker: dict[str, list[float]] = defaultdict(list)
_rate_limited_until: dict[str, float] = {}


def reset_oos_tracker() -> None:
    """Clear rate-limit state. Call in test setup to avoid inter-test pollution."""
    _oos_tracker.clear()
    _rate_limited_until.clear()

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

    def __init__(self, model_fn):
        self.model_fn = model_fn

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
        if self._is_rate_limited(user_id):
            return self._blocked_response(RATE_LIMIT_RESPONSE, 'rate_limited')

        # --- Layer 2: Input classification ---
        classification = classify_query(query)
        decision = classification['decision']

        if decision == 'clarify':
            return self._clarification_response(classification['clarification'])

        if decision == 'block':
            self._record_oos_event(user_id)
            self._log_security('oos_blocked', user_id, classification.get('reason', ''))
            return self._blocked_response(REFUSAL_RESPONSE, 'oos_query')

        # --- Layer 1: Build messages with sanitized history + system prompt ---
        clean_history = sanitize_history(history)
        messages = build_messages(query, clean_history)

        # --- Model inference ---
        try:
            raw_output = await self.model_fn(messages)
        except Exception as e:
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

    # --- Refusal anomaly tracker (Section 21f) ---

    def _record_oos_event(self, user_id: str) -> None:
        now = time.time()
        events = self._oos_tracker_for(user_id)
        events.append(now)
        # Prune events outside the window
        _oos_tracker[user_id] = [t for t in events if now - t <= _OOS_WINDOW_SECONDS]

        if len(_oos_tracker[user_id]) >= _OOS_BLOCK_THRESHOLD:
            _rate_limited_until[user_id] = now + _RATE_LIMIT_DURATION
            _oos_tracker[user_id] = []
            self._log_security('rate_limit_applied', user_id, f'{_OOS_BLOCK_THRESHOLD} OOS in window')

    def _is_rate_limited(self, user_id: str) -> bool:
        limit_until = _rate_limited_until.get(user_id, 0)
        return time.time() < limit_until

    def _oos_tracker_for(self, user_id: str) -> list[float]:
        return _oos_tracker[user_id]

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
