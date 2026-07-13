"""FastAPI application entry point.

Wires up middleware, routers (all under ``/api``), a WebSocket for live status
updates, global error handling, and static serving of the frontend SPA.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import auth, chat, documents, stats
from app.core.config import settings
from app.services import document_service, indexing_service

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("zeviq")

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Production-ready RAG API powered by ChromaDB + Ollama (Llama 3.2).",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Lifecycle
# --------------------------------------------------------------------------- #
@app.on_event("startup")
async def on_startup() -> None:
    settings.ensure_dirs()
    logger.info("%s v%s starting up", settings.APP_NAME, settings.APP_VERSION)
    logger.info("Data dir:   %s", settings.DATA_DIR)
    logger.info("Chroma dir: %s", settings.CHROMA_DIR)


# --------------------------------------------------------------------------- #
# Error handling
# --------------------------------------------------------------------------- #
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)},
    )


# --------------------------------------------------------------------------- #
# Routers (mounted under /api)
# --------------------------------------------------------------------------- #
api_prefix = "/api"
app.include_router(auth.router, prefix=api_prefix)
app.include_router(chat.router, prefix=api_prefix)
app.include_router(documents.router, prefix=api_prefix)
app.include_router(stats.router, prefix=api_prefix)


@app.get("/api")
async def api_root() -> dict:
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "endpoints": [
            "POST /api/auth/login",
            "POST /api/auth/logout",
            "GET  /api/status",
            "POST /api/chat",
            "POST /api/chat/stream",
            "GET  /api/chat/suggestions",
            "GET  /api/documents",
            "POST /api/documents/upload",
            "DELETE /api/documents/{id}",
            "POST /api/documents/delete",
            "POST /api/documents/reindex",
            "GET  /api/documents/{id}/preview",
            "GET  /api/stats",
            "GET  /api/activity",
            "WS   /api/ws/status",
        ],
    }


# --------------------------------------------------------------------------- #
# WebSocket: live status updates
# --------------------------------------------------------------------------- #
@app.websocket("/api/ws/status")
async def ws_status(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            payload = {
                "total_documents": len(document_service.list_documents()),
                "total_chunks": indexing_service.total_chunks(),
            }
            await websocket.send_json(payload)
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        return
    except Exception:  # noqa: BLE001
        return


# --------------------------------------------------------------------------- #
# Static frontend (mounted last so /api routes win)
# --------------------------------------------------------------------------- #
_frontend_dir = settings.PROJECT_ROOT / "frontend"
if _frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
    logger.info("Serving frontend from %s", _frontend_dir)
