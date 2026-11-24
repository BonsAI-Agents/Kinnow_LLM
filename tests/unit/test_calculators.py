import random
import sys
from pathlib import Path

import pytest

from guardrails import calculators as c
from guardrails.retrieval import sources_line, with_notes

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import generate_calc_rows as g  # noqa: E402


def test_arithmetic_matches_the_generator():
    """The server calculators and the training-data generator must agree on every figure."""
    rng = random.Random(1)
    for _ in range(200):
        taxable = rng.randrange(100_000, 6_000_000, 1_000)
        a, b = c.new_regime_tax(taxable), g.new_regime_tax(taxable)
        assert a == b
    for n in (0, 5, 999, 1_000, 12_345, 7_50_000, 12_34_56_789):
        assert c.inr(n) == g.inr(n)
    assert c.rup("2.5") == g.rup("2.5") == 3


def test_amounts_reads_indian_formats():
    vals = [v for v, _, _ in c.amounts("Rs 12,75,000 plus 5.5L and 40k and 2 crore")]
    assert 1275000 in vals and 550000 in vals and 40000 in vals and 20000000 in vals


def test_gratuity():
    out = c.computed_hint("Employee with 12 completed years of service, last drawn wages Rs 52,000 a month. Calculate the gratuity.")
    assert "Rs 3,60,000" in out and "15/26" in out


def test_gratuity_rounds_up_after_six_months():
    out = c.computed_hint("Gratuity for 10 years and 7 months of service with last drawn wages of Rs 40,000 per month?")
    assert "counts as 11 years" in out


def test_new_regime_rebate_and_relief():
    low = c.computed_hint("New regime FY 2025-26, salary only, gross Rs 12,75,000. What is the tax payable?")
    assert "87A rebate" in low and "nil" in low
    rs1 = c.computed_hint("New regime, gross salary Rs 12,75,100. Tax payable?")
    assert "marginal relief" in rs1 and "Rs 104" in rs1       # Rs 100 tax + 4% cess


def test_old_regime_plain_case_is_computed_and_complex_cases_are_left_to_the_model():
    out = c.computed_hint("Old regime, FY 2025-26. Gross salary Rs 8,00,000, tax payable?")
    assert "Rs 7,50,000" in out and "Rs 62,500" in out and "Rs 65,000" in out        # 12,500 + 50,000, cess 2,500
    six = c.computed_hint("Old regime, FY 2025-26. Gross salary Rs 8,00,000, 80C investments Rs 1,50,000. Tax with cess?")
    assert "Rs 32,500" in six and "Rs 33,800" in six
    assert c.computed_hint("Old regime, gross salary Rs 8,00,000, pays rent of Rs 20,000 a month. Tax?") is None   # HRA: not plain
    assert c.computed_hint("Gross salary Rs 5,50,000, old regime. Tax?").endswith("makes tax nil.")


def test_late_fee_counts_the_days_and_picks_the_rate():
    q = "GSTR-3B for August 2026 (due 20 Sep, tax payable) was filed on 3 Oct 2026. Compute the late fee."
    out = c.computed_hint(q)
    assert "13 days" in out and "13 x 50 = Rs 650" in out
    nil = c.computed_hint("Nil GSTR-1 for August 2026 (due 11 Sep) was filed on 20 Sep 2026. Late fee?")
    assert "9 days" in nil and "Rs 180" in nil and "Rs 20 a day" in nil
    assert c.computed_hint("GSTR-9 late fee for 2025-26, filed 30 days late?") is None        # annual return: different rule
    assert c.computed_hint("What is the late fee for GSTR-3B?") is None                       # no dates


def test_rule_37_reverses_the_unpaid_share_after_180_days():
    q = ("Invoice dated 3 Mar 2026: 4,10,000 plus 18% GST = 4,83,800. We have paid only 1,20,950 so far, "
         "balance still open today (17 Nov 2026). What is the ITC position and how much do we reverse?")
    out = c.computed_hint(q)
    assert "30 Aug 2026" in out and "Rs 55,350" in out and "75%" in out
    early = c.computed_hint("Invoice dated 3 Oct 2026: 1,00,000 plus 18% GST. We have paid Rs 50,000, balance open today (17 Nov 2026). Reverse ITC?")
    assert "does not yet require" in early


def test_hra_exemption_is_the_least_of_three_and_never_guesses_the_city():
    out = c.computed_hint("Basic is Rs 40,000 per month, HRA received Rs 16,000, rent paid Rs 15,000 in Mumbai. Old regime. Monthly HRA exemption?")
    assert "Rs 11,000 a month" in out and "Rs 5,000" in out
    assert c.computed_hint("Basic Rs 40,000 per month, HRA Rs 16,000, rent Rs 15,000 in Pune. Monthly HRA exemption?") is None


def test_new_regime_marginal_relief_with_a_second_amount_in_the_question():
    out = c.computed_hint("New regime FY 2025-26, gross salary Rs 12,90,000 and nothing else. "
                          "The employee says the 12 lakh rebate is gone. Is tax the full slab tax?")
    assert "Rs 62,250" in out and "Rs 15,000" in out and "Rs 15,600" in out


def test_epf_uses_the_25000_ceiling():
    out = c.computed_hint("Basic plus DA is 31,500 a month. What are the employee and employer EPF contributions?")
    assert "Rs 25,000" in out and "Rs 3,000" in out


def test_esi_rounds_up_and_respects_the_limit():
    inside = c.computed_hint("Gross monthly wages 19,800. ESI contribution split?")
    assert "Rs 149" in inside and "Rs 644" in inside
    above = c.computed_hint("Gross monthly wages of Rs 23,000. Is ESI deducted?")
    assert "not deducted" in above


def test_interest():
    out = c.computed_hint("GST of Rs 2,00,000 was paid 30 days late. Interest?")
    assert "18%" in out and "Rs 2,959" in out
    wrong = c.computed_hint("ITC of Rs 80,000 was wrongly availed and used for 45 days. What interest applies?")
    assert "Section 50(3)" in wrong and "Rs 1,775" in wrong


def test_ambiguous_or_unrelated_questions_get_no_figure():
    assert c.computed_hint("What is the due date of GSTR-3B?") is None
    assert c.computed_hint("Explain how gratuity works") is None            # no wage, no years
    assert c.computed_hint("Gratuity for 10 years, ESI on wages of Rs 15,000") is None   # two calculators fire


def test_with_notes_adds_the_computed_block_before_the_question():
    out = with_notes("How much?", [], computed="Rs 5.")
    assert out.startswith("Computed by the system") and out.endswith("Question: How much?")
    assert with_notes("hello", []) == "hello"


def test_sources_line_uses_only_what_the_notes_cite():
    hits = [{"completion": "Under Section 16(2)(aa) and Rule 37, file GSTR-3B.", "score": 10.0},
            {"completion": "Section 99 is cited here.", "score": 2.0}]            # too weak: ignored
    line = sources_line(hits)
    assert line == "Sources: Section 16(2)(aa), Rule 37, GSTR-3B."
    assert sources_line([]) == "" and sources_line([{"completion": "no citation", "score": 1}]) == ""


@pytest.mark.parametrize("fn", c.CALCULATORS)
def test_every_calculator_survives_garbage(fn):
    assert fn("") is None or isinstance(fn(""), str)
    assert fn("Rs ,,, 999999999999999 days lakh crore ESI PF gratuity interest tax salary") is None or True
