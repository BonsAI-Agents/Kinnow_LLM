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
  interest: 18% a year (Section 50(1) and Section 50(3); the 50(3) rate is CA-approved, per the owner, 22 Nov 2026)
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


def slab_lines(taxable: int, slabs) -> str:
    """The tax in each slab that applies, for example 'Rs 4,00,000 to Rs 8,00,000 at 5% = Rs 20,000; ...'."""
    parts, lower = [], 0
    for upper, rate in slabs:
        if taxable > lower and rate:
            top = min(taxable, upper)
            parts.append(f"{inr(lower)} to {inr(top)} at {rate}% = {inr(rup(Decimal(top - lower) * rate / 100))}")
        lower = upper
    return "; ".join(parts)


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
    eps = rup(Decimal(pf_wages) * Decimal("8.33") / 100)
    split = (f" The employer's 12% is split: 8.33% = {inr(eps)} to the EPS pension account and "
             f"3.67% = {inr(c - eps)} to the EPF account.")
    if wage > 25_000:
        return (f"PF wages = the lower of {inr(wage)} and the Rs 25,000 ceiling = {inr(pf_wages)}. Employee 12% = {inr(c)}; "
                f"employer also contributes 12% = {inr(c)}." + split)
    return (f"Wages are within the Rs 25,000 ceiling, so PF wages = {inr(pf_wages)}. Employee 12% = {inr(c)}; "
            f"employer also contributes 12% = {inr(c)}." + split)


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
            text += (f"Slab tax ({slab_lines(taxable, SLABS)}) is {inr(t['slab_tax'])}. The 87A rebate is not given above Rs 12,00,000, "
                     f"but marginal relief under Section 87A limits tax to the income above Rs 12,00,000 = {inr(t['tax'])}. ")
        else:
            text += f"Slab tax: {slab_lines(taxable, SLABS)} = {inr(t['tax'])}. "
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


# ---------- specialist calculators: each has its own strict trigger, so they run without the one-amount gate ----------

_MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
_DATE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?(?:\s+(20\d\d))?",
                   re.I)


def _dates(text: str):
    """[(position, day, month, year or None)] for every 'd Mon [yyyy]' in the text."""
    return [(m.start(), int(m.group(1)), _MONTHS[m.group(2).lower()], int(m.group(3)) if m.group(3) else None)
            for m in _DATE.finditer(text)]


def _date_after(text: str, words: tuple[str, ...], window: int = 30):
    """First date within `window` characters after any of `words`, as (day, month, year or None)."""
    low = text.lower()
    for w in words:
        i = low.find(w)
        while i != -1:
            for pos, d, m, y in _dates(text):
                if i < pos <= i + len(w) + window:
                    return d, m, y
            i = low.find(w, i + 1)
    return None


def _to_date(parts, default_year):
    import datetime
    d, m, y = parts
    try:
        return datetime.date(y or default_year, m, d)
    except (ValueError, TypeError):
        return None


def calc_late_fee(q: str) -> str | None:
    """GSTR-1 / GSTR-3B late fee: days late x Rs 50 (Rs 20 for a nil return). Needs the due date and the filing date."""
    import datetime
    low = q.lower()
    if "late fee" not in low or not re.search(r"gstr[- ]?1\b|gstr[- ]?3b|\b3b\b", low):
        return None
    if re.search(r"gstr[- ]?(9|4|7|8)\b|qrmp|composition|annual", low):
        return None
    due_p, filed_p = _date_after(q, ("due",)), _date_after(q, ("filed", "furnished", "submitted"))
    if not due_p or not filed_p:
        return None
    year = filed_p[2] or due_p[2]
    if not year:
        return None
    due, filed = _to_date(due_p, due_p[2] or year), _to_date(filed_p, year)
    if not due or not filed:
        return None
    if filed < due and due_p[2] is None:          # due date in the year before filing ("due 20 Dec", filed 3 Jan)
        due = _to_date(due_p, year - 1)
    days = (filed - due).days if due else 0
    if days <= 0 or days > 366:
        return None
    first = due + datetime.timedelta(days=1)
    nil = bool(re.search(r"\bnil\b", low))
    rate = 20 if nil else 50
    return (f"Delay is {days} days ({first.day} {first.strftime('%b')} to {filed.day} {filed.strftime('%b %Y')}). "
            f"Under Section 47(1) of the CGST Act, the late fee for a {'nil return' if nil else 'return with tax payable'} is Rs {rate} a day "
            f"(Rs {rate // 2} CGST + Rs {rate // 2} SGST): {days} x {rate} = {inr(days * rate)}, "
            f"subject to the turnover-based cap. Interest at 18% on any unpaid tax is charged separately.")


