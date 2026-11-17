# Kinnow ERP LLM: dataset format and sample

This folder shows exactly what we need for the Kinnow ERP assistant (GST, payroll, invoice matching, ERP operations; English and Hindi). Please send the real dataset in the same shape as the two sample files.

| File | What it is |
|---|---|
| `sample_sft.jsonl` | 46 supervised fine-tuning (SFT) examples. This is the main dataset. |
| `sample_dpo_pairs.jsonl` | 12 preference pairs for the alignment step. Optional, send if you have them. |

## Format: JSONL (one JSON object per line)

JSONL, UTF-8, one example per line, no trailing commas, no wrapping `[ ]`.

Why JSONL for a medium-sized dataset (a few thousand rows): answers contain line breaks (numbered steps), commas, quotes and Hindi text, which break CSV; a single JSON array has to be loaded whole and one bad row breaks everything; JSONL can be appended to, diffed in git, and checked line by line. Our training code reads it directly.

If you prefer to work in Excel or Google Sheets, that is fine: send `.xlsx` or `.csv` with the three column names below and we will convert it. JSONL is still preferred.

### SFT row (`sample_sft.jsonl`)

```json
{"domain": "GST", "prompt": "What is the GST rate on software development services?", "completion": "Software development services fall under SAC code 998314 and attract GST at 18% ..."}
```

| Field | Required | Rule |
|---|---|---|
| `domain` | yes | exactly one of `GST`, `PAYROLL`, `INVOICE`, `ERP` |
| `prompt` | yes | the user's question, 10-300 characters |
| `completion` | yes | the correct answer, 30-600 characters; use `\n` for numbered steps |

Target volume (per `data/FORMAT.md`): about 2,000 examples, roughly 500 GST, 500 PAYROLL, 500 INVOICE and 400 ERP. One combined file is fine; we split train and validation ourselves.

### DPO row (`sample_dpo_pairs.jsonl`)

```json
{"prompt": "What is the EPF wage ceiling?", "chosen": "The EPFO statutory wage ceiling is ₹25,000 per month from 17 September 2026 (it was ₹15,000 earlier).", "rejected": "The EPF wage ceiling is ₹15,000 per month. Employees earning more than this can opt out of PF."}
```

Exactly three fields: `prompt`, `chosen` (the answer we want), `rejected` (a realistic bad answer to the same prompt). Good `rejected` answers look like real model mistakes: vague ("around", "usually"), pushing the question to a CA or the portal, wrong or outdated numbers, padding ("Great question!"), mixing in off-topic content, or refusing a valid ERP question.

## Rules for every completion

- Be specific and citable: exact rates, SAC/HSN codes, section numbers, due dates.
- Never hedge: no "I think", "maybe", "probably", "might be", "around", "usually". If you are unsure of the answer, skip the example.
- Be direct, with no filler or greetings.
- Hindi questions get Hindi answers, and English questions get English answers.
- ERP topics only: no weather, sports or similar. Refusals belong in the DPO file, not in SFT.
- No duplicate prompts.
- **State the date or period when a rule changed recently** (for example "FY 2025-26", "from 22 September 2025"). Several rules changed in 2025-26, so undated answers go stale.

## Check your file before sending

From the repo root:

```bash
python scripts/validate_data.py path/to/your_file.jsonl
```

It reports totals per domain, schema errors, duplicates, hedging words and language mismatches. The sample SFT file passes with 0 errors and 0 warnings.

## Please double-check these against official sources

The sample was researched on 17 November 2026, mostly from secondary sources (tax and legal advisory sites). Please confirm these against the official notifications before we rely on them:

| Topic | What the sample says | Confirm against |
|---|---|---|
| GST slabs | 5%, 18%, 40%; 12% and 28% removed from 22 Sep 2025 | CBIC rate notifications, 56th GST Council meeting |
| EPF wage ceiling | ₹25,000 from 17 Sep 2026 (was ₹15,000) | Ministry of Labour notification S.O. 5109(E) |
| ESI wage ceiling | ₹21,000 (₹25,000 for persons with disabilities), rates 0.75% / 3.25% | ESIC; a rise to ₹25,000-30,000 has been proposed |
| Income-tax Act 2025 | Salary TDS Section 392, Form 130, Form 138 from 1 Apr 2026 | Income-tax Act 2025 and Income-tax Rules 2026 |
| Statutory bonus | Eligibility up to ₹21,000, 8.33%-20%, notified Aug 2026 | Code on Wages notifications dated 25 Aug 2026 |
| Gratuity, fixed-term | 1 year for fixed-term employees | Code on Social Security |
| E-invoicing | ₹5 crore threshold; 30-day IRP limit at ₹10 crore and above | GST portal and CBIC notifications |

## Not covered by the sample

- **Kinnow-specific product questions** (how a feature works inside Kinnow ERP). The sample does not invent product behaviour. These need to come from the product team or product docs.
- **Refusal data.** The production plan describes a large `REFUSAL` set, but the current validator accepts only the four domains above. Until that is decided, send refusal pairs in the DPO file only.
