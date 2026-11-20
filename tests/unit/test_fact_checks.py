import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "eval"))

from run_fact_check import check, load_claims  # noqa: E402


def test_every_claim_passes_its_own_reference():
    for c in load_claims():
        assert check(c["reference"], c)["passed"], c["id"]


def test_claim_ids_are_unique_and_have_a_question():
    claims = load_claims()
    assert len({c["id"] for c in claims}) == len(claims)
    assert all(c["question"] and (c["all_of"] or c["any_of"]) for c in claims)


def test_stale_figure_fails_the_claim():
    c = next(c for c in load_claims() if c["id"] == "comp_services")
    assert not check("The limit for services is 25 lakh and 50 lakh.", c)["passed"]
    assert check("The limit for services is 50 lakh.", c)["passed"]


def test_checklist_notes_are_well_formed():
    rows = [json.loads(l) for l in open(ROOT / "data/knowledge_extra/checklist_notes.jsonl", encoding="utf-8") if l.strip()]
    assert rows and all(r["domain"] and r["prompt"] and r["completion"] for r in rows)
