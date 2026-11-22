"""
One-shot Kaggle job: set up, rebuild the data, fine-tune (QLoRA SFT), then score the new adapter.

Started from the runbook notebook (notebooks/kinnow_kaggle_runbook.ipynb), step "Train a new version".
HF_TOKEN comes from Kaggle Secrets into the environment and is never printed.

Environment variables:
    VERSION    label for this run, e.g. v5            (required: it names the output folder and the HF repo)
    HF_USER    Hugging Face user                       (default KaraPatelDev)
    BASE       base model                              (default Qwen/Qwen2.5-7B-Instruct)
    MAX_STEPS  training steps                          (default 600, same as every version so far)
    FLAGS      eval flags after training               (default "--rag 4 --hybrid --calc --cite")
    SEED       random seed (default 42); train twice with different seeds to measure run-to-run variation

What it does, in order (each step prints a ">>" line to job.log):
    1. clone or update the repo, build the Python 3.11 environment (about 10 minutes on a fresh session)
    2. rebuild the training data (scripts/merge_tejas_data.py, split_data.py) and the lookup notes (build_kb.py)
    3. create the private HF repo <HF_USER>/kinnow-<VERSION>-qwen25-sft-adapter
    4. train (about 3 h 50 min for 600 steps on 2 x T4), push the adapter, copy it to /kaggle/working/sft_<VERSION>_backup
    5. run the full eval on the new adapter (about 45 minutes) and save /kaggle/working/<VERSION>_full.json
Markers in job.log: "TRAIN DONE", "EVAL SAVED", "JOB DONE".
"""

import os
import shutil
import subprocess
import sys

W = "/kaggle/working"
R = W + "/Kinnow_LLM"
PY = W + "/venv/bin/python"
VERSION = os.getenv("VERSION")
if not VERSION:
    sys.exit("Set VERSION, e.g. VERSION=v5")
HF_USER = os.getenv("HF_USER", "KaraPatelDev")
BASE = os.getenv("BASE", "Qwen/Qwen2.5-7B-Instruct")
MAX_STEPS = os.getenv("MAX_STEPS", "600")
FLAGS = os.getenv("FLAGS", "--rag 4 --hybrid --calc --cite")
HF_REPO = f"{HF_USER}/kinnow-{VERSION}-qwen25"


def sh(cmd, cwd=R, check=True, env=None):
    print(">>", cmd[:200], flush=True)
    return subprocess.run(cmd, shell=True, cwd=cwd, check=check, env=env)


# 1. code and environment
if os.path.isdir(R):
    sh("git fetch --depth 1 origin main && git reset --hard origin/main")
else:
    sh("git clone --depth 1 https://github.com/BonsAI-Agents/Kinnow_LLM.git " + R, cwd=W)
sh("git log --oneline -1")
if not os.path.exists(PY):
    sh("pip install -q uv", cwd=W)
    sh("uv venv --python 3.11 " + W + "/venv", cwd=W)
    sh("uv pip install -q --python " + PY + " -r training/requirements-train.txt")
    sh("uv pip install -q --python " + PY + " setuptools wheel rich 'datasets==2.21.0' 'pyarrow==17.0.0'")
    sh("uv pip install -q --python " + PY + " 'sentence-transformers==3.2.1'")   # the lookup's embedding model

# 2. data and lookup notes
sh(PY + " scripts/merge_tejas_data.py > /dev/null")
sh(PY + " scripts/split_data.py data/v2_training/raw.jsonl --val-ratio 0.1 | tail -3")
sh(PY + " scripts/build_kb.py")

# 3. private repo for the adapter, so the final push cannot publish an unreviewed model
sh(PY + " -c \"import os;from huggingface_hub import create_repo;"
        "create_repo('" + HF_REPO + "-sft-adapter', private=True, exist_ok=True, token=os.environ['HF_TOKEN'])\"")

# 4. train
env = dict(os.environ, DATA_DIR="data/v2_training", OUTPUT_DIR="models/sft_" + VERSION, HF_REPO=HF_REPO,
           BASE_MODEL=BASE, MAX_STEPS=MAX_STEPS, SEED=os.getenv("SEED", "42"))
sh(PY + " training/sft_train.py --dry-run | tail -8", env=env)
sh(PY + " training/sft_train.py", env=env)
print("TRAIN DONE", flush=True)
out_dir = R + "/models/sft_" + VERSION
if os.path.isdir(out_dir):
    shutil.copytree(out_dir, W + "/sft_" + VERSION + "_backup", dirs_exist_ok=True)

# 5. score the new adapter (the eval exits non-zero when a target is missed, which is expected)
sh(PY + " eval/run_full_eval.py --model-id " + BASE + " --adapter models/sft_" + VERSION + " " + FLAGS + " --tag " + VERSION,
   check=False)
if os.path.exists(R + "/eval/results/full_eval.json"):
    shutil.copy(R + "/eval/results/full_eval.json", W + "/" + VERSION + "_full.json")
    print("EVAL SAVED", flush=True)
print("JOB DONE", flush=True)