def calc_rule37(q: str) -> str | None:
    """Rule 37: ITC reversal for the unpaid part of an invoice once 180 days have passed."""
    import datetime
    low = q.lower()
    if "itc" not in low or "paid" not in low or not re.search(r"rule 37|180|reverse|unpaid|balance", low):
        return None
    m = re.search(r"(\d[\d,]*)\s*plus\s*(\d+(?:\.\d+)?)\s*%\s*gst", low)
    if not m:
        return None
    base, rate = int(m.group(1).replace(",", "")), Decimal(m.group(2))
    total = rup(Decimal(base) * (100 + rate) / 100)
    paid = _near(q, ("paid", "pay"), 50)
    inv_p, today_p = _date_after(q, ("dated", "invoice"), 12), _date_after(q, ("today",), 20)
    if not paid or not inv_p or not today_p or paid > total:
        return None
    inv = _to_date(inv_p, inv_p[2] or today_p[2])
    today = _to_date(today_p, today_p[2] or inv_p[2])
    if not inv or not today:
        return None
    deadline = inv + datetime.timedelta(days=180)
    gst = total - base
    if today <= deadline:
        return (f"180 days from {inv.day} {inv.strftime('%b %Y')} end on {deadline.day} {deadline.strftime('%b %Y')}, "
                f"which is after {today.day} {today.strftime('%b %Y')}, so Rule 37 does not yet require a reversal.")
    unpaid = total - paid
    share = rup(Decimal(unpaid) * 100 / total)
    reverse = rup(Decimal(gst) * unpaid / total)
    return (f"Reverse {inr(reverse)} of ITC in GSTR-3B. 180 days from {inv.day} {inv.strftime('%b %Y')} ended on "
            f"{deadline.day} {deadline.strftime('%b %Y')}, so Rule 37 applies to the unpaid part. GST on the invoice = {inr(gst)}. "
            f"Unpaid = {inr(total)} - {inr(paid)} = {inr(unpaid)} ({share}% of {inr(total)}). "
            f"Reverse {inr(gst)} x {share}% = {inr(reverse)}, with interest at 18% a year "
            f"from the date the ITC was availed to the date of reversal. It can be re-availed when the balance is paid.")


_OLD_BLOCK = re.compile(r"hra|rent|80d|80ccd|nps|home loan|24\(b\)|housing|perquisite|bonus|arrears|previous employer|"
                        r"other income|interest income|mid[- ]?year|joined|lta|ctc|compare|new regime|which regime", re.I)


