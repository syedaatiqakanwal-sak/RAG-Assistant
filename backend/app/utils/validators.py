"""Input validation and sanitisation helpers."""
from __future__ import annotations

import re
from pathlib import Path

from app.core.config import settings


def human_size(num_bytes: int) -> str:
    """Format a byte count as a human readable string."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def sanitize_filename(filename: str) -> str:
    """Strip directory components and unsafe characters from an uploaded filename."""
    name = Path(filename).name  # drop any path traversal segments
    name = name.replace("\x00", "")
    # Allow letters, numbers, space, dot, dash, underscore, parentheses.
    name = re.sub(r"[^A-Za-z0-9 ._()\-]", "_", name).strip()
    return name or "unnamed"


def is_allowed_extension(filename: str) -> bool:
    return Path(filename).suffix.lower() in settings.ALLOWED_EXTENSIONS


def validate_upload(filename: str, size: int) -> tuple[bool, str]:
    """Return (ok, reason) for an upload candidate."""
    if not is_allowed_extension(filename):
        allowed = ", ".join(settings.ALLOWED_EXTENSIONS)
        return False, f"Unsupported file type. Allowed: {allowed}"
    if size > settings.max_upload_bytes:
        return False, f"File exceeds the {settings.MAX_UPLOAD_MB} MB limit"
    if size == 0:
        return False, "File is empty"
    return True, "ok"
