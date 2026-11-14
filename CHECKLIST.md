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

## Phase 2 — Data Pipeline (scripts only; actual data provided by Tejas)

| # | Item | Status |
|---|------|--------|
| 2.1 | `data/FORMAT.md` — exact JSONL schema + good/bad example guide for Tejas | ✅ Done |
| 2.2 | `scripts/validate_data.py` — schema check, dedup, language detection | ✅ Done |
| 2.3 | `scripts/split_data.py` — train/val split (90/10), stratified by domain | ✅ Done |
| 2.4 | `scripts/build_centroids.py` — build embedding centroids from training data for Layer 2 | ✅ Done |
| 2.5 | `eval/eval_guardrails.py` — eval suite: OOS block rate, ERP pass rate, latency | ✅ Done |
| 2.6 | Actual training data (GST ~500 + Payroll ~500 + Invoice ~500 + ERP ~500 examples) | ⏳ Blocked — waiting on Tejas |

---

## Phase 3 — Training (Kaggle)

| # | Item | Status |
|---|------|--------|
| 3.1 | `training/sft_train.py` — QLoRA SFT training script (Qwen2.5-7B, r=64, α=128) | ✅ Script written |
| 3.2 | `training/dpo_train.py` — DPO preference alignment script | ✅ Script written |
| 3.3 | `training/merge_adapter.py` — merge LoRA adapter into base model | ✅ Script written |
| 3.4 | `training/quantize_awq.py` — AWQ 4-bit compression (15 GB → 4.5 GB) | ✅ Script written |
| 3.5 | `eval/eval_model.py` — post-training eval gate (must beat baseline before accepting) | ✅ Script written |
| 3.6 | Kaggle notebook — end-to-end training run | ⏳ Blocked — waiting on training data from Tejas |
| 3.7 | Push adapter + quantized model to HuggingFace (`KaraPatelDev/kinnow-v1`) | ⏳ Blocked — waiting on training data from Tejas |

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
| G.2 | Eval gate: model beats baseline on ERP accuracy | ⏳ Blocked — needs training run |
| G.3 | Load test: 21 req/sec, p95 < 2s sustained | ⏳ Blocked — needs deployed model |
| G.4 | Guardrail audit: OOS block rate > 99%, ERP pass rate > 95% | ✅ 100% / 100% verified |
| G.5 | Security scan: no critical CVEs in Docker image | ⏳ Blocked — needs Docker build |
| G.6 | Dependabot enabled | ✅ Done |
| G.7 | K8s NetworkPolicy + PodSecurityContext applied | ✅ Done |
| G.8 | Monitoring dashboards live and alerting tested | ⏳ Blocked — needs deployment |
| G.9 | Circuit breaker tested (manual failure injection) | ⏳ Blocked — needs deployment |
| G.10 | Canary deployment at 5% traffic — no SLO breach for 30 min | ⏳ Blocked — needs training |
| G.11 | Rollback tested | ⏳ Blocked — needs deployment |
| G.12 | `/v1/feedback` endpoint live and writing to Redis | ⏳ Blocked — needs deployment |

---

_Last updated: Phases 1, 2, 4, 5, 6, 7, 8 ✅ — all code complete. 68/68 tests passing. 3 audit passes, 31 bugs fixed. Guardrail eval: OOS 100%, ERP 100%, injection 100%, p95 2.5ms. Only remaining work: Phase 3 training + go-live steps (G.2–G.3, G.5, G.8–G.12) — all blocked on training data from Tejas._
