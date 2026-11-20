import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import generate_calc_rows as g  # noqa: E402


def test_indian_grouping():
    assert g.inr(750000) == "Rs 7,50,000"
    assert g.inr(1234567) == "Rs 12,34,567"
    assert g.inr(986) == "Rs 986"
    assert g.inr(25000, "₹") == "₹25,000"


def test_gratuity_matches_known_examples():
    assert g.gratuity(52000, 12) == (360000, False)
    assert g.gratuity(150000, 30) == (2_000_000, True)    # 26.9 lakh capped at 20 lakh


def test_new_regime_tax_matches_the_worked_example_in_the_data():
    t = g.new_regime_tax(2_425_000)                        # gross 25 lakh - 75,000
    assert (t["tax"], t["cess"], t["total"]) == (307_500, 12_300, 319_800)


def test_rebate_and_marginal_relief():
    assert g.new_regime_tax(1_200_000)["total"] == 0
    r = g.new_regime_tax(1_230_000)                        # slab tax 64,500 but only 30,000 is above 12 lakh
    assert (r["slab_tax"], r["tax"], r["note"]) == (64_500, 30_000, "relief")


def test_interest_examples_from_the_training_data():
    assert g.interest(50_000, 24, 73) == 2_400
    assert g.interest(9_000, 24, 73) == 432
    assert g.interest(50_000, 24, 30) == 986


def test_leave_encashment_takes_the_least_of_four_limits():
    r = g.leave_encashment_exempt(years=20, balance_days=300, avg_monthly=100_000, received=1_000_000)
    assert (r["a"], r["b"], r["exempt"], r["taxable"]) == (1_000_000, 1_000_000, 1_000_000, 0)
    r = g.leave_encashment_exempt(years=5, balance_days=300, avg_monthly=60_000, received=600_000)
    assert r["eligible_days"] == 150 and r["exempt"] == 300_000   # only 30 days a year of service count


def test_generation_is_repeatable_unique_and_covers_every_template():
    rows = g.generate(42)
    assert rows == g.generate(42)
    assert len({r["prompt"].lower() for r in rows}) == len(rows)
    assert {fn.__name__ for fn, _ in g.PLAN} == {r["template"] for r in rows}
    assert {r["domain"] for r in rows} == {"PAYROLL", "INVOICE", "GST"}
    assert all(r["completion"].rstrip().endswith((".", "।")) for r in rows)
