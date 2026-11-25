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


def _amount_before(text: str, words: tuple[str, ...], window: int = 12):
    """The money amount written just before one of `words`, for example '23k gross'."""
    low = text.lower()
    for w in words:
        i = low.find(w)
        while i != -1:
            for v, s, e in amounts(text):
                if v >= 100 and 0 <= i - e <= window:
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
    # A person with a disability has a higher ceiling (Rs 25,000); do not guess, leave it to the model
    if re.search(r"disab", low) and not re.search(r"\b(no|not|without|non)\b[^.?]{0,15}disab", low):
        return None
    wage = _near(q, ("gross", "wages", "salary", "pay"), 60) or _amount_before(q, ("gross", "wages", "salary"))
    if not wage:
        return None
    if wage > 21_000:
        return (f"Gross wages of {inr(wage)} are above the Rs 21,000 ESI wage ceiling, so ESI is not deducted, unless the "
                f"employee is already inside a contribution period that began when wages were within the limit.")
    e, r = ceil_rup(Decimal(wage) * Decimal("0.0075")), ceil_rup(Decimal(wage) * Decimal("0.0325"))
    return (f"Gross wages of {inr(wage)} are within the Rs 21,000 ESI limit. Employee 0.75% = {inr(e)}; employer 3.25% = {inr(r)}, "
            f"each rounded up to the next rupee.")


_NOT_SALARY_TAX = re.compile(
    r"\bgst\b|\bigst\b|invoice|\bfees?\b|professional|technical|commission|contractor|vendor|supplier|director|gratuity|"
    r"leave encash|\brent\b|dividend|capital gain|\blottery\b|crypto", re.I)


def calc_new_regime_tax(q: str) -> str | None:
    low = q.lower()
    if "old regime" in low or "old tax regime" in low:
        return None
    if not any(w in low for w in ("tax", "tds")):
        return None
    # It must be a salary-tax question. "pay" is not enough ("pays Rs 3,00,000 plus GST", "paying tax on gratuity"),
    # and questions about GST, invoices, fees, gratuity or other income are not salary tax.
    if not re.search(r"\b(salary|gross|ctc|wages|annual income|take[- ]?home)\b", low):
        return None
    if _NOT_SALARY_TAX.search(low):
        return None
    gross = _near(q, ("gross", "salary", "ctc", "wages"), 60)
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


_AFTER_APR_2026 = re.compile(
    r"2026-27|2026/27|tax year 2026|fy 2026|\b(?:apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s+2026|\b2027\b", re.I)


def _nr_text(taxable: int) -> str:
    """New-regime tax working for a taxable income (FY 2025-26 slabs), in the same words as calc_new_regime_tax."""
    t = new_regime_tax(taxable)
    if t["note"] == "rebate":
        return (f"Slab tax: {slab_lines(taxable, SLABS)} = {inr(t['slab_tax'])}. Taxable income is within Rs 12,00,000, "
                f"so the Section 87A rebate reduces the tax to nil.")
    if t["note"] == "relief":
        return (f"Slab tax: {slab_lines(taxable, SLABS)} = {inr(t['slab_tax'])}. Marginal relief under Section 87A limits tax to "
                f"the income above Rs 12,00,000 = {inr(t['tax'])}. Cess 4% = {inr(t['cess'])}. Total tax = {inr(t['total'])}.")
    return (f"Slab tax: {slab_lines(taxable, SLABS)} = {inr(t['tax'])}. Cess 4% = {inr(t['cess'])}. Total tax = {inr(t['total'])}.")


def calc_tds_professional(q: str) -> str | None:
    """TDS on a professional fee when the invoice shows GST separately: the base leaves GST out (Circular 23/2017)."""
    low = q.lower()
    if "tds" not in low or not re.search(r"professional|consultan|194j", low):
        return None
    if re.search(r"contractor|technical|rent|commission|salary|director|royalty", low) or _AFTER_APR_2026.search(low):
        return None
    if "gst" not in low or "separate" not in low:
        return None
    fee = _near(q, ("professional fee", "consultancy fee", "fee"), 40)
    if not fee or fee < 50_000:                      # below the Rs 50,000 threshold, or no fee read
        return None
    gst = _near(q, ("gst of",), 20) or _near(q, ("gst",), 25)
    rate = re.search(r"(\d+(?:\.\d+)?)\s*%\s*gst|gst\s*(?:@|at)?\s*(\d+(?:\.\d+)?)\s*%", low)
    if not gst and rate:
        gst = rup(Decimal(fee) * Decimal(rate.group(1) or rate.group(2)) / 100)
    if not gst or gst > fee * 3 // 10:               # GST above 30% of the fee means a wrong amount was read
        return None
    tds = rup(Decimal(fee) * 10 / 100)
    total = fee + gst
    return (f"TDS under Section 194J on professional fees is 10%. Because GST is shown separately in the invoice, the base is the fee "
            f"excluding GST (CBDT Circular 23/2017). Base = {inr(fee)}; TDS = {inr(fee)} x 10% = {inr(tds)}. "
            f"Invoice total = {inr(fee)} + {inr(gst)} GST = {inr(total)}; pay {inr(total - tds)} after deducting TDS.")


