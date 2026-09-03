"""Chat request/response schemas."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class Source(BaseModel):
    content: str = ""
    preview: str = ""
    source: str = "Unknown"
    filename: str = "Unknown"
    file_type: str = "Unknown"
    category: str = "Unknown"
    page: Optional[int] = None


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    temperature: float = Field(0.2, ge=0.0, le=1.0)
    top_k: int = Field(4, ge=1, le=10)
    stream: bool = False


class ChatResponse(BaseModel):
    answer: str
    sources: List[Source]
    latency_ms: int
    timestamp: str