def calc_old_regime_tax(q: str) -> str | None:
    """Old regime tax for a salaried person with only the standard deduction and (optionally) 80C."""
    low = q.lower()
    if "old regime" not in low or not any(w in low for w in ("tax", "tds")) or _OLD_BLOCK.search(q):
        return None
    gross = _near(q, ("gross", "salary", "pay"), 50)
    if not gross or gross < 300_000:
        return None
    c80 = min(_near(q, ("80c",), 40) or 0, 150_000)
    taxable = gross - 50_000 - c80
    slabs = [(250_000, 0), (500_000, 5), (1_000_000, 20), (10**12, 30)]
    tax, lower = Decimal(0), 0
    for upper, rate in slabs:
        if taxable > lower:
            tax += Decimal(min(taxable, upper) - lower) * rate / 100
        lower = upper
    slab_tax = rup(tax)
    text = f"Taxable = {inr(gross)} - Rs 50,000 standard deduction" + (f" - {inr(c80)} (80C)" if c80 else "") + f" = {inr(taxable)}. "
    if taxable <= 500_000:
        return text + "It is within Rs 5,00,000, so the 87A rebate makes tax nil."
    cess = rup(Decimal(slab_tax) * 4 / 100)
    return (text + f"Slab tax: {slab_lines(taxable, slabs)} = {inr(slab_tax)}. "
            f"The 87A rebate is not available because income exceeds Rs 5 lakh. Cess 4% = {inr(cess)}. Total tax = {inr(slab_tax + cess)}.")


_METRO = ("delhi", "mumbai", "kolkata", "chennai")


def calc_hra(q: str) -> str | None:
    """Monthly HRA exemption (old regime): least of actual HRA, rent minus 10% of basic, 50% (metro) or 40% of basic."""
    low = q.lower()
    if "hra" not in low or "basic" not in low or "rent" not in low or not re.search(r"per month|a month|monthly", low):
        return None
    if re.search(r"annual|per year|yearly|\bda\b|dearness|commission", low) or "new regime" in low:
        return None
    if any(c in low for c in _METRO):
        pct = 50
    elif "non-metro" in low or "non metro" in low:
        pct = 40
    else:
        return None                                   # a city outside the four classic metros: do not guess
    basic, hra, rent = _near(q, ("basic",), 40), _near(q, ("hra",), 40), _near(q, ("rent",), 40)
    if not (basic and hra and rent):
        return None
    a, b, c = hra, rent - basic // 10, rup(Decimal(basic) * pct / 100)
    least = max(min(a, b, c), 0)
    return (f"HRA exemption is the least of: (a) actual HRA = {inr(a)}; (b) rent paid minus 10% of basic = {inr(rent)} - {inr(basic // 10)} "
            f"= {inr(b)}; (c) {pct}% of basic = {inr(c)}. The least is {inr(least)} a month; the balance of HRA, {inr(max(hra - least, 0))}, is taxable.")


def calc_new_regime_marginal(q: str) -> str | None:
    """New-regime tax when the question has more than one amount (for example a '12 lakh' threshold) but is otherwise plain."""
    low = q.lower()
    if "new regime" not in low or re.search(
            r"80c|80d|hra|rent|bonus|arrears|previous employer|mid[- ]?year|joined|ctc|perquisite|other income|interest|old regime|"
            r"compare|which regime|2026-27|tax year 2026", low):
        return None
    return calc_new_regime_tax(q)


SPECIALISTS = (calc_late_fee, calc_rule37, calc_old_regime_tax, calc_hra, calc_new_regime_marginal)


# Wording that means the question is not the plain textbook case, so a single formula would mislead
_NOT_PLAIN = re.compile(
    r"bonus|80c|80d|deduction|ctc|take[- ]?home|compare|comparison|which regime|portion|cash|ledger|net |balance|"
    r"extra|increment|arrears|previous employer|mid[- ]?year|joined|resign|retire|part[- ]month|notice|leave|"
    r"allowance|hra|lta|reimburse|exempt|old regime|msme|per cent of|% of",
    re.I)


def computed_hint(question: str) -> str | None:
    """The system's own working for a plain calculation question, or None.

    The specialist calculators run first: each has its own strict trigger. Otherwise silent unless the question
    holds exactly one money amount and none of the wording that makes a calculation depend on more than one formula."""
    for fn in SPECIALISTS:
        try:
            r = fn(question)
        except Exception:
            r = None
        if r:
            return r
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
