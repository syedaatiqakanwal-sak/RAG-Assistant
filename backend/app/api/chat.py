"""Chat endpoints: JSON answer, SSE streaming, and suggestions."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.deps import client_id, rate_limit_chat
from app.models.chat import ChatRequest, ChatResponse
from app.services import chat_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request,
               _: None = Depends(rate_limit_chat)) -> ChatResponse:
    """Non-streaming chat: returns the full answer and sources as JSON."""
    try:
        text, sources, latency = await chat_service.answer(
            payload.question, payload.temperature, payload.top_k,
            client=client_id(request),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Chat failed")
        raise HTTPException(
            status_code=503,
            detail=f"Failed to generate answer. Is Ollama running? ({exc})",
        )
    return ChatResponse(
        answer=text,
        sources=sources,
        latency_ms=latency,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.post("/stream")
async def chat_stream(payload: ChatRequest, request: Request,
                      _: None = Depends(rate_limit_chat)) -> StreamingResponse:
    """Server-Sent Events stream.

    Event sequence:
      event: sources   data: [ ...source objects... ]
      event: token     data: {"token": "..."}   (repeated)
      event: done      data: {"ok": true}
      event: error     data: {"detail": "..."}   (on failure)
    """
    try:
        token_iter, sources = await chat_service.stream(
            payload.question, payload.temperature, payload.top_k,
            client=client_id(request),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Chat stream init failed")
        raise HTTPException(
            status_code=503,
            detail=f"Failed to start answer stream. Is Ollama running? ({exc})",
        )

    async def event_generator():
        yield _sse("sources", sources)
        try:
            async for token in token_iter:
                yield _sse("token", {"token": token})
            yield _sse("done", {"ok": True})
        except Exception as exc:  # noqa: BLE001
            logger.exception("Error while streaming tokens")
            yield _sse("error", {"detail": str(exc)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/suggestions")
async def suggestions() -> dict:
    return {"suggestions": chat_service.suggested_questions()}


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
