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
# Newer batches from Tejas (24 Nov 2026 onward), checked by scripts/ingest_new_batches.py and by hand. Each file is used only if it
# exists, so the build works before they are added. Rows carry extra fields (type, confidence, sources); only the three
# training fields are kept.
NEW_FILES = [ROOT / "data" / "tejas" / "new_v3" / "sft_rows.jsonl",               # clean rows from batches 1-9 and later
             ROOT / "data" / "tejas" / "new_v3" / "checked_rows_verified.jsonl"]  # rows flagged "check" that were verified or fixed
GLOSSARY_FILE = ROOT / "data" / "tejas" / "new_v3" / "glossary.jsonl"    # {term, full, meaning, also_written_as}
V1 = ROOT / "data" / "v1_training" / "raw.jsonl"
OUT = ROOT / "data" / "v2_training"

_PAYROLL_TERMS = {"epf", "eps", "esi", "pt", "lwf", "hra", "lta", "ctc", "pan", "tan", "da", "fnf", "lop", "87a", "80c", "80d",
                  "form 130", "form 131", "form 132", "form 138", "form 140", "form 141", "form 144", "form 122", "form 123",
                  "form 124", "form 39", "form 16", "form 12b", "24q", "26as", "ais", "vetan", "tds", "tcs"}
_INVOICE_TERMS = {"hsn", "sac", "irn", "lut", "e-way bill", "eway bill", "challan", "bill", "gstin"}


def glossary_rows(entries: list[dict]) -> list[dict]:
    """Turn glossary entries into short training rows: 'What does RCM mean?' -> 'RCM stands for ...'.
    Teaches the model to spell terms out (our scorer looks for words such as "reverse charge")."""
    rows = []
    for e in entries:
        term, full, meaning = (e.get("term") or "").strip(), (e.get("full") or "").strip(), (e.get("meaning") or "").strip()
        if not term or not full or not meaning:
            continue
        key = term.lower()
        domain = "PAYROLL" if key in _PAYROLL_TERMS else ("INVOICE" if key in _INVOICE_TERMS else "GST")
        also = [a for a in (e.get("also_written_as") or []) if a and a.lower() != key]
        tail = f" It is also written as {', '.join(also)}." if also else ""
        rows.append({"domain": domain, "prompt": f"What does {term} mean?",
                     "completion": f"{term} stands for {full}. {meaning}{tail}"})
    return rows

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
# Post-supply discounts: until 31 Oct 2026 Section 15(3)(b) needed an agreement before the supply and a link to invoices.
# Finance Act 2026 sections 153-155 (Notification 03/2026-CT) removed those conditions from 1 Nov 2026, and whether the
# recipient must still reverse ITC is reported differently by different sources. These rows state the old conditions as the
# test, so they are held until the amended rule is confirmed and the answers are rewritten with the date. Each pattern is the
# start of the question, so the list is exact.
HOLD: dict[str, str] = {
    "states the pre-1 Nov 2026 post-supply discount conditions as current law":
        r"^(How is GST computed on discounts\?"
        r"|What is a credit note for a post-sale discount\?"
        r"|Invoice of Rs 2,00,000 at 18%\. Contract gave a 3% volume discount"
        r"|We gave a Rs 10,000 festive discount by credit note a month later"
        r"|Supplier gave a post-sale discount through a credit note of Rs 11,800"
        r"|Credit note and ITC: supplier issued credit note for 10% post-sale"
        r"|Customer wants a discount of 3% on an October 2026 invoice"
        r"|Annual volume rebate agreed in contract"
        r"|Price reduced by agreement 6 months after supply)",
    # New batches (24 Nov 2026): these two apply the 1 Nov 2026 rule by SUPPLY date, but which date decides is unsettled.
    "applies the 1 Nov 2026 post-supply discount rule by supply date (which date decides is unsettled)":
        r"^(Supply on 6 November 2026 of Rs 4,00,000 at 18%"
        r"|User: A wholesaler in Cuttack sold goods of Rs 9,20,000 on 10 November 2026)",
}

# Rows used in training before a CA has confirmed them, listed in assumed_pending_ca.jsonl so a CA can check them
# later. Empty now: Section 50(3) interest at 18% a year on ITC wrongly availed and utilised (Notification 14/2022-CT
# per Tejas; the Act's 24% is the ceiling) was chosen by the owner on 21 Nov 2026 and, per the owner, approved by
# the CA on 22 Nov 2026 (see data/tejas_review/DECISIONS.md). Add a pattern here for any new unconfirmed point.
ASSUMED_CONFIRMED: dict[str, str] = {}

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
    new_rows = [{k: r[k] for k in ("domain", "prompt", "completion")} for f in NEW_FILES if f.exists() for r in load(f)]
    tejas += new_rows
    gloss = glossary_rows(load(GLOSSARY_FILE)) if GLOSSARY_FILE.exists() else []
    tejas += gloss
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
        "new_batch_rows_included": len(new_rows),
        "glossary_rows_included": len(gloss),
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
