from pathlib import Path
from typing import Any

from auroragaze.config import settings


def _parse_metadata(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    meta: dict[str, str] = {}
    body_start = 0
    if lines and lines[0].startswith("# "):
        for token in lines[0][2:].split():
            if "=" in token:
                k, v = token.split("=", 1)
                meta[k] = v
        body_start = 1
    body = "\n".join(lines[body_start:]).strip()
    return meta, body


def _coerce_meta(meta: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in meta.items():
        if k in {"kp_peak", "kp_at_observation"}:
            try:
                out[k] = float(v)
                continue
            except ValueError:
                pass
        if k == "bz_min":
            try:
                out[k] = float(v)
                continue
            except ValueError:
                pass
        out[k] = v
    return out


def ingest_corpus(
    corpus_dir: Path | None = None,
    chroma_dir: Path | None = None,
    collection_name: str = "auroragaze",
) -> int:
    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

    corpus_dir = corpus_dir or settings.corpus_dir
    chroma_dir = chroma_dir or settings.chroma_dir
    chroma_dir.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(chroma_dir))
    embedder = SentenceTransformerEmbeddingFunction(model_name="BAAI/bge-small-en-v1.5")
    collection = client.get_or_create_collection(name=collection_name, embedding_function=embedder)

    files = sorted(corpus_dir.glob("*.txt"))
    ids: list[str] = []
    docs: list[str] = []
    metas: list[dict[str, Any]] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        meta, body = _parse_metadata(text)
        meta = _coerce_meta(meta)
        meta["filename"] = path.name
        ids.append(path.stem)
        docs.append(body)
        metas.append(meta)

    if ids:
        collection.upsert(ids=ids, documents=docs, metadatas=metas)
    return len(ids)
