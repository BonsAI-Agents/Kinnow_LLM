"""Intake checks for the new data batches, and the lenient scorer."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval"))
import lenient  # noqa: E402

LONG = "The supply is inter-state so IGST at 18% applies on the taxable value, as per section 7 of the IGST Act, 2017, in full."


def test_lenient_accepts_short_forms_but_never_scores_lower():
    assert lenient.evaluate("RCM applies at 18%", ["reverse charge", "18%"])["passed"]
    assert lenient.evaluate("Claim ITC in 3B", ["input tax credit"])["passed"]
    assert not lenient.evaluate("Regular charge at 18%", ["reverse charge"])["passed"]
    assert not lenient.evaluate("tax is 12%", ["18%"])["passed"]
    assert lenient.evaluate("in november", ["nov"])["passed"]                  # plain keywords stay substring matches
    assert not lenient.evaluate("inputs", ["itc"])["passed"]


def run_ingest(tmp_path, rows15=(), rows1=()):
    d = tmp_path / "in"
    d.mkdir()
    (d / "batch01_gst_pos.jsonl").write_text("\n".join(json.dumps(r) for r in rows1) + "\nnot json\n", encoding="utf-8")
    (d / "batch15_kb_note.jsonl").write_text("\n".join(json.dumps(r) for r in rows15), encoding="utf-8")
    out = tmp_path / "out"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "ingest_new_batches.py"), str(d)], check=True, capture_output=True,
                   env={**__import__("os").environ, "KINNOW_INGEST_OUT": str(out)})
    return json.loads((out / "report.json").read_text(encoding="utf-8")), out


def test_ingest_filters(tmp_path):
    good = {"domain": "GST", "prompt": "Zephyr Traders in Indore sells machine parts to a Pune firm for Rs 91,000. Which tax?",
            "completion": LONG, "type": "gst_pos", "confidence": "high"}
    rows = [good,
            {**good, "prompt": "Another unique prompt about a cinema in Mysuru", "confidence": "check"},
            {**good, "prompt": "Third unique prompt about a bakery in Nashik", "completion": "Yes."},
            {**good, "prompt": "Fourth unique prompt about interest", "completion": LONG + " Interest under 50(3) is 24% a year."},
            dict(good)]                                             # exact repeat
    note = {"domain": "GST", "topic": "x", "note": "y", "citation": "s 1", "effective_from": "always", "confidence": "high"}
    rep, out = run_ingest(tmp_path, [note], rows)
    reasons = rep["rejected_by_reason"]
    assert rep["accepted_training_rows"] == 1 and rep["notes"] == 1
    assert reasons["marked check"] == 1 and reasons["answer too short"] == 1 and reasons["repeated prompt"] == 1
    assert reasons["old 24% for Section 50(3)"] == 1 and reasons["not valid JSON"] == 1


def test_ingest_rejects_rows_that_repeat_an_earlier_batch(tmp_path):
    import os
    prior = tmp_path / "prior"
    prior.mkdir()
    old = {"domain": "GST", "prompt": "Zephyr Traders in Indore sells machine parts to a Pune firm for Rs 91,000. Which tax applies?",
           "completion": LONG, "type": "gst_pos", "confidence": "high"}
    (prior / "batch01_gst_pos.jsonl").write_text(json.dumps(old), encoding="utf-8")
    new = tmp_path / "new"
    new.mkdir()
    near = {**old, "prompt": "Zephyr Traders in Indore sells machine parts to a Pune firm for Rs 91,000. Which tax applies here?"}
    fresh = {**old, "prompt": "A bakery in Nashik ships cakes to a customer in Goa and bills Rs 3,200 with 5% GST. What is charged?"}
    (new / "batch10_inv_calc.jsonl").write_text(json.dumps(near) + "\n" + json.dumps(fresh), encoding="utf-8")
    out = tmp_path / "out"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "ingest_new_batches.py"), str(new), "--prior", str(prior)], check=True,
                   capture_output=True, env={**os.environ, "KINNOW_INGEST_OUT": str(out)})
    rep = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert rep["accepted_training_rows"] == 1 and rep["rejected_by_reason"] == {"too close to an earlier batch": 1}
