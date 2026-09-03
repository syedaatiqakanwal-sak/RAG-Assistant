"""Academic grading pipeline: retrieve, classify, two-pass LLM, cache, review."""
from __future__ import annotations

import logging
import tempfile
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core import classification, correction_log, grade_cache, grading_memory, reports_store
from app.core.chunking import chunk_plain_text
from app.core.config import settings
from app.core.hashing import submission_cache_hash
from app.core.json_util import parse_json_object
from app.core.reranker import rerank_hits
from app.core.vectorstore import (
    get_curriculum_store,
    parse_json_meta,
    query_collection,
)

logger = logging.getLogger(__name__)

REASONING_SYSTEM = """You are an academic assignment advisor for human teachers.
You produce an advisory report only. A teacher will always review and confirm.
Never auto-fail, auto-reject, or invent a numeric score or syllabus status —
those values are provided and FIXED. Do not contradict them.

Your job is to:
1. Explain why the retrieval-based status was assigned.
2. List matched topics and learning outcomes that appear in the curriculum excerpts.
3. List out-of-scope topics present in the submission (if any).
4. Write draft_feedback a teacher could send to a student: constructive, specific,
   and consistent with the few-shot grading examples when they are provided.

Return ONLY valid JSON with this shape:
{
  "matched_topics": ["..."],
  "matched_learning_outcomes": ["..."],
  "out_of_scope_topics": ["..."],
  "rationale": "...",
  "draft_feedback": "..."
}
Do not include status or similarity_score in your JSON."""

POLISH_SYSTEM = """You are a copy-editor. Rewrite the teacher's draft feedback to
fix grammar, tone, and clarity. Do NOT add new claims, examples, scores, topics,
or judgments. Do NOT change the meaning or implied verdict. Return ONLY the
rewritten feedback as plain text, with no preamble or quotation marks."""


def extract_submission_text(filename: str, content: bytes) -> str:
    """Turn an uploaded assignment into plain text."""
    ext = Path(filename or "submission.txt").suffix.lower() or ".txt"
    if ext in {".txt", ".md", ".markdown", ".csv"}:
        return content.decode("utf-8", errors="replace").strip()

    suffix = ext if ext.startswith(".") else f".{ext}"
    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        from app.core.ingestion import extract_text

        return extract_text(tmp_path)
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except TypeError:
                if tmp_path.exists():
                    tmp_path.unlink()


def _preview(text: str, limit: int = 280) -> str:
    text = text or ""
    return text[:limit] + ("..." if len(text) > limit else "")


