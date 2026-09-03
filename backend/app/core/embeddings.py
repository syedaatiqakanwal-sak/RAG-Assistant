"""Embedding model management.

Two process-wide singletons:

* ``get_embeddings()`` — lightweight model used by the existing /api/chat flow.
* ``get_grading_embeddings()`` — higher-capacity model used by CURRICULUM_KB and
  GRADING_MEMORY_KB. Falls back to the chat model if the grading model cannot
  be loaded (e.g. first-run download failure).
"""
from __future__ import annotations

import logging
import threading

from app.core.config import settings

logger = logging.getLogger(__name__)

_chat_embeddings = None
_grading_embeddings = None
_lock = threading.Lock()


def _build_hf(model_name: str, *, normalize: bool = False):
    from langchain_huggingface import HuggingFaceEmbeddings

    kwargs = {
        "model_name": model_name,
        "model_kwargs": {"device": "cpu"},
    }
    if normalize:
        kwargs["encode_kwargs"] = {"normalize_embeddings": True}
    logger.info("Loading embedding model: %s", model_name)
    return HuggingFaceEmbeddings(**kwargs)


def get_embeddings():
    """Return the chat/general-purpose HuggingFaceEmbeddings singleton."""
    global _chat_embeddings
    if _chat_embeddings is None:
        with _lock:
            if _chat_embeddings is None:
                _chat_embeddings = _build_hf(settings.EMBEDDING_MODEL, normalize=False)
    return _chat_embeddings


def get_grading_embeddings():
    """Return the grading/curriculum embedding singleton (bge by default)."""
    global _grading_embeddings
    if _grading_embeddings is None:
        with _lock:
            if _grading_embeddings is None:
                try:
                    _grading_embeddings = _build_hf(
                        settings.GRADING_EMBEDDING_MODEL, normalize=True
                    )
                except Exception:
                    logger.exception(
                        "Failed to load grading embedding model %s; "
                        "falling back to chat model %s",
                        settings.GRADING_EMBEDDING_MODEL,
                        settings.EMBEDDING_MODEL,
                    )
                    _grading_embeddings = get_embeddings()
    return _grading_embeddings
