"""Local cross-encoder reranking of vector-search hits.

Uses ``sentence-transformers.CrossEncoder`` (already a dependency of the
installed ``sentence-transformers`` package). The model is loaded lazily on
first grade request. If loading fails, hits are returned in cosine order and
``rerank_score`` is left null.
"""
from __future__ import annotations

import logging
import math
import threading
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_model = None
_failed = False
_lock = threading.Lock()


def _sigmoid(value: float) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-float(value)))
    except OverflowError:
        return 0.0 if value < 0 else 1.0


def get_reranker():
    """Return the CrossEncoder singleton, or None if unavailable."""
    global _model, _failed
    if not settings.ENABLE_RERANKER:
        return None
    if _failed:
        return None
    if _model is None:
        with _lock:
            if _model is None and not _failed:
                try:
                    from sentence_transformers import CrossEncoder

                    logger.info("Loading reranker model: %s", settings.RERANKER_MODEL)
                    _model = CrossEncoder(settings.RERANKER_MODEL)
                except Exception:
                    logger.exception(
                        "Failed to load reranker %s; cosine order will be used",
                        settings.RERANKER_MODEL,
                    )
                    _failed = True
                    return None
    return _model


def rerank_hits(
    query: str,
    hits: List[Dict[str, Any]],
    top_n: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Attach rerank scores and reorder *hits*. Cosine scores are preserved.

    Hits are never dropped for being below a score threshold — the caller always
    sees what matched, including near-misses.
    """
    top_n = top_n or settings.GRADE_RERANK_TOP_N
    if not hits:
        return []

    model = get_reranker()
    annotated = [dict(hit) for hit in hits]

    if model is None:
        for hit in annotated:
            hit.setdefault("rerank_score", None)
            hit.setdefault("rerank_score_normalized", None)
        annotated.sort(key=lambda h: h.get("cosine_score", 0.0), reverse=True)
        return annotated

    pairs = [(query, hit.get("content") or "") for hit in annotated]
    try:
        scores = model.predict(pairs)
    except Exception:
        logger.exception("Reranker inference failed; using cosine order")
        for hit in annotated:
            hit.setdefault("rerank_score", None)
            hit.setdefault("rerank_score_normalized", None)
        annotated.sort(key=lambda h: h.get("cosine_score", 0.0), reverse=True)
        return annotated

    for hit, score in zip(annotated, scores):
        raw = float(score)
        hit["rerank_score"] = raw
        hit["rerank_score_normalized"] = _sigmoid(raw)

    annotated.sort(
        key=lambda h: (
            h.get("rerank_score") is not None,
            h.get("rerank_score") if h.get("rerank_score") is not None else -1e9,
        ),
        reverse=True,
    )
    return annotated
