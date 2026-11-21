"""
Build data/v2_training/raw.jsonl: Tejas's 500 rows plus our v1 rows that do not conflict with them.

Rules:
  1. Tejas's rows come first and win: a v1 row with the same prompt is dropped.
  2. All v1 REFUSAL rows are kept (Tejas's SFT file has none), except any that state the old tax forms.
  3. v1 rows that rely on the superseded income-tax regime (Income-tax Act 1961, Form 16/16A, 24Q/26Q/27Q,
     26AS, old TDS section numbers) are NOT used. They go to dropped_old_regime.jsonl with the reason, so a CA
     can rewrite and re-add them. Tejas's law (Income-tax Act 2025, Forms 130/138, Sections 392/393) wins.

data/v1_training/raw.jsonl is left alone: CI builds the guardrail centroids from it.

Usage:
    python scripts/merge_tejas_data.py
    python scripts/split_data.py data/v2_training/raw.jsonl --val-ratio 0.1
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_calc_rows import generate as generate_calc_rows  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TEJAS_FILES = [ROOT / "data" / "tejas" / "kinnow_sft_500_v2.jsonl",             # 500 rows, Section 50(3) fixed to 18% (21 Nov 2026)
               ROOT / "data" / "tejas" / "kinnow_sft_payroll_invoice_v2.jsonl"]  # 89 worked examples and traps
V1 = ROOT / "data" / "v1_training" / "raw.jsonl"
OUT = ROOT / "data" / "v2_training"

# Why a v1 row is not used. Each pattern is a marker of the pre-2026 income-tax regime.
OLD_REGIME = {
    "Income-tax Act 1961": r"Income[- ]tax Act,? 1961|IT Act,? 1961",
    "Form 16 / 16A": r"\bForm 16A?\b",
    "Form 24Q/26Q/27Q/27EQ": r"\b(24Q|26Q|27Q|27EQ)\b",
    "Form 26AS": r"26AS",
    "old TDS section numbers": r"\b(Section|Sec\.?|u/s)\s*(192|193|194[A-Z]{0,2}|195|206[A-Z]{0,3})\b",
    "old TDS section (bare)": r"\b194[A-Z]{1,2}\b|\b194\b|\b206(AA|AB|C)\b",
}


# Rows held out of training until a CA confirms them (data/tejas_review/VERIFICATION_REPORT.md).
# Applies to our own v1 rows only: they state 24% for Section 50(3), which the owner replaced with Tejas's 18%
# (21 Nov 2026). They are listed in held_for_verification.jsonl so a CA can rewrite and re-add them.
V1_HOLD: dict[str, str] = {
    "v1 row states 24% for Section 50(3) (owner chose 18%)":
        r'(?i)50\(3\)|24% (p\.a\.?|per annum|a year|interest)|interest at 24%|24% interest|24% (p\.a|per annum) ?(for|on)|24% वार्षिक',
}
HOLD: dict[str, str] = {}

# Rows used in training on the owner's decision (21 Nov 2026) although no CA has confirmed them yet.
# Section 50(3): 18% a year on ITC wrongly availed and utilised (Notification 14/2022-CT per Tejas; the Act's 24% is the ceiling).
# They are listed in assumed_pending_ca.jsonl so a CA can check them later; fix and retrain if one disagrees.
ASSUMED_CONFIRMED = {
    "Section 50(3) interest rate 18% (assumed confirmed, CA pending)":
        r'(?i)50\(3\)',
}

# Tejas rows rewritten because the law moved on: prompt -> new completion.
# Meal vouchers: Income-tax Rules 2026 (Rule 15(5)(a)) raised Rs 50 to Rs 200 per meal from tax year 2026-27.
# The regime question is left out on purpose: sources disagree and the CA has not confirmed it.
OVERRIDES = {
    "Are meal vouchers taxable for employees?":
        "Employer-provided meals, or vouchers usable only at eating places, are exempt up to Rs 200 per meal "
        "during working hours from tax year 2026-27, under Rule 15(5)(a) of the Income-tax Rules, 2026. "
        "Up to FY 2025-26 the limit was Rs 50 per meal. A cash meal allowance is added to salary and fully taxed, "
        "as is any value above the limit.",
}


def load(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def old_regime_reasons(row: dict) -> list[str]:
    text = row["prompt"] + " " + row["completion"]
    return [name for name, pat in OLD_REGIME.items() if re.search(pat, text)]


def main():
    tejas = [r for f in TEJAS_FILES for r in load(f)]
    v1 = load(V1)
    held, assumed = [], []

    def assumed_reasons(row: dict) -> list[str]:
        text = row["prompt"] + " " + row["completion"]
        return [name for name, pat in ASSUMED_CONFIRMED.items() if re.search(pat, text)]

    def hold_reasons(row: dict) -> list[str]:
        text = row["prompt"] + " " + row["completion"]
        return [name for name, pat in HOLD.items() if re.search(pat, text)]

    rewritten = 0
    kept_tejas = []
    for r in tejas:
        if r["prompt"].strip() in OVERRIDES:
            r = {**r, "completion": OVERRIDES[r["prompt"].strip()]}
            rewritten += 1
        reasons = hold_reasons(r)
        if reasons:
            held.append({**r, "reason": reasons, "source": "tejas"})
        else:
            if assumed_reasons(r):
                assumed.append({**r, "reason": assumed_reasons(r), "source": "tejas"})
            kept_tejas.append(r)
    tejas_rows_in = len(tejas)
    tejas = kept_tejas
    seen = {norm(r["prompt"]) for r in tejas}
    kept, dropped, dup = [], [], 0
    v1_hold = {**HOLD, **V1_HOLD}
    for r in v1:
        reasons = [name for name, pat in v1_hold.items() if re.search(pat, r["prompt"] + " " + r["completion"])]
        if reasons:
            held.append({**r, "reason": reasons, "source": "v1"})
            continue
        if norm(r["prompt"]) in seen:
            dup += 1
            continue
        reasons = old_regime_reasons(r)
        if reasons:
            dropped.append({**r, "reason": reasons})
            continue
        seen.add(norm(r["prompt"]))
        if assumed_reasons(r):
            assumed.append({**r, "reason": assumed_reasons(r), "source": "v1"})
        kept.append(r)

    # Calculation rows computed by scripts/generate_calc_rows.py (fixed seed, so every build gives the same rows)
    seen_prompts = {norm(r["prompt"]) for r in tejas + kept}
    generated = [{"domain": g["domain"], "prompt": g["prompt"], "completion": g["completion"]}
                 for g in generate_calc_rows(42) if norm(g["prompt"]) not in seen_prompts]
    merged = tejas + kept + generated
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "raw.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for r in merged:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(OUT / "dropped_old_regime.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for r in dropped:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    with open(OUT / "held_for_verification.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for r in held:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    with open(OUT / "assumed_pending_ca.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for r in assumed:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    manifest = {
        "tejas_rows_received": tejas_rows_in,
        "tejas_rows": len(tejas),
        "tejas_rows_rewritten": rewritten,
        "rows_held_for_verification": len(held),
        "rows_assumed_confirmed_pending_ca": len(assumed),
        "held_by_source": dict(Counter(r["source"] for r in held)),
        "v1_rows_kept": len(kept),
        "v1_rows_dropped_old_regime": len(dropped),
        "v1_rows_dropped_same_prompt_as_tejas": dup,
        "generated_calc_rows": len(generated),
        "total": len(merged),
        "domains": dict(Counter(r["domain"] for r in merged)),
        "dropped_by_domain": dict(Counter(r["domain"] for r in dropped)),
        "dropped_by_reason": dict(Counter(x for r in dropped for x in r["reason"])),
    }
    with open(OUT / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
