"""Academic grading endpoints (teacher/admin)."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from app.api.deps import rate_limit_chat, require_teacher
from app.core import correction_log, reports_store
from app.models.grading import GradeResponse, ReviewRequest
from app.services import grade_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/grade", tags=["grading"])


def _payload_dict(payload: ReviewRequest) -> dict:
    if hasattr(payload, "model_dump"):
        return payload.model_dump()
    return payload.dict()


@router.post("", response_model=GradeResponse)
async def grade_assignment(
    file: UploadFile = File(...),
    assignment_id: Optional[str] = Form(None),
    level: str = Form(""),
    unit_id: str = Form(""),
    skip_cache: bool = Form(False),
    _: dict = Depends(require_teacher),
    __: None = Depends(rate_limit_chat),
) -> GradeResponse:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    try:
        record = await asyncio.to_thread(
            grade_service.grade_submission,
            filename=file.filename or "submission.txt",
            content=content,
            assignment_id=assignment_id,
            level=level,
            unit_id=unit_id,
            skip_cache=skip_cache,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Grading pipeline failed")
        raise HTTPException(
            status_code=503,
            detail=f"Grading failed. Is Ollama running and is curriculum indexed? ({exc})",
        ) from exc
    return GradeResponse(**record)


@router.get("/corrections")
async def list_corrections(
    limit: int = Query(200, ge=1, le=1000),
    assignment_id: Optional[str] = Query(None),
    _: dict = Depends(require_teacher),
) -> dict:
    return {
        "corrections": correction_log.list_corrections(
            limit=limit, assignment_id=assignment_id
        )
    }


@router.get("/reports")
async def list_reports(
    limit: int = Query(50, ge=1, le=200),
    _: dict = Depends(require_teacher),
) -> dict:
    return {"reports": reports_store.list_reports(limit=limit)}


@router.get("/{assignment_id}", response_model=GradeResponse)
async def get_grade(
    assignment_id: str,
    _: dict = Depends(require_teacher),
) -> GradeResponse:
    record = reports_store.load_report(assignment_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Assignment report not found")
    public = grade_service._public_report(record)
    return GradeResponse(**public)


@router.post("/{assignment_id}/review", response_model=GradeResponse)
async def review_grade(
    assignment_id: str,
    payload: ReviewRequest,
    user: dict = Depends(require_teacher),
) -> GradeResponse:
    try:
        record = await asyncio.to_thread(
            grade_service.apply_review,
            assignment_id,
            _payload_dict(payload),
            user.get("sub") or "teacher",
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Assignment report not found")
    return GradeResponse(**record)
