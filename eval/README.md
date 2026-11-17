# Kinnow eval sets

Held-out evaluation data for the v1 exit criteria in `kinnow-production-plan-v1.md`. None of it is used for training.

| File | Items | Plan section | Scored by |
|---|---|---|---|
| `golden_set.jsonl` | 192 (GST 54, INVOICE 52, PAYROLL 50, REFUSAL 36) | 6d | `run_full_eval.py` |
| `hindi_eval_30.jsonl` | 27 (GST 9, PAYROLL 10, REFUSAL 8) | 19g | `run_full_eval.py` |
| `multiturn_eval_20.jsonl` | 20 conversations, 60 turns | 19f | `run_full_eval.py` |
| `domain_lock_cases.jsonl` | 130 (84 should be blocked, 46 should pass) | 21h | `test_domain_lock.py` (guardrails only, no model) |
| `pending_mixed_behavior.jsonl` | 3 | - | not scored, see below |

## Run

```bash
python eval/run_full_eval.py --self-test                       # checks the sets against their own references
python eval/run_full_eval.py --model-id Qwen/Qwen2.5-7B-Instruct --tag baseline   # measure the base model first
python eval/run_full_eval.py --model-id <trained model> --tag v1
python eval/test_domain_lock.py                                # needs data/centroids.npy for production behaviour
```

`run_full_eval.py` calls the model with the production system prompt, checks the plan's targets (overall 78%, GST 65%, Payroll 82%, Invoice 86%, false refusals under 3%, Hindi gap), and applies the 5pp regression gate against the previous run. It exits 1 on any failure.

Scoring is the plan's `must_contain` / `must_not_contain` (6a), plus one change: digit-grouping commas are ignored, so `25,000`, `25000` and `2,00,000` / `200000` match.

## Limits to keep in mind

- **Same author as the training data.** Training rows and eval items were written by the same model, so expect optimistic scores. Add real user questions from logs as soon as you have them.
- **Facts are not expert-verified.** Have a CA or payroll expert review the golden set the same way as the training data.
- **Keyword scoring misses quality.** A response can pass by containing the right terms in a wrong sentence. The plan's LLM-as-judge (6b) is not built yet.
- **`pending_mixed_behavior.jsonl`** holds 3 items that mix a real ERP question with an off-topic one and expect a full refusal. The training set teaches the opposite for mixed messages (answer the ERP part, decline the rest). Decide the behaviour first, then fold these back in or rewrite them.
- 8 items that nearly duplicated training prompts were removed from the golden and Hindi sets. Items that differ only in the numbers were kept on purpose.
