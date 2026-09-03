"""SHA-256 helpers for incremental curriculum sync and grade-result caching."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_submission_text(text: str) -> str:
    """Collapse whitespace/case so near-identical resubmissions share a cache key."""
    collapsed = re.sub(r"\s+", " ", text or "").strip().lower()
    return collapsed


def submission_cache_hash(text: str) -> str:
    return sha256_text(normalize_submission_text(text))
