"""Document management endpoints (admin protected, except listing/preview reads)."""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from app.api.deps import require_admin
from app.models.documents import (
    DeleteRequest,
    DocumentListResponse,
    DocumentPreview,
    GenericResponse,
    UploadResponse,
    UploadResultItem,
)
from app.services import document_service, indexing_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=DocumentListResponse)
async def list_documents(search: Optional[str] = Query(None)) -> DocumentListResponse:
    docs = (document_service.search_documents(search)
            if search else document_service.list_documents())
    return DocumentListResponse(documents=docs, total=len(docs))


@router.post("/upload", response_model=UploadResponse)
async def upload_documents(
    files: List[UploadFile] = File(...),
    reindex: bool = Query(True, description="Re-index after a successful upload"),
    _: dict = Depends(require_admin),
) -> UploadResponse:
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    results: List[UploadResultItem] = []
    any_saved = False
    for upload in files:
        content = await upload.read()
        ok, detail = document_service.save_single(upload.filename, content)
        any_saved = any_saved or ok
        results.append(UploadResultItem(filename=upload.filename, success=ok, detail=detail))

    reindex_result = None
    if any_saved and reindex:
        reindex_result = await indexing_service.reindex_all()

    saved = sum(1 for r in results if r.success)
    return UploadResponse(
        success=any_saved,
        message=f"Uploaded {saved} of {len(results)} file(s)"
                + (" and re-indexed." if reindex_result else "."),
        results=results,
        reindex=reindex_result,
    )


@router.post("/reindex", response_model=GenericResponse)
async def reindex_documents(_: dict = Depends(require_admin)) -> GenericResponse:
    result = await indexing_service.reindex_all()
    return GenericResponse(
        success=True,
        message=f"Re-indexed {result['documents']} document(s) into "
                f"{result['chunks']} chunk(s).",
        data=result,
    )


@router.post("/delete", response_model=GenericResponse)
async def delete_documents(payload: DeleteRequest,
                           _: dict = Depends(require_admin)) -> GenericResponse:
    if not payload.ids:
        raise HTTPException(status_code=400, detail="No document ids provided")
    deleted, errors = document_service.delete_by_ids(payload.ids)
    if deleted:
        await indexing_service.reindex_all()
    return GenericResponse(
        success=deleted > 0,
        message=f"Deleted {deleted} document(s)."
                + (f" {len(errors)} error(s)." if errors else ""),
        data={"deleted": deleted, "errors": errors},
    )


@router.delete("/{doc_id}", response_model=GenericResponse)
async def delete_document(doc_id: str,
                          _: dict = Depends(require_admin)) -> GenericResponse:
    deleted, errors = document_service.delete_by_ids([doc_id])
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Document not found")
    await indexing_service.reindex_all()
    return GenericResponse(success=True, message="Document deleted and re-indexed.")


@router.get("/{doc_id}/preview", response_model=DocumentPreview)
async def preview_document(doc_id: str) -> DocumentPreview:
    data = document_service.preview(doc_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentPreview(**data)
