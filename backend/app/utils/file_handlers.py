"""Filesystem helpers for storing, locating and previewing document files."""
from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from app.core.config import settings
from app.utils.validators import human_size

logger = logging.getLogger(__name__)


def make_document_id(path: Path) -> str:
    """Stable, URL-safe id derived from the file's path relative to DATA_DIR."""
    try:
        rel = path.resolve().relative_to(settings.DATA_DIR.resolve())
    except ValueError:
        rel = Path(path.name)
    raw = str(rel).replace("\\", "/")
    return base64.urlsafe_b64encode(raw.encode("utf-8")).rstrip(b"=").decode("ascii")


def resolve_document_id(doc_id: str) -> Optional[Path]:
    """Reverse of make_document_id -> absolute Path, or None if it escapes DATA_DIR."""
    try:
        padding = "=" * (-len(doc_id) % 4)
        rel = base64.urlsafe_b64decode(doc_id + padding).decode("utf-8")
    except Exception:
        return None
    candidate = (settings.DATA_DIR / rel).resolve()
    # Guard against path traversal.
    if settings.DATA_DIR.resolve() not in candidate.parents:
        return None
    return candidate


def describe(path: Path) -> dict:
    stat = path.stat()
    folder_name = path.parent.name
    return {
        "id": make_document_id(path),
        "name": path.name,
        "category": settings.CATEGORY_LABELS.get(folder_name, folder_name),
        "file_type": path.suffix.lower(),
        "size": stat.st_size,
        "size_human": human_size(stat.st_size),
        "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "path": str(path),
    }


def list_documents() -> List[dict]:
    docs: List[dict] = []
    for ext, folder_name in settings.EXTENSION_FOLDERS.items():
        folder = settings.DATA_DIR / folder_name
        if not folder.exists():
            continue
        for file_path in sorted(folder.glob(f"*{ext}")):
            if file_path.is_file():
                docs.append(describe(file_path))
    docs.sort(key=lambda d: d["modified"], reverse=True)
    return docs


def save_upload(filename: str, content: bytes) -> Path:
    """Persist uploaded bytes into the correct typed folder. Returns the path."""
    ext = Path(filename).suffix.lower()
    target_dir = settings.folder_for_extension(ext)
    target_dir.mkdir(parents=True, exist_ok=True)

    target = target_dir / filename
    # Avoid clobbering an existing document with the same name.
    counter = 1
    stem, suffix = target.stem, target.suffix
    while target.exists():
        target = target_dir / f"{stem}_{counter}{suffix}"
        counter += 1

    target.write_bytes(content)
    return target


def preview_text(path: Path, max_chars: int = 4000) -> tuple[str, bool]:
    """Extract a short text preview for a document. Returns (text, truncated)."""
    ext = path.suffix.lower()
    try:
        if ext in {".txt", ".md", ".markdown", ".csv"}:
            text = path.read_text(encoding="utf-8", errors="replace")
        elif ext == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            pages = []
            for page in reader.pages[:5]:
                pages.append(page.extract_text() or "")
            text = "\n".join(pages)
        elif ext == ".docx":
            import docx

            document = docx.Document(str(path))
            text = "\n".join(p.text for p in document.paragraphs)
        else:
            text = "Preview not available for this file type."
    except Exception as exc:  # noqa: BLE001
        logger.warning("Preview failed for %s: %s", path, exc)
        return f"Could not generate preview: {exc}", False

    if len(text) > max_chars:
        return text[:max_chars], True
    return text, False