def calc_bonus_tds(q: str) -> str | None:
    """Extra annual tax caused by a bonus, new regime FY 2025-26: tax with the bonus minus tax without it."""
    low = q.lower()
    if "bonus" not in low or "new regime" not in low or "old regime" in low or _AFTER_APR_2026.search(low):
        return None
    if not re.search(r"extra (tds|tax)|additional (tds|tax)|tds (on|because of|due to) (the )?bonus|tax on (the )?bonus", low):
        return None
    bonus = _near(q, ("bonus of", "bonus"), 30)
    salary = _near(q, ("salary is", "salary of", "salary"), 40)
    if not bonus or not salary or bonus == salary or salary + bonus < 300_000:
        return None
    t0, t1 = new_regime_tax(salary - 75_000), new_regime_tax(salary + bonus - 75_000)
    return (f"The bonus is added to the estimated annual salary. Without the bonus: taxable {inr(salary - 75_000)}, tax {inr(t0['tax'])} "
            f"+ cess {inr(t0['cess'])} = {inr(t0['total'])}. With the bonus: taxable {inr(salary + bonus - 75_000)}, tax {inr(t1['tax'])} "
            f"+ cess {inr(t1['cess'])} = {inr(t1['total'])}. Extra tax because of the bonus = {inr(t1['total'] - t0['total'])}. "
            f"It is recovered through the estimated-annual-income TDS, not as a flat rate on the bonus.")


def calc_prev_employer(q: str) -> str | None:
    """Full-year new-regime tax for a mid-year joiner whose previous employer's salary is on Form 12B (FY 2025-26)."""
    low = q.lower()
    if not ("12b" in low or "previous employer" in low) or "new regime" not in low or "old regime" in low:
        return None
    if not any(w in low for w in ("tax", "tds")) or _AFTER_APR_2026.search(low):
        return None
    j = _date_after(q, ("joined",), 25)
    if not j or j[0] != 1 or (j[2] not in (None, 2025) and not (j[2] == 2026 and j[1] <= 3)):
        return None
    m = re.search(r"(?:rs\.?\s*)?(\d[\d,]*)\s*(?:a|per)\s*month", low)
    prev = _near(q, ("12b", "previous employer"), 45)
    if not m or not prev:
        return None
    monthly, month = int(m.group(1).replace(",", "")), j[1]
    months = 16 - month if month >= 4 else 4 - month
    if monthly < 5_000 or months < 1:
        return None
    gross = prev + monthly * months
    taxable = gross - 75_000
    return (f"Add the previous employer's salary from Form 12B: {inr(prev)} + {inr(monthly)} x {months} months = {inr(gross)}. "
            f"The Rs 75,000 standard deduction is allowed once for the year: taxable = {inr(gross)} - Rs 75,000 = {inr(taxable)}. "
            + _nr_text(taxable))


_FINANCIAL = re.compile(r"nbfc|non[- ]?bank|bank|insurer|insurance|financial institution|finance company", re.I)


def _labelled_dates(q: str) -> dict:
    """{'service': (d, m, y|None), 'invoice': ..., 'payment': ...}: each date is labelled by the words just before it."""
    out, prev_end = {}, 0
    for m in _DATE.finditer(q):
        seg = q[max(prev_end, m.start() - 45):m.start()].lower()
        if re.search(r"payment|paid|received|advance", seg):
            lab = "payment"
        elif re.search(r"invoice|bill", seg):
            lab = "invoice"
        elif re.search(r"service|completed|rendered|renders|provided|supply|finished|\bdone\b|\bwork\b", seg):
            lab = "service"
        else:
            lab = None
        if lab and lab not in out:
            out[lab] = (int(m.group(1)), _MONTHS[m.group(2).lower()], int(m.group(3)) if m.group(3) else None)
        prev_end = m.end()
    return out


