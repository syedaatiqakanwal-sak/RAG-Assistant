"""Document management operations (list / upload / delete / preview / search)."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Tuple

from app.core.state import app_state
from app.utils import file_handlers
from app.utils.validators import sanitize_filename, validate_upload

logger = logging.getLogger(__name__)


def list_documents() -> List[dict]:
    return file_handlers.list_documents()


def search_documents(query: str) -> List[dict]:
    query = query.strip().lower()
    if not query:
        return list_documents()
    return [d for d in list_documents() if query in d["name"].lower()
            or query in d["category"].lower()]


def stats_summary() -> Dict:
    docs = list_documents()
    by_category: Dict[str, int] = {}
    total_size = 0
    for doc in docs:
        by_category[doc["category"]] = by_category.get(doc["category"], 0) + 1
        total_size += doc["size"]
    return {
        "total_documents": len(docs),
        "by_category": by_category,
        "total_size": total_size,
    }


def save_single(filename: str, content: bytes) -> Tuple[bool, str]:
    safe_name = sanitize_filename(filename)
    ok, reason = validate_upload(safe_name, len(content))
    if not ok:
        return False, reason
    try:
        path = file_handlers.save_upload(safe_name, content)
        app_state.record_event("upload", f"Uploaded {path.name}")
        return True, f"Saved as {path.name}"
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to save %s", filename)
        return False, str(exc)


def delete_by_ids(ids: List[str]) -> Tuple[int, List[str]]:
    """Delete files for the given ids. Returns (deleted_count, errors)."""
    deleted = 0
    errors: List[str] = []
    for doc_id in ids:
        path = file_handlers.resolve_document_id(doc_id)
        if path is None or not path.exists():
            errors.append(f"{doc_id}: not found")
            continue
        try:
            name = path.name
            path.unlink()
            deleted += 1
            app_state.record_event("delete", f"Deleted {name}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{doc_id}: {exc}")
    return deleted, errors


def preview(doc_id: str) -> Dict | None:
    path = file_handlers.resolve_document_id(doc_id)
    if path is None or not path.exists():
        return None
    text, truncated = file_handlers.preview_text(path)
    return {
        "id": doc_id,
        "name": path.name,
        "file_type": path.suffix.lower(),
        "content": text,
        "truncated": truncated,
    }
