"""Hybrid retrieval: dense (Chroma + bge-small) + lexical (BM25), fused via
Reciprocal Rank Fusion, then optionally reranked by a cross-encoder."""

from __future__ import annotations

import logging
import os
import re
from functools import lru_cache
from typing import Any

from auroragaze.config import settings
from auroragaze.schemas import Chunk

USE_RERANKER = os.getenv("USE_RERANKER", "1") != "0"
USE_BM25 = os.getenv("USE_BM25", "1") != "0"
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
RRF_K = 60

_logger = logging.getLogger(__name__)
_reranker_failed = False
_TOKEN = re.compile(r"[A-Za-z0-9_\-]+")


def _tokenise(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text)]


def _meta_source(meta: dict[str, Any]) -> str:
    return str(meta.get("source", meta.get("filename", "unknown")))


@lru_cache(maxsize=1)
def _collection() -> Any:
    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

    client = chromadb.PersistentClient(path=str(settings.chroma_dir))
    embedder = SentenceTransformerEmbeddingFunction(model_name="BAAI/bge-small-en-v1.5")
    return client.get_or_create_collection(name="auroragaze", embedding_function=embedder)


@lru_cache(maxsize=1)
def _corpus() -> tuple[list[str], list[str], list[dict[str, Any]]]:
    """Return (ids, documents, metadatas) for the full collection, in order."""
    coll = _collection()
    got = coll.get(include=["documents", "metadatas"])
    return (
        list(got.get("ids") or []),
        list(got.get("documents") or []),
        list(got.get("metadatas") or []),
    )


@lru_cache(maxsize=1)
def _bm25() -> Any:
    from rank_bm25 import BM25Okapi

    _, docs, _ = _corpus()
    return BM25Okapi([_tokenise(d) for d in docs]) if docs else None


@lru_cache(maxsize=1)
def _reranker() -> Any | None:
    """Lazy-load the cross-encoder. Returns None and disables itself on failure."""
    global _reranker_failed
    if _reranker_failed:
        return None
    try:
        from sentence_transformers import CrossEncoder

        return CrossEncoder(RERANKER_MODEL, max_length=512)
    except Exception as exc:
        _logger.warning("reranker load failed (%s); falling back to dense-only", exc)
        _reranker_failed = True
        return None


def _chunk_from(doc: str, meta: dict[str, Any], score: float | None = None) -> Chunk:
    return Chunk(
        text=doc,
        source=_meta_source(meta),
        event_date=str(meta.get("date", "")) or None,
        kp_peak=meta.get("kp_peak") or meta.get("kp_at_observation"),
        score=score,
    )


def dense_search(query: str, k: int = 20, persona: str | None = None) -> list[tuple[str, Chunk]]:
    """Return [(doc_id, chunk)] in dense-similarity order."""
    where: dict[str, Any] | None = None
    if persona:
        where = {"persona": {"$in": [persona, "both"]}}
    res = _collection().query(query_texts=[query], n_results=k, where=where)
    ids = res.get("ids", [[]])[0]
    docs = res["documents"][0]
    metas = res["metadatas"][0]
    distances = res["distances"][0] if "distances" in res else [None] * len(docs)
    out: list[tuple[str, Chunk]] = []
    for doc_id, doc, meta, dist in zip(ids, docs, metas, distances, strict=False):
        score = (1.0 - dist) if dist is not None else None
        out.append((doc_id, _chunk_from(doc, meta, score)))
    return out


def bm25_search(query: str, k: int = 20, persona: str | None = None) -> list[tuple[str, Chunk]]:
    """Return [(doc_id, chunk)] in BM25-score order, persona-filtered."""
    bm25 = _bm25()
    if bm25 is None:
        return []
    ids, docs, metas = _corpus()
    if not ids:
        return []
    scores = bm25.get_scores(_tokenise(query))
    triples = list(zip(ids, docs, metas, strict=True))
    paired = sorted(zip(scores, triples, strict=True), key=lambda p: float(p[0]), reverse=True)
    out: list[tuple[str, Chunk]] = []
    for score, (doc_id, doc, meta) in paired:
        if persona and meta.get("persona") not in (persona, "both", None):
            continue
        out.append((doc_id, _chunk_from(doc, meta, float(score))))
        if len(out) >= k:
            break
    return out


def _rrf_fuse(
    rankings: list[list[tuple[str, Chunk]]],
    k_const: int = RRF_K,
) -> list[Chunk]:
    """Reciprocal Rank Fusion. score = sum 1/(k + rank) across rankings."""
    score: dict[str, float] = {}
    chunk: dict[str, Chunk] = {}
    for ranking in rankings:
        for rank, (doc_id, c) in enumerate(ranking):
            score[doc_id] = score.get(doc_id, 0.0) + 1.0 / (k_const + rank + 1)
            chunk[doc_id] = c
    fused = sorted(score.items(), key=lambda p: p[1], reverse=True)
    return [chunk[doc_id].model_copy(update={"score": s}) for doc_id, s in fused]


def rerank(query: str, candidates: list[Chunk], top_k: int = 5) -> list[Chunk]:
    if not candidates:
        return []
    model = _reranker()
    if model is None:
        return candidates[:top_k]
    try:
        pairs = [(query, c.text) for c in candidates]
        scores = model.predict(pairs)
    except Exception as exc:
        _logger.warning("reranker predict failed (%s); using fused order", exc)
        return candidates[:top_k]
    ranked = sorted(zip(candidates, scores, strict=True), key=lambda p: float(p[1]), reverse=True)
    return [c.model_copy(update={"score": float(s)}) for c, s in ranked[:top_k]]


def retrieve(query: str, k: int = 5, persona: str | None = None) -> list[Chunk]:
    dense = dense_search(query=query, k=20, persona=persona)
    rankings: list[list[tuple[str, Chunk]]] = [dense]
    if USE_BM25:
        rankings.append(bm25_search(query=query, k=20, persona=persona))
    fused = _rrf_fuse(rankings)[:15]
    if USE_RERANKER:
        return rerank(query=query, candidates=fused, top_k=k)
    return fused[:k]
