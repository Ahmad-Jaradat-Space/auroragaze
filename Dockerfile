FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/app/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/app/.cache/st \
    TRANSFORMERS_CACHE=/app/.cache/huggingface

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install CPU-only torch first (much smaller than the GPU wheel pulled by transitive deps).
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu \
    "torch==2.4.1+cpu"

COPY pyproject.toml README.md ./
COPY src ./src
COPY frontend ./frontend
COPY data/corpus ./data/corpus

RUN pip install -e .

# Pre-warm only the embedding model (small, ~130 MB) and ingest the
# corpus. The cross-encoder reranker is OFF in production: hybrid
# dense + BM25 + RRF gives ~0.92 eval precision without it, which
# is sufficient for a 35-doc curated corpus and avoids the 4 GB RAM
# requirement and ~570 MB image bloat.
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('BAAI/bge-small-en-v1.5')"
RUN python -c "from auroragaze.retrieval.ingest import ingest_corpus; print('ingested:', ingest_corpus())"

# Strip caches and bytecode that we don't need at runtime.
RUN find /usr/local/lib/python3.11 -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true \
 && find /usr/local/lib/python3.11 -name '*.pyc' -delete 2>/dev/null || true \
 && rm -rf /root/.cache/pip /tmp/* /var/tmp/*


FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/app/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/app/.cache/st \
    USE_RERANKER=0

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

EXPOSE 8080

CMD ["uvicorn", "auroragaze.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