def _unique(items: List[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for item in items:
        cleaned = (item or "").strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return out


def _majority(values: List[str]) -> Optional[str]:
    values = [v for v in values if v]
    if not values:
        return None
    return Counter(values).most_common(1)[0][0]


def _merge_hits(groups: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    best: Dict[str, Dict[str, Any]] = {}
    for group in groups:
        for hit in group:
            hid = hit.get("id") or f"anon_{id(hit)}"
            current = best.get(hid)
            if current is None or hit.get("cosine_score", 0) > current.get("cosine_score", 0):
                best[hid] = hit
    return list(best.values())


def _search_curriculum(submission_text: str) -> List[Dict[str, Any]]:
    store = get_curriculum_store()
    query = submission_text[: settings.GRADE_QUERY_MAX_CHARS]
    groups: List[List[Dict[str, Any]]] = [
        query_collection(store, query, settings.GRADE_TOP_K),
    ]
    for chunk in chunk_plain_text(submission_text)[:4]:
        if chunk.strip():
            groups.append(query_collection(store, chunk, 3))
    merged = _merge_hits(groups)
    return rerank_hits(query, merged, top_n=settings.GRADE_RERANK_TOP_N)


def _serialize_match(hit: Dict[str, Any]) -> Dict[str, Any]:
    meta = hit.get("metadata") or {}
    content = hit.get("content") or ""
    cosine = float(hit.get("cosine_score") or 0.0)
    page = meta.get("page")
    try:
        page_val = int(page) if page is not None and page != "" else None
    except (TypeError, ValueError):
        page_val = None
    return {
        "id": hit.get("id"),
        "content": content,
        "preview": _preview(content),
        "source_file": meta.get("source_file") or meta.get("source") or "",
        "filename": meta.get("filename") or "",
        "page": page_val,
        "doc_type": meta.get("doc_type"),
        "level": meta.get("level") or None,
        "unit_id": meta.get("unit_id") or None,
        "unit_name": meta.get("unit_name") or None,
        "cosine_score": round(cosine, 4),
        "cosine_percent": classification.to_percent(cosine),
        "rerank_score": hit.get("rerank_score"),
        "rerank_score_normalized": hit.get("rerank_score_normalized"),
    }


def _serialize_example(hit: Dict[str, Any]) -> Dict[str, Any]:
    meta = hit.get("metadata") or {}
    content = hit.get("content") or ""
    score = meta.get("final_score")
    try:
        score_val = float(score) if score is not None and score != "" else None
    except (TypeError, ValueError):
        score_val = None
    return {
        "assignment_id": meta.get("assignment_id"),
        "similarity_verdict": meta.get("similarity_verdict"),
        "final_score": score_val,
        "feedback_text": meta.get("feedback_text") or "",
        "level": meta.get("level") or None,
        "unit_id": meta.get("unit_id") or None,
        "cosine_score": round(float(hit.get("cosine_score") or 0.0), 4),
        "rerank_score": hit.get("rerank_score"),
        "preview": _preview(content),
    }


def _matched_curriculum(hits: List[Dict[str, Any]]) -> Dict[str, Any]:
    levels, units, names = [], [], []
    topics: List[str] = []
    outcomes: List[str] = []
    for hit in hits:
        meta = hit.get("metadata") or {}
        if meta.get("level"):
            levels.append(str(meta["level"]))
        if meta.get("unit_id"):
            units.append(str(meta["unit_id"]))
        if meta.get("unit_name"):
            names.append(str(meta["unit_name"]))
        topics.extend(parse_json_meta(meta.get("core_topics"), []))
        outcomes.extend(parse_json_meta(meta.get("learning_outcomes"), []))
    return {
        "level": _majority(levels),
        "unit_id": _majority(units),
        "unit_name": _majority(names),
        "matched_topics": _unique([str(t) for t in topics]),
        "matched_learning_outcomes": _unique([str(o) for o in outcomes]),
    }


def _build_llm(temperature: float, json_mode: bool = False):
    from langchain_ollama import OllamaLLM

    kwargs: Dict[str, Any] = {
        "model": settings.OLLAMA_MODEL,
        "temperature": temperature,
        "base_url": settings.OLLAMA_BASE_URL,
    }
    if json_mode:
        kwargs["format"] = "json"
    return OllamaLLM(**kwargs)


def _format_matches_for_prompt(matches: List[Dict[str, Any]]) -> str:
    blocks = []
    for i, match in enumerate(matches, 1):
        blocks.append(
            f"[Curriculum {i} | unit={match.get('unit_id')} "
            f"type={match.get('doc_type')} cosine={match.get('cosine_percent')}% "
            f"rerank={match.get('rerank_score')}]\n{match.get('content')}"
        )
    return "\n\n".join(blocks) or "(no curriculum chunks retrieved)"


def _format_examples_for_prompt(examples: List[Dict[str, Any]]) -> str:
    blocks = []
    for i, ex in enumerate(examples, 1):
        blocks.append(
            f"[Example {i} | verdict={ex.get('similarity_verdict')} "
            f"score={ex.get('final_score')} unit={ex.get('unit_id')}]\n"
            f"Submission preview: {ex.get('preview')}\n"
            f"Approved feedback: {ex.get('feedback_text')}"
        )
    return "\n\n".join(blocks) or "(no approved calibration examples yet)"


def _reasoning_pass(
    *,
    status: str,
    score: float,
    submission_text: str,
    matches: List[Dict[str, Any]],
    examples: List[Dict[str, Any]],
    matched: Dict[str, Any],
) -> Dict[str, Any]:
    user = (
        f"FIXED status: {status}\n"
        f"FIXED similarity_score (percent): {score}\n"
        f"Matched unit: {matched.get('unit_id')} ({matched.get('unit_name')}) "
        f"level={matched.get('level')}\n\n"
        f"Curriculum excerpts (already reranked):\n{_format_matches_for_prompt(matches)}\n\n"
        f"Few-shot calibration examples (human-approved, same unit if available):\n"
        f"{_format_examples_for_prompt(examples)}\n\n"
        f"Student submission:\n{submission_text[: settings.GRADE_QUERY_MAX_CHARS]}"
    )
    llm = _build_llm(settings.GRADE_REASONING_TEMPERATURE, json_mode=True)
    raw = llm.invoke(f"{REASONING_SYSTEM}\n\n{user}")
    parsed = parse_json_object(raw if isinstance(raw, str) else str(raw))
    return {
        "matched_topics": parsed.get("matched_topics") or [],
        "matched_learning_outcomes": parsed.get("matched_learning_outcomes") or [],
        "out_of_scope_topics": parsed.get("out_of_scope_topics") or [],
        "rationale": (parsed.get("rationale") or "").strip(),
        "draft_feedback": (parsed.get("draft_feedback") or "").strip(),
    }


def _polish_pass(draft_feedback: str) -> str:
    if not (draft_feedback or "").strip():
        return ""
    llm = _build_llm(settings.GRADE_POLISH_TEMPERATURE, json_mode=False)
    raw = llm.invoke(
        f"{POLISH_SYSTEM}\n\nDRAFT FEEDBACK:\n{draft_feedback.strip()}"
    )
    text = raw if isinstance(raw, str) else str(raw)
    return text.strip().strip('"')


def _empty_teacher_review() -> Dict[str, Any]:
    return {
        "status": "pending",
        "reviewed_by": None,
        "override_verdict": None,
        "override_score": None,
        "override_reason": None,
        "edited_feedback": None,
        "reviewed_at": None,
    }


def _public_report(record: Dict[str, Any]) -> Dict[str, Any]:
    """Strip internal-only fields before returning through the API."""
    clone = dict(record)
    clone.pop("submission_text", None)
    syllabus = dict(clone.get("syllabus_check") or {})
    if not settings.SHOW_DRAFT_FEEDBACK:
        syllabus["draft_feedback"] = None
    clone["syllabus_check"] = syllabus
    return clone


def _build_syllabus_check(
    *,
    status: str,
    score: float,
    max_score: float,
    matched: Dict[str, Any],
    matches: List[Dict[str, Any]],
    examples: List[Dict[str, Any]],
    rationale: str,
    draft: str,
    polished: str,
    out_of_scope: List[str],
) -> Dict[str, Any]:
    return {
        "status": status,
        "similarity_score": score,
        "max_similarity_score": max_score,
        "thresholds": {
            "IN_SYLLABUS": settings.IN_SYLLABUS_THRESHOLD,
            "PARTIALLY_RELATED": settings.PARTIALLY_RELATED_THRESHOLD,
        },
        "matched_curriculum": matched,
        "out_of_scope_topics": out_of_scope,
        "rationale": rationale,
        "draft_feedback": draft,
        "polished_feedback": polished,
        "matches": matches,
        "calibration_examples": examples,
    }


def grade_submission(
    *,
    filename: str,
    content: bytes,
    assignment_id: Optional[str] = None,
    level: str = "",
    unit_id: str = "",
    skip_cache: bool = False,
) -> Dict[str, Any]:
    """Run the full advisory grading pipeline and persist the report."""
    submission_text = extract_submission_text(filename, content)
    if not submission_text.strip():
        raise ValueError("Could not extract any text from the submission")

    assignment_id = assignment_id or str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    sub_hash = submission_cache_hash(submission_text)

    if not skip_cache:
        cached = grade_cache.get_cached_report(submission_text)
        if cached:
            record = {
                "assignment_id": assignment_id,
                "timestamp": timestamp,
                "from_cache": True,
                "submission_hash": sub_hash,
                "filename": filename,
                "submission_text": submission_text,
                "syllabus_check": cached.get("syllabus_check") or {},
                "ai_detection_check": None,
                "plagiarism_check": None,
                "final_teacher_review": _empty_teacher_review(),
            }
            reports_store.save_report(assignment_id, record)
            return _public_report(record)

    hits = _search_curriculum(submission_text)
    llm_hits = hits[: settings.GRADE_RERANK_TOP_N]
    cosine_values = [float(h.get("cosine_score") or 0.0) for h in llm_hits]
    mean_cosine = classification.aggregate_similarity(cosine_values)
    max_cosine = max(cosine_values) if cosine_values else 0.0
    score = classification.to_percent(mean_cosine)
    max_score = classification.to_percent(max_cosine)
    status = classification.classify_syllabus_status(score)

    matched = _matched_curriculum(llm_hits)
    if unit_id:
        matched["unit_id"] = unit_id
    if level:
        matched["level"] = level

    serialized_matches = [_serialize_match(h) for h in hits]
    llm_matches = serialized_matches[: settings.GRADE_RERANK_TOP_N]

    cal_hits = grading_memory.search_calibration_examples(
        submission_text[: settings.GRADE_QUERY_MAX_CHARS],
        unit_id=matched.get("unit_id") or "",
    )
    examples = [_serialize_example(h) for h in cal_hits]

    rationale = (
        "No curriculum chunks were retrieved. The similarity score is 0, so this "
        "submission is flagged OUT_OF_SYLLABUS pending teacher review. Index a "
        "syllabus under data/curriculum before relying on this report."
        if not hits else
        f"Aggregate cosine similarity of the top {len(llm_hits)} reranked "
        f"curriculum chunks is {score}% (max {max_score}%). Status is assigned "
        "from configured thresholds, not by the language model."
    )
    draft = (
        "Advisory only: the system could not compare this submission against "
        "indexed curriculum material. Please review manually."
        if not hits else ""
    )
    polished = draft
    out_of_scope: List[str] = []

    if hits:
        try:
            reasoned = _reasoning_pass(
                status=status,
                score=score,
                submission_text=submission_text,
                matches=llm_matches,
                examples=examples,
                matched=matched,
            )
            matched["matched_topics"] = _unique(
                list(matched.get("matched_topics") or [])
                + [str(t) for t in reasoned.get("matched_topics") or []]
            )
            matched["matched_learning_outcomes"] = _unique(
                list(matched.get("matched_learning_outcomes") or [])
                + [str(t) for t in reasoned.get("matched_learning_outcomes") or []]
            )
            out_of_scope = _unique([str(t) for t in reasoned.get("out_of_scope_topics") or []])
            rationale = reasoned.get("rationale") or rationale
            draft = reasoned.get("draft_feedback") or draft
        except Exception:
            logger.exception("Reasoning pass failed; returning retrieval-only report")
            draft = draft or (
                "Advisory retrieval report only — the language model did not produce "
                "feedback. Please review the matched curriculum excerpts below."
            )
        try:
            polished = _polish_pass(draft) or draft
        except Exception:
            logger.exception("Polish pass failed; returning draft feedback")
            polished = draft

    syllabus_check = _build_syllabus_check(
        status=status,
        score=score,
        max_score=max_score,
        matched=matched,
        matches=serialized_matches,
        examples=examples,
        rationale=rationale,
        draft=draft,
        polished=polished,
        out_of_scope=out_of_scope,
    )

    cache_payload = {"syllabus_check": syllabus_check}
    grade_cache.store_cached_report(submission_text, cache_payload)

    record = {
        "assignment_id": assignment_id,
        "timestamp": timestamp,
        "from_cache": False,
        "submission_hash": sub_hash,
        "filename": filename,
        "submission_text": submission_text,
        "syllabus_check": syllabus_check,
        "ai_detection_check": None,
        "plagiarism_check": None,
        "final_teacher_review": _empty_teacher_review(),
    }
    reports_store.save_report(assignment_id, record)
    return _public_report(record)


def apply_review(
    assignment_id: str,
    payload: Dict[str, Any],
    reviewed_by: str,
) -> Dict[str, Any]:
    """Apply a teacher decision: correction log + optional grading-memory ingest."""
    record = reports_store.load_report(assignment_id)
    if record is None:
        raise KeyError(assignment_id)

    syllabus = record.get("syllabus_check") or {}
    system_verdict = syllabus.get("status")
    system_score = syllabus.get("similarity_score")
    override_verdict = payload.get("override_verdict")
    override_score = payload.get("override_score")
    override_reason = payload.get("override_reason")
    edited_feedback = payload.get("edited_feedback")
    review_status = payload.get("status") or "approved"
    add_memory = payload.get("add_to_grading_memory", True)

    verdict_changed = (
        override_verdict is not None
        and str(override_verdict) != str(system_verdict)
    )
    score_changed = False
    if override_score is not None:
        try:
            score_changed = abs(float(override_score) - float(system_score or 0)) > 0.05
        except (TypeError, ValueError):
            score_changed = True

    if verdict_changed or score_changed:
        correction_log.append_correction({
            "submission_id": assignment_id,
            "system_verdict": system_verdict,
            "system_score": system_score,
            "corrected_verdict": override_verdict if override_verdict is not None else system_verdict,
            "corrected_score": override_score if override_score is not None else system_score,
            "correction_reason": override_reason or "",
            "reviewed_by": reviewed_by,
        })

    final_verdict = override_verdict or system_verdict
    final_score = override_score if override_score is not None else system_score
    final_feedback = edited_feedback or syllabus.get("polished_feedback") or syllabus.get("draft_feedback") or ""
    matched = syllabus.get("matched_curriculum") or {}

    record["final_teacher_review"] = {
        "status": review_status,
        "reviewed_by": reviewed_by,
        "override_verdict": override_verdict,
        "override_score": override_score,
        "override_reason": override_reason,
        "edited_feedback": edited_feedback,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }
    reports_store.save_report(assignment_id, record)

    if add_memory:
        try:
            grading_memory.add_approved_example(
                assignment_id=assignment_id,
                submission_text=record.get("submission_text") or "",
                similarity_verdict=str(final_verdict or ""),
                final_score=float(final_score or 0.0),
                feedback_text=final_feedback,
                level=matched.get("level") or "",
                unit_id=matched.get("unit_id") or "",
                unit_name=matched.get("unit_name") or "",
                reviewed_by=reviewed_by,
            )
        except Exception:
            logger.exception(
                "Teacher review saved but GRADING_MEMORY_KB ingest failed for %s",
                assignment_id,
            )

    return _public_report(record)