def _resolve_dates(labelled: dict):
    """Real dates for the labelled ones; a year the question leaves out is assumed only to do the day count."""
    import datetime
    base = next((p[2] for p in labelled.values() if p[2]), 2026)
    out = {}
    for lab in ("service", "invoice", "payment"):
        if lab in labelled:
            d = _to_date(labelled[lab], labelled[lab][2] or base)
            if not d:
                return None
            if "service" in out and d < out["service"] and not labelled[lab][2]:
                d = _to_date(labelled[lab], base + 1) or d
            out[lab] = d
    return out


def _fmt(d, show_year: bool) -> str:
    return f"{d.day} {d.strftime('%b')}" + (f" {d.year}" if show_year else "")


def calc_invoice_deadline(q: str) -> str | None:
    """Rule 47: the invoice for a service is due within 30 days of the service (45 days for banks, NBFCs and insurers)."""
    import datetime
    low = q.lower()
    if "invoice" not in low or not re.search(r"\blate\b|within|on time|in time|deadline|too late", low):
        return None
    lab = _labelled_dates(q)
    if "service" not in lab or "invoice" not in lab:
        return None
    d = _resolve_dates(lab)
    if not d:
        return None
    limit = 45 if _FINANCIAL.search(low) else 30
    deadline = d["service"] + datetime.timedelta(days=limit)
    gap = (d["invoice"] - d["service"]).days
    if gap < 0 or gap > 400:
        return None
    yr = bool(lab["service"][2] or lab["invoice"][2])
    who = "banks, NBFCs and other financial institutions" if limit == 45 else "other service providers"
    head = (f"Rule 47 of the CGST Rules requires the invoice for services within {limit} days of the service for {who} "
            f"(30 days for others, 45 days for banks, NBFCs and insurers). Service on {_fmt(d['service'], yr)} + {limit} days = "
            f"{_fmt(deadline, yr)}. The invoice on {_fmt(d['invoice'], yr)} is {gap} days after the service, so ")
    if gap <= limit:
        return head + "it is not late."
    return head + f"it is late by {gap - limit} days. A late invoice makes the date of the service (or an earlier payment) the time of supply."


def calc_time_of_supply(q: str) -> str | None:
    """Time of supply for services (Section 13(2) CGST Act): depends on whether the invoice came within the Rule 47 period."""
    import datetime
    low = q.lower()
    if not re.search(r"time of supply|which date decides|return period|liability", low) or "invoice" not in low:
        return None
    if not re.search(r"service|completed|rendered|provided|finished|\bdone\b|\bwork\b", low):
        return None
    lab = _labelled_dates(q)
    if "service" not in lab or "invoice" not in lab:
        return None
    d = _resolve_dates(lab)
    if not d:
        return None
    limit = 45 if _FINANCIAL.search(low) else 30
    gap = (d["invoice"] - d["service"]).days
    if gap < 0 or gap > 400:
        return None
    pay = d.get("payment")
    yr = any(p[2] for p in lab.values())
    late = gap > limit
    if late:
        tos = min(d["service"], pay) if pay else d["service"]
        why = (f"The invoice was issued {gap} days after the service, beyond the {limit}-day period, so the time of supply is the "
               f"earlier of the date of the service and the date of payment" + (f" ({_fmt(pay, yr)})" if pay else "") + ".")
    else:
        if not pay:
            return None                              # on time and no payment date: the invoice date decides, nothing to compute
        tos = min(d["invoice"], pay)
        why = (f"The invoice was issued within {limit} days, so the time of supply is the earlier of the invoice date "
               f"and the payment date ({_fmt(pay, yr)}).")
    month = tos.strftime("%B") + (f" {tos.year}" if yr else "")
    return (f"Time of supply of services under Section 13(2) of the CGST Act: {why} Here it is {_fmt(tos, yr)}. "
            f"The tax goes in the {month} return (GSTR-1 and GSTR-3B), even if the invoice or payment comes later.")


SPECIALISTS = (calc_late_fee, calc_rule37, calc_old_regime_tax, calc_hra, calc_new_regime_marginal,
               calc_tds_professional, calc_bonus_tds, calc_prev_employer, calc_invoice_deadline, calc_time_of_supply)


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
