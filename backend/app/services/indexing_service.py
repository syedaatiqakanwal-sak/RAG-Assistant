"""Indexing operations: thin async wrapper around the ingestion core.

Indexing is CPU/IO heavy and synchronous (LangChain + sentence-transformers), so
we run it in a worker thread to avoid blocking the event loop.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Dict

from app.core import ingestion
from app.core.state import app_state

logger = logging.getLogger(__name__)

# Serialise indexing so two concurrent re-index requests can't corrupt the store.
_index_lock = asyncio.Lock()


async def reindex_all(chunk_size: int | None = None,
                     chunk_overlap: int | None = None) -> Dict:
    async with _index_lock:
        result = await asyncio.to_thread(ingestion.reindex, chunk_size, chunk_overlap)
    app_state.record_event(
        "reindex",
        f"Re-indexed {result['documents']} documents into {result['chunks']} chunks",
    )
    return result


def total_chunks() -> int:
    return ingestion.total_chunks()
