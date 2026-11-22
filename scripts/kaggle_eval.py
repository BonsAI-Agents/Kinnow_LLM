"""
One-shot Kaggle job: set up, rebuild the data and notes, and run the full eval on a trained adapter.

Started from a notebook cell (HF_TOKEN comes from Kaggle Secrets into the environment, never printed):

    !curl -s https://raw.githubusercontent.com/BonsAI-Agents/Kinnow_LLM/main/scripts/kaggle_eval.py -o /kaggle/working/kaggle_eval.py
    import os, subprocess
    from kaggle_secrets import UserSecretsClient as U
    e = dict(os.environ, HF_TOKEN=U().get_secret("HF_TOKEN"))
    subprocess.Popen("python /kaggle/working/kaggle_eval.py > /kaggle/working/job.log 2>&1", shell=True, env=e, start_new_session=True)

Environment variables (all optional):
    ADAPTER   Hugging Face adapter repo   (default KaraPatelDev/kinnow-v4-qwen25-sft-adapter)
    FLAGS     extra eval flags            (default "--rag 4 --hybrid --calc --cite")
    TAG       label for the run           (default v4-new)
Markers in job.log: "EVAL SAVED" then "JOB DONE". Results: /kaggle/working/<TAG>_full.json
"""

import os
import shutil
import subprocess

W = "/kaggle/working"
R = W + "/Kinnow_LLM"
PY = W + "/venv/bin/python"
ADAPTER = os.getenv("ADAPTER", "KaraPatelDev/kinnow-v4-qwen25-sft-adapter")
FLAGS = os.getenv("FLAGS", "--rag 4 --hybrid --calc --cite")
TAG = os.getenv("TAG", "v4-new")


def sh(cmd, cwd=W, check=True):
    print(">>", cmd[:200], flush=True)
    return subprocess.run(cmd, shell=True, cwd=cwd, check=check)


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
sh(PY + " scripts/build_kb.py", R)

model = "--model-id Qwen/Qwen2.5-7B-Instruct --adapter " + ADAPTER
# the eval exits non-zero when a target is missed, which is expected here
sh(PY + " eval/run_full_eval.py " + model + " " + FLAGS + " --tag " + TAG, R, check=False)
if os.path.exists(R + "/eval/results/full_eval.json"):
    shutil.copy(R + "/eval/results/full_eval.json", W + "/" + TAG + "_full.json")
    print("EVAL SAVED", flush=True)
print("JOB DONE", flush=True)
