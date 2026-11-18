# Multi-stage build: deps → app
# Stage 1 installs Python deps into a clean layer.
# Stage 2 copies only what's needed — no build tools in production image.

# ---- Stage 1: dependency builder ----
FROM python:3.11-slim AS builder

WORKDIR /build

# CPU-only torch: the API only runs a small embedding model; the default Linux wheel
# pulls in several GB of CUDA libraries. (vLLM runs in its own GPU container.)
ENV PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt


# ---- Stage 2: production image ----
FROM python:3.11-slim AS app

# Non-root user for security (Section 20)
RUN addgroup --system kinnow && adduser --system --ingroup kinnow kinnow

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY guardrails/ guardrails/
COPY serve/ serve/

# Create data dir; centroids.npy is optional — mounted at runtime via K8s volume
# or S3-downloaded on startup. The server runs in keyword-only mode without it.
RUN mkdir -p data

# Owned by non-root user
RUN chown -R kinnow:kinnow /app

USER kinnow

EXPOSE 8000

# Healthcheck so Docker/K8s knows when the container is ready
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

CMD ["uvicorn", "serve.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--log-level", "warning"]
