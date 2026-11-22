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
│   ├── pipeline.py                 orchestration + refusal anomaly tracker
│   ├── answer_support.py           reference notes, calculators and Sources line around the model (optional)
│   ├── retrieval.py                the rule lookup: word matching, hybrid matching, Sources line
│   └── calculators.py              gratuity, PF, ESI, new-regime tax and interest worked in code
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

## Answer support (lookup, calculators, sources)

Around the model call, `guardrails/answer_support.py` does three optional things. On the eval they moved the v4
model from 50.0% to 57.8% overall (see `notebooks/kinnow_kaggle_runbook.ipynb`, section 7):

1. **Lookup.** The 4 most relevant reviewed Q&A notes are put in front of the question.
2. **Calculators.** For a plain calculation question the server works out the figure and gives it to the model.
3. **Sources line.** After the answer, a line such as `Sources: Section 16(2)(aa), Rule 37`, taken only from the notes shown.

Set it up once per knowledge update:

```bash
python scripts/merge_tejas_data.py && python scripts/build_kb.py --embed   # writes data/knowledge/kb.jsonl and its embeddings
```

Mount the `data/knowledge/` folder next to `data/centroids.npz` (read-only is fine once the embeddings are cached).
Every step falls back to the plain question or answer on any error, and the server runs without the knowledge file.
The sources line is only added to answers that are not refusals, after the output validator has checked the model's own text.

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

Classifier thresholds: **≥0.50** pass · **0.35–0.50** ask for clarification ·
**<0.35** block (when in doubt, block); with an ERP keyword present they are
0.35 / 0.20, and 0.10 lower for Hindi. A user who sends 10 out-of-scope
queries in 5 minutes is rate limited for 10 minutes and raises a security event.

### API (plan section 11a)

All `/v1` endpoints need `Authorization: Bearer <API_KEY_PROD>`.

```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d '{"user_id": "u-42", "session_id": "s-1", "message": "What is the GST rate on laptops?"}'
```

Response: `response`, `blocked`, `category_detected`, `guardrail_triggered`
(`injection_defense`, `input_classifier`, `output_validator`, `rate_limiter`, ...),
`latency_ms`, `session_id`, `model_version`, `request_id`.

- **Rate limit:** 20 requests a minute and 500 a day per user (`RATE_LIMIT_PER_MINUTE/DAY`);
  beyond that, HTTP 429 with a `Retry-After` header.
- **Feedback:** `POST /v1/feedback` with `user_id`, `session_id`, `request_id` and a 1-5
  `rating`; answers 204. Ratings of 1-2 are queued for review with the text kept for one hour.
- **Health:** `GET /health` returns `status`, `model_version`, `uptime_seconds`; `GET /ready` checks Redis and vLLM.
- **`/metrics` is internal only.** Requests that came through the ingress (proxy headers present)
  get 404, and the ingress routes only `/v1` and `/health`. Prometheus scrapes the pod directly.
- **Logging is privacy-safe:** each request logs lengths, category, guardrail and a hashed user id,
  never the message, the response or the raw user id.
- The container runs as non-root uid 1000.

---

## Running locally

```bash
# 1. Dependencies
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt   # API + tests. Training (Kaggle): training/requirements-train.txt,
                                      # AWQ quantisation: training/requirements-quantize.txt (each standalone)

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
python eval/run_adversarial.py    # 58 injection/off-topic attacks, 100% must be blocked
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

# Serve with vLLM (GPU host). Defaults to models/kinnow-v1-awq, the directory quantize_awq.py writes;
# override with MODEL_PATH, MODEL_NAME, VLLM_PORT. See the header of the script.
./scripts/start_vllm.sh
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
| `API_KEY_PROD` | yes | API key clients send as `Authorization: Bearer <key>` (24+ characters in production). The server refuses to start without it |
| `API_KEY_NEW` | no | Second accepted key while rotating keys |
| `CENTROIDS_PATH` | no | Domain centroid archive (default `data/centroids.npz`; built by `scripts/build_centroids.py`) |
| `MODEL_NAME` | no | Model name sent to vLLM (default `kinnow-v1`) |
| `KINNOW_LOOKUP` | no | How reference notes are found: `hybrid` (default, word + embedding matching), `bm25` (word matching only) or `off` |
| `KINNOW_KB_PATH` | no | Knowledge file for the lookup (default `data/knowledge/kb.jsonl`; built by `scripts/build_kb.py --embed`). Without it the server runs without the lookup |
| `KINNOW_LOOKUP_K` | no | Notes shown per question (default 4; 6 scored lower in testing) |
| `KINNOW_CALC` | no | `1` (default) / `0`: calculators for plain gratuity, PF, ESI, new-regime tax and interest questions |
| `KINNOW_SOURCES` | no | `1` (default) / `0`: add a "Sources: Section ..., Rule ..." line taken from the notes shown to the model |
| `ENV` | no | `development` / `staging` / `production` |
| `LOG_LEVEL` | no | Log verbosity |
| `HF_TOKEN` | training only | HuggingFace read/write token |

`.env` is gitignored. `.env.example` is committed — it contains no secrets.
