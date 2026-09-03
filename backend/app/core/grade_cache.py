"""Hash-based cache of structured grade reports.

Keys are SHA-256 of whitespace-normalised submission text so identical and
near-identical resubmissions skip the LLM pipeline.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.hashing import submission_cache_hash

logger = logging.getLogger(__name__)
_lock = threading.Lock()


def _path_for(cache_hash: str) -> Path:
    return settings.GRADE_CACHE_DIR / f"{cache_hash}.json"


def get_cached_report(submission_text: str) -> Optional[Dict[str, Any]]:
    if not settings.ENABLE_GRADE_CACHE:
        return None
    cache_hash = submission_cache_hash(submission_text)
    path = _path_for(cache_hash)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["cache_hash"] = cache_hash
        return data
    except Exception:
        logger.warning("Ignoring corrupt grade cache file %s", path)
        return None


def store_cached_report(submission_text: str, payload: Dict[str, Any]) -> str:
    cache_hash = submission_cache_hash(submission_text)
    if not settings.ENABLE_GRADE_CACHE:
        return cache_hash
    path = _path_for(cache_hash)
    with _lock:
        settings.GRADE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return cache_hash
