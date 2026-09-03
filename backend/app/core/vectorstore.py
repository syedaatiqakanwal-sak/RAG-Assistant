"""Chroma collection helpers for the three-tier knowledge base.

Why Chroma (not Qdrant) for this module
---------------------------------------
The existing Zeviq chat path already persists a Chroma directory and the grading
module needs three named collections with metadata filters, not a cluster-grade
vector DB. Chroma gives us:

* multiple collections in the same persist dir (chat + curriculum + memory)
* `where` filters (`approved == true`, `unit_id == ...`)
* no new service/process and no chat-index migration

Qdrant is the better *later* production choice (payload indexes, hybrid search,
filtering at scale). ``settings.VECTOR_BACKEND`` is reserved so a swap can land
behind this module without touching /api/chat.
"""
from __future__ import annotations

import json
import logging
import threading
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.embeddings import get_embeddings, get_grading_embeddings

logger = logging.getLogger(__name__)

_client = None
_stores: Dict[str, Any] = {}
_lock = threading.Lock()


def chroma_safe_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Chroma only accepts str/int/float/bool metadata values (no None, no lists)."""
    out: Dict[str, Any] = {}
    for key, value in (metadata or {}).items():
        if value is None:
            continue
        if isinstance(value, bool):
            out[key] = value
        elif isinstance(value, (str, int, float)):
            out[key] = value
        elif isinstance(value, (list, dict, tuple)):
            out[key] = json.dumps(value, ensure_ascii=False)
        else:
            out[key] = str(value)
    return out


def parse_json_meta(value: Any, default: Any = None):
    if default is None:
        default = []
    if value is None or value == "":
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def get_chroma_client():
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                import chromadb

                _client = chromadb.PersistentClient(path=str(settings.CHROMA_DIR))
    return _client


def invalidate() -> None:
    """Drop cached LangChain store wrappers after an index mutation."""
    global _stores, _client
    with _lock:
        _stores = {}
        _client = None


def _langchain_chroma(collection_name: str, embeddings, *, cosine: bool = True):
    from langchain_community.vectorstores import Chroma

    kwargs = {
        "persist_directory": str(settings.CHROMA_DIR),
        "embedding_function": embeddings,
        "collection_name": collection_name,
    }
    if cosine:
        kwargs["collection_metadata"] = {"hnsw:space": "cosine"}
    return Chroma(**kwargs)


def get_chat_store():
    """Existing general-document collection used by /api/chat."""
    name = settings.CHAT_COLLECTION
    if name not in _stores:
        with _lock:
            if name not in _stores:
                _stores[name] = _langchain_chroma(
                    name, get_embeddings(), cosine=False
                )
    return _stores[name]


def get_curriculum_store():
    name = settings.CURRICULUM_COLLECTION
    if name not in _stores:
        with _lock:
            if name not in _stores:
                _stores[name] = _langchain_chroma(
                    name, get_grading_embeddings(), cosine=True
                )
    return _stores[name]


def get_grading_memory_store():
    name = settings.GRADING_MEMORY_COLLECTION
    if name not in _stores:
        with _lock:
            if name not in _stores:
                _stores[name] = _langchain_chroma(
                    name, get_grading_embeddings(), cosine=True
                )
    return _stores[name]


def raw_collection(name: str):
    """Return the underlying Chroma collection, or None if it does not exist."""
    client = get_chroma_client()
    try:
        return client.get_collection(name)
    except Exception:
        return None


def collection_count(name: str) -> int:
    col = raw_collection(name)
    if col is None:
        return 0
    try:
        return col.count()
    except Exception:
        return 0


def cosine_similarity_from_distance(distance: float) -> float:
    """Chroma cosine space stores distance = 1 - cosine_similarity."""
    try:
        sim = 1.0 - float(distance)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, sim))


def query_collection(
    store,
    query_text: str,
    k: int,
    where: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Vector search that keeps ids, cosine similarity, documents and metadata."""
    collection = store._collection
    count = collection.count()
    if count == 0 or not (query_text or "").strip():
        return []

    n_results = max(1, min(k, count))
    embeddings = store._embedding_function
    query_embedding = embeddings.embed_query(query_text)
    kwargs: Dict[str, Any] = {
        "query_embeddings": [query_embedding],
        "n_results": n_results,
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where

    try:
        raw = collection.query(**kwargs)
    except Exception:
        logger.exception("Chroma query failed on %s", getattr(collection, "name", "?"))
        return []

    ids = (raw.get("ids") or [[]])[0]
    docs = (raw.get("documents") or [[]])[0]
    metas = (raw.get("metadatas") or [[]])[0]
    dists = (raw.get("distances") or [[]])[0]

    hits: List[Dict[str, Any]] = []
    for i, doc_id in enumerate(ids):
        distance = dists[i] if i < len(dists) else 1.0
        hits.append({
            "id": doc_id,
            "content": docs[i] if i < len(docs) else "",
            "metadata": metas[i] if i < len(metas) else {},
            "distance": float(distance) if distance is not None else 1.0,
            "cosine_score": cosine_similarity_from_distance(distance),
        })
    return hits


def delete_ids(store, ids: List[str]) -> None:
    if not ids:
        return
    try:
        store._collection.delete(ids=ids)
    except Exception:
        logger.warning("Failed to delete %d ids from collection", len(ids), exc_info=True)


def add_texts(store, texts: List[str], metadatas: List[dict], ids: List[str]) -> None:
    if not texts:
        return
    safe_metas = [chroma_safe_metadata(m) for m in metadatas]
    store.add_texts(texts=texts, metadatas=safe_metas, ids=ids)
