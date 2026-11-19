# Comparing Qwen2.5-7B-Instruct and Qwen3-8B

Same data, same settings, only the base model differs. Each run gets its own output folder and Hugging Face
repo so nothing is overwritten. `<user>` is your Hugging Face username. Run on Kaggle/Colab, one run per session.

## 0. Data (once per session)

```bash
python scripts/merge_tejas_data.py
python scripts/split_data.py data/v2_training/raw.jsonl --val-ratio 0.1
python scripts/build_dpo_pairs.py
```

## 1. Baselines (untrained models, same eval)

```bash
python eval/run_full_eval.py --model-id Qwen/Qwen2.5-7B-Instruct --tag base-qwen25
python eval/run_full_eval.py --model-id Qwen/Qwen3-8B            --tag base-qwen3
```

## 2. SFT

```bash
# Qwen2.5-7B
DATA_DIR=data/v2_training OUTPUT_DIR=models/sft_qwen25 HF_REPO=<user>/kinnow-test-qwen25 \
  python training/sft_train.py

# Qwen3-8B
BASE_MODEL=Qwen/Qwen3-8B DATA_DIR=data/v2_training OUTPUT_DIR=models/sft_qwen3 HF_REPO=<user>/kinnow-test-qwen3 \
  python training/sft_train.py
```

Run `--dry-run` first with the same environment variables. Qwen3's training text starts each answer with an
empty `<think></think>` block; that is expected, and the server sends `enable_thinking: false` to match.

## 3. Score the fine-tunes

```bash
python eval/run_full_eval.py --model-id Qwen/Qwen2.5-7B-Instruct --adapter models/sft_qwen25 --tag sft-qwen25
python eval/run_full_eval.py --model-id Qwen/Qwen3-8B            --adapter models/sft_qwen3  --tag sft-qwen3
```

## 4. What to compare

- Per-category pass rate (GST, Payroll, Invoice, Refusal), overall and Hindi vs English.
- False-refusal rate (a valid ERP question wrongly refused) and the refusal rate on off-topic questions.
- Multi-turn score, and latency per answer.
- Each model against its own baseline: the question is how much training adds, and which gets further.

Pick the winner on the eval numbers, not the training loss, and only trust a difference of a few points if both
runs used the same data and steps. DPO comes afterwards, on the winner only.
