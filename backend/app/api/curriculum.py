"""Curriculum knowledge-base endpoints (teacher/admin)."""
from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from app.api.deps import require_teacher
from app.models.documents import GenericResponse
from app.services import curriculum_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/curriculum", tags=["curriculum"])

_VALID_DOC_TYPES = {"syllabus", "brief", "lecture"}


@router.get("/status")
async def curriculum_status(_: dict = Depends(require_teacher)) -> dict:
    return curriculum_service.status()


@router.post("/sync", response_model=GenericResponse)
async def sync_curriculum(
    force: bool = Query(False, description="Re-index every file, ignoring the hash manifest"),
    _: dict = Depends(require_teacher),
) -> GenericResponse:
    result = await curriculum_service.sync(force=force)
    return GenericResponse(
        success=len(result.get("failed") or []) == 0,
        message=(
            f"Curriculum sync complete: {len(result.get('added') or [])} added, "
            f"{len(result.get('updated') or [])} updated, "
            f"{len(result.get('skipped') or [])} unchanged, "
            f"{len(result.get('deleted') or [])} removed."
        ),
        data=result,
    )


@router.post("/upload", response_model=GenericResponse)
async def upload_curriculum(
    files: List[UploadFile] = File(...),
    level: str = Form(...),
    unit_id: str = Form(...),
    unit_name: str = Form(""),
    doc_type: str = Form("syllabus"),
    _: dict = Depends(require_teacher),
) -> GenericResponse:
    doc_type = doc_type.strip().lower()
    if not level.strip() or not unit_id.strip():
        raise HTTPException(status_code=400, detail="level and unit_id are required")
    if doc_type not in _VALID_DOC_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"doc_type must be one of {sorted(_VALID_DOC_TYPES)}",
        )
    saved = 0
    details = []
    for upload in files:
        content = await upload.read()
        ok, detail, _path = curriculum_service.save_curriculum_file(
            upload.filename or "untitled.txt",
            content,
            level=level.strip(),
            unit_id=unit_id.strip(),
            unit_name=(unit_name or unit_id).strip(),
            doc_type=doc_type,
        )
        details.append({"filename": upload.filename, "success": ok, "detail": detail})
        if ok:
            saved += 1
    reindex = None
    if saved:
        reindex = await curriculum_service.sync(force=False)
    return GenericResponse(
        success=saved > 0,
        message=f"Uploaded {saved} of {len(files)} curriculum file(s).",
        data={"results": details, "sync": reindex},
    )
