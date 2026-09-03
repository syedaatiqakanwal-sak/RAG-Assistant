"""Request/response schemas for the academic grading RAG module.

The top-level GradeResponse is shaped so a later AI-detector module and a
plagiarism-detector module can fill ``ai_detection_check`` and
``plagiarism_check`` without breaking this contract.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChunkMatch(BaseModel):
    id: Optional[str] = None
    content: str = ""
    preview: str = ""
    source_file: str = ""
    filename: str = ""
    page: Optional[int] = None
    doc_type: Optional[str] = None
    level: Optional[str] = None
    unit_id: Optional[str] = None
    unit_name: Optional[str] = None
    cosine_score: float = 0.0
    cosine_percent: float = 0.0
    rerank_score: Optional[float] = None
    rerank_score_normalized: Optional[float] = None


class CalibrationExample(BaseModel):
    assignment_id: Optional[str] = None
    similarity_verdict: Optional[str] = None
    final_score: Optional[float] = None
    feedback_text: Optional[str] = None
    level: Optional[str] = None
    unit_id: Optional[str] = None
    cosine_score: Optional[float] = None
    rerank_score: Optional[float] = None
    preview: str = ""


class MatchedCurriculum(BaseModel):
    level: Optional[str] = None
    unit_id: Optional[str] = None
    unit_name: Optional[str] = None
    matched_topics: List[str] = Field(default_factory=list)
    matched_learning_outcomes: List[str] = Field(default_factory=list)


class SyllabusCheck(BaseModel):
    status: str
    similarity_score: float
    max_similarity_score: float = 0.0
    thresholds: Dict[str, float] = Field(default_factory=dict)
    matched_curriculum: MatchedCurriculum = Field(default_factory=MatchedCurriculum)
    out_of_scope_topics: List[str] = Field(default_factory=list)
    rationale: str = ""
    draft_feedback: Optional[str] = None
    polished_feedback: str = ""
    matches: List[ChunkMatch] = Field(default_factory=list)
    calibration_examples: List[CalibrationExample] = Field(default_factory=list)


class TeacherReview(BaseModel):
    status: str = "pending"
    reviewed_by: Optional[str] = None
    override_verdict: Optional[str] = None
    override_score: Optional[float] = None
    override_reason: Optional[str] = None
    edited_feedback: Optional[str] = None
    reviewed_at: Optional[str] = None


class GradeResponse(BaseModel):
    assignment_id: str
    timestamp: str
    from_cache: bool = False
    submission_hash: str = ""
    filename: Optional[str] = None
    syllabus_check: SyllabusCheck
    ai_detection_check: Optional[Dict[str, Any]] = None
    plagiarism_check: Optional[Dict[str, Any]] = None
    final_teacher_review: TeacherReview = Field(default_factory=TeacherReview)


class ReviewRequest(BaseModel):
    status: str = Field(
        "approved",
        description="approved | overridden — never an automatic student fail",
    )
    override_verdict: Optional[str] = None
    override_score: Optional[float] = None
    override_reason: Optional[str] = None
    edited_feedback: Optional[str] = None
    add_to_grading_memory: bool = True
