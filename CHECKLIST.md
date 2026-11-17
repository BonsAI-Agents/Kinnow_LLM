# Kinnow ERP LLM — Implementation Checklist

Track every deliverable in order. Update status after each implementation.
Legend: ✅ Done | 🔄 In Progress | ⬜ Pending | ⏳ Blocked (waiting on external)

---

## Phase 1 — Guardrails

| # | Item | Status |
|---|------|--------|
| 1.1 | `guardrails/layer4_injection.py` — sanitize + injection detection (25 patterns) | ✅ Done |
| 1.2 | `guardrails/layer2_classifier.py` — keyword + embedding classifier | ✅ Done |
| 1.3 | `guardrails/layer1_system_prompt.py` — system prompt lock + history sanitization | ✅ Done |
| 1.4 | `guardrails/layer3_output_validator.py` — PII, GST rate, OOS topic check | ✅ Done |
| 1.5 | `guardrails/pipeline.py` — full pipeline + refusal rate-limiter | ✅ Done |
| 1.6 | Unit tests — layer4, layer2, layer3, pipeline (68 tests, all passing) | ✅ Done |
| 1.7 | Integration tests — full pipeline end-to-end | ✅ Done |

---

## Phase 2 — Data Pipeline and Eval Sets

| # | Item | Status |
|---|------|--------|
| 2.1 | `data/FORMAT.md` — exact JSONL schema + good/bad example guide for Tejas | ✅ Done |
| 2.2 | `scripts/validate_data.py` — schema check, dedup, language detection | ✅ Done |
| 2.3 | `scripts/split_data.py` — train/val split (90/10), stratified by domain | ✅ Done |
| 2.4 | `scripts/build_centroids.py` — build embedding centroids from training data for Layer 2 | ✅ Done — skips the REFUSAL domain (a REFUSAL centroid would let off-topic queries pass); `data/centroids.npy` built from train.jsonl (gitignored, rebuild per environment) |
| 2.5 | `eval/eval_guardrails.py` — eval suite: OOS block rate, ERP pass rate, latency | ✅ Done — ⚠ runs in keyword-only mode (no centroids), so its 100% results do not reflect production; see 2.13 |
| 2.6 | v1 SFT training data (plan §3b: GST 600, Payroll 400, Invoice 400, Refusal 400, ERP 100) | 🔄 Generated 2026-11-17: 1,927 rows (train 1,737 / val 190: GST 606, Payroll 392, Invoice 384, Refusal 429, ERP 116), ~263 Hindi. **Not expert-reviewed.** `train.jsonl` / `val.jsonl` are gitignored; `raw.jsonl` is tracked. Tejas's own dataset can still replace or extend it |
| 2.7 | Expert review of the dataset (CA / payroll specialist; ≥100 random rows per domain plus the facts listed in `data/v1_training/DATASET_README.md`) | ⬜ Pending |
| 2.8 | Golden set — `eval/golden_set.jsonl` (192: GST 54, Invoice 52, Payroll 50, Refusal 36) | ✅ Built; facts not expert-verified; same author as training data (expect optimistic scores) |
| 2.9 | Hindi eval (`eval/hindi_eval_30.jsonl`, 27) and multi-turn eval (`eval/multiturn_eval_20.jsonl`, 20 conversations / 60 turns) | ✅ Built |
| 2.10 | Domain-lock suite — `eval/domain_lock_cases.jsonl` (130 cases) + `eval/test_domain_lock.py` (§21h) | ✅ Built — ❌ currently **fails (91/130)**, see 2.13 |
| 2.11 | Full eval runner — `eval/run_full_eval.py` (§6a/6c/6e/6f: per-category scores, false-refusal rate, Hindi gap, multi-turn, regression gate, `--self-test`) | ✅ Done (self-test 100%; negative test fails correctly). Not yet run on a model |
| 2.12 | DPO / ORPO preference pairs (plan builds them from the SFT model's real failures) | ⬜ Pending — needs the trained model; format sample in `data/sample_for_tejas/` |
| 2.13 | Recalibrate Layer 2 thresholds (pass ≥ 0.65 / clarify ≥ 0.45) — with centroids, legitimate queries score median 0.56 (so most get "clarify"), off-topic median 0.10; a cutoff near 0.33 separated them on the first 76 cases. Only 8 of 46 legitimate domain-lock queries pass today; 83 of 84 off-topic are blocked. Competitor-ERP queries need keyword patterns (§21c) | ⬜ Pending — decide thresholds on held-out data (val vs off-topic set); security-relevant change |
| 2.14 | Mixed ERP + off-topic message behaviour (training: answer the ERP part, decline the rest; 3 eval items expect a full refusal, parked in `eval/pending_mixed_behavior.jsonl`) | ⬜ Pending decision |
| 2.15 | LLM-as-judge eval (§6b) | ⬜ Pending |

---

## Phase 3 — Training (Kaggle)

| # | Item | Status |
|---|------|--------|
| 3.1 | `training/sft_train.py` — QLoRA SFT training script (Qwen2.5-7B, r=64, α=128) | ✅ Script written — now prepends `PRODUCTION_SYSTEM_PROMPT` (plan §4e); longest example 803 tokens vs `max_seq_length=1024`. Not yet run |
| 3.2 | `training/dpo_train.py` — DPO preference alignment script | ✅ Script written — ⚠ learning rate is 5e-5 but the plan says 5e-6; check before running |
| 3.3 | `training/merge_adapter.py` — merge LoRA adapter into base model | ✅ Script written |
| 3.4 | `training/quantize_awq.py` — AWQ 4-bit compression (15 GB → 4.5 GB) | ✅ Script written |
| 3.5 | `eval/eval_model.py` — post-training eval gate (must beat baseline before accepting) | ✅ Script written — ⚠ superseded by `eval/run_full_eval.py`: only 10 hard-coded cases, no system prompt, expects "192" and a "12%" packaged-food rate (both stale) |
| 3.6 | Baseline eval of the untuned base model (`python eval/run_full_eval.py --model-id Qwen/Qwen2.5-7B-Instruct --tag baseline`) | ⬜ Pending — run first so v1 has a number to beat |
| 3.7 | Kaggle notebook — end-to-end SFT training run | ⬜ Pending — data is ready; waiting on expert review (2.7) |
| 3.8 | Push adapter + quantized model to HuggingFace (`KaraPatelDev/kinnow-v1`) | ⬜ Pending — needs a training run and a passing eval gate |

---

## Phase 4 — API Server

| # | Item | Status |
|---|------|--------|
| 4.1 | `serve/app.py` — FastAPI app skeleton + lifespan (load model, build centroids) | ✅ Done |
| 4.2 | `serve/routes/chat.py` — `POST /v1/chat` endpoint with guardrail pipeline | ✅ Done |
| 4.3 | `serve/routes/health.py` — `GET /health` + `GET /ready` endpoints | ✅ Done |
| 4.4 | `serve/routes/feedback.py` — `POST /v1/feedback` (thumbs-up/down for data flywheel) | ✅ Done |
| 4.5 | `serve/vllm_client.py` — vLLM async client wrapper (model inference) | ✅ Done |
| 4.6 | `serve/redis_client.py` — Redis session cache + rate-limit state | ✅ Done |
| 4.7 | `serve/middleware.py` — request ID injection, structured JSON logging | ✅ Done |
| 4.8 | `serve/metrics.py` — Prometheus counters (requests, latency, block rate by layer) | ✅ Done |
| 4.9 | `serve/circuit_breaker.py` — circuit breaker wrapper around model calls | ✅ Done |
| 4.10 | `.env.example` — all required environment variables documented | ✅ Done |

---

## Phase 5 — Infrastructure

| # | Item | Status |
|---|------|--------|
| 5.1 | `Dockerfile` — multi-stage build (base → deps → app) | ✅ Done |
| 5.2 | `docker-compose.yml` — local dev stack (app + Redis + Prometheus + Grafana) | ✅ Done |
| 5.3 | `k8s/deployment.yaml` — K8s deployment with resource limits (GPU request) | ✅ Done |
| 5.4 | `k8s/service.yaml` — K8s service + ingress | ✅ Done |
| 5.5 | `k8s/networkpolicy.yaml` — K8s NetworkPolicy (Section 20) | ✅ Done |
| 5.6 | `k8s/pod-security.yaml` — PodSecurityContext (non-root, read-only FS) | ✅ Done |
| 5.7 | `monitoring/prometheus.yml` — scrape config | ✅ Done |
| 5.8 | `monitoring/grafana-dashboard.json` — latency, block rate, error rate panels | ✅ Done |
| 5.9 | `monitoring/alerts.yml` — Prometheus alert rules (p95 > 2s, error rate > 1%) | ✅ Done |

---

## Phase 6 — CI/CD

| # | Item | Status |
|---|------|--------|
| 6.1 | `.github/workflows/ci.yml` — lint + unit tests + integration tests on every PR | ✅ Done |
| 6.2 | `.github/workflows/eval.yml` — eval gate (runs after training, blocks merge if score drops) | ✅ Done |
| 6.3 | `.github/workflows/deploy.yml` — Docker build → push ECR → canary → production | ✅ Done |
| 6.4 | `.github/dependabot.yml` — Dependabot config for pip dependency updates | ✅ Done |

---

## Phase 7 — Load Testing & Security

| # | Item | Status |
|---|------|--------|
| 7.1 | `tests/load/locustfile.py` — load test: 21 req/sec, p95 < 2s, 10 min ramp | ✅ Done |
| 7.2 | `tests/load/scenarios.py` — mixed ERP + OOS + injection query scenarios | ✅ Done |
| 7.3 | Security scan integration in CI (Trivy for Docker image, Bandit for Python) | ✅ Done |

---

## Phase 8 — Data Flywheel

| # | Item | Status |
|---|------|--------|
| 8.1 | `scripts/export_feedback.py` — export thumbs-down queries from Redis for human review | ✅ Done |
| 8.2 | `scripts/prepare_v2_data.py` — merge reviewed feedback into new training JSONL | ✅ Done |
| 8.3 | Human review queue workflow documentation | ✅ Done |

---

## Go-Live Checklist (final sign-off)

| # | Item | Status |
|---|------|--------|
| G.1 | All unit + integration tests passing | ✅ 68/68 passing |
| G.2 | Eval gate: `run_full_eval.py` passes (overall ≥ 78%, GST ≥ 65%, Payroll ≥ 82%, Invoice ≥ 86%, false refusals < 3%, no category drop > 5pp) | ⏳ Blocked — needs training run |
| G.3 | Load test: 21 req/sec, p95 < 2s sustained | ⏳ Blocked — needs deployed model |
| G.4 | Guardrail audit: OOS block rate > 99%, ERP pass rate > 95% (with centroids loaded, as in production) | ❌ Not met. Earlier 100% / 100% was keyword-only mode. With centroids: off-topic blocked 83/84, but only 8/46 legitimate queries pass (domain-lock 91/130). Fix via 2.13 |
| G.4b | Domain-lock suite (§21h): 100% pass required | ❌ 91/130 — blocked until 2.13 |
| G.5 | Security scan: no critical CVEs in Docker image | ⏳ Blocked — needs Docker build |
| G.6 | Dependabot enabled | ✅ Done |
| G.7 | K8s NetworkPolicy + PodSecurityContext applied | ✅ Done |
| G.8 | Monitoring dashboards live and alerting tested | ⏳ Blocked — needs deployment |
| G.9 | Circuit breaker tested (manual failure injection) | ⏳ Blocked — needs deployment |
| G.10 | Canary deployment at 5% traffic — no SLO breach for 30 min | ⏳ Blocked — needs training |
| G.11 | Rollback tested | ⏳ Blocked — needs deployment |
| G.12 | `/v1/feedback` endpoint live and writing to Redis | ⏳ Blocked — needs deployment |

---

_Last updated 2026-11-17. Code for Phases 1, 4, 5, 6, 7, 8 is complete (68 tests reported passing in the previous update; not re-run since). Training data (1,927 rows) and the eval sets now exist; the training run itself has not started._

**Next, in order**
1. Expert review of the dataset (2.7), and decide mixed-message behaviour (2.14).
2. Recalibrate the Layer 2 thresholds and add competitor keyword patterns (2.13), then get the domain-lock suite to 100% (G.4, G.4b).
3. Run the baseline eval (3.6), then the SFT run on Kaggle (3.7), then `run_full_eval.py` on the result (G.2).
4. Build DPO pairs from the model's failures (2.12), merge, quantize, push (3.8), then deploy and work through G.3, G.5, G.8–G.12.

**Known caveats**
- Dataset facts came from the generating model plus secondary sources; the EPF ceiling (₹25,000 from 17 Sep 2026), Income-tax Act 2025 renumbering, ESI and bonus ceilings need checking against official notifications.
- Eval items and training rows share an author, so scores will look optimistic; add real user questions when available.
- `data/v1_training/train.jsonl`, `val.jsonl` and `data/centroids.npy` are gitignored; regenerate with `scripts/split_data.py` and `scripts/build_centroids.py`.
- Multi-turn behaviour is covered only in eval; the SFT data is single-turn.
