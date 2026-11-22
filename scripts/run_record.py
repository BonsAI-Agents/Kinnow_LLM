"""
Run records and run comparison for the Kaggle jobs.

Every training or scoring job ends by writing ONE record file, /kaggle/working/<LABEL>_record.json, that holds
everything needed to understand its scores later: which code (git commit), how many training rows, the training
settings, the scoring switches, the scores, and the fact-check results. `compare()` then prints finished runs side
by side, with the change from each run to the next, so versions never have to be compared by hand.

    python scripts/run_record.py v4-new_record.json v5_record.json            # compare finished runs
    python scripts/run_record.py a_full.json b_record.json                     # a plain eval result file works too

Used by scripts/kaggle_train.py and scripts/kaggle_eval.py (both import it after cloning the repo) and by the
runbook notebook (section 8f).
"""

import json
import subprocess
import sys
import time
from pathlib import Path

TOPICS = ("GST", "INVOICE", "PAYROLL")


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def _count_lines(path) -> int | None:
    try:
        with open(path, encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
    except OSError:
        return None


def _git(root, *args) -> str:
    try:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception:
        return ""


def fact_summary(path) -> dict | None:
    """Counts from a fact-check result file (a list of per-claim rows)."""
    rows = _read_json(path)
    if not isinstance(rows, list) or not rows:
        return None
    out = {"claims": len(rows)}
    if "answer_ok" in rows[0]:
        out["answers_ok"] = sum(1 for r in rows if r.get("answer_ok"))
    if "notes_ok" in rows[0]:
        out["notes_ok"] = sum(1 for r in rows if r.get("notes_ok"))
    out["missed"] = [r["id"] for r in rows if "answer_ok" in r and not r["answer_ok"]]
    return out


def _eval_block(full_eval: dict) -> dict:
    s = full_eval.get("summary", {})
    golden = full_eval.get("golden", [])
    block = {
        "overall": s.get("overall"), "per_category": s.get("per_category", {}),
        "hindi_overall": s.get("hindi_overall"),
        "multiturn_conversations_pct": s.get("multiturn_conversations_pass_pct"),
        "multiturn_turns_pct": s.get("multiturn_turns_pass_pct"),
        "false_refusal_rate_pct": s.get("false_refusal_rate_pct"),
        "latency_p50_ms": s.get("latency_p50_ms"), "n_golden": s.get("n_golden"),
        "targets_missed": s.get("problems", []),
    }
    if golden and "passed_plain" in golden[0]:        # the run also scored every answer without the Sources line
        n = len(golden)
        block["overall_without_sources_line"] = round(100 * sum(1 for g in golden if g["passed_plain"]) / n, 1)
        cats = {}
        for g in golden:
            cats.setdefault(g["category"], []).append(1 if g["passed_plain"] else 0)
        block["per_category_without_sources_line"] = {c: round(100 * sum(v) / len(v), 1) for c, v in cats.items()}
    return block


def build_record(label: str, root: str, working: str, job: dict, started: float | None = None,
                 training_dir: str | None = None) -> dict:
    """The record for one finished job. `job` holds the job's own settings (version, adapter, flags, ...)."""
    root_p, work = Path(root), Path(working)
    data = {
        "training_rows_total": _count_lines(root_p / "data/v2_training/raw.jsonl"),
        "training_rows_train": _count_lines(root_p / "data/v2_training/train.jsonl"),
        "training_rows_val": _count_lines(root_p / "data/v2_training/val.jsonl"),
        "lookup_notes": _count_lines(root_p / "data/knowledge/kb.jsonl"),
    }
    manifest = _read_json(root_p / "data/v2_training/manifest.json")
    if manifest:
        data["rows_by_topic"] = manifest.get("domains")
        data["generated_calc_rows"] = manifest.get("generated_calc_rows")
        data["rows_held_for_verification"] = manifest.get("rows_held_for_verification")
    training = None
    for d in filter(None, [training_dir]):
        training = _read_json(Path(d) / "run_settings.json") or training
    full = _read_json(work / f"{label}_full.json") or _read_json(root_p / "eval/results/full_eval.json") or {}
    record = {
        "label": label,
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "minutes": round((time.time() - started) / 60) if started else None,
        "code": {"commit": _git(root, "rev-parse", "--short", "HEAD"), "message": _git(root, "log", "-1", "--format=%s")},
        "job": job,
        "data": data,
        "training": training,
        "eval": _eval_block(full) if full else None,
        "fact_check_with_lookup": fact_summary(work / f"{label}_fact_lookup.json"),
        "fact_check_without_lookup": fact_summary(work / f"{label}_fact_nolookup.json"),
    }
    return record


def save_record(record: dict, working: str) -> Path:
    path = Path(working) / f"{record['label']}_record.json"
    path.write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
    return path


def load_run(path) -> dict | None:
    """One run in a common shape, from either a record file or a plain eval result file."""
    d = _read_json(path)
    if not d:
        return None
    if "eval" in d and "label" in d:                       # a record
        e = d["eval"] or {}
        return {"name": d["label"], "eval": e, "fact_lookup": d.get("fact_check_with_lookup"),
                "fact_nolookup": d.get("fact_check_without_lookup"), "commit": (d.get("code") or {}).get("commit"),
                "rows": (d.get("data") or {}).get("training_rows_total")}
    if "summary" in d:                                     # a plain eval result file
        return {"name": Path(path).stem.replace("_full", ""), "eval": _eval_block(d), "fact_lookup": None,
                "fact_nolookup": None, "commit": None, "rows": None}
    return None


def _fmt(v, suffix="") -> str:
    return "-" if v is None else f"{v}{suffix}"


def _fact(f, key) -> str:
    return "-" if not f or key not in f else f"{f[key]}/{f['claims']}"


def compare(paths) -> str:
    """A table of finished runs side by side. Each row shows its change in overall score from the row above."""
    runs = [r for r in (load_run(p) for p in paths) if r]
    if not runs:
        return "no readable runs"
    head = (f"{'run':<22}{'overall':>8}{'change':>8}{'GST':>7}{'invoice':>8}{'payroll':>8}{'refusal':>8}{'hindi':>7}"
            f"{'multi-turn':>11}{'no-src':>8}{'facts+look':>11}{'facts-look':>11}  commit  rows")
    lines = [head, "-" * len(head)]
    prev = None
    for r in runs:
        e = r["eval"]
        pc = e.get("per_category", {})
        overall = e.get("overall")
        change = "" if prev is None or overall is None else f"{overall - prev:+.1f}"
        lines.append(
            f"{r['name'][:21]:<22}{_fmt(overall):>8}{change:>8}{_fmt(pc.get('GST')):>7}{_fmt(pc.get('INVOICE')):>8}"
            f"{_fmt(pc.get('PAYROLL')):>8}{_fmt(pc.get('REFUSAL')):>8}{_fmt(e.get('hindi_overall')):>7}"
            f"{_fmt(e.get('multiturn_conversations_pct'), '%'):>11}{_fmt(e.get('overall_without_sources_line')):>8}"
            f"{_fact(r['fact_lookup'], 'answers_ok'):>11}{_fact(r['fact_nolookup'], 'answers_ok'):>11}  "
            f"{(r['commit'] or '-'):<7} {_fmt(r['rows'])}")
        if overall is not None:
            prev = overall
    lines.append("")
    lines.append("overall/GST/invoice/payroll/refusal/hindi in percent; no-src = overall without the Sources line; "
                 "facts = Tejas's 50 claims answered right (with / without the lookup).")
    lines.append("With about 50 questions per topic one question is about 2 points: treat changes of a few points as chance.")
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    print(compare(sys.argv[1:]))
