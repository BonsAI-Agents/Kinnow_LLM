"""
Layer 3 — Output Validator
Runs after model inference. Catches hallucinated GST rates, PII leaks,
off-topic responses that slipped through the input classifier (Section 21a).
"""

import re

# --- PII patterns ---

PII_PATTERNS = [
    (r'\b\d{12}\b', 'aadhaar_number'),
    (r'\b[A-Z]{5}\d{4}[A-Z]\b', 'pan_number'),
    (r'\b\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]\b', 'gstin'),
    (r'\b[6-9]\d{9}\b', 'phone_number'),
    (r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b', 'email'),
    (r'\b\d{9,18}\b', 'bank_account_number'),  # 9-18 digit bank account
    (r'\bIFSC\s*:?\s*[A-Z]{4}0[A-Z0-9]{6}\b', 'ifsc_code'),
]

# --- GST rate validation ---
# GST has specific slabs. Flag anything else as likely hallucination.
VALID_GST_RATES = {0, 0.1, 0.25, 1, 1.5, 3, 5, 6, 7.5, 9, 12, 14, 18, 28}

GST_RATE_PATTERN = re.compile(r'GST[^%\n]{0,30}?(\d+(?:\.\d+)?)\s*%', re.IGNORECASE)

# --- Output OOS keywords (Section 21a) ---
# If response contains these AND no ERP signal words → flag as OOS slip-through

OOS_OUTPUT_KEYWORDS = [
    r'\b(here\'s\s+)?(today\'s\s+)?weather\b',
    r'\b(the\s+)?(current\s+)?temperature\b',
    r'\b(cricket\s+)?(match\s+)?score\b',
    r'\bgoal\s+scored\b',
    r'\b(latest\s+)?news\b',
    r'\bhow\s+to\s+cook\b',
    r'\brecipe\s+for\b',
    r'\bdear\s+(user|sir|madam)',  # generic email opener — not ERP
    r'\bonce\s+upon\s+a\s+time\b',  # creative writing
]

ERP_SIGNAL_WORDS = [
    r'\b(gst|igst|cgst|sgst|hsn|sac|itc)\b',
    r'\b(payroll|salary|pf|epf|esic|tds)\b',
    r'\b(gstr|e-invoice|e-way|irn)\b',
    r'\b(kinnow|erp|ledger|journal|invoice)\b',
    r'\b(advance\s+tax|professional\s+tax|tcs)\b',
    r'\b(form\s+16|form\s+24q|itr)\b',
]

# Max output length to guard against prompt-injection via verbose response padding
MAX_OUTPUT_CHARS = 4000

# Min output length to catch empty/whitespace-only responses
MIN_OUTPUT_CHARS = 10


def check_pii(text: str) -> list[dict]:
    """Return list of PII hits: [{type, start, end}]."""
    hits = []
    for pattern, pii_type in PII_PATTERNS:
        for m in re.finditer(pattern, text):
            hits.append({'type': pii_type, 'start': m.start(), 'end': m.end()})
    return hits


def check_gst_rates(text: str) -> list[dict]:
    """Return invalid GST rate claims in the response."""
    invalid = []
    for m in GST_RATE_PATTERN.finditer(text):
        try:
            rate = float(m.group(1))
            if rate not in VALID_GST_RATES:
                invalid.append({'claimed_rate': rate, 'snippet': m.group(0)})
        except ValueError:
            pass
    return invalid


def validate_output_topic(text: str) -> dict:
    """
    Section 21a: Check if the model's response is about ERP at all.
    Returns {'is_oos': bool, 'reason': str}.
    """
    text_lower = text.lower()

    oos_hit = any(re.search(p, text_lower) for p in OOS_OUTPUT_KEYWORDS)
    erp_hit = any(re.search(p, text_lower, re.IGNORECASE) for p in ERP_SIGNAL_WORDS)

    if oos_hit and not erp_hit:
        return {'is_oos': True, 'reason': 'response_contains_oos_content_no_erp_signal'}

    if not erp_hit and len(text.split()) > 50:
        # Long response with zero ERP vocabulary — suspicious
        return {'is_oos': True, 'reason': 'long_response_with_no_erp_signal'}

    return {'is_oos': False, 'reason': 'ok'}


def validate_output(text: str) -> dict:
    """
    Basic output validation: length, PII presence.
    Returns {'valid': bool, 'issues': list[str]}.
    """
    issues = []

    if len(text) < MIN_OUTPUT_CHARS:
        issues.append('output_too_short')
    if len(text) > MAX_OUTPUT_CHARS:
        issues.append('output_too_long')

    pii_hits = check_pii(text)
    if pii_hits:
        issues.append(f'pii_detected:{",".join(h["type"] for h in pii_hits)}')

    return {'valid': len(issues) == 0, 'issues': issues}


def validate_output_v2(text: str) -> dict:
    """
    Full output validation (Section 21a):
    - Length
    - PII
    - Invalid GST rate claims
    - OOS topic check
    Returns {'valid': bool, 'issues': list[str], 'pii_hits': list, 'gst_errors': list}
    """
    basic = validate_output(text)
    issues = list(basic['issues'])

    gst_errors = check_gst_rates(text)
    if gst_errors:
        issues.append(f'invalid_gst_rate:{",".join(str(e["claimed_rate"]) for e in gst_errors)}')

    topic_check = validate_output_topic(text)
    if topic_check['is_oos']:
        issues.append(f'oos_response:{topic_check["reason"]}')

    return {
        'valid': len(issues) == 0,
        'issues': issues,
        'pii_hits': check_pii(text),
        'gst_errors': gst_errors,
        'topic': topic_check,
    }
