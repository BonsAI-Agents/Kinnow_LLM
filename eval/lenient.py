"""A second, more forgiving way to score an answer: short forms and full names count as the same word.

The strict scorer (run_full_eval.evaluate_example) needs the exact required word. That fails a correct answer that says
"RCM" when the test wants "reverse charge". This module changes nothing about figures, percentages or section numbers:
it only treats a short form, its full name and spelling variants (hyphen, space) as equal.
"""

import re

# Each group lists words that mean the same thing. Keep to short forms and spelling variants only.
GROUPS = [
    ["reverse charge", "rcm", "reverse-charge"],
    ["input tax credit", "itc"],
    ["letter of undertaking", "lut"],
    ["invoice reference number", "irn"],
    ["goods transport agency", "gta"],
    ["non-banking financial", "non banking financial", "nbfc"],
    ["tax deducted at source", "tds"],
    ["tax collected at source", "tcs"],
    ["online information and database access", "oidar"],
    ["e-commerce", "ecommerce", "e commerce"],
    ["e-invoice", "einvoice", "e invoice", "e-invoicing"],
    ["e-way bill", "eway bill", "e way bill"],
    ["inter-state", "interstate", "inter state"],
    ["intra-state", "intrastate", "intra state"],
    ["credit note", "credit-note"],
    ["debit note", "debit-note"],
    ["house rent allowance", "hra"],
    ["marginal relief", "marginal-relief"],
    ["employees' provident fund", "employees provident fund", "epf"],
    ["employees' state insurance", "employees state insurance", "esi", "esic"],
    ["professional tax", "pt"],
    ["full and final", "full-and-final", "fnf", "f&f"],
    ["goods and services tax identification number", "gstin"],
    ["integrated gst", "igst"],
    ["central gst", "cgst"],
    ["state gst", "sgst"],
]


def _norm(text: str) -> str:
    text = text.lower()
    text = re.sub(r"(\d+)\s+percent", r"\1%", text)
    text = re.sub(r"(\d+)\.0%", r"\1%", text)
    text = re.sub(r"(?<=\d),(?=\d)", "", text)
    return text.replace("\u2019", "'")


def _has(response: str, word: str) -> bool:
    """True if the word is there as a whole word (short forms like 'pt' or 'itc' must not match inside other words)."""
    if len(word) <= 4 and word.isalpha():
        return re.search(r"(?<![a-z])" + re.escape(word) + r"(?![a-z])", response) is not None
    return word in response


def has_word(response: str, keyword: str) -> bool:
    r, k = _norm(response), _norm(keyword)
    if k in r:                       # the strict rule always applies first, so lenient can never score lower than strict
        return True
    for group in GROUPS:
        if k in group:
            return any(_has(r, alt) for alt in group)
    return False


def evaluate(response: str, must_contain: list, must_not_contain: list | None = None) -> dict:
    ok = all(has_word(response, m) for m in must_contain)
    bad = any(has_word(response, m) for m in (must_not_contain or []))
    return {"passed": ok and not bad, "passed_must_contain": ok, "failed_must_not_contain": bad}
