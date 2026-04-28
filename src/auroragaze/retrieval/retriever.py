from functools import lru_cache
from typing import Any

from auroragaze.config import settings
from auroragaze.schemas import Chunk


@lru_cache(maxsize=1)
def _collection() -> Any:
    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

    client = chromadb.PersistentClient(path=str(settings.chroma_dir))
    embedder = SentenceTransformerEmbeddingFunction(model_name="BAAI/bge-small-en-v1.5")
    return client.get_or_create_collection(name="auroragaze", embedding_function=embedder)


@lru_cache(maxsize=1)
def _reranker() -> Any:
    from sentence_transformers import CrossEncoder

    return CrossEncoder("BAAI/bge-reranker-v2-m3", max_length=512)


def _meta_source(meta: dict[str, Any]) -> str:
    return str(meta.get("source", meta.get("filename", "unknown")))


def dense_search(query: str, k: int = 20, persona: str | None = None) -> list[Chunk]:
    where: dict[str, Any] | None = None
    if persona:
        where = {"persona": {"$in": [persona, "both"]}}
    res = _collection().query(query_texts=[query], n_results=k, where=where)
    docs = res["documents"][0]
    metas = res["metadatas"][0]
    distances = res["distances"][0] if "distances" in res else [None] * len(docs)
    chunks: list[Chunk] = []
    for doc, meta, dist in zip(docs, metas, distances, strict=False):
        chunks.append(
            Chunk(
                text=doc,
                source=_meta_source(meta),
                event_date=str(meta.get("date", "")) or None,
                kp_peak=meta.get("kp_peak") or meta.get("kp_at_observation"),
                score=(1.0 - dist) if dist is not None else None,
            )
        )
    return chunks


def rerank(query: str, candidates: list[Chunk], top_k: int = 5) -> list[Chunk]:
    if not candidates:
        return []
    pairs = [(query, c.text) for c in candidates]
    scores = _reranker().predict(pairs)
    ranked = sorted(zip(candidates, scores, strict=True), key=lambda p: float(p[1]), reverse=True)
    out: list[Chunk] = []
    for chunk, score in ranked[:top_k]:
        out.append(chunk.model_copy(update={"score": float(score)}))
    return out


def retrieve(query: str, k: int = 5, persona: str | None = None) -> list[Chunk]:
    candidates = dense_search(query=query, k=20, persona=persona)
    return rerank(query=query, candidates=candidates, top_k=k)
