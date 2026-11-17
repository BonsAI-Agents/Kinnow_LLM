# Kinnow v1 SFT dataset

Generated 2026-11-17 against `kinnow-production-plan-v1.md`. **Not yet expert-reviewed** (see "Before you train").

## Files

| File | Rows | Use |
|---|---|---|
| `train.jsonl` | 1,737 | read by `training/sft_train.py` |
| `val.jsonl` | 190 | held out (stratified by domain) |
| `raw.jsonl` | 1,927 | combined, before the split |
| `edge_case_manifest.jsonl` | 1,927 | domain, topic tag and prompt per row, for coverage review (not used in training) |

Schema: `{"domain", "prompt", "completion"}` as read by `training/sft_train.py` (the script adds the production system prompt at training time). All files pass `python scripts/validate_data.py`.

## Composition (train + val = 1,927)

| Domain | Rows | Plan v1 minimum |
|---|---|---|
| GST | 606 | 600 |
| PAYROLL | 392 | 400 |
| INVOICE | 384 | 400 |
| REFUSAL | 429 | 400 |
| ERP | 116 | 100 |

About 260 rows are Hindi (Devanagari prompt and answer). Every answer is 600 characters or fewer, and the longest training example is 803 tokens including the system prompt (limit in the script: 1,024).

## Edge cases covered

- **GST:** composition edge cases, reverse charge (GTA, advocates, imports, unregistered vendors), place of supply and intra vs inter-state, time of supply on advances, exports and LUT, e-invoice and e-way bill mechanics, ITC (Sections 16/17/18, Rules 37/42/43/37A, blocked credits), interest and late fees, registration thresholds, refunds, the post-22-Sep-2025 two-slab structure.
- **Payroll:** PF with the 17-Sep-2026 wage-ceiling change, ESI ceiling edge cases, gratuity (rounding, death, fixed-term), bonus, leave encashment, new vs old regime worked tax computations (FY 2025-26), HRA/LTA, mid-year joiners, arrears (Section 89(1)), Section 192 to 392 and Form 16 to 130 transition.
- **Invoice matching:** GSTR-2A vs 2B, mismatch types and fixes, credit and debit notes, advances, partial payments, returns, Rule 37 reversal, MSME 45-day rule, TDS interplay, three-way matching.
- **Refusal:** the plan's 11 out-of-scope categories (section 21g) plus subtle cases; jailbreak and role-change attempts, including the multi-turn "you've been so helpful" pivot; clarify-on-ambiguity; "verify with a CA" for unknowable questions; mixed ERP + off-topic messages; 50 false-refusal guards (legitimate questions that contain off-topic-looking words).

## Decisions taken (change if you disagree)

1. **Refusal wording follows plan section 21d (one exact string)**, not the 12 variants in section 5g. Canonical strings are in the generation brief; every refusal row uses one of them exactly.
2. **A `REFUSAL` domain was added** to `scripts/validate_data.py` (the plan requires about 400 refusal rows; the validator previously rejected the domain).
3. **Mixed messages** (ERP question plus off-topic question) answer the ERP part, then add one fixed sentence declining the rest. The plan does not specify this behaviour.
4. **No Kinnow product-specific answers.** There are no product docs, so ERP rows are general accounting and compliance.
5. Seven rows citing "Section 192" carry no "1961 Act" label because adding it would exceed 600 characters.

## Before you train

- **These facts came from the generating model plus secondary sources.** Have a CA or payroll expert review at least the items listed in `data/sample_for_tejas/README_FOR_TEJAS.md` (EPF ceiling, Income-tax Act 2025 renumbering, ESI ceiling, bonus ceiling, GST slabs) and a random sample of about 100 rows per domain. A wrong rate in training data becomes a confident wrong answer in production.
- **Not included:** multi-turn, Hindi and golden eval sets (plan 19f, 19g, 6d; they must never overlap this training data), and DPO pairs. The plan builds DPO pairs from the SFT model's real failures after the first training run; `data/sample_for_tejas/sample_dpo_pairs.jsonl` shows the format.
- Training now uses the production system prompt (`training/sft_train.py` was changed to prepend `PRODUCTION_SYSTEM_PROMPT`), matching what the server sends.
