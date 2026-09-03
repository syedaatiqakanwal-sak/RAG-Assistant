"""GRADING_MEMORY_KB: append-mostly store of human-approved grading examples."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.vectorstore import (
    add_texts,
    chroma_safe_metadata,
    get_grading_memory_store,
    invalidate,
    query_collection,
)
from app.core.reranker import rerank_hits

logger = logging.getLogger(__name__)


def add_approved_example(
    *,
    assignment_id: str,
    submission_text: str,
    similarity_verdict: str,
    final_score: float,
    feedback_text: str,
    level: str = "",
    unit_id: str = "",
    unit_name: str = "",
    reviewed_by: str = "",
) -> str:
    """Upsert one human-approved calibration example. Returns the Chroma id."""
    example_id = f"gm_{assignment_id}"
    store = get_grading_memory_store()
    meta = chroma_safe_metadata({
        "assignment_id": assignment_id,
        "similarity_verdict": similarity_verdict,
        "final_score": float(final_score),
        "feedback_text": (feedback_text or "")[:8000],
        "level": level or "",
        "unit_id": unit_id or "",
        "unit_name": unit_name or "",
        "approved": True,
        "reviewed_by": reviewed_by or "",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    text = (submission_text or "").strip()[:12000] or "(empty submission)"
    add_texts(store, [text], [meta], [example_id])
    invalidate()
    logger.info("Stored approved grading example %s (unit=%s)", example_id, unit_id)
    return example_id


def search_calibration_examples(
    query: str,
    *,
    unit_id: str = "",
    k: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Retrieve similar *approved* past grades, optionally restricted to a unit."""
    k = k or settings.CALIBRATION_EXAMPLE_COUNT
    store = get_grading_memory_store()
    if store._collection.count() == 0:
        return []

    where: Optional[Dict[str, Any]]
    if unit_id:
        where = {"$and": [{"approved": True}, {"unit_id": unit_id}]}
    else:
        where = {"approved": True}

    hits = query_collection(store, query, max(k, settings.GRADE_TOP_K), where=where)
    if not hits and unit_id:
        hits = query_collection(
            store, query, max(k, settings.GRADE_TOP_K), where={"approved": True}
        )
    if not hits:
        return []

    ranked = rerank_hits(query, hits, top_n=k)
    return ranked[:k]
