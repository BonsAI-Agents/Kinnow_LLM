# Comparing Qwen2.5-7B-Instruct and Qwen3-8B

Same data, same settings, only the base model differs. Each run gets its own output folder and Hugging Face
repo so nothing is overwritten. `<user>` is your Hugging Face username. Run on Kaggle/Colab, one run per session.

## Kaggle setup (tested 19 Nov 2026, GPU T4 x2, internet on)

Kaggle's default image is now Python 3.13 with torch 2.11 / transformers 5.x, and the pinned stack in
`requirements-train.txt` cannot install there. Build a Python 3.11 environment next to it instead:

```
!git clone --depth 1 https://github.com/BonsAI-Agents/Kinnow_LLM.git /kaggle/working/Kinnow_LLM
%cd /kaggle/working/Kinnow_LLM
!pip install -q uv
!uv venv --python 3.11 /kaggle/working/venv
!uv pip install --python /kaggle/working/venv/bin/python -r training/requirements-train.txt
# extras the pinned set needs on a fresh venv (found the hard way):
!uv pip install --python /kaggle/working/venv/bin/python setuptools wheel rich "datasets==2.21.0" "pyarrow==17.0.0"
```

Then run every script with `/kaggle/working/venv/bin/python` (the install takes about 8 minutes). Add the
`HF_TOKEN` secret under Add-ons > Secrets and attach it to the notebook. Create the Hugging Face repo as private
before training so the final push cannot publish an unreviewed model:

```
import os
from kaggle_secrets import UserSecretsClient
from huggingface_hub import create_repo
os.environ["HF_TOKEN"] = UserSecretsClient().get_secret("HF_TOKEN")
os.environ["HF_REPO"] = "<user>/kinnow-test-qwen25"
os.environ["DATA_DIR"] = "data/v2_training"
os.environ["OUTPUT_DIR"] = "models/sft_qwen25"
create_repo(os.environ["HF_REPO"] + "-sft-adapter", private=True, exist_ok=True, token=os.environ["HF_TOKEN"])
```

Speed: about 25 seconds a step on two T4s (naive model split, so one GPU works at a time), so the 600-step
SFT run takes roughly 4 to 5 hours of the 30 weekly GPU hours.

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
