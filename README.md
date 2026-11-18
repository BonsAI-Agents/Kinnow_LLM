# Kinnow ERP LLM

Production-grade LLM assistant for **Kinnow ERP** — an Indian business management
platform. The assistant answers GST, payroll, invoice matching and ERP operations
questions in English and Hindi, and refuses everything outside that scope.

Built to the blueprint in `kinnow-production-plan-v1.md`.

> 📖 **New to this codebase?** Start with **[`ARCHITECTURE.md`](ARCHITECTURE.md)** — a complete
> walkthrough of the request flow, all four guardrail layers, the training pipeline, the ops
> surface, and the known sharp edges.

| Target | Value |
|---|---|
| Base model | `Qwen/Qwen2.5-7B-Instruct` (Apache 2.0) |
| Method | QLoRA SFT → DPO alignment → merge → AWQ 4-bit |
| Serving | vLLM (A10G, 24GB) behind a FastAPI guardrail gateway |
| Guardrails | 4 layers + 3 overlapping domain-lock checks |
| Accuracy target | ≥78% overall at v1, ≥85% at production scale |
| Latency target | p95 < 2s |

---

## Repository layout

```
Kinnow_LLM/
├── ARCHITECTURE.md    complete codebase walkthrough (read this first)
├── guardrails/        4-layer guardrail pipeline (the safety core)
│   ├── layer1_system_prompt.py     server-side prompt lock + history sanitisation
│   ├── layer2_classifier.py        keyword → embedding input classifier
│   ├── layer3_output_validator.py  PII / GST rate / out-of-scope output checks
│   ├── layer4_injection.py         prompt injection detection + sanitisation
│   └── pipeline.py                 orchestration + refusal anomaly tracker
├── serve/             FastAPI serving layer
│   ├── app.py                     application + lifespan (Redis, vLLM, centroids)
│   ├── routes/chat.py             POST /v1/chat
│   ├── routes/health.py           GET /health, GET /ready
│   ├── routes/feedback.py         POST /v1/feedback (data flywheel)
│   ├── vllm_client.py             async vLLM OpenAI-compatible client
│   ├── redis_client.py            Redis lifecycle, cache, feedback queue
│   ├── circuit_breaker.py         CLOSED → OPEN → HALF-OPEN
│   ├── metrics.py                 Prometheus metrics
│   └── middleware.py              request IDs + structured JSON logging
├── training/          offline scripts (Kaggle/Colab)
│   ├── sft_train.py               QLoRA supervised fine-tuning
│   ├── dpo_train.py               preference alignment
│   ├── merge_adapter.py           merge LoRA into base weights
│   └── quantize_awq.py            AWQ 4-bit quantization
├── eval/              evaluation suites and gates
│   ├── eval_guardrails.py         OOS block rate, ERP pass rate, latency
│   └── eval_model.py              post-training model quality gate
├── scripts/           operational tooling
│   ├── validate_data.py           dataset schema + quality validation
│   ├── split_data.py              stratified 90/10 train/val split
│   ├── build_centroids.py         embedding centroids for Layer 2
│   ├── check_slos.py              canary SLO checker (Prometheus)
│   ├── export_feedback.py         drain the human review queue
│   └── prepare_v2_data.py         merge reviewed feedback into v2 data
├── data/FORMAT.md     training data contract for contributors
├── tests/             unit (68) + integration + Locust load scenarios
├── k8s/               deployment, service, NetworkPolicy, PodSecurityContext
├── monitoring/        Prometheus config, alert rules, Grafana dashboard
├── .github/           CI, eval gate, deploy pipelines, Dependabot
└── CHECKLIST.md       phase-by-phase delivery status and go-live sign-off
```

---

## Guardrail order

A user query never reaches the model without passing through all of this:

```
query
  → Layer 4  injection defence      (sanitise, detect, block)
  → Layer 2  input classifier       (keyword → embedding → pass / clarify / block)
  → Layer 1  system prompt lock     (server-side, never client-controllable)
  →          model inference        (vLLM)
  → Layer 3  output validator       (PII, GST rates, out-of-scope topic)
  → response
```

Classifier thresholds: **≥0.65** pass · **0.45–0.65** ask for clarification ·
**<0.45** block (when in doubt, block). A user who sends 10 out-of-scope
queries in 5 minutes is rate limited for 10 minutes and raises a security event.

---

## Running locally

```bash
# 1. Dependencies
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt   # API + tests. Training (Kaggle): requirements-train.txt,
                                      # AWQ quantisation: requirements-quantize.txt (each standalone)

# 2. Configuration
cp .env.example .env              # fill in HF_TOKEN and the local URLs

# 3. Infrastructure (API + Redis + Prometheus + Grafana)
docker compose up -d
docker compose ps

# 4. API
uvicorn serve.app:app --host 0.0.0.0 --port 8000 --workers 1

# 5. Checks
curl http://localhost:8000/health
python -m pytest tests/ -v
python eval/eval_guardrails.py
```

vLLM runs separately on a GPU host — see the model preparation steps below.

---

## Model preparation

```bash
# Train (Kaggle/Colab)
python training/sft_train.py
python training/dpo_train.py

# Prepare a servable artefact
python training/merge_adapter.py
python training/quantize_awq.py

# Serve with vLLM
python -m vllm.entrypoints.openai.api_server \
    --model /models/kinnow-v1-awq-4bit \
    --max-model-len 4096 \
    --gpu-memory-utilization 0.90 \
    --served-model-name kinnow-v1 \
    --port 8001
```

---

## Data

Training data is **not** in this repository — it is supplied as JSONL and
validated before every run. The contract is in [`data/FORMAT.md`](data/FORMAT.md).

```bash
python scripts/validate_data.py data/v1_training/train.jsonl
python scripts/split_data.py data/v1_training/raw.jsonl --val-ratio 0.1
python scripts/build_centroids.py data/v1_training/train.jsonl
```

---

## Deployment

```bash
# Canary
kubectl set image deployment/kinnow-api api=<tag> -n kinnow
kubectl rollout status deployment/kinnow-api -n kinnow --timeout=120s

# SLO gate — non-zero exit rolls the canary back
python scripts/check_slos.py --prometheus-url http://prometheus:9090

# Promote
kubectl scale deployment/kinnow-api --replicas=2 -n kinnow

# Rollback
kubectl rollout undo deployment/kinnow-api -n kinnow
```

---

## Current status

Phases 1, 2, 4, 5, 6, 7 and 8 are complete — **68/68 tests passing**, guardrail
eval at OOS 100% / ERP 100% / injection 100% with 2.5ms classifier p95.

Phase 3 (the actual training run) and the go-live steps are blocked on the
training dataset and a deployed model. See [`CHECKLIST.md`](CHECKLIST.md) for
the item-by-item status.

---

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `VLLM_BASE_URL` | yes | Address of the vLLM inference server |
| `REDIS_URL` | yes | Session history and rate-limit state |
| `CENTROIDS_PATH` | no | Domain centroid artefact (default `data/centroids.npy`) |
| `MODEL_NAME` | no | Model name sent to vLLM (default `kinnow-v1`) |
| `ENV` | no | `development` / `staging` / `production` |
| `LOG_LEVEL` | no | Log verbosity |
| `HF_TOKEN` | training only | HuggingFace read/write token |

`.env` is gitignored. `.env.example` is committed — it contains no secrets.
