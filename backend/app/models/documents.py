"""Document-related schemas."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class DocumentMeta(BaseModel):
    id: str
    name: str
    category: str
    file_type: str
    size: int
    size_human: str
    modified: str
    path: str


class DocumentListResponse(BaseModel):
    documents: List[DocumentMeta]
    total: int


class UploadResultItem(BaseModel):
    filename: str
    success: bool
    detail: str


class UploadResponse(BaseModel):
    success: bool
    message: str
    results: List[UploadResultItem]
    reindex: Optional[dict] = None


class DeleteRequest(BaseModel):
    ids: List[str]


class GenericResponse(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None


class DocumentPreview(BaseModel):
    id: str
    name: str
    file_type: str
    content: str
    truncated: bool
