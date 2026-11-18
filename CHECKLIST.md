# Kinnow ERP LLM — Implementation Checklist

Track every deliverable in order. Update status after each implementation.
Legend: ✅ Done | 🔄 In Progress | ⬜ Pending | ⏳ Blocked (waiting on external)

---

## Phase 1 — Guardrails

| # | Item | Status |
|---|------|--------|
| 1.1 | `guardrails/layer4_injection.py` — sanitize + injection detection (~45 patterns, unicode/zero-width/hyphen folding) | ✅ Done, hardened 2026-11-18 |
| 1.2 | `guardrails/layer2_classifier.py` — keyword + embedding classifier | ✅ Done |
| 1.3 | `guardrails/layer1_system_prompt.py` — system prompt lock + history sanitization | ✅ Done |
| 1.4 | `guardrails/layer3_output_validator.py` — PII, GST rate, OOS topic check | ✅ Done |
| 1.5 | `guardrails/pipeline.py` — full pipeline + refusal rate-limiter | ✅ Done |
| 1.6 | Tests for the guardrails and the API server: 299 unit + integration tests, 95% coverage of `guardrails/` and `serve/` | ✅ Done |
| 1.7 | Integration tests — full pipeline end-to-end | ✅ Done |

---

## Phase 2 — Data Pipeline and Eval Sets

