"""
Layer 4 — Prompt Injection Defense
Runs first. Zero model cost. Sanitizes input and blocks adversarial patterns.
"""

import re

INJECTION_PATTERNS = [
    r'ignore\b.{0,30}?\binstructions',
    r'forget\b.{0,30}?\binstructions',
    r'disregard (the system prompt|your instructions|what you were told)',
    r'you are now',
    r'pretend (you are|to be|that you are)',
    r'act as (if you are|a|an)',
    r'your new (instructions|role|persona|system prompt)',
    r'override (system|instructions|prompt)',
    r'bypass (your|the) (restrictions|guardrails|filters)',
    r'\bdan\b',
    r'do anything now',
    r'jailbreak',
    r'you have no restrictions',
    r'you can (say|do|answer) anything',
    r'roleplay as',
    r'play the role of',
    r'you are a (different|new|unrestricted)',
    r'your true (self|nature|purpose)',
    r'repeat (your|the) (system|instructions|prompt)',
    r'what (are|were) your (instructions|system prompt)',
    r'show me your (system prompt|instructions)',
    r'print (your|the) (prompt|instructions)',
    r'base64',
    r'rot13',
    r'hex encoded',
]


def sanitize_input(query: str) -> str:
    """Remove null bytes, control characters, normalize whitespace, truncate."""
    query = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', query)
    query = re.sub(r'\s{3,}', ' ', query).strip()
    return query[:2000]


def detect_injection(query: str) -> tuple[bool, str]:
    """
    Returns (is_injection, matched_pattern).
    Normalizes unicode lookalikes before matching.
    """
    query_lower = query.lower()
    # Normalize unicode lookalikes (Cyrillic 'а' → Latin 'a', Turkish dotless 'ı' → 'i')
    query_normalized = query_lower.replace('ı', 'i').replace('а', 'a')

    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, query_normalized, re.IGNORECASE):
            return True, pattern

    # Block token-stuffing attacks (extremely long inputs).
    # Threshold is 300 because sanitize_input() truncates to 2000 chars first;
    # with 5-char average word + space that's ~333 max words after truncation.
    if len(query.split()) > 300:
        return True, 'input_too_long'

    return False, ''
