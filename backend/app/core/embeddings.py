"""Embedding model management.

The HuggingFace embedding model is relatively expensive to construct (it loads a
sentence-transformers model into memory), so we build it once and reuse the
singleton across ingestion and retrieval.
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_embeddings = None
_lock = threading.Lock()


def get_embeddings():
    """Return a process-wide singleton HuggingFaceEmbeddings instance."""
    global _embeddings
    if _embeddings is None:
        with _lock:
            if _embeddings is None:
                # Imported lazily so importing the app package doesn't pull in
                # torch/sentence-transformers until embeddings are actually used.
                from langchain_huggingface import HuggingFaceEmbeddings

                logger.info("Loading embedding model: %s", settings.EMBEDDING_MODEL)
                _embeddings = HuggingFaceEmbeddings(model_name=settings.EMBEDDING_MODEL)
    return _embeddings