| # | Item | Status |
|---|------|--------|
| 2.1 | `data/FORMAT.md` — exact JSONL schema + good/bad example guide for Tejas | ✅ Done |
| 2.2 | `scripts/validate_data.py` — schema check, dedup, language detection | ✅ Done |
| 2.3 | `scripts/split_data.py` — train/val split (90/10), stratified by domain | ✅ Done |
| 2.4 | `scripts/build_centroids.py` — build embedding centroids from training data for Layer 2 | ✅ Done — skips the REFUSAL domain (a REFUSAL centroid would let off-topic queries pass); writes `data/centroids.npz` (no pickle; gitignored, rebuild per environment). The CI domain-lock job rebuilds it from the tracked `raw.jsonl` |
| 2.5 | `eval/eval_guardrails.py` — OOS block rate, ERP pass rate, latency | ✅ Done — loads the centroids like the server (it ran keyword-only, which flattered the result) and can now import `guardrails` when run as `python eval/eval_guardrails.py`. With centroids: OOS 100%, ERP 95%, injection 100%, p95 77 ms |
| 2.6 | v1 SFT training data (plan §3b: GST 600, Payroll 400, Invoice 400, Refusal 400, ERP 100) | 🔄 Generated 2026-11-17: 1,927 rows (train 1,737 / val 190: GST 606, Payroll 392, Invoice 384, Refusal 429, ERP 116), ~263 Hindi. **Not expert-reviewed.** `train.jsonl` / `val.jsonl` are gitignored; `raw.jsonl` is tracked. Tejas's own dataset can still replace or extend it |
| 2.7 | Expert review of the dataset (CA / payroll specialist; ≥100 random rows per domain plus the facts listed in `data/v1_training/DATASET_README.md`) | ⬜ Pending |
| 2.8 | Golden set — `eval/golden_set.jsonl` (192: GST 54, Invoice 52, Payroll 50, Refusal 36) | ✅ Built; facts not expert-verified; same author as training data (expect optimistic scores) |
| 2.9 | Hindi eval (`eval/hindi_eval_30.jsonl`, 27) and multi-turn eval (`eval/multiturn_eval_20.jsonl`, 20 conversations / 60 turns) | ✅ Built |
| 2.10 | Domain-lock suite — `eval/domain_lock_cases.jsonl` (130 cases) + `eval/test_domain_lock.py` (§21h) | ✅ Built; passes 130/130 as of 2026-11-18 (part of its pool was used to calibrate Layer 2, so re-check on fresh queries) |
| 2.11 | Full eval runner — `eval/run_full_eval.py` (§6a/6c/6e/6f: per-category scores, false-refusal rate, Hindi gap, multi-turn, regression gate, `--self-test`) | ✅ Done (self-test 100%; negative test fails correctly). Not yet run on a model |
| 2.12 | DPO / ORPO preference pairs (plan builds them from the SFT model's real failures) | ⬜ Pending — needs the trained model; format sample in `data/sample_for_tejas/` |
| 2.13 | Recalibrate Layer 2 (thresholds and keyword tiers) | ✅ Done 2026-11-18. On a held-out pool (350 legitimate / 156 off-topic): legitimate queries wrongly blocked 2.2% (was 12.6%), off-topic passed 1.8%. STRONG/WEAK off-topic patterns, wider ERP vocabulary, role-change and investing patterns, thresholds 0.50 / 0.35 (0.35 / 0.20 with an ERP keyword), 0.10 lower for Hindi. Subtle off-topic questions (personal business advice, legal disputes) still pass Layer 2 (about 1 in 5 of the golden-set cases) and depend on the model |
| 2.14 | Mixed ERP + off-topic message behaviour (training: answer the ERP part, decline the rest; 3 eval items expect a full refusal, parked in `eval/pending_mixed_behavior.jsonl`) | ⬜ Pending decision |
| 2.15 | LLM-as-judge eval (§6b) | ⬜ Pending |

---

## Phase 3 — Training (Kaggle)

| # | Item | Status |
|---|------|--------|
| 3.1 | `training/sft_train.py` — QLoRA SFT training script (Qwen2.5-7B, r=64, α=128) | ✅ Script written — now prepends `PRODUCTION_SYSTEM_PROMPT` (plan §4e); longest example 803 tokens vs `max_seq_length=1024`. Aligned with plan 4d/4f on 2026-11-18: fp16 on a T4 and bf16 on Ampere (auto-detected), loss on the assistant reply only (85% of tokens were prompt), batch 2x4, 600 steps, gradient checkpointing, adamw_8bit, cosine. `--dry-run` checks the data and mask without a GPU. Not yet run |
| 3.2 | `training/dpo_train.py` — DPO preference alignment script | ✅ Script written — ⚠ learning rate is 5e-5 but the plan says 5e-6; check before running |
| 3.3 | `training/merge_adapter.py` — merge LoRA adapter into base model | ✅ Script written |
| 3.4 | `training/quantize_awq.py` — AWQ 4-bit compression (15 GB → 4.5 GB) | ✅ Script written |
| 3.5 | `eval/eval_model.py` — post-training eval gate (must beat baseline before accepting) | ✅ Script written — now sends the production system prompt; superseded by the fuller `eval/run_full_eval.py` |
| 3.6 | Baseline eval of the untuned base model (`python eval/run_full_eval.py --model-id Qwen/Qwen2.5-7B-Instruct --tag baseline`) | ⬜ Pending — run first so v1 has a number to beat |
| 3.7 | Kaggle notebook — end-to-end SFT training run | ⬜ Pending — data is ready; waiting on expert review (2.7) |
| 3.8 | Push adapter + quantized model to HuggingFace (`KaraPatelDev/kinnow-v1`) | ⬜ Pending — needs a training run and a passing eval gate |

---

## Phase 4 — API Server

| # | Item | Status |
|---|------|--------|
| 4.1 | `serve/app.py` — FastAPI app skeleton + lifespan (load model, build centroids) | ✅ Done |
| 4.2 | `serve/routes/chat.py` — `POST /v1/chat` endpoint with guardrail pipeline | ✅ Done |
| 4.3 | `serve/routes/health.py` — `GET /health` (status, model_version, uptime) + `GET /ready` | ✅ Done |
| 4.4 | `serve/routes/feedback.py` — `POST /v1/feedback` per plan 11a (`request_id` + 1-5 rating, 204; thumbs-down text kept 1h for review) | ✅ Done 2026-11-18 |
| 4.5 | `serve/vllm_client.py` — vLLM async client wrapper (model inference) | ✅ Done |
| 4.6 | `serve/redis_client.py` — Redis session cache + rate-limit state | ✅ Done |
| 4.7 | `serve/middleware.py` — request ID injection, structured JSON logging | ✅ Done |
| 4.8 | `serve/metrics.py` — Prometheus counters (requests, latency, block rate by layer) | ✅ Done |
| 4.9 | `serve/circuit_breaker.py` — circuit breaker wrapper around model calls | ✅ Done — fixed 2026-11-18: counts consecutive failures, no leaked coroutines, an open circuit now answers 503 |
| 4.10 | `.env.example` — all required environment variables documented | ✅ Done |
| 4.11 | `serve/auth.py` — Bearer API-key authentication on `/v1/chat` and `/v1/feedback`; sessions namespaced per key | ✅ Done 2026-11-18 (`API_KEY_PROD`, optional `API_KEY_NEW` for rotation; `/health`, `/ready` stay open; `/metrics` is internal only) |
| 4.12 | `serve/rate_limiter.py` — Redis-backed off-topic rate limiter shared by all replicas (in-process fallback, bounded) | ✅ Done 2026-11-18 |
| 4.14 | API contract per plan 11a (`user_id`, `request_id`, `blocked`, `guardrail_triggered`, `model_version`) | ✅ Done 2026-11-18 |
| 4.15 | Per-user rate limit 20/min and 500/day -> 429 + `Retry-After` (`serve/rate_limit.py`) | ✅ Done 2026-11-18 |
| 4.16 | Privacy-safe request logging, plan 13a (`serve/request_log.py`: lengths, category, guardrail, hashed user id) | ✅ Done 2026-11-18 |
| 4.17 | `/metrics` internal only (`serve/internal_only.py`; ingress routes only `/v1` and `/health`) | ✅ Done 2026-11-18 |
| 4.18 | Container runs as uid 1000 | ✅ Done 2026-11-18 (image rebuilt, `id` shows 1000) |
| 4.13 | Centroids loaded without pickle (`.npz`); embedding model loaded at startup | ✅ Done 2026-11-18 |

---

## Phase 5 — Infrastructure

| # | Item | Status |
|---|------|--------|
| 5.1 | `Dockerfile` — multi-stage build (base → deps → app) | ✅ Done — built and checked 2026-11-18: 2.9 GB, CPU-only torch, non-root, embedding model baked in; the model loads on a read-only filesystem with no network |
| 5.2 | `docker-compose.yml` — local dev stack (app + Redis + Prometheus + Grafana) | ✅ Done |
| 5.3 | `k8s/deployment.yaml` — K8s deployment with resource limits | ✅ Done — non-root, read-only filesystem, no GPU (vLLM runs separately), API key from the `kinnow-secrets` secret, startup probe for the model load. Never applied to a cluster |
| 5.4 | `k8s/service.yaml` — K8s service + ingress | ✅ Done |
| 5.5 | `k8s/networkpolicy.yaml` — K8s NetworkPolicy (Section 20) | ✅ Done |
| 5.6 | `k8s/pod-security.yaml` — PodSecurityContext (non-root, read-only FS) | ✅ Done |
| 5.7 | `monitoring/prometheus.yml` — scrape config | ✅ Done |
| 5.8 | `monitoring/grafana-dashboard.json` — latency, block rate, error rate panels | ✅ Done |
| 5.9 | `monitoring/alerts.yml` — Prometheus alert rules (p95 > 2s, error rate > 1%) | ✅ Done |
| 5.10 | `scripts/start_vllm.sh` — launch the vLLM server (plan §8c) | ✅ Done 2026-11-18 (never run: needs a GPU host and the quantised model) |

---

## Phase 6 — CI/CD

| # | Item | Status |
|---|------|--------|
| 6.1 | `.github/workflows/ci.yml` — lint + unit tests + integration tests on every PR | ✅ Done |
| 6.2 | `.github/workflows/eval.yml` — eval gate (runs after training, blocks merge if score drops) | ✅ Done |
| 6.3 | `.github/workflows/deploy.yml` — Docker build → push ECR → canary → production | ✅ Done |
| 6.4 | `.github/dependabot.yml` — Dependabot config for pip dependency updates | ✅ Done |
| 6.5 | CI `domain-lock` job: builds centroids from `raw.jsonl`, runs the 130-case suite and the guardrail eval | ✅ Written; not yet run on GitHub |
| 6.6 | Deploy waits for CI on the same commit; production promotion is the manual `promote-production.yml` workflow | ✅ Done — GitHub required reviewers are unavailable for private repos on this plan. The deploy pipeline has never run end to end: no cluster credentials, AWS secrets or Prometheus URL are configured, and the workflows have no kubeconfig step |

---

## Phase 7 — Load Testing & Security

| # | Item | Status |
|---|------|--------|
| 7.1 | `tests/load/locustfile.py` — load test: 21 req/sec, p95 < 2s, 10 min ramp | ✅ Done |
| 7.2 | `tests/load/scenarios.py` — mixed ERP + OOS + injection query scenarios | ✅ Done |
| 7.4 | Adversarial suite — `data/eval/injection_suite.jsonl` (58 attacks) + `eval/run_adversarial.py`, 100% block gate in CI (plan 7d) | ✅ Done 2026-11-18 (58/58, each by the expected guardrail) |
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
| G.1 | All unit + integration tests passing | ✅ 299/299 locally on Python 3.11; CI on GitHub was green for commit ee52231 |
| G.2 | Eval gate: `run_full_eval.py` passes (overall ≥ 78%, GST ≥ 65%, Payroll ≥ 82%, Invoice ≥ 86%, false refusals < 3%, no category drop > 5pp) | ⏳ Blocked — needs training run |
| G.3 | Load test: 21 req/sec, p95 < 2s sustained | ⏳ Blocked — needs deployed model |
| G.4 | Guardrail audit: OOS block rate > 99%, ERP pass rate > 95% (with centroids loaded, as in production) | ✅ OOS 100%, ERP 95%, injection 100% (2026-11-18). Earlier 100% / 100% was keyword-only and the real figures were far lower |
| G.4b | Domain-lock suite (§21h): 100% pass required | ✅ 130/130 (2026-11-18) |
| G.5 | Security scan: no critical CVEs in Docker image | 🔄 The CI Trivy dependency scan passes (28 findings fixed); the built image itself has not been scanned |
| G.6 | Dependabot enabled | ✅ Done |
| G.7 | K8s NetworkPolicy + PodSecurityContext applied | ✅ Done |
| G.8 | Monitoring dashboards live and alerting tested | ⏳ Blocked — needs deployment |
| G.9 | Circuit breaker tested (manual failure injection) | ⏳ Blocked — needs deployment |
| G.10 | Canary deployment at 5% traffic — no SLO breach for 30 min | ⏳ Blocked — needs training |
| G.11 | Rollback tested | ⏳ Blocked — needs deployment |
| G.12 | `/v1/feedback` endpoint live and writing to Redis | ⏳ Blocked — needs deployment |

---

_Last updated 2026-11-18. Code for Phases 1, 4, 5, 6, 7, 8 is complete and covered by 299 tests. The v1 training data (1,927 rows) and the eval sets exist; the training run itself has not started._

**Next, in order**
1. Expert review of the dataset (2.7), and decide mixed-message behaviour (2.14).
2. Run the baseline eval (3.6), then the SFT run on Kaggle (3.7), then `eval/run_full_eval.py` on the result (G.2). Use `training/requirements-train.txt`; `sft_train.py` runs on a T4 (fp16) or an Ampere GPU (bf16); run `python training/sft_train.py --dry-run` first.
3. Build DPO pairs from the model's failures (2.12), merge, quantise, push (3.8).
4. Provide cluster details (kubeconfig or EKS cluster name), AWS secrets and the Prometheus URL; then deploy and work through G.3, G.8–G.12.

**Known caveats**
- Dataset facts came from the generating model plus secondary sources; the EPF ceiling (₹25,000 from 17 Sep 2026), Income-tax Act 2025 renumbering, ESI and bonus ceilings need checking against official notifications.
- Eval items and training rows share an author, so scores will look optimistic; add real user questions when available.
- `data/v1_training/train.jsonl`, `val.jsonl` and `data/centroids.npz` are gitignored; regenerate with `scripts/split_data.py` and `scripts/build_centroids.py`. Note `raw.jsonl` (the full dataset) is tracked.
- Multi-turn behaviour is covered only in eval; the SFT data is single-turn.
- The 14 sharp edges in `ARCHITECTURE.md` section 9 are all addressed; section 9.3 lists what is still true (shared API key per client, fixed-window Redis limit, subtle off-topic questions, deploy pipeline untested).
