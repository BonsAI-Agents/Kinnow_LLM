"""
Layer 4 — Prompt Injection Defense
Runs first. Zero model cost. Sanitizes input and blocks adversarial patterns.
"""

import re
import unicodedata

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
    # direct override / forget / disable
    r'forget (everything|all|what|your)',
    r'(override|ignore|disable|bypass|stop following)\b.{0,25}?\b(rules|restrictions|filters|guidelines|guardrails|scope|system prompt)',
    r'new (instructions|policy|rules)\s*:',
    r'no longer have a scope',
    # prompt / configuration exfiltration
    r'\bsystem prompt\b',
    r'(hidden|initial|original|secret) (instructions|prompt|rules)',
    r'(reveal|print|output|show|repeat|display|forward)\b.{0,40}?\b(your (instructions|rules|configuration|config)|rules you were given|context window|text above)',
    r'repeat the text above',
    # mode switches
    r'developer mode',
    r'(without|no) (any )?(filters|restrictions|limits)',
    # fake system / delimiter injection
    r'\[/?system\]',
    r'</?system>',
    r'#{2,}\s*(instruction|system)',
    r'system override',
    # roleplay and claimed authority
    r'you are (a|an|my) .{0,30}\bnow\b',
    r"let'?s play a game",
    r'i am the (kinnow )?(developer|admin|administrator|owner)',
    r'official audit',
]

# Characters used to hide a phrase from a pattern match
_HOMOGLYPHS = str.maketrans({
    'ı': 'i', 'ι': 'i', 'а': 'a', 'е': 'e', 'о': 'o', 'р': 'p',
    'с': 'c', 'у': 'y', 'х': 'x',
    'α': 'a', 'ο': 'o', 'ν': 'v', 'ρ': 'p', 'ε': 'e', 'τ': 't',
})
_INVISIBLE = re.compile(r'[\u200b-\u200f\u2060\ufeff\u00ad]')
_SPELLED_OUT = re.compile(r'(?<=\b\w)-(?=\w\b)')   # "i-g-n-o-r-e" -> "ignore"


def sanitize_input(query: str) -> str:
    """Remove null bytes, control characters, normalize whitespace, truncate."""
    query = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', query)
    query = re.sub(r'\s{3,}', ' ', query).strip()
    return query[:2000]


def _normalize(query: str) -> str:
    """Fold invisible characters, lookalike letters and letter-by-letter hyphenation."""
    q = unicodedata.normalize('NFKC', query)
    q = _INVISIBLE.sub('', q).lower().translate(_HOMOGLYPHS)
    return _SPELLED_OUT.sub('', q)


def detect_injection(query: str) -> tuple[bool, str]:
    """
    Returns (is_injection, matched_pattern).
    Normalizes unicode lookalikes before matching.
    """
    query_normalized = _normalize(query)

    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, query_normalized, re.IGNORECASE):
            return True, pattern

    # Block token-stuffing attacks (extremely long inputs).
    # Threshold is 300 because sanitize_input() truncates to 2000 chars first;
    # with 5-char average word + space that's ~333 max words after truncation.
    if len(query.split()) > 300:
        return True, 'input_too_long'

    return False, ''
