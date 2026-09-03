"""Syllabus-tier classification from aggregate similarity scores."""
from __future__ import annotations

from typing import Iterable, List

from app.core.config import settings


def aggregate_similarity(scores: Iterable[float]) -> float:
    values: List[float] = [float(s) for s in scores]
    if not values:
        return 0.0
    return sum(values) / len(values)


def to_percent(cosine_similarity: float) -> float:
    return round(max(0.0, min(1.0, float(cosine_similarity))) * 100.0, 2)


def classify_syllabus_status(
    score_percent: float,
    in_threshold: float | None = None,
    partial_threshold: float | None = None,
) -> str:
    in_cut = settings.IN_SYLLABUS_THRESHOLD if in_threshold is None else in_threshold
    partial_cut = (
        settings.PARTIALLY_RELATED_THRESHOLD
        if partial_threshold is None
        else partial_threshold
    )
    if score_percent >= in_cut:
        return "IN_SYLLABUS"
    if score_percent >= partial_cut:
        return "PARTIALLY_RELATED"
    return "OUT_OF_SYLLABUS"
