"""Lightweight in-memory application state with JSON persistence.

Tracks aggregate counters (questions asked) and a rolling activity log of user
interactions. Backed by a JSON file so the numbers survive a restart. Access is
guarded by a lock because FastAPI runs request handlers concurrently.
"""
from __future__ import annotations

import json
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Deque, Dict, List

from app.core.config import settings

_MAX_ACTIVITY = 500


class AppState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._questions_asked: int = 0
        self._activity: Deque[dict] = deque(maxlen=_MAX_ACTIVITY)
        self._load()

    # --- persistence -----------------------------------------------------
    def _load(self) -> None:
        path = settings.STATE_FILE
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self._questions_asked = int(data.get("questions_asked", 0))
                for entry in data.get("activity", [])[-_MAX_ACTIVITY:]:
                    self._activity.append(entry)
            except Exception:
                # Corrupt state file should never crash the app.
                pass

    def _persist(self) -> None:
        try:
            settings.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "questions_asked": self._questions_asked,
                "activity": list(self._activity),
            }
            settings.STATE_FILE.write_text(
                json.dumps(payload, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    # --- mutations -------------------------------------------------------
    def record_question(self, question: str, *, sources: int = 0,
                        latency_ms: int = 0, client: str = "anonymous") -> None:
        with self._lock:
            self._questions_asked += 1
            self._activity.append({
                "type": "question",
                "question": question,
                "sources": sources,
                "latency_ms": latency_ms,
                "client": client,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            self._persist()

    def record_event(self, event_type: str, message: str,
                    client: str = "system") -> None:
        with self._lock:
            self._activity.append({
                "type": event_type,
                "question": message,
                "sources": 0,
                "client": client,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            self._persist()

    # --- reads -----------------------------------------------------------
    @property
    def questions_asked(self) -> int:
        with self._lock:
            return self._questions_asked

    def recent_activity(self, limit: int = 50) -> List[Dict]:
        with self._lock:
            items = list(self._activity)
        return list(reversed(items[-limit:]))


app_state = AppState()
