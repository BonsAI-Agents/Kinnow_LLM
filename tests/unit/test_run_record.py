"""The run record and run comparison used by the Kaggle jobs."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import run_record as rr  # noqa: E402


def write(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")


def make_eval(overall, gst, inv, pay, plain=None):
    golden = [{"category": "GST", "passed": True, "passed_plain": True},
              {"category": "GST", "passed": True, "passed_plain": False}] if plain else []
    return {"summary": {"overall": overall, "per_category": {"GST": gst, "INVOICE": inv, "PAYROLL": pay, "REFUSAL": 97.2},
                        "hindi_overall": 55.6, "multiturn_conversations_pass_pct": 15.0,
                        "multiturn_turns_pass_pct": 50.0, "false_refusal_rate_pct": 0.0, "latency_p50_ms": 6000,
                        "n_golden": 192, "problems": ["overall below target"]}, "golden": golden}


def test_build_record_collects_everything(tmp_path):
    root, work = tmp_path / "repo", tmp_path / "work"
    write(root / "data/v2_training/raw.jsonl", '{"a":1}\n{"a":2}\n{"a":3}\n')
    write(root / "data/v2_training/train.jsonl", '{"a":1}\n{"a":2}\n')
    write(root / "data/v2_training/val.jsonl", '{"a":3}\n')
    write(root / "data/v2_training/manifest.json", {"domains": {"GST": 2}, "generated_calc_rows": 312, "rows_held_for_verification": 15})
    write(root / "data/knowledge/kb.jsonl", '{"n":1}\n{"n":2}\n')
    write(root / "models/sft_v9/run_settings.json", {"seed": 7, "max_steps": 600, "best_eval_loss": 1.01})
    write(work / "v9_full.json", make_eval(57.8, 44.4, 50.0, 52.0, plain=True))
    write(work / "v9_fact_lookup.json", [{"id": "a", "answer_ok": True, "notes_ok": True},
                                         {"id": "b", "answer_ok": False, "notes_ok": True}])
    write(work / "v9_fact_nolookup.json", [{"id": "a", "answer_ok": False}, {"id": "b", "answer_ok": False}])
    rec = rr.build_record("v9", str(root), str(work), {"kind": "train and score", "seed": "7"}, started=None,
                          training_dir=str(root / "models/sft_v9"))
    assert rec["data"]["training_rows_total"] == 3 and rec["data"]["training_rows_val"] == 1
    assert rec["data"]["generated_calc_rows"] == 312 and rec["data"]["lookup_notes"] == 2
    assert rec["training"]["seed"] == 7 and rec["training"]["best_eval_loss"] == 1.01
    assert rec["eval"]["overall"] == 57.8 and rec["eval"]["per_category"]["GST"] == 44.4
    assert rec["eval"]["overall_without_sources_line"] == 50.0           # 1 of 2 passed without the line
    assert rec["fact_check_with_lookup"]["answers_ok"] == 1 and rec["fact_check_with_lookup"]["missed"] == ["b"]
    assert rec["fact_check_without_lookup"]["answers_ok"] == 0
    assert rec["job"]["seed"] == "7" and "commit" in rec["code"]
    path = rr.save_record(rec, str(work))
    assert path.name == "v9_record.json" and json.loads(path.read_text(encoding="utf-8"))["label"] == "v9"


def test_build_record_survives_missing_files(tmp_path):
    rec = rr.build_record("x", str(tmp_path / "none"), str(tmp_path / "none2"), {"kind": "score"})
    assert rec["eval"] is None and rec["training"] is None and rec["data"]["training_rows_total"] is None
    assert rec["fact_check_with_lookup"] is None


def test_compare_shows_runs_side_by_side_with_the_change(tmp_path):
    write(tmp_path / "v4_full.json", make_eval(50.0, 38.9, 38.5, 42.0))
    write(tmp_path / "v5_record.json", {"label": "v5", "eval": rr._eval_block(make_eval(57.8, 44.4, 50.0, 52.0, plain=True)),
                                        "fact_check_with_lookup": {"claims": 50, "answers_ok": 48},
                                        "fact_check_without_lookup": {"claims": 50, "answers_ok": 34},
                                        "code": {"commit": "abc1234"}, "data": {"training_rows_total": 2691}})
    out = rr.compare([tmp_path / "v4_full.json", tmp_path / "v5_record.json"])
    lines = out.splitlines()
    v4 = next(l for l in lines if l.startswith("v4"))
    v5 = next(l for l in lines if l.startswith("v5"))
    assert "50.0" in v4 and "+" not in v4.split()[2]                     # the first run has no change
    assert "57.8" in v5 and "+7.8" in v5 and "48/50" in v5 and "34/50" in v5 and "abc1234" in v5 and "2691" in v5
    assert "chance" in out


def test_compare_skips_unreadable_files(tmp_path):
    write(tmp_path / "bad.json", "not json")
    assert rr.compare([tmp_path / "bad.json", tmp_path / "missing.json"]) == "no readable runs"
