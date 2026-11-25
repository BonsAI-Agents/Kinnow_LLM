"""
One-shot Kaggle job: set up, rebuild the data and notes, then score a trained adapter.

Started from the runbook notebook (cell 8b). HF_TOKEN comes from Kaggle Secrets into the environment and is never
printed. By hand it looks like this:

    !curl -s https://raw.githubusercontent.com/BonsAI-Agents/Kinnow_LLM/main/scripts/kaggle_eval.py -o /kaggle/working/kaggle_eval.py
    import os, subprocess
    from kaggle_secrets import UserSecretsClient as U
    e = dict(os.environ, HF_TOKEN=U().get_secret("HF_TOKEN"))
    subprocess.Popen("python /kaggle/working/kaggle_eval.py > /kaggle/working/job.log 2>&1", shell=True, env=e, start_new_session=True)

Environment variables (all optional):
    ADAPTER   Hugging Face adapter repo   (default KaraPatelDev/kinnow-v4-qwen25-sft-adapter)
    FLAGS     scoring switches            (default "--rag 4 --hybrid --calc --cite")
    TAG       label for the run           (default v4-new)

What it does, in order (each step prints a ">>" line):
    1. clone or update the repo and build the Python 3.11 environment (about 10-15 minutes on a fresh session)
    2. rebuild the training data and the lookup notes
    3. score the adapter on the golden, Hindi and multi-turn questions (about 45 minutes)
    4. run the fact check twice, with and without the lookup (about 25 minutes)
    5. write the run record, one file with the code version, data size, settings, scores and fact-check results
Markers in the log: "EVAL SAVED", "FACTS SAVED", "RECORD SAVED", "JOB DONE".
Files: /kaggle/working/<TAG>_full.json (every answer), <TAG>_fact_lookup.json, <TAG>_fact_nolookup.json, <TAG>_record.json
"""

import os
import shutil
import subprocess
import sys
import time

W = "/kaggle/working"
R = W + "/Kinnow_LLM"
PY = W + "/venv/bin/python"
ADAPTER = os.getenv("ADAPTER", "KaraPatelDev/kinnow-v4-qwen25-sft-adapter")
FLAGS = os.getenv("FLAGS", "--rag 4 --hybrid --calc --cite")
TAG = os.getenv("TAG", "v4-new")
BASE = os.getenv("BASE", "Qwen/Qwen2.5-7B-Instruct")
STARTED = time.time()


def sh(cmd, cwd=W, check=True):
    print(">>", cmd[:200], flush=True)
    return subprocess.run(cmd, shell=True, cwd=cwd, check=check)


def keep(src_name, dst_name):
    """Copy a result file out of the repo folder, if it exists."""
    src = R + "/eval/results/" + src_name
    if os.path.exists(src):
        shutil.copy(src, W + "/" + dst_name)
        return True
    return False


if os.path.isdir(R):
    sh("git fetch --depth 1 origin main && git reset --hard origin/main", R)
else:
    sh("git clone --depth 1 https://github.com/BonsAI-Agents/Kinnow_LLM.git " + R)
sh("git log --oneline -1", R)

if not os.path.exists(PY):
    sh("pip install -q uv")
    sh("uv venv --python 3.11 " + W + "/venv")
    sh("uv pip install -q --python " + PY + " -r training/requirements-train.txt", R)
    sh("uv pip install -q --python " + PY + " setuptools wheel rich 'datasets==2.21.0' 'pyarrow==17.0.0'", R)
    # the lookup's embedding model; 3.x works with the pinned transformers 4.46
    sh("uv pip install -q --python " + PY + " 'sentence-transformers==3.2.1'", R)

sh(PY + " -c 'import sentence_transformers, transformers, torch; print(sentence_transformers.__version__, transformers.__version__, torch.__version__)'", R)
sh(PY + " scripts/merge_tejas_data.py > /dev/null", R)
sh(PY + " scripts/split_data.py data/v2_training/raw.jsonl --val-ratio 0.1 | tail -3", R)
sh(PY + " scripts/build_kb.py", R)

model = "--model-id " + BASE + " --adapter " + ADAPTER
# the scoring and fact-check programs exit with an error code when a target is missed, which is expected here
sh(PY + " eval/run_full_eval.py " + model + " " + FLAGS + " --tag " + TAG, R, check=False)
if keep("full_eval.json", TAG + "_full.json"):
    print("EVAL SAVED", flush=True)

sh(PY + " eval/run_fact_check.py " + model + " " + FLAGS, R, check=False)          # with the lookup
got_a = keep("fact_check.json", TAG + "_fact_lookup.json")
sh(PY + " eval/run_fact_check.py " + model, R, check=False)                         # without the lookup
got_b = keep("fact_check.json", TAG + "_fact_nolookup.json")
if got_a and got_b:
    print("FACTS SAVED", flush=True)

# the run record: one file that explains the scores
sys.path.insert(0, R + "/scripts")
try:
    import run_record
    rec = run_record.build_record(TAG, R, W, {"kind": "score an existing adapter", "adapter": ADAPTER, "base_model": BASE,
                                              "flags": FLAGS}, started=STARTED)
    print("RECORD SAVED", run_record.save_record(rec, W), flush=True)
except Exception as e:                      # noqa: BLE001  the scores are already saved above
    print("could not write the run record:", e, flush=True)
print("JOB DONE", flush=True)
