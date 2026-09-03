"""Append-only CORRECTION_LOG (JSONL). Not embedded, never fed to the LLM."""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)
_lock = threading.Lock()


def append_correction(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Append one teacher override. Returns the stored record (with timestamp)."""
    record = dict(entry)
    record.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    line = json.dumps(record, ensure_ascii=False)
    with _lock:
        settings.CORRECTION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with settings.CORRECTION_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    return record


def list_corrections(
    limit: int = 200,
    assignment_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    path = settings.CORRECTION_LOG_PATH
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if assignment_id and row.get("submission_id") != assignment_id:
                    continue
                rows.append(row)
    except Exception:
        logger.exception("Failed to read correction log")
        return []
    return list(reversed(rows[-limit:]))
