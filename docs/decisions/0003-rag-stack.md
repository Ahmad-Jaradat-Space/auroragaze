# 0003 — ChromaDB + bge-small + bge-reranker-v2-m3, not pgvector

## Context

The retrieval layer needs:
- Persistent vector storage across restarts.
- Decent recall on a small (~25 doc) corpus.
- Reranking to keep precision@3 high.
- No external service dependency for the demo deploy.
- A path to swap in a hosted store later without touching the graph code.

Choices considered: ChromaDB (local persistent), pgvector (Postgres
extension), Qdrant Cloud (hosted), in-memory FAISS, plain BM25.

## Decision

ChromaDB persistent at `data/chroma/` with `BAAI/bge-small-en-v1.5`
embeddings (384-dim, ~130MB) and `BAAI/bge-reranker-v2-m3` cross-encoder
for reranking. Hybrid retrieval is dense top-20 → rerank → top-5.

The retriever is a pure function `retrieve(query, k, persona) -> list[Chunk]`.
The graph never imports ChromaDB directly. Swapping the store is one file
change.

## Consequences

- Zero external services for the live demo: one Docker container ships the
  whole product. Lower deploy surface, lower failure modes.
- bge-small + bge-reranker-v2-m3 together give a measurable lift in
  precision@3 over dense-only on this corpus (eval reports the delta).
- Memory footprint at runtime: ~700MB for both models loaded. Fits in
  Fly.io's 1GB free tier with headroom.
- Persistent ChromaDB is baked into the Docker image at build time, so
  cold-start is one query later than dense-only but never has to ingest
  on boot.
- If the corpus grows past ~10k documents we revisit. pgvector with a
  hosted Postgres is the most likely upgrade path; a separate ADR will
  capture the trigger.
