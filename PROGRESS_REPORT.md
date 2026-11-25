# Kinnow ERP LLM: Progress Report

**From v1 to v6q3 (Qwen3-8B) · status as of 25 November 2026**

This file is a dated record of what was built, what data was used, what each version scored, what was learned, and what is open.
For how the code works, read [`ARCHITECTURE.md`](ARCHITECTURE.md). For the plan and targets, read [`kinnow-production-plan-v1.md`](kinnow-production-plan-v1.md).
Disputed legal points and who settled them are logged in [`data/tejas_review/DECISIONS.md`](data/tejas_review/DECISIONS.md).

## Contents
1. [Project and goal](#1-project-and-goal)
2. [Where we stand now](#2-where-we-stand-now)
3. [Version by version](#3-version-by-version)
4. [Training data used](#4-training-data-used)
5. [Features built](#5-features-built)
6. [Testing and measurement tools](#6-testing-and-measurement-tools)
7. [Data checking and research](#7-data-checking-and-research)
8. [Legal points researched](#8-legal-points-researched)
9. [Infrastructure](#9-infrastructure)
10. [Problems and lessons](#10-problems-and-lessons)
11. [Pending and blocked](#11-pending-and-blocked)
12. [What to do next, in order](#12-what-to-do-next-in-order)
13. [The honest picture](#13-the-honest-picture)

---

## 1. Project and goal
- **What it is:** an ERP assistant for GST, Payroll and Invoicing, built on Qwen2.5-7B-Instruct (v1 to v5) and now Qwen3-8B (v6q3), fine-tuned with QLoRA, behind a four-layer safety gateway (FastAPI).
- **Training setup:** QLoRA with r=64 and alpha=128, 4-bit (nf4), fp16 on T4, completion-only loss, 600 steps, a check every 100 steps.
- **Targets:** 78% overall, GST 65%, Payroll 82%, Invoice 86%, wrong refusals under 3%.
- **Test set:** 192 English questions, plus 27 Hindi and 20 multi-turn conversations.
- **Fact check:** 50 facts from Tejas's checklist, scored with and without the lookup.
- **Where it runs:** Kaggle (2 × T4). Code is on GitHub (`BonsAI-Agents/Kinnow_LLM`, currently public).

## 2. Where we stand now

| Measure | Target | v5 (Qwen2.5-7B) | Now: v6q3 (Qwen3-8B) |
|---|---|---|---|
| Overall | 78% | 62.0% | **66.7%** (11 points short) |
| GST | 65% | 50.0% | **61.1%** |
| Invoice | 86% | 53.8% | **57.7%** |
| Payroll | 82% | 58.0% | **62.0%** |
| Wrong refusals | under 3% | 0.0% | 0.0% (0 of 156) |
| Hindi | n/a | 55.6% | **70.4%** |
| Multi-turn (conversations / turns) | n/a | 20% / 51.7% | **25% / 60%** |
| Fact check, with lookup | n/a | 48 of 50 | 47 of 50 |
| Fact check, without lookup | n/a | 34 of 50 | **37 of 50** |

- **Code:** on `main`, pushed, commit `5d45cac`.
- **Calculators added after v6q3:** six new or fixed calculators are pushed but have not been scored in any run yet (see section 3).
- **Kaggle:** session off, about 1 hour of the weekly quota left.
- **Latest run (v6q3):** the first run on Qwen3-8B. It is clearly better than v5 and is the best result so far.
- **Model files:** the Qwen3-8B adapter should be in the private Hugging Face repo `KaraPatelDev/kinnow-v6q3-qwen3-sft-adapter` (not yet confirmed). The Kaggle copy and result files were wiped when the session was powered off.

## 3. Version by version

| Version | What changed | Score |
|---|---|---|
| Untrained | Plain Qwen2.5-7B, no training | 22.9% |
| v1 | First training run, answers never stopped (bug) | not recorded |
| v2 | Bug fixed, Tejas's 500 rows | 41.7%, 52.1% with lookup |
| v3 | Lookup notes plus 312 computed rows | 54.7% with lookup |
| v4 | Tejas's corrected 500 rows plus 89 new rows | 50.0% with lookup |
| v4 + features | Better lookup, calculators, Sources line (no retraining) | 57.8% |
| v4 + calculators | Five more calculators (no retraining) | 59.9% |
| v4 + wording fixes | Calculator wording fixes (no retraining) | 61.5% |
| v5 | New training run on 2,909 rows (seed 7) | 62.0% |
| v6q3 | Same data and settings as v5, base model changed to Qwen3-8B | **66.7%** |

### Untrained model
- Plain Qwen2.5-7B with no extra training.
- Score: **22.9%**.

### v1: first training run
- **Data:** our own reviewed rows (`data/v1_training`).
- **Result:** unusable. The model never stopped writing.
- **Cause:** the padding marker was the same as the end-of-answer marker.
- **Fix (in v2):** a different padding marker, plus a safety check that stops training if the end marker isn't learned.

### v2: bug fix plus Tejas's 500 rows
- **Data:** Tejas's 500 reviewed rows plus our own v1 rows that don't conflict.
- **Cleanup:** rows built on the old tax law (1961 Act, Form 16, 24Q) were set aside.
- **Score:** 41.7%, or 52.1% with the lookup.
- **Lesson:** training added about 19 points, and the lookup about 10 more.

### v3: lookup notes plus 312 computed rows
- **Data added:** 312 rows with figures computed by a program (gratuity, PF, ESI, tax, interest, Rule 37, e-invoice limits).
- **Score:** 54.7% with the lookup.
- **Lookup size test:** 6 notes scored lower than 4, so the lookup stays at 4.
- **Weak spot:** Payroll did not improve, because the test questions are multi-condition cases.

### v4: Tejas's corrected data
- **Data:** 500 corrected rows plus 89 new Payroll and Invoice worked examples. Section 50(3) interest set to 18%. Training set: 2,691 rows.
- **Score:** 50.0%, within chance of v3.
- **Lesson:** adding 589 rows did not measurably help.

### v4 plus answer features (no retraining)
- Better lookup plus calculators: 52.6%.
- Plus the Sources line: **57.8%**.
- The lenient scorer on the same answers gives about 60%.

### v4 plus extended calculators (no retraining)
- Five new calculators (late fee, Rule 37, old-regime tax, HRA, marginal relief): **59.9%**.
- Calculator wording fixes (section reference, slab breakdown, EPF split): **61.5%**.

### v5: retrained on the new data
- **Data:** 2,909 rows (v4's 2,691 plus 100 checked, 47 verified and 80 glossary rows, minus rows held back).
- **Settings:** seed 7, 600 steps.
- **Score:** **62.0%**, which is no real change: 61.5 to 62.0 is inside the noise.
- **Topic movement:** GST +1.9, Invoice +3.8, Payroll −4.0, in both directions and 2 to 4 questions each.

### v6q3: Qwen3-8B (25 Nov 2026)
- **What changed:** only the base model (Qwen3-8B instead of Qwen2.5-7B). Same 2,909 rows, seed, 600 steps and scoring settings as v5, so the comparison is fair.
- **Code changes needed:** `transformers` 4.51.3 (Qwen3 needs 4.51 or later), the trainer option `eval_strategy`, and a small fix that moves a loss count onto the right GPU when the model is split across two T4s.
- **Training:** about 5 hours for 600 steps (about 22 s a step). Held-back error fell at every check: 1.199, 1.057, 0.952, 0.906 (v5 finished at 0.995).
- **Score:** **66.7% overall** (v5: 62.0%). GST 61.1, Payroll 62.0, Invoice 57.7. Refusal-type questions 94.4%. Typical answer took about 9 s, 95% under 18 s.
- **Other results:** Hindi 70.4% (v5: 55.6%). Multi-turn 25% of conversations and 60% of turns (v5: 20% and 51.7%). Wrong refusals 0 of 156.
- **Fact check:** 47 of 50 with the lookup (missed hotel rate, rebate 87A, meal voucher) and 37 of 50 without (v5: 48 and 34).
- **Reading it:** the gain is 4.7 points (about 9 of 192 questions), larger than the roughly 3-point run-to-run noise, but it is one run. GST and Hindi moved most.
- **Targets:** none of the topic or overall targets are met. GST is 4 points short, Payroll 20 short, Invoice 28 short.

**v6q3: what is not yet confirmed**
- **The adapter's location.** It should be in the private Hugging Face repo `KaraPatelDev/kinnow-v6q3-qwen3-sft-adapter` (training reported TRAIN DONE). It was not checked, and the Kaggle copy was wiped when the session was powered off.
- **Serving.** The server loads whatever `MODEL_NAME` points to in vLLM, and already sends `enable_thinking: false`. Serving Qwen3-8B plus this adapter has not been tested.
- **Run-to-run noise.** There is one run. A second seed would show how much of the 4.7-point gain is chance.
- **Untrained Qwen3-8B baseline.** Skipped to save quota, so how much training added on top of the model is unknown.
- **Result files.** The scores above were read from the run before the session was powered off. The full answer files are gone, so the per-question failures of v6q3 cannot be listed.

### After v6q3: new calculators (25 Nov 2026, pushed as `5d45cac`)
The server uses these at answer time, so no retraining is needed, but they only reach the live product after the next deploy. They are not in any scored run yet.
- **ESI fix:** reads "23k gross" (amount before the word), applies the Rs 21,000 ceiling, and stays silent if a disability is mentioned.
- **TDS on a professional fee:** 10% on the fee excluding GST when GST is shown separately (Circular 23/2017). Example: fee Rs 1,35,000 gives TDS Rs 13,500, pay Rs 1,45,800.
- **Extra tax from a bonus:** tax with the bonus minus tax without it, new regime FY 2025-26. Example: Rs 2L bonus on Rs 18L salary gives Rs 41,600.
- **Previous employer (Form 12B):** adds the earlier salary, applies the standard deduction once. Example: taxable Rs 11,25,000, tax nil.
- **Invoice deadline (Rule 47):** 30 days, or 45 for banks, NBFCs and insurers.
- **Time of supply for services (Section 13(2)):** which date decides and which return the tax goes in.
- **Safety:** each stays silent when a date or amount is missing, for tax year 2026-27 (rules unsettled), or when an amount looks wrong.
- **Checks:** 18 new tests, written first from the failing questions. All 192 golden questions were compared before and after: exactly the 7 targeted ones change, none of the other 185 do. Reworded questions with different numbers were also tested, which found and fixed two narrow triggers.
- **A caution on the score:** the calculators were built from the same questions that sit in the golden test set, so any gain there will look bigger than the real gain. Tejas's review of real answers is the better measure.
- **Not covered:** the mistakes that need knowledge, not arithmetic (composite AC rate, GSTR-1A, the SUV 40% slab, ITC timing, Section 192/24Q, final-settlement TDS). They need verified lookup notes.

## 4. Training data used
- **Our own v1 rows:** the original base set, kept unless they conflicted with Tejas's.
- **Tejas's 500 rows:** the core reviewed set. Section 50(3) corrected to 18%.
- **Tejas's 89 worked examples:** 44 Payroll and 45 Invoice, including traps (amounts Rs 1 over a limit, mid-year joiners, late credit notes).
- **312 computed calculation rows:** made by `scripts/generate_calc_rows.py`, so the arithmetic cannot be wrong.
- **Refusal rows:** examples of politely refusing off-topic or improper requests.
- **Old-law rows:** set aside, held for rewriting.
- **Held rows:** rows held for verification, including 9 that state the pre-1 Nov 2026 discount rule.
- **Tejas's 16 new batches (24 Nov 2026):** 14 training batches, one batch of knowledge notes and one glossary batch.
- **Used from the 16 batches:**
  - 100 individually checked rows
  - 47 rows verified from the earlier "check" set
  - 80 glossary entries, turned into "What does RCM mean?" rows
  - 56 verified knowledge notes, for the lookup
- **Not used:** 311 unchecked rows, kept in a separate file (`sft_rows_unchecked.jsonl`). Set `KINNOW_INCLUDE_UNCHECKED=1` to add them.
- **Training set sizes:** v4 2,691 rows, v5 2,909 rows.

## 5. Features built
- **Four-layer safety gateway:** domain check, output validation, injection protection and more.
- **Rule lookup:** before answering, finds the 4 best-matching approved notes and shows them to the model.
- **Better lookup:** searches by words and by meaning, then merges the lists.
- **Sources line:** adds "Sources: Section 16(2)(aa), Rule 37", using only references found in the notes.
- **Calculators:** gratuity, EPF, ESI, new-regime tax, interest, GST late fee, Rule 37, old-regime tax, HRA and 87A marginal relief. Added on 25 Nov 2026: TDS on a professional fee excluding GST, extra tax from a bonus, previous-employer (Form 12B) full-year tax, the Rule 47 invoice deadline and the Section 13(2) time of supply, plus a fix so ESI reads "23k gross".
- **Calculator safety:** each has a strict trigger and stays silent when unsure. A misfire on non-salary tax questions was found and fixed.
- **Server wiring:** everything above plugs in through `AnswerSupport`. Each part can be switched off and falls back if anything fails.

## 6. Testing and measurement tools
- **Strict scorer:** an answer passes if it contains the required words.
- **Lenient scorer** (`eval/lenient.py`, `scripts/rescore.py`): short forms count as full names ("RCM" for "reverse charge").
- **Fact check:** 50 claims, with and without the lookup.
- **Run record** (`scripts/run_record.py`): one file per run with code version, data size, settings and all scores.
- **Compare table:** puts runs side by side.
- **Failure analysis:** sorted failures into wording-only, real mistakes and unclear.
- **Review materials for Tejas:** a 50-answer review sheet (answer key kept private) and a list of 28 likely mistakes.
- **Researched verdicts on the 28 mistakes** (`data/review/real_mistakes_researched.md`, local only): see section 7.

## 7. Data checking and research
- **Intake script** (`scripts/ingest_new_batches.py`): checks format, repeats, overlap with the test set, the old 24% rate and "check" rows.
- **Research check of 78 flagged rows:** 18 kept, 29 fixed, 31 dropped.
- **First sample of 58 rows:** 22% needed a fix or a drop.
- **Second sample of 100 rows:** 47% needed a fix or a drop (stricter standard).
- **Knowledge notes:** each checked, 56 kept.
- **Assembly script** (`scripts/assemble_new_batches.py`): builds the final files from the batches, the verdicts and the overrides.
- **Web research on the 28 likely model mistakes (25 Nov 2026):** four research agents checked seven each. Result: 19 model mistakes, 9 fine (only wording differed), 0 where our reference answer was wrong. Confidence: 16 high, 11 medium, 1 low.
- **How far to trust it:** every calculation was recomputed independently and matches (tax slabs, late-fee day counts, the Rule 37 reversal of Rs 55,350, the NBFC 45-day limit). The legal rules mostly rest on secondary sources (tax blogs, advisory sites), because few official pages could be opened in full. These verdicts are not a CA's or Tejas's judgement.
- **Where the 19 mistakes sit:** 5 already had calculators (late fees, Rule 37, marginal relief, old-regime tax); 7 more are now covered by the new calculators (ESI, 194J TDS, bonus, Form 12B, invoice deadline, two time-of-supply questions); the last 7 need verified lookup notes. The mistakes come from an older run (v4), so Qwen3-8B may already have fixed some.

## 8. Legal points researched
These come from web sources (tax blogs, advisory sites, law-firm updates), not from official texts. Full log: `data/tejas_review/DECISIONS.md`.
- **GTA:** 5% without credit or 18% with credit, no 12% option, from 22 Sep 2025.
- **Post-supply discounts:** the prior-agreement condition was removed from 1 Nov 2026. Which date decides is unsettled.
- **New income-tax forms:** 130, 131, 138, 140, 141, 144, 122, 123, 124. Form 39 replaces 10E from tax year 2026-27.
- **EPF wage ceiling:** Rs 25,000 from 17 Sep 2026.
- **Meal vouchers:** Rs 50, then Rs 200 per meal from tax year 2026-27. New-regime eligibility is disputed.
- **Maharashtra professional tax:** men's slabs confirmed. Women nil up to Rs 25,000, web-sourced only.
- **Section 50(3) interest:** set at 18% by the owner on web research. Web sources show 24% for Section 50(3), so the label may be wrong. This is the owner's decision, not a CA confirmation.

## 9. Infrastructure
- **Kaggle job scripts:** one for training and scoring, one for scoring only. Both run the fact check and write the run record.
- **Runbook notebook** (`notebooks/kinnow_kaggle_runbook.ipynb`): plain language, with a "what this does" box per cell.
- **Models:** adapters are stored in private Hugging Face repos.
- **Prompts for Tejas:** two data-generation prompts (`data/tejas_review/`).
- **Tests:** the last full run passed 358 unit tests. Two more were added afterwards, and they pass with the calculator and answer-support tests.
- **Qwen3-8B job:** the same Kaggle script trains it when `BASE=Qwen/Qwen3-8B` is set. It installs `transformers` 4.51.3 for that case and names the Hugging Face repo `kinnow-<version>-qwen3`, so the Qwen2.5 adapters are not touched.
- **Kaggle limits:** 30 GPU hours a week, a 12-hour session, shutdown after about 40 minutes without interaction. A 10-minute check kept the Qwen3 run alive. The Qwen3-8B run used about 5 hours of training plus about 1 hour 15 minutes of scoring and fact check.

## 10. Problems and lessons
- **v1 end-marker bug:** fixed.
- **Kaggle idle shutdown (40 minutes):** killed one run. A check every 10 minutes fixed it.
- **Wrong EPF ceiling in an early prompt to Tejas:** found and corrected.
- **Calculator misfire on non-salary questions:** fixed and tested.
- **Fact-check dip (48 to 46):** not noise, the same four facts were missed twice. v5 is back to 48.
- **More of the same data stopped helping:** several rounds moved the score under 3 points. A better base model (Qwen3-8B) moved it 4.7 points.
- **Qwen3-8B needed three fixes before it trained:** newer `transformers`, the `eval_strategy` option name, and a loss count on the wrong GPU. Each showed up only after about 10 minutes on the GPU, so a dry run does not catch them.
- **Typing into the Kaggle notebook is risky:** keystrokes sent while no cell is in edit mode act as notebook shortcuts and change cells. Check edit mode first.

## 11. Pending and blocked
- **Tejas:** the 50-answer review, his own verdicts on the 28 likely mistakes (web-research verdicts are in `data/review/real_mistakes_researched.md`: 19 model mistakes, 9 fine), and his spot-check count.
- **Open legal points:** treated as settled by web research (the owner's decision, not a CA statement), except the post-supply discount date test and meal-voucher regime eligibility, which stay unstated. See `DECISIONS.md`.
- **Bigger-model (14B) run:** approved, but it needs about 10–11 GPU hours and the weekly quota is nearly used.
- **Qwen3-8B adapter:** confirm it is in the private Hugging Face repo, and test serving it (base model plus adapter through vLLM).
- **Knowledge-type mistakes:** composite AC rate, GSTR-1A, SUV 40% slab, ITC timing, Section 192/24Q and final-settlement TDS still need verified lookup notes.
- **Repo is public:** to be made private when the owner decides.
- **Unchecked data:** 311 rows not yet verified.
- **Local-only files:** `data/review/` (including the researched verdicts), `data/tejas_review/PROMPT_*` and the other untracked files are not on GitHub.
- **Kaggle quota:** about 1 hour left this week, so no full training run can start until the weekly reset.
- **Draft notebook:** the Kaggle control notebook has a few stray cells left from typing mistakes. It is only a draft and can be cleaned.

## 12. What to do next, in order

**A. Now, no GPU needed**
1. **Confirm the Qwen3-8B adapter** is in the private Hugging Face repo. It protects the 5 hours of training.
2. **Send Tejas** `review_sheet_for_tejas.csv`, `README_FOR_TEJAS.md` and `real_mistakes_for_tejas.md` (never the KEY file). His marks show the real accuracy, which the automatic scorer cannot.
3. **Write verified lookup notes** for the knowledge-type mistakes listed in section 11.
4. **Improve the weak topics' data:** check the 311 unchecked rows or generate more Payroll and Invoice examples. These are the topics furthest from target.
5. **Test serving** Qwen3-8B plus the adapter, so a switch is not a surprise later.

**B. After the weekly Kaggle reset**
6. **Train v7 on Qwen3-8B** with the improved data (about 6 hours, one run per week of quota). A second seed, if quota allows, shows how much chance matters.
7. **Score it with the new calculators on,** and compare with v6q3 (66.7%) to see what the data and calculators added.

**C. Decisions for the owner**
8. **Make Qwen3-8B the base for future runs.** Recommended.
9. **A bigger model (14B) or preference training (DPO)** are expensive. Only worth it if v7 still falls far short. DPO needs approval.
10. **Faster hardware** (for example Colab Pro) would remove the weekly quota limit.
11. **Make the GitHub repo private** when ready.

## 13. The honest picture
- **Progress:** 22.9% untrained to 66.7% now. The biggest single jump after the first training came from changing the base model (+4.7 points), while adding more of the same data gave little.
- **Gap:** the overall target is 78% and none of the topics is there. Payroll (62 against 82) and Invoice (57.7 against 86) are far away.
- **Likeliest gains:** more accurate data and calculators aimed at specific mistakes, and Tejas's review of real answers.
- **Realistic target:** reaching 78% in every topic may need a larger model, or a target adjusted to what Tejas's review shows is achievable.
- **Trust in the numbers:** one run per model, a roughly 3-point run-to-run noise, a scorer that checks for required words, and a test set that some calculators were built from. Treat small differences with caution.
