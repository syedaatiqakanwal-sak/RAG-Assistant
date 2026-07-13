"""Chat operations that wrap the RAG core and record activity."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncIterator, Dict, List, Tuple

from app.core import rag
from app.core.state import app_state

logger = logging.getLogger(__name__)


async def answer(question: str, temperature: float, top_k: int,
                 client: str = "anonymous") -> Tuple[str, List[Dict], int]:
    """Return (answer_text, sources, latency_ms) for a non-streaming request."""
    start = time.perf_counter()
    text, sources = await asyncio.to_thread(rag.answer, question, temperature, top_k)
    latency_ms = int((time.perf_counter() - start) * 1000)
    app_state.record_question(question, sources=len(sources),
                              latency_ms=latency_ms, client=client)
    return text, sources, latency_ms


async def stream(question: str, temperature: float, top_k: int,
                 client: str = "anonymous") -> Tuple[AsyncIterator[str], List[Dict]]:
    """Resolve sources, then return an async generator of answer tokens.

    The synchronous token generator from the RAG core is pumped through a thread
    so it never blocks the event loop.
    """
    start = time.perf_counter()
    token_iter, sources = await asyncio.to_thread(rag.stream, question, temperature, top_k)

    async def _aiter() -> AsyncIterator[str]:
        loop = asyncio.get_running_loop()
        sentinel = object()
        it = iter(token_iter)

        def _next():
            try:
                return next(it)
            except StopIteration:
                return sentinel

        while True:
            token = await loop.run_in_executor(None, _next)
            if token is sentinel:
                break
            yield token

        latency_ms = int((time.perf_counter() - start) * 1000)
        app_state.record_question(question, sources=len(sources),
                                  latency_ms=latency_ms, client=client)

    return _aiter(), sources


def suggested_questions() -> List[str]:
    """Generate simple suggested questions based on indexed document names."""
    from app.services import document_service

    docs = document_service.list_documents()
    base = [
        "What are the main topics covered in the documents?",
        "Give me a summary of the available information.",
        "What key facts can you find in the documents?",
    ]
    for doc in docs[:3]:
        stem = doc["name"].rsplit(".", 1)[0].replace("_", " ").replace("-", " ")
        base.append(f"What does the document '{stem}' say?")
    return base[:6]
