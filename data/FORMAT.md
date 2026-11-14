# Training Data Format Guide

This document explains exactly how to write training examples for the Kinnow ERP LLM.
Share this with anyone contributing data before they start writing examples.

---

## File format

Each training example is one JSON object per line (JSONL). Save your examples in:
- `data/v1_training/train.jsonl` — main training set (~1,800 examples)
- `data/v1_training/val.jsonl` — validation set (~200 examples, held out during training)

You can submit one file and the split script will divide it automatically.

---

## Schema

```json
{
  "domain": "GST",
  "prompt": "What is the GST rate on restaurant services?",
  "completion": "Restaurant services fall under SAC code 996331 and attract GST at 5% (no ITC available). This applies to restaurants other than those in hotels with room tariff above ₹7,500, which attract 18% with ITC."
}
```

| Field | Type | Required | Values |
|-------|------|----------|--------|
| `domain` | string | Yes | `GST`, `PAYROLL`, `INVOICE`, `ERP` |
| `prompt` | string | Yes | The user's question, 10–300 characters |
| `completion` | string | Yes | The correct answer, 30–600 characters |

---

## Domain breakdown — target count

| Domain | Target | Topics to cover |
|--------|--------|-----------------|
| `GST` | ~500 | Rates by HSN/SAC, GSTR-1/3B/9 filing, ITC, e-invoicing, e-way bills, reverse charge, composition scheme, TCS/TDS under GST |
| `PAYROLL` | ~500 | PF/EPF, ESI, TDS on salary (Section 192), Form 16, Form 24Q, gratuity, bonus, CTC structure, professional tax |
| `INVOICE` | ~500 | GSTR-2A/2B reconciliation, vendor invoice matching, IRN generation, debit/credit notes, supplier mismatches |
| `ERP` | ~400 | Kinnow ERP features, ledger setup, journal entries, masters, MCA filings, advance tax, general compliance |

---

## What makes a GOOD example

**Specific, citable, actionable:**
```json
{
  "domain": "GST",
  "prompt": "What is the GST rate on software development services?",
  "completion": "Software development services fall under SAC code 998314 and attract GST at 18% (CGST 9% + SGST 9% for intra-state, or IGST 18% for inter-state). ITC is available to the recipient if registered."
}
```

**Multi-step process (use numbered steps):**
```json
{
  "domain": "GST",
  "prompt": "How do I file GSTR-3B?",
  "completion": "To file GSTR-3B:\n1. Log in to the GSTN portal (gstin.gov.in) with your GSTIN credentials.\n2. Go to Returns > GSTR-3B.\n3. Select the tax period and click Prepare Online.\n4. Enter outward supplies (Table 3.1), ITC claimed (Table 4), and tax payable.\n5. Pay any tax due via challan before filing.\n6. Submit and file using DSC or EVC.\nDeadline: 20th of the following month for monthly filers."
}
```

**Hindi question, Hindi answer:**
```json
{
  "domain": "PAYROLL",
  "prompt": "PF कितने प्रतिशत कटता है?",
  "completion": "कर्मचारी भविष्य निधि (EPF) में कर्मचारी की बेसिक सैलरी + DA का 12% काटा जाता है। नियोक्ता भी 12% का योगदान करता है, जिसमें से 8.33% EPS (पेंशन) और 3.67% EPF में जाता है। ₹15,000 से अधिक बेसिक पर PF अनिवार्य नहीं, लेकिन स्वैच्छिक योगदान किया जा सकता है।"
}
```

---

## What makes a BAD example — do not write these

**Vague, no specific numbers:**
```json
{
  "prompt": "What is GST?",
  "completion": "GST is a tax in India."
}
```
❌ Too short. No rates, no SAC codes, no actionable info.

---

**Speculative or uncertain language:**
```json
{
  "prompt": "What is the GST rate on ice cream?",
  "completion": "I think ice cream might be taxed at 18%, but you should check."
}
```
❌ Never say "I think" or "might be". If you are unsure, write the correct answer or skip the example.

---

**Off-topic (do not include):**
```json
{
  "prompt": "What is the weather in Delhi?",
  "completion": "I cannot answer that."
}
```
❌ Do not include off-topic examples. The guardrail system handles these; training data should contain only ERP content.

---

**Answer too long or padded:**
```json
{
  "prompt": "What is the due date for GSTR-1?",
  "completion": "Great question! GSTR-1 is a very important return that all GST-registered taxpayers need to file. It is a monthly or quarterly return depending on your turnover. The due date is the 11th of the following month for monthly filers and the 13th of the month following the quarter for quarterly filers under QRMP. I hope this helps and please feel free to ask more questions!"
}
```
❌ Remove filler. Answer should be direct: "GSTR-1 is due by the 11th of the following month (monthly filers with turnover > ₹5 crore) or 13th of the month following the quarter (QRMP filers with turnover ≤ ₹5 crore)."

---

## Checklist before submitting

- [ ] Every example has `domain`, `prompt`, and `completion`
- [ ] All GST rates are correct and cite the HSN/SAC code where applicable
- [ ] All PF/TDS percentages are correct and cite the relevant section
- [ ] No "I think", "might", "I believe", "probably" in any completion
- [ ] No examples about weather, sports, movies, or any non-ERP topic
- [ ] Hindi examples have correct Hindi completions (not English answers to Hindi questions)
- [ ] No duplicate prompts
- [ ] File saved as `.jsonl` — one JSON object per line, no trailing commas

---

## Quick validation

Run this after saving your file to check for errors:

```bash
cd kinnow-llm
python scripts/validate_data.py data/v1_training/your_file.jsonl
```

It will report: total examples, domain breakdown, any schema errors, duplicates, and language mismatches.
