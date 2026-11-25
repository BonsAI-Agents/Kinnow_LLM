"""Calculators added for the model mistakes confirmed by the 25 Nov 2026 research (data/review/real_mistakes_researched.md).

Each question below is a test question the earlier model got wrong. The expected figures were recomputed by hand and match
the researched answers.
"""

from guardrails import calculators as c


# ---- ESI: the amount is written before the word "gross" ----

def test_esi_amount_before_gross_is_read_and_ceiling_applied():
    out = c.computed_hint("esi on 23k gross? new guy no disability")
    assert out and "Rs 23,000" in out and "Rs 21,000" in out and "not deducted" in out


def test_esi_within_limit_still_works():
    out = c.computed_hint("ESI on gross wages of Rs 18,000 a month?")
    assert "Rs 135" in out and "Rs 585" in out


# ---- TDS on a professional fee: GST shown separately is left out of the base ----

def test_tds_professional_fee_excludes_gst():
    q = ("Consultant invoice: professional fee 1,35,000 plus 18% GST of 24,300 shown separately; payment on 12 Jan 2026. "
         "What is the TDS and on what base?")
    out = c.computed_hint(q)
    assert out and "Rs 13,500" in out and "Rs 1,35,000" in out and "Rs 1,45,800" in out
    assert "excluding GST" in out


def test_tds_professional_fee_silent_without_separate_gst():
    assert c.calc_tds_professional("TDS on a professional fee of Rs 1,00,000 paid to a consultant?") is None


def test_tds_professional_fee_silent_for_technical_or_contractor():
    assert c.calc_tds_professional("Contractor bill: fee 1,35,000 plus 18% GST of 24,300 shown separately. TDS?") is None


# ---- extra TDS because of a bonus (new regime FY 2025-26) ----

def test_bonus_extra_tax_new_regime():
    q = "bonus of 2L paid in diwali month, rest of year salary is 18L, new regime FY 2025-26. how much extra tds because of bonus"
    out = c.computed_hint(q)
    assert out and "Rs 41,600" in out and "Rs 1,45,000" in out and "Rs 1,85,000" in out


def test_bonus_silent_for_old_regime_and_for_2026_27():
    assert c.calc_bonus_tds("old regime, bonus of 2L, rest of year salary is 18L. how much extra tds because of bonus") is None
    assert c.calc_bonus_tds("new regime tax year 2026-27, bonus of 2L, salary is 18L. extra tds because of bonus?") is None


# ---- previous employer's salary (Form 12B) ----

def test_previous_employer_12b_full_year_tax():
    q = ("Employee joined on 1 October 2025 at Rs 1,00,000 a month. Form 12B shows Rs 6,00,000 salary from the previous "
         "employer for April to September 2025. New regime FY 2025-26. What is the full-year tax?")
    out = c.computed_hint(q)
    assert out and "Rs 12,00,000" in out and "Rs 11,25,000" in out and "Rs 52,500" in out and "nil" in out


def test_previous_employer_silent_if_joined_mid_month():
    q = ("Employee joined on 15 October 2025 at Rs 1,00,000 a month. Form 12B shows Rs 6,00,000 from the previous employer. "
         "New regime FY 2025-26. Full-year tax?")
    assert c.calc_prev_employer(q) is None


# ---- invoice deadline (Rule 47) and time of supply for services (Section 13(2)) ----

def test_nbfc_invoice_has_45_days():
    out = c.computed_hint("A non-bank finance company renders a service on 5 Oct 2026 and issues the invoice on 15 Nov 2026. Is it late?")
    assert out and "19 Nov 2026" in out and "45 days" in out and "not late" in out


def test_ordinary_service_invoice_has_30_days():
    out = c.computed_hint("A consultant renders a service on 5 Oct 2026 and issues the invoice on 15 Nov 2026. Is it late?")
    assert out and "4 Nov 2026" in out and "30 days" in out and "late" in out and "not late" not in out


def test_time_of_supply_when_invoice_is_late_and_payment_after():
    q = ("Services were completed on 1 October. The invoice was issued on 5 November and payment received on 10 November. "
         "Time of supply and return period?")
    out = c.computed_hint(q)
    assert out and "Here it is 1 Oct." in out and "October return" in out


def test_time_of_supply_when_invoice_is_late_no_payment():
    out = c.computed_hint(
        "Services completed 1 Sep 2026 but the invoice was raised only on 10 Oct 2026. Which date decides GST liability and what follows?")
    assert out and "1 Sep 2026" in out and "September 2026" in out


def test_time_of_supply_payment_before_service_date_wins():
    out = c.calc_time_of_supply(
        "Services completed on 20 Oct 2026, invoice issued on 28 Nov 2026, payment received on 5 Oct 2026. Time of supply?")
    assert out and "5 Oct 2026" in out


def test_time_of_supply_silent_when_invoice_on_time_and_no_payment():
    assert c.calc_time_of_supply("Services completed on 1 Oct 2026, invoice issued on 10 Oct 2026. Time of supply?") is None


def test_reworded_questions_are_read():
    """Different numbers and phrasing from the original failing questions."""
    out = c.computed_hint("We paid a CA professional fees of Rs 80,000 plus GST 18% (Rs 14,400) billed separately. TDS to deduct?")
    assert out and "Rs 8,000" in out and "Rs 80,000" in out
    out = c.computed_hint(
        "Architect finished work on 3 Mar 2026, invoice raised on 15 Apr 2026, payment came 2 May 2026. Time of supply and which return?")
    assert out and "3 Mar 2026" in out and "March 2026 return" in out
    out = c.computed_hint("Services done 12 Dec 2026, invoice 20 Jan 2027, no payment yet. Time of supply?")
    assert out and "12 Dec 2026" in out and "December 2026 return" in out
    out = c.computed_hint("ESI 19500 gross, regular employee, how much does he pay?")
    assert "Rs 147" in out and "Rs 634" in out


def test_gst_amount_larger_than_a_third_of_the_fee_is_not_trusted():
    assert c.calc_tds_professional("Professional fee Rs 50,000, GST shown separately, Rs 49,000. TDS?") is None


def test_dateless_questions_stay_silent():
    assert c.calc_time_of_supply("What is the time of supply for services?") is None
    assert c.calc_invoice_deadline("Is my invoice late?") is None
