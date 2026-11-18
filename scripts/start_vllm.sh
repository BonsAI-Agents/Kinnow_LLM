#!/usr/bin/env bash
# Start the vLLM OpenAI-compatible server for the Kinnow model (plan section 8c).
#
# Needs a GPU host. The API (serve/) reaches this server over HTTP via VLLM_BASE_URL,
# so it runs as its own process or container, not inside the API image.
#
# Usage:
#   ./scripts/start_vllm.sh
#   MODEL_PATH=/models/kinnow-v1-awq VLLM_PORT=8001 ./scripts/start_vllm.sh
#
# Environment (all optional):
#   MODEL_PATH       model directory (default models/kinnow-v1-awq, written by training/quantize_awq.py)
#   MODEL_NAME       name clients request (default kinnow-v1); must equal MODEL_NAME in the API's environment
#   VLLM_PORT        port to listen on (default 8001); must match VLLM_BASE_URL
#   VLLM_EXTRA_ARGS  extra flags appended as-is (flag names change between vLLM versions)
set -euo pipefail

MODEL_PATH="${MODEL_PATH:-models/kinnow-v1-awq}"
MODEL_NAME="${MODEL_NAME:-kinnow-v1}"
VLLM_PORT="${VLLM_PORT:-8001}"

if [ ! -d "$MODEL_PATH" ]; then
    echo "Model directory not found: $MODEL_PATH" >&2
    echo "Run training/merge_adapter.py and then training/quantize_awq.py first, or set MODEL_PATH." >&2
    exit 1
fi

# shellcheck disable=SC2086  # VLLM_EXTRA_ARGS is intentionally word-split
exec python -m vllm.entrypoints.openai.api_server \
    --model "$MODEL_PATH" \
    --dtype auto \
    --max-model-len 4096 \
    --gpu-memory-utilization 0.90 \
    --tensor-parallel-size 1 \
    --host 0.0.0.0 \
    --port "$VLLM_PORT" \
    --served-model-name "$MODEL_NAME" \
    --max-num-seqs 32 \
    ${VLLM_EXTRA_ARGS:-}
