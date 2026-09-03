"""Async wrappers around curriculum sync / upload."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Dict, Tuple

from app.core import curriculum
from app.core.config import settings
from app.core.state import app_state
from app.utils.validators import sanitize_filename, validate_upload

logger = logging.getLogger(__name__)
_lock = asyncio.Lock()


async def sync(force: bool = False) -> Dict:
    async with _lock:
        result = await asyncio.to_thread(curriculum.sync_curriculum, force=force)
    app_state.record_event(
        "curriculum_sync",
        f"Curriculum sync added={len(result.get('added') or [])} "
        f"updated={len(result.get('updated') or [])} "
        f"skipped={len(result.get('skipped') or [])}",
    )
    return result


def status() -> Dict:
    return curriculum.curriculum_status()


def save_curriculum_file(
    filename: str,
    content: bytes,
    *,
    level: str,
    unit_id: str,
    unit_name: str,
    doc_type: str,
) -> Tuple[bool, str, Path | None]:
    safe_name = sanitize_filename(filename)
    ok, reason = validate_upload(safe_name, len(content))
    if not ok:
        return False, reason, None
    target_dir = curriculum.curriculum_target_dir(level, unit_id, unit_name, doc_type)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / safe_name
    counter = 1
    stem, suffix = target.stem, target.suffix
    while target.exists():
        target = target_dir / f"{stem}_{counter}{suffix}"
        counter += 1
    target.write_bytes(content)
    try:
        rel = target.resolve().relative_to(settings.CURRICULUM_DIR.resolve()).as_posix()
    except ValueError:
        rel = target.name
    app_state.record_event("curriculum_upload", f"Uploaded {target.name} to {level}/{unit_id}")
    return True, f"Saved as {rel}", target
