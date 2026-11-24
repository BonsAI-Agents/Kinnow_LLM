"""Assemble the checked training rows and lookup notes from Tejas's batches.

    python scripts/assemble_new_batches.py <folder with batch01..batch16 .jsonl>

Reads data/tejas/new_v3/verification/*_verdicts.json (one verdict per row or note: KEEP, FIX or DROP, written by the
research check) and data/tejas/new_v3/overrides.json (extra drops, and notes whose citation is cleared or set), then writes
to data/tejas/new_v3/:
    sft_rows.jsonl            clean training rows from batches 1-14 (rows marked "check" go through checked_rows_verified.jsonl)
    sft_rows_status.jsonl     per row id: checked by the research check or not
    kb_notes_verified.jsonl   knowledge notes (batch 15) that passed
    glossary.jsonl            glossary entries (batch 16), unchanged
    rejected.jsonl            every row left out, with the reason
Row ids look like b06r15 (batch 6, row 15); note ids like n15r33.
"""

import collections
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ingest_new_batches as ing  # noqa: E402

OUT = ROOT / "data" / "tejas" / "new_v3"


def batch_rows(folder: str, n: int) -> list[dict]:
    path = glob.glob(str(Path(folder) / f"batch{n:02d}_*.jsonl"))[0]
    return [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]


def load_verdicts() -> dict:
    ver = {}
    for f in sorted(glob.glob(str(OUT / "verification" / "*_verdicts.json"))):
        for v in json.load(open(f, encoding="utf-8")):
            ver.setdefault(v["id"], v)
    return ver


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    folder = sys.argv[1]
    ver = load_verdicts()
    over = json.load(open(OUT / "overrides.json", encoding="utf-8"))
    for rid, why in over["drop"].items():
        if rid in ver:
            ver[rid] = {**ver[rid], "verdict": "DROP", "reason": why + " | checker said: " + ver[rid].get("reason", "")}
        else:
            ver[rid] = {"id": rid, "verdict": "DROP", "reason": why}
    tests = ing.test_questions()
    seen = set()
    for p in ["data/tejas/kinnow_sft_500_v2.jsonl", "data/tejas/kinnow_sft_payroll_invoice_v2.jsonl", "data/v1_training/raw.jsonl"]:
        for line in open(ROOT / p, encoding="utf-8"):
            if line.strip():
                seen.add(ing.norm(json.loads(line)["prompt"]))
    prior: list = []
    out, rej, stat = [], [], collections.Counter()
    for n in range(1, 15):
        new_prior = []
        for i, r in enumerate(batch_rows(folder, n), 1):
            rid = f"b{n:02d}r{i:02d}"
            if r.get("confidence") == "check":
                stat["marked check (see checked_rows_verified)"] += 1
                continue
            v = ver.get(rid)
            if v and v["verdict"] == "DROP":
                rej.append({"id": rid, "reason": "checker: " + v["reason"][:240]})
                stat["dropped by the check"] += 1
                continue
            row = {"domain": r["domain"], "prompt": r["prompt"], "completion": r["completion"]}
            if v and v["verdict"] == "FIX":
                row["completion"] = v.get("corrected_completion") or row["completion"]
                row["prompt"] = v.get("corrected_prompt") or row["prompt"]
                stat["fixed by the check"] += 1
            why = ing.check_sft({**row, "confidence": "high"}, seen, tests, False, prior)
            if why:
                rej.append({"id": rid, "reason": why})
                stat[why] += 1
                continue
            seen.add(ing.norm(row["prompt"]))
            new_prior.append(ing.words(row["prompt"]))
            out.append({**row, "_id": rid, "_checked": bool(v)})
            stat["kept"] += 1
        if n <= 9:
            prior += new_prior
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "sft_rows.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for r in out:
            f.write(json.dumps({k: r[k] for k in ("domain", "prompt", "completion")}, ensure_ascii=False) + "\n")
    # Rows that went through the research check are used for training. The others are kept apart until they are checked.
    for name, flag in (("sft_rows_checked.jsonl", True), ("sft_rows_unchecked.jsonl", False)):
        with open(OUT / name, "w", encoding="utf-8", newline="\n") as f:
            for r in out:
                if r["_checked"] == flag:
                    f.write(json.dumps({k: r[k] for k in ("domain", "prompt", "completion")}, ensure_ascii=False) + "\n")
    with open(OUT / "sft_rows_status.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for r in out:
            f.write(json.dumps({"id": r["_id"], "checked": r["_checked"]}) + "\n")
    notes, kept_notes, dropped_notes = batch_rows(folder, 15), [], []
    for i, r in enumerate(notes, 1):
        rid = f"n15r{i:02d}"
        v = ver.get(rid)
        if v is None or v["verdict"] == "DROP":
            dropped_notes.append({"id": rid, "reason": (v or {}).get("reason", "not checked")[:240]})
            continue
        note, cite = r["note"], r["citation"]
        if v["verdict"] == "FIX":
            note = v.get("corrected_note") or note
            cite = v["corrected_citation"] if "corrected_citation" in v else cite
        if rid in over.get("clear_citation", []):
            cite = ""
        cite = over.get("set_citation", {}).get(rid, cite)
        kept_notes.append({"domain": r["domain"], "topic": r["topic"], "note": note, "citation": cite or "", "effective_from": r["effective_from"]})
    with open(OUT / "kb_notes_verified.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for r in kept_notes:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(OUT / "glossary.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for r in batch_rows(folder, 16):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(OUT / "rejected.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for r in rej + dropped_notes:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    checked = sum(r["_checked"] for r in out)
    print(json.dumps({"training_rows": len(out), "checked": checked, "unchecked": len(out) - checked, "notes_kept": len(kept_notes),
                      "notes_dropped": len(dropped_notes), "detail": dict(stat)}, indent=2))


if __name__ == "__main__":
    main()
