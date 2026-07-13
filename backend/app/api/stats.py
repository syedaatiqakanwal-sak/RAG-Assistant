"""System status, statistics and activity endpoints."""
from __future__ import annotations

import logging
import socket
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Query

from app.api.deps import require_admin
from app.core.config import settings
from app.core.state import app_state
from app.services import document_service, indexing_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["system"])


def _ollama_reachable() -> bool:
    parsed = urlparse(settings.OLLAMA_BASE_URL)
    host = parsed.hostname or "localhost"
    port = parsed.port or 11434
    try:
        with socket.create_connection((host, port), timeout=1.5):
            return True
    except OSError:
        return False


@router.get("/status")
async def status() -> dict:
    """Public health/status check used by the frontend banner."""
    docs = document_service.list_documents()
    return {
        "status": "online",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "ollama": {
            "model": settings.OLLAMA_MODEL,
            "reachable": _ollama_reachable(),
            "base_url": settings.OLLAMA_BASE_URL,
        },
        "embedding_model": settings.EMBEDDING_MODEL,
        "total_documents": len(docs),
        "total_chunks": indexing_service.total_chunks(),
    }


@router.get("/stats")
async def stats(_: dict = Depends(require_admin)) -> dict:
    """Detailed statistics for the admin dashboard."""
    summary = document_service.stats_summary()
    return {
        "total_documents": summary["total_documents"],
        "total_chunks": indexing_service.total_chunks(),
        "questions_asked": app_state.questions_asked,
        "by_category": summary["by_category"],
        "total_size": summary["total_size"],
        "ollama_reachable": _ollama_reachable(),
    }


@router.get("/activity")
async def activity(limit: int = Query(50, ge=1, le=200),
                   _: dict = Depends(require_admin)) -> dict:
    return {"activity": app_state.recent_activity(limit)}
