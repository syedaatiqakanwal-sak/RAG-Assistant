"""On-disk store for per-assignment grade reports (JSON files)."""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)
_lock = threading.Lock()


def _path_for(assignment_id: str) -> Path:
    safe = "".join(ch for ch in assignment_id if ch.isalnum() or ch in "-_")
    return settings.GRADING_REPORTS_DIR / f"{safe}.json"


def save_report(assignment_id: str, report: Dict[str, Any]) -> None:
    path = _path_for(assignment_id)
    with _lock:
        settings.GRADING_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def load_report(assignment_id: str) -> Optional[Dict[str, Any]]:
    path = _path_for(assignment_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Corrupt grade report %s", path)
        return None


def list_reports(limit: int = 50) -> List[Dict[str, Any]]:
    folder = settings.GRADING_REPORTS_DIR
    if not folder.exists():
        return []
    files = sorted(folder.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    out: List[Dict[str, Any]] = []
    for path in files[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        out.append({
            "assignment_id": data.get("assignment_id") or path.stem,
            "timestamp": data.get("timestamp"),
            "status": (data.get("syllabus_check") or {}).get("status"),
            "similarity_score": (data.get("syllabus_check") or {}).get("similarity_score"),
            "review_status": (data.get("final_teacher_review") or {}).get("status"),
            "from_cache": data.get("from_cache", False),
        })
    return out
