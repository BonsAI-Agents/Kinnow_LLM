"""
Generate Invoice and Payroll calculation rows for training and the notes file.

Every number in an answer is computed by the functions below, so the arithmetic cannot be wrong; the
rules come from Tejas's FACTS_TO_VERIFY.md (and the Section 50(3) point the owner assumed confirmed).
No new section numbers or forms are invented here. Rules that are not in the checklist and not settled
law are left out (Maharashtra professional tax, EPS split, overtime).

    python scripts/generate_calc_rows.py                 # writes data/generated/calc_rows.jsonl, prints a sample
    python scripts/generate_calc_rows.py --seed 7 --show 30

Review the sample before the file goes into training.
"""

import argparse
import json
import random
import sys
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, ROUND_CEILING, Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "generated" / "calc_rows.jsonl"


# ---------- helpers (also used by the tests) ----------

def rup(x) -> int:
    """Round half up to a whole rupee."""
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


def pl(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def gratuity(last_drawn: int, completed_years: int, cap: int = 2_000_000) -> tuple[int, bool]:
    """Last drawn wages x 15/26 x completed years, capped at Rs 20 lakh. Returns (amount, capped)."""
    amount = rup(Decimal(last_drawn) * 15 / 26 * completed_years)
    return (cap, True) if amount > cap else (amount, False)


NEW_REGIME_SLABS_FY2025_26 = [(400_000, 0), (800_000, 5), (1_200_000, 10), (1_600_000, 15),
                              (2_000_000, 20), (2_400_000, 25), (10**12, 30)]


def new_regime_tax(taxable: int) -> dict:
    """New regime FY 2025-26: slabs, 87A rebate up to Rs 12 lakh with marginal relief, 4% cess."""
    tax, lower = Decimal(0), 0
    for upper, rate in NEW_REGIME_SLABS_FY2025_26:
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


def leave_encashment_exempt(years: int, balance_days: int, avg_monthly: int, received: int) -> dict:
    eligible_days = min(balance_days, 30 * years)
    a = rup(Decimal(eligible_days) * avg_monthly / 30)
    b = 10 * avg_monthly
    c = 2_500_000
    exempt = min(a, b, c, received)
    return {"eligible_days": eligible_days, "a": a, "b": b, "c": c, "exempt": exempt, "taxable": received - exempt}


def interest(amount: int, rate_pct: int, days: int) -> int:
    return rup(Decimal(amount) * rate_pct / 100 * days / 365)


def fy_of(d: date) -> str:
    y = d.year if d.month >= 4 else d.year - 1
    return f"{y}-{str(y + 1)[2:]}"


# ---------- payroll templates ----------

def p_gratuity(rng):
    years = rng.randint(5, 32)
    months = rng.randint(0, 11)
    w = rng.randrange(20_000, 150_001, 2_500)
    y = years + 1 if months >= 6 else years
    amt, capped = gratuity(w, y)
    q = rng.choice([
        f"An employee served {pl(years, 'year')} {pl(months, 'month')}. Last drawn basic plus DA is {inr(w)} a month. Gratuity payable?",
        f"Gratuity for {pl(years, 'year')} and {pl(months, 'month')} of service with last drawn wages (basic + DA) of {inr(w)} per month?",
        f"Employee resigns after {pl(years, 'year')} {pl(months, 'month')}, last drawn basic and DA {inr(w)}. Work out the gratuity.",
    ])
    rounding = ("more than 6 months rounds up" if months >= 6 else "months up to 6 are ignored")
    a = (f"Gratuity = last drawn wages x 15/26 x completed years of service. {pl(years, 'year')} {pl(months, 'month')} counts as {y} years "
         f"({rounding}). {inr(w)} x 15/26 x {y} = {inr(amt if not capped else rup(Decimal(w) * 15 / 26 * y))}.")
    if capped:
        a += f" Gratuity is capped at {inr(2_000_000)}, so {inr(2_000_000)} is payable."
    return "PAYROLL", q, a


def p_gratuity_fixed(rng):
    years = rng.randint(1, 4)
    months = rng.randint(0, 11)
    w = rng.randrange(18_000, 90_001, 1_000)
    y = years + 1 if months >= 6 else years
    amt, _ = gratuity(w, y)
    q = rng.choice([
        f"A fixed-term employee completed {pl(years, 'year')} {pl(months, 'month')}. Last drawn wages {inr(w)} a month. Is gratuity payable, and how much?",
        f"Fixed-term contract employee leaves after {pl(years, 'year')} {pl(months, 'month')}, last drawn wages {inr(w)}. Gratuity?",
    ])
    a = (f"Yes. Under the labour codes a fixed-term employee is eligible for gratuity after 1 year of service. "
         f"Gratuity = {inr(w)} x 15/26 x {pl(y, 'year')} = {inr(amt)}.")
    return "PAYROLL", q, a


def p_epf(rng):
    w = rng.randrange(8_000, 90_001, 500)
    pf_wages = min(w, 25_000)
    c = rup(Decimal(pf_wages) * 12 / 100)
    q = rng.choice([
        f"Basic plus DA is {inr(w)} a month. What are the employee and employer EPF contributions with the Rs 25,000 wage ceiling?",
        f"Employee earns {inr(w)} a month as basic and DA. EPF contribution on the current wage ceiling?",
        f"Compute the monthly PF deduction for basic + DA of {inr(w)}, given the EPF wage ceiling.",
    ])
    if w > 25_000:
        a = (f"PF wages = the lower of {inr(w)} and the Rs 25,000 ceiling (from 17 September 2026) = {inr(pf_wages)}. "
             f"Employee 12% = {inr(c)}; employer also contributes 12% = {inr(c)}. Mandatory contribution is on wages up to the ceiling; "
             f"anything above it needs agreement.")
    else:
        a = (f"Wages are within the Rs 25,000 ceiling (from 17 September 2026), so PF wages = {inr(pf_wages)}. "
             f"Employee 12% = {inr(c)}; employer also contributes 12% = {inr(c)}.")
    return "PAYROLL", q, a


def p_esi(rng):
    g = rng.randrange(8_000, 30_001, 250)
    q = rng.choice([
        f"Employee's gross wages are {inr(g)} a month. Is ESI deductible, and how much?",
        f"ESI contribution for gross monthly wages of {inr(g)}?",
        f"Monthly gross {inr(g)}. Work out the ESI split between employee and employer.",
    ])
    if g <= 21_000:
        e, r = ceil_rup(Decimal(g) * Decimal("0.0075")), ceil_rup(Decimal(g) * Decimal("0.0325"))
        a = (f"Yes. Gross wages of {inr(g)} are within the Rs 21,000 ESI limit. Employee 0.75% = {inr(e)}; "
             f"employer 3.25% = {inr(r)}, each rounded up to the next rupee.")
    else:
        a = (f"No. Gross wages of {inr(g)} are above the Rs 21,000 ESI wage ceiling, so ESI is not deducted, "
             f"unless the employee is already inside a contribution period that began when wages were within the limit.")
    return "PAYROLL", q, a


def p_tds_new(rng):
    gross = rng.randrange(500_000, 4_500_001, 25_000)
    taxable = gross - 75_000
    t = new_regime_tax(taxable)
    q = rng.choice([
        f"Salary of {inr(gross)} a year, new regime, FY 2025-26, no other income. Tax and monthly TDS?",
        f"Annual gross salary {inr(gross)}. Compute income tax under the new regime for FY 2025-26 and the monthly TDS.",
        f"New tax regime FY 2025-26: employee's gross pay is {inr(gross)}. What tax is payable and what monthly TDS should be cut?",
    ])
    a = f"Taxable income = {inr(gross)} - Rs 75,000 standard deduction = {inr(taxable)}. "
    if t["note"] == "rebate":
        a += "It is within Rs 12,00,000, so the 87A rebate makes tax nil. Monthly TDS is nil."
    else:
        if t["note"] == "relief":
            a += (f"Slab tax is {inr(t['slab_tax'])}, but marginal relief limits tax to the income above Rs 12,00,000 = {inr(t['tax'])}. ")
        else:
            a += f"Slab tax = {inr(t['tax'])}. "
        a += f"Cess 4% = {inr(t['cess'])}. Total tax = {inr(t['total'])}; monthly TDS = {inr(rup(Decimal(t['total']) / 12))}."
    return "PAYROLL", q, a


def p_leave(rng):
    years = rng.randint(8, 35)
    avg = rng.randrange(30_000, 200_001, 5_000)
    bal = rng.randrange(60, 421, 10)
    received = rup(Decimal(bal) * avg / 30)
    r = leave_encashment_exempt(years, bal, avg, received)
    q = rng.choice([
        f"Private sector employee retires after {years} years with {bal} days of unavailed leave. Average monthly salary {inr(avg)}; leave encashment received {inr(received)}. How much is exempt?",
        f"Leave encashment of {inr(received)} paid at retirement for {bal} days of leave, {years} years of service, average salary {inr(avg)} a month. Exempt and taxable parts?",
    ])
    a = (f"Exempt amount is the least of: (a) leave for up to 30 days per year of service ({r['eligible_days']} days x {inr(avg)}/30) = {inr(r['a'])}; "
         f"(b) 10 months' average salary = {inr(r['b'])}; (c) {inr(r['c'])}; (d) amount received = {inr(received)}. "
         f"Exempt = {inr(r['exempt'])}; taxable = {inr(r['taxable'])}.")
    return "PAYROLL", q, a


MONTHS = [("July", 2026, 31), ("August", 2026, 31), ("September", 2026, 30), ("October", 2026, 31),
          ("November", 2026, 30), ("December", 2026, 31), ("January", 2027, 31), ("February", 2027, 28),
          ("March", 2027, 31)]


def p_partial(rng):
    name, yr, dim = rng.choice(MONTHS)
    m = rng.randrange(20_000, 150_001, 2_500)
    if rng.random() < 0.5:
        d = rng.randint(2, dim - 2)
        days = dim - d + 1
        q = rng.choice([
            f"Employee joins on {d} {name} {yr} at {inr(m)} a month. Salary payable for {name}?",
            f"New joiner starts on {d} {name} {yr}, monthly salary {inr(m)}. How much is paid for {name} on a calendar-day basis?",
        ])
        a = f"{name} has {dim} days. Days payable from {d} {name} = {days}. Salary = {inr(m)} x {days}/{dim} = {inr(rup(Decimal(m) * days / dim))}."
    else:
        d = rng.randint(3, dim - 1)
        q = rng.choice([
            f"Employee's last working day is {d} {name} {yr}; monthly salary {inr(m)}. Salary for {name}?",
            f"Employee resigns with the last day on {d} {name} {yr}, salary {inr(m)} a month. Pay for {name} on a calendar-day basis?",
        ])
        a = f"{name} has {dim} days. Days payable up to {d} {name} = {d}. Salary = {inr(m)} x {d}/{dim} = {inr(rup(Decimal(m) * d / dim))}."
    return "PAYROLL", q, a


def p_bonus(rng):
    w = rng.choice([4_500, 6_000, 7_000, 9_000, 12_000, 15_000, 18_000, 20_000, 21_000, 23_000, 26_000])
    months = rng.choice([6, 8, 10, 12])
    if w > 21_000:
        q = f"Employee earns {inr(w)} a month and worked {months} months. Is statutory bonus payable?"
        a = f"No. Statutory bonus applies to employees earning up to Rs 21,000 a month, and {inr(w)} is above that limit."
    else:
        base = min(w, 7_000) * months
        lo, hi = rup(Decimal(base) * Decimal("0.0833")), rup(Decimal(base) * 20 / 100)
        q = rng.choice([
            f"Employee earns {inr(w)} a month and worked {months} months. What is the minimum and maximum statutory bonus?",
            f"Statutory bonus range for monthly wages of {inr(w)} over {months} months of work?",
        ])
        a = (f"Eligible, since wages are within Rs 21,000. Bonus is computed on wages up to Rs 7,000 a month (or the minimum wage, if higher): "
             f"{inr(min(w, 7_000))} x {months} = {inr(base)}. Minimum 8.33% = {inr(lo)}; maximum 20% = {inr(hi)}.")
    return "PAYROLL", q, a


def p_pf_hi(rng):
    w = rng.randrange(8_000, 90_001, 500)
    pw = min(w, 25_000)
    c = rup(Decimal(pw) * 12 / 100)
    q = f"बेसिक + DA {inr(w, '₹')} प्रति माह है। PF वेतन सीमा ₹25,000 के साथ कर्मचारी और नियोक्ता का PF योगदान कितना होगा?"
    a = (f"PF वेतन = {inr(w, '₹')} और ₹25,000 सीमा में से कम = {inr(pw, '₹')}। कर्मचारी का 12% = {inr(c, '₹')}, "
         f"और नियोक्ता भी 12% = {inr(c, '₹')} देता है।")
    return "PAYROLL", q, a


def p_esi_hi(rng):
    g = rng.randrange(8_000, 30_001, 250)
    q = f"कर्मचारी का सकल वेतन {inr(g, '₹')} प्रति माह है। क्या ESI कटेगा और कितना?"
    if g <= 21_000:
        e, r = ceil_rup(Decimal(g) * Decimal("0.0075")), ceil_rup(Decimal(g) * Decimal("0.0325"))
        a = (f"हाँ। {inr(g, '₹')} का वेतन ₹21,000 की ESI सीमा के भीतर है। कर्मचारी का 0.75% = {inr(e, '₹')} और "
             f"नियोक्ता का 3.25% = {inr(r, '₹')}, दोनों अगले पूरे रुपये तक।")
    else:
        a = f"नहीं। {inr(g, '₹')} का वेतन ₹21,000 की ESI वेतन सीमा से ऊपर है, इसलिए ESI नहीं कटेगा।"
    return "PAYROLL", q, a


def p_gratuity_hi(rng):
    y = rng.randint(5, 30)
    w = rng.randrange(20_000, 120_001, 2_500)
    amt, capped = gratuity(w, y)
    q = f"अंतिम बेसिक + DA {inr(w, '₹')} प्रति माह है और सेवा {y} पूर्ण वर्ष की है। ग्रेच्युटी कितनी बनेगी?"
    a = f"ग्रेच्युटी = अंतिम वेतन x 15/26 x पूर्ण वर्ष = {inr(w, '₹')} x 15/26 x {y} = {inr(amt, '₹')}।"
    if capped:
        a += " यह ₹20,00,000 की सीमा तक ही देय है।"
    return "PAYROLL", q, a


# ---------- invoice templates ----------

STATES = [("Karnataka", "Maharashtra"), ("Gujarat", "Rajasthan"), ("Tamil Nadu", "Kerala"), ("Delhi", "Punjab"),
          ("Telangana", "Odisha"), ("Haryana", "Uttar Pradesh"), ("West Bengal", "Assam")]


def i_invoice(rng):
    v = rng.randrange(10_000, 2_000_001, 5_000)
    r = rng.choice([5, 18, 18, 18, 40])
    a_state, b_state = rng.choice(STATES)
    inter = rng.random() < 0.5
    tax = rup(Decimal(v) * r / 100)
    kind = rng.choice(["goods", "services"])
    if inter:
        q = f"A supplier in {a_state} invoices a buyer in {b_state} {inr(v)} for {kind} taxable at {r}%. What GST applies and what is the invoice total?"
        a = f"Inter-state supply, so IGST {r}% = {inr(tax)}. Invoice total = {inr(v)} + {inr(tax)} = {inr(v + tax)}."
    else:
        half = Decimal(r) / 2
        h = rup(Decimal(v) * half / 100)
        q = rng.choice([
            f"A business in {a_state} invoices a customer in {a_state} {inr(v)} for {kind} taxable at {r}%. Show the GST and invoice total.",
            f"Intra-state sale within {a_state}: taxable value {inr(v)}, GST rate {r}%. Tax split and total?",
        ])
        a = (f"Intra-state supply, so CGST {half}% = {inr(h)} and SGST {half}% = {inr(h)}, total tax {inr(h * 2)}. "
             f"Invoice total = {inr(v)} + {inr(h * 2)} = {inr(v + h * 2)}.")
    return "INVOICE", q, a


def i_inclusive(rng):
    v = rng.randrange(1_000, 500_001, 100)
    r = rng.choice([5, 18, 18, 40])
    gross = v * (100 + r) // 100
    tax = gross - v
    q = rng.choice([
        f"A price of {inr(gross)} includes GST at {r}%. What are the taxable value and the GST?",
        f"Invoice amount {inr(gross)} is GST-inclusive at {r}%. Split it into taxable value and tax.",
    ])
    a = f"Taxable value = {inr(gross)} x 100/{100 + r} = {inr(v)}. GST at {r}% = {inr(gross)} - {inr(v)} = {inr(tax)}."
    return "INVOICE", q, a


def i_credit_note(rng):
    v = rng.randrange(50_000, 1_000_001, 5_000)
    r = rng.choice([5, 18, 18, 40])
    ret = rng.randrange(5_000, v, 5_000)
    tax = rup(Decimal(ret) * r / 100)
    q = rng.choice([
        f"Goods worth {inr(ret)} (taxable value) from an invoice of {inr(v)} at {r}% GST were returned. What does the credit note show?",
        f"Customer returns part of an invoice: taxable value {inr(ret)}, GST rate {r}%. Credit note value and tax?",
    ])
    a = (f"Credit note taxable value = {inr(ret)}; GST at {r}% = {inr(tax)}; credit note total = {inr(ret + tax)}. "
         f"Issue it under Section 34 and report it in GSTR-1; the buyer reverses ITC of {inr(tax)}.")
    return "INVOICE", q, a


def i_cn_deadline(rng):
    d = date(2025, 4, 1) + timedelta(days=rng.randint(0, 364))
    q = rng.choice([
        f"By when must a credit note be issued for an invoice dated {d.day} {d.strftime('%B %Y')} (FY {fy_of(d)})?",
        f"Last date to issue a credit note against the invoice dated {d.strftime('%d %B %Y').lstrip('0')}?",
    ])
    deadline_year = (d.year if d.month >= 4 else d.year - 1) + 1
    a = (f"The invoice falls in FY {fy_of(d)}. Under Section 34(2) the credit note must be issued by 30 November {deadline_year} "
         f"or the date of filing the annual return (GSTR-9) for that year, whichever is earlier.")
    return "INVOICE", q, a


def i_interest18(rng):
    t = rng.randrange(10_000, 2_000_001, 5_000)
    d = rng.randint(5, 240)
    q = rng.choice([
        f"GST of {inr(t)} was paid {d} days late. Interest under Section 50(1)?",
        f"Output tax of {inr(t)} was paid after a delay of {d} days. Compute the interest.",
    ])
    a = f"Interest under Section 50(1) is 18% a year. {inr(t)} x 18% x {d}/365 = {inr(interest(t, 18, d))}."
    return "INVOICE", q, a


def i_interest503(rng):
    # Section 50(3) rate: 18% (Notification 14/2022-CT per Tejas, 21 Nov 2026; owner's decision, CA still to confirm)
    t = rng.randrange(10_000, 1_000_001, 1_000)
    d = rng.randint(5, 200)
    q = rng.choice([
        f"ITC of {inr(t)} was wrongly availed and utilised, then reversed after {d} days. Interest payable?",
        f"We claimed and used ITC of {inr(t)} that was not eligible and reversed it {d} days later. What is the interest?",
    ])
    a = (f"Section 50(3) charges 18% a year on ITC wrongly availed and utilised, from the date of utilisation to the date of reversal "
         f"(Rule 88B). {inr(t)} x 18% x {d}/365 = {inr(interest(t, 18, d))}.")
    return "INVOICE", q, a


def i_rule37(rng):
    t = rng.randrange(10_000, 1_000_001, 1_000)
    d = rng.randint(185, 330)
    q = rng.choice([
        f"A supplier's invoice with ITC of {inr(t)} stayed unpaid beyond 180 days. The ITC was availed {d} days before we reversed it. What must be done and what interest applies?",
        f"ITC of {inr(t)} on an invoice unpaid for over 180 days is being reversed {d} days after it was availed. Show the reversal and the interest.",
    ])
    a = (f"Rule 37: if the supplier is not paid within 180 days of the invoice date, reverse the ITC of {inr(t)} (in proportion to the unpaid amount) in GSTR-3B Table 4(B)(2). "
         f"Interest at 18% under Section 50(1) = {inr(t)} x 18% x {d}/365 = {inr(interest(t, 18, d))}. The ITC can be claimed again once payment is made.")
    return "INVOICE", q, a


def i_rule42(rng):
    c = rng.randrange(50_000, 1_000_001, 10_000)
    f = rng.randrange(20, 201) * 100_000
    e = rng.randrange(1, 10) * f // 10
    d = rup(Decimal(c) * e / f)
    q = rng.choice([
        f"Common ITC for the month is {inr(c)}. Exempt turnover is {inr(e)} out of total turnover of {inr(f)}. How much ITC is reversed?",
        f"A business makes taxable and exempt supplies. Common credit {inr(c)}; exempt turnover {inr(e)}; total turnover {inr(f)}. Reversal under Rule 42?",
    ])
    a = (f"Rule 42 reversal = common ITC x exempt turnover / total turnover = {inr(c)} x {inr(e)} / {inr(f)} = {inr(d)}. "
         f"This assumes the common credit has no blocked credit and no credit used only for taxable supplies.")
    return "INVOICE", q, a


def i_einv_threshold(rng):
    cr = rng.choice([1, 2, 3, 4, 4.5, 5, 5.5, 6, 8, 10, 15, 25, 60])
    q = rng.choice([
        f"Aggregate annual turnover is Rs {cr} crore. Is e-invoicing mandatory?",
        f"Does a business with AATO of Rs {cr} crore have to issue e-invoices?",
    ])
    if cr > 5:
        a = f"Yes. E-invoicing is mandatory for aggregate turnover above Rs 5 crore, and Rs {cr} crore is above it."
    else:
        a = f"No. E-invoicing is mandatory only above Rs 5 crore aggregate turnover, and Rs {cr} crore is not above it."
    return "INVOICE", q, a


def i_einv_30day(rng):
    cr = rng.choice([10, 12, 15, 25, 40, 100])
    inv = date(2026, 6, 1) + timedelta(days=rng.randint(0, 200))
    lag = rng.randint(5, 55)
    rep = inv + timedelta(days=lag)
    fmt = lambda x: f"{x.day} {x.strftime('%B %Y')}"
    q = rng.choice([
        f"AATO is Rs {cr} crore. An invoice dated {fmt(inv)} is reported on the IRP on {fmt(rep)}. Is it within the time limit?",
        f"Invoice date {fmt(inv)}, IRP reporting on {fmt(rep)}, AATO Rs {cr} crore. Compliant?",
    ])
    verdict = "within" if lag <= 30 else "outside"
    a = (f"AATO of Rs {cr} crore is Rs 10 crore or more, so the invoice must be reported on the IRP within 30 days of its date. "
         f"{fmt(inv)} to {fmt(rep)} is {lag} days, which is {verdict} the 30-day limit.")
    return "INVOICE", q, a


def i_gst_tds(rng):
    v = rng.choice([rng.randrange(50_000, 250_001, 5_000), rng.randrange(255_000, 3_000_001, 5_000)])
    q = rng.choice([
        f"A government department pays a supplier under a contract of {inr(v)} excluding GST. Is GST TDS deducted, and how much?",
        f"GST TDS on a government contract with taxable value {inr(v)}?",
    ])
    if v > 250_000:
        t = rup(Decimal(v) * 2 / 100)
        a = (f"Yes. The contract value is above Rs 2.5 lakh, so the government deducts GST TDS at 2% = {inr(v)} x 2% = {inr(t)} "
             f"(1% CGST + 1% SGST, or 2% IGST on an inter-state supply).")
    else:
        a = f"No. GST TDS applies only when the contract value is above Rs 2.5 lakh, and {inr(v)} is not above it."
    return "INVOICE", q, a


def g_composition(rng):
    cat, rate = rng.choice([("a trader or manufacturer", 1), ("a restaurant not serving alcohol", 5), ("a service provider", 6)])
    t = rng.randrange(100_000, 2_000_001, 10_000)
    qtr = rng.choice([("July to September", "18 October"), ("October to December", "18 January"),
                      ("January to March", "18 April"), ("April to June", "18 July")])
    tax = rup(Decimal(t) * rate / 100)
    q = rng.choice([
        f"A composition dealer who is {cat} had turnover of {inr(t)} for {qtr[0]}. What tax is payable and when?",
        f"Composition scheme: {cat}, quarterly turnover {inr(t)} ({qtr[0]}). Tax and due date of CMP-08?",
    ])
    a = (f"Composition rate for {cat} is {rate}% of turnover: {inr(t)} x {rate}% = {inr(tax)}. "
         f"Pay it with CMP-08 by {qtr[1]}, the 18th of the month after the quarter.")
    return "GST", q, a


PLAN = [
    (p_gratuity, 22), (p_gratuity_fixed, 8), (p_epf, 18), (p_esi, 16), (p_tds_new, 28), (p_leave, 12),
    (p_partial, 14), (p_bonus, 8), (p_pf_hi, 8), (p_esi_hi, 8), (p_gratuity_hi, 8),
    (i_invoice, 32), (i_inclusive, 16), (i_credit_note, 16), (i_cn_deadline, 6), (i_interest18, 16),
    (i_interest503, 10), (i_rule37, 12), (i_rule42, 12), (i_einv_threshold, 10), (i_einv_30day, 10),
    (i_gst_tds, 10), (g_composition, 12),
]


def generate(seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    rows, seen = [], set()
    for fn, n in PLAN:
        made, tries = 0, 0
        while made < n and tries < n * 50:
            tries += 1
            domain, q, a = fn(rng)
            key = q.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            rows.append({"domain": domain, "prompt": q, "completion": a, "template": fn.__name__})
            made += 1
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--show", type=int, default=2, help="sample rows to print per template")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    rows = generate(args.seed)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter
    print(f"{len(rows)} rows -> {OUT.relative_to(ROOT)}  {dict(Counter(r['domain'] for r in rows))}")
    shown = Counter()
    for r in rows:
        if shown[r["template"]] < args.show:
            shown[r["template"]] += 1
            print(f"\n[{r['domain']}/{r['template']}]\nQ: {r['prompt']}\nA: {r['completion']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
