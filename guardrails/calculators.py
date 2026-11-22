"""
Deterministic calculators for payroll and GST questions.

The model explains rules well but slips on arithmetic, so when a question is a plain calculation the
server computes the figure here and hands it to the model as "Computed by the system", in the same words
the training answers use. The model writes the explanation; it does not do the sum.

Conservative on purpose: a calculator fires only when every input it needs can be read from the question
without guessing. Anything ambiguous returns None and the model answers as before.

Rules come from Tejas's reviewed checklist (data/tejas_review/FACTS_TO_VERIFY*.md):
  gratuity 15/26 x last drawn wages x completed years (6+ months rounds up), cap Rs 20 lakh
  EPF 12% on wages up to the Rs 25,000 ceiling; ESI 0.75% / 3.25% on gross wages up to Rs 21,000, rounded up
  new regime: Rs 75,000 standard deduction, slabs to 30%, rebate to Rs 12 lakh with marginal relief, 4% cess
  interest: 18% a year (Section 50(1); Section 50(3) too, on the owner's decision, CA to confirm)
"""

import re
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

# ---------- arithmetic ----------


def rup(x) -> int:
    return int(Decimal(str(x)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def ceil_rup(x) -> int:
    return int(Decimal(str(x)).quantize(Decimal(1), rounding=ROUND_CEILING))


def inr(n, sym="Rs ") -> str:
    """Indian digit grouping: 7,50,000."""
    n = int(n)
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return f"{sym}{'-' if n < 0 else ''}{s}"


SLABS = [(400_000, 0), (800_000, 5), (1_200_000, 10), (1_600_000, 15), (2_000_000, 20), (2_400_000, 25), (10**12, 30)]


def new_regime_tax(taxable: int) -> dict:
    tax, lower = Decimal(0), 0
    for upper, rate in SLABS:
        if taxable > lower:
            tax += Decimal(min(taxable, upper) - lower) * rate / 100
        lower = upper
    slab_tax = rup(tax)
    note, final = "", slab_tax
    if taxable <= 1_200_000:
        final, note = 0, "rebate"
    elif slab_tax > taxable - 1_200_000:
        final, note = taxable - 1_200_000, "relief"
    cess = rup(Decimal(final) * 4 / 100)
    return {"slab_tax": slab_tax, "tax": final, "cess": cess, "total": final + cess, "note": note}


# ---------- reading numbers from a question ----------

_NUM = re.compile(
    r"(?:rs\.?|inr|₹)?\s*(\d[\d,]*(?:\.\d+)?)\s*(lakhs?|lacs?|l\b|crores?|cr\b|k\b|thousand)?", re.I)


def amounts(text: str) -> list[tuple[int, int, int]]:
    """(value in rupees, start, end) for every money-looking number, e.g. 'Rs 12,75,000', '5.5L', '40k'."""
    out = []
    for m in _NUM.finditer(text):
        raw, unit = m.group(1), (m.group(2) or "").lower()
        try:
            v = Decimal(raw.replace(",", ""))
        except Exception:
            continue
        # a financial year or calendar year ("FY 2025-26", "in 2026") is not money
        if re.fullmatch(r"20\d\d", raw) and not unit and not re.search(r"(rs\.?|inr|₹)\s*$", text[:m.start(1)], re.I):
            continue
        if unit.startswith(("lakh", "lac")) or unit == "l":
            v *= 100_000
        elif unit.startswith("cr"):
            v *= 10_000_000
        elif unit in ("k", "thousand"):
            v *= 1000
        out.append((int(v), m.start(), m.end()))
    return out


def _near(text: str, words: tuple[str, ...], window: int = 60):
    """First amount within `window` characters after any of `words`."""
    low = text.lower()
    for w in words:
        i = low.find(w)
        while i != -1:
            for v, s, _ in amounts(text):
                if i <= s <= i + len(w) + window and v >= 100:
                    return v
            i = low.find(w, i + 1)
    return None


# ---------- calculators: each returns a short "Computed" text or None ----------


def calc_gratuity(q: str) -> str | None:
    low = q.lower()
    if "gratuity" not in low:
        return None
    wage = _near(q, ("last drawn", "wages", "basic"), 80)
    ym = re.search(r"(\d+)\s*(?:completed\s*)?years?(?:\s*(?:and)?\s*(\d+)\s*months?)?", low)
    if not wage or not ym:
        return None
    years, months = int(ym.group(1)), int(ym.group(2) or 0)
    counted = years + 1 if months >= 6 else years
    raw = rup(Decimal(wage) * 15 / 26 * counted)
    rounding = "more than 6 months rounds up" if months >= 6 else "months up to 6 are ignored"
    text = (f"Gratuity = last drawn wages x 15/26 x completed years of service. {years} years {months} months counts as "
            f"{counted} years ({rounding}). {inr(wage)} x 15/26 x {counted} = {inr(raw)}.")
    if raw > 2_000_000:
        text += f" Gratuity is capped at {inr(2_000_000)}."
    return text


def calc_epf(q: str) -> str | None:
    low = q.lower()
    if not ("pf" in re.findall(r"[a-z]+", low) or "provident fund" in low or "epf" in low):
        return None
    if not any(w in low for w in ("contribution", "deduction", "deduct", "compute", "calculate", "how much")):
        return None
    wage = _near(q, ("basic", "wages", "salary", "pay"), 60)
    if not wage:
        return None
    pf_wages = min(wage, 25_000)
    c = rup(Decimal(pf_wages) * 12 / 100)
    if wage > 25_000:
        return (f"PF wages = the lower of {inr(wage)} and the Rs 25,000 ceiling = {inr(pf_wages)}. Employee 12% = {inr(c)}; "
                f"employer also contributes 12% = {inr(c)}.")
    return (f"Wages are within the Rs 25,000 ceiling, so PF wages = {inr(pf_wages)}. Employee 12% = {inr(c)}; "
            f"employer also contributes 12% = {inr(c)}.")


def calc_esi(q: str) -> str | None:
    low = q.lower()
    if "esi" not in re.findall(r"[a-z]+", low):
        return None
    wage = _near(q, ("gross", "wages", "salary", "pay"), 60)
    if not wage:
        return None
    if wage > 21_000:
        return (f"Gross wages of {inr(wage)} are above the Rs 21,000 ESI wage ceiling, so ESI is not deducted, unless the "
                f"employee is already inside a contribution period that began when wages were within the limit.")
    e, r = ceil_rup(Decimal(wage) * Decimal("0.0075")), ceil_rup(Decimal(wage) * Decimal("0.0325"))
    return (f"Gross wages of {inr(wage)} are within the Rs 21,000 ESI limit. Employee 0.75% = {inr(e)}; employer 3.25% = {inr(r)}, "
            f"each rounded up to the next rupee.")


def calc_new_regime_tax(q: str) -> str | None:
    low = q.lower()
    if "old regime" in low or "old tax regime" in low:
        return None
    if not any(w in low for w in ("tax", "tds")):
        return None
    if not any(w in low for w in ("salary", "gross", "ctc", "pay")):
        return None
    gross = _near(q, ("gross", "salary", "ctc", "pay"), 60)
    if not gross or gross < 300_000:
        return None
    taxable = gross - 75_000
    t = new_regime_tax(taxable)
    text = f"Taxable income = {inr(gross)} - Rs 75,000 standard deduction = {inr(taxable)}. "
    if t["note"] == "rebate":
        text += "It is within Rs 12,00,000, so the 87A rebate makes tax nil. Monthly TDS is nil."
    else:
        if t["note"] == "relief":
            text += f"Slab tax is {inr(t['slab_tax'])}, but marginal relief limits tax to the income above Rs 12,00,000 = {inr(t['tax'])}. "
        else:
            text += f"Slab tax = {inr(t['tax'])}. "
        text += f"Cess 4% = {inr(t['cess'])}. Total tax = {inr(t['total'])}; monthly TDS = {inr(rup(Decimal(t['total']) / 12))}."
    return text


def calc_interest(q: str) -> str | None:
    low = q.lower()
    if "interest" not in low:
        return None
    if "msme" in low or "bank rate" in low:
        return None
    dm = re.search(r"(\d+)\s*days?", low)
    if not dm:
        return None
    amt = _near(q, ("itc of", "gst of", "tax of", "itc", "gst", "tax", "amount"), 40)
    if not amt:
        return None
    days = int(dm.group(1))
    if days > 3650:
        return None
    i = rup(Decimal(amt) * 18 / 100 * days / 365)
    which = "Section 50(3)" if ("wrongly" in low or "utilised" in low or "utilized" in low) else "Section 50(1)"
    return f"Interest under {which} is 18% a year. {inr(amt)} x 18% x {days}/365 = {inr(i)}."


CALCULATORS = (calc_gratuity, calc_epf, calc_esi, calc_new_regime_tax, calc_interest)


# Wording that means the question is not the plain textbook case, so a single formula would mislead
_NOT_PLAIN = re.compile(
    r"bonus|80c|80d|deduction|ctc|take[- ]?home|compare|comparison|which regime|portion|cash|ledger|net |balance|"
    r"extra|increment|arrears|previous employer|mid[- ]?year|joined|resign|retire|part[- ]month|notice|leave|"
    r"allowance|hra|lta|reimburse|exempt|old regime|msme|per cent of|% of",
    re.I)


def computed_hint(question: str) -> str | None:
    """The system's own working for a plain calculation question, or None.

    Silent unless the question holds exactly one money amount and none of the wording that makes a
    calculation depend on more than one formula."""
    big = {v for v, _, _ in amounts(question) if v >= 1000}
    if len(big) != 1 or _NOT_PLAIN.search(question):
        return None
    results = []
    for fn in CALCULATORS:
        try:
            r = fn(question)
        except Exception:
            r = None
        if r:
            results.append(r)
    # Two calculators firing on one question means the question is ambiguous: say nothing
    return results[0] if len(results) == 1 else None
