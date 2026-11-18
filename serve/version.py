"""Model version and process start time, reported by /health and in every chat response."""

import os
import time

# MODEL_VERSION identifies what is serving traffic (plan 12c: tell canary from stable apart).
# It defaults to MODEL_NAME, the name sent to vLLM.
MODEL_VERSION = os.getenv('MODEL_VERSION') or os.getenv('MODEL_NAME', 'kinnow-v1')

START_TIME = time.time()
