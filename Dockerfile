FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/app/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/app/.cache/st

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
COPY frontend ./frontend
COPY data/corpus ./data/corpus

RUN pip install -e .

# Pre-warm: download embedding + reranker weights and ingest corpus into
# ChromaDB so the image boots ready-to-serve. No network needed at runtime
# for retrieval.
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; \
    SentenceTransformer('BAAI/bge-small-en-v1.5'); \
    CrossEncoder('BAAI/bge-reranker-v2-m3', max_length=512)"
RUN python -c "from auroragaze.retrieval.ingest import ingest_corpus; print('ingested:', ingest_corpus())"

EXPOSE 8080

CMD ["uvicorn", "auroragaze.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
