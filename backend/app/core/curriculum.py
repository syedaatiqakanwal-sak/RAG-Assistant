"""CURRICULUM_KB ingestion with SHA-256 delta-hash incremental sync.

Source layout (under settings.CURRICULUM_DIR)::

    {level}/{unit_id}_{unit_name}/{Syllabus|Assignment_Criteria|Lecture_Notes}/file

Unchanged files are skipped. New and modified files are re-chunked with the
structure-aware splitter and upserted. Files removed from disk have their chunks
deleted. This replaces full-rebuild behaviour for curriculum only; the general
chat collection in ingestion.py is unchanged.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.core import chunking
from app.core.config import settings
from app.core.hashing import sha256_file
from app.core.vectorstore import (
    add_texts,
    chroma_safe_metadata,
    delete_ids,
    get_curriculum_store,
    invalidate as invalidate_stores,
)

logger = logging.getLogger(__name__)
_sync_lock = threading.Lock()

_DOC_TYPE_FOLDERS = {
    "syllabus": "syllabus",
    "assignment_criteria": "brief",
    "assignment_briefs": "brief",
    "assignment-criteria": "brief",
    "briefs": "brief",
    "brief": "brief",
    "lecture_notes": "lecture",
    "lecture-notes": "lecture",
    "lectures": "lecture",
    "lecture": "lecture",
    "notes": "lecture",
}

_SUPPORTED_EXT = set(settings.EXTENSION_FOLDERS.keys())
_UNIT_FOLDER_RE = re.compile(r"^([A-Za-z]?\d+)[_+\-]+(.+)$")


def _norm_folder(name: str) -> str:
    return name.lower().replace(" ", "_").replace("-", "_")


def split_unit_folder(folder: str) -> Tuple[str, str]:
    match = _UNIT_FOLDER_RE.match(folder.strip())
    if match:
        return match.group(1), match.group(2).replace("_", " ").strip()
    cleaned = folder.replace("_", " ").strip()
    return folder, cleaned


def infer_doc_type(type_folder: str, filename_stem: str) -> str:
    mapped = _DOC_TYPE_FOLDERS.get(_norm_folder(type_folder))
    if mapped:
        return mapped
    stem = filename_stem.lower()
    if "syllabus" in stem:
        return "syllabus"
    if "brief" in stem or "criteria" in stem:
        return "brief"
    if "lecture" in stem or "note" in stem:
        return "lecture"
    return "lecture"


def parse_curriculum_path(path: Path, root: Optional[Path] = None) -> Dict[str, str]:
    """Derive level / unit / doc_type from a hierarchical curriculum path."""
    root = (root or settings.CURRICULUM_DIR).resolve()
    try:
        rel = path.resolve().relative_to(root)
    except ValueError:
        rel = Path(path.name)

    parts = rel.parts
    # Expected: {level}/{unit_folder}/{Syllabus|Assignment_Criteria|Lecture_Notes}/file
    if len(parts) >= 4:
        level, unit_folder, type_folder = parts[0], parts[1], parts[2]
    elif len(parts) == 3:
        level, unit_folder, type_folder = parts[0], parts[1], ""
    elif len(parts) == 2:
        level, unit_folder, type_folder = parts[0], "", ""
    else:
        level, unit_folder, type_folder = "", "", ""
    unit_id, unit_name = split_unit_folder(unit_folder) if unit_folder else ("", "")
    doc_type = infer_doc_type(type_folder, path.stem)
    return {
        "level": level,
        "unit_id": unit_id,
        "unit_name": unit_name,
        "doc_type": doc_type,
        "relative_path": rel.as_posix(),
    }


def curriculum_target_dir(level: str, unit_id: str, unit_name: str, doc_type: str) -> Path:
    """Build the canonical folder for an uploaded curriculum file."""
    unit_folder = f"{unit_id}_{unit_name.replace(' ', '_')}" if unit_name else unit_id
    type_folder = {
        "syllabus": "Syllabus",
        "brief": "Assignment_Criteria",
        "lecture": "Lecture_Notes",
    }.get(doc_type, "Lecture_Notes")
    return settings.CURRICULUM_DIR / level / unit_folder / type_folder


def iter_curriculum_files(root: Optional[Path] = None) -> List[Path]:
    root = root or settings.CURRICULUM_DIR
    files: List[Path] = []
    if not root.exists():
        return files
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue
        if path.suffix.lower() not in _SUPPORTED_EXT:
            continue
        files.append(path)
    return files


def _load_manifest() -> Dict[str, Any]:
    path = settings.CURRICULUM_MANIFEST_PATH
    if not path.exists():
        return {"version": 1, "files": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data.setdefault("version", 1)
        data.setdefault("files", {})
        return data
    except Exception:
        logger.warning("Corrupt curriculum manifest at %s; starting fresh", path)
        return {"version": 1, "files": {}}


def _save_manifest(manifest: Dict[str, Any]) -> None:
    path = settings.CURRICULUM_MANIFEST_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _chunk_ids_for(file_hash: str, n: int) -> List[str]:
    return [f"cur_{file_hash[:16]}_{i:04d}" for i in range(n)]


def _metadata_for(path: Path, parsed: Dict[str, str], text: str, page: Any = None) -> dict:
    outcomes = chunking.extract_learning_outcomes(text)
    topics = chunking.extract_core_topics(text, extra=[parsed.get("unit_name") or ""])
    meta = {
        "level": parsed.get("level") or "",
        "unit_id": parsed.get("unit_id") or "",
        "unit_name": parsed.get("unit_name") or "",
        "core_topics": topics,
        "learning_outcomes": outcomes,
        "source_file": parsed.get("relative_path") or path.name,
        "source": str(path),
        "filename": path.name,
        "doc_type": parsed.get("doc_type") or "lecture",
        "file_type": path.suffix.lower(),
    }
    if page is not None:
        meta["page"] = page
    return chroma_safe_metadata(meta)


def _index_file(path: Path, file_hash: str) -> List[str]:
    from app.core.ingestion import load_file

    parsed = parse_curriculum_path(path)
    documents = load_file(path)
    if not documents:
        return []

    full_text = "\n\n".join(d.page_content or "" for d in documents)
    chunks = chunking.chunk_documents_structured(documents, curriculum=True)
    if not chunks:
        return []

    texts: List[str] = []
    metas: List[dict] = []
    for chunk in chunks:
        page = chunk.metadata.get("page")
        meta = _metadata_for(path, parsed, full_text, page=page)
        # Per-chunk overlay: keep any page the loader already set.
        texts.append(chunk.page_content)
        metas.append(meta)

    ids = _chunk_ids_for(file_hash, len(texts))
    store = get_curriculum_store()
    add_texts(store, texts, metas, ids)
    return ids


def sync_curriculum(*, force: bool = False) -> Dict[str, Any]:
    """Incrementally sync CURRICULUM_KB with files on disk.

    Returns a summary of skipped / indexed / deleted files.
    """
    with _sync_lock:
        return _sync_curriculum_unlocked(force=force)


def _sync_curriculum_unlocked(*, force: bool = False) -> Dict[str, Any]:
    settings.CURRICULUM_DIR.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest()
    known: Dict[str, Any] = manifest["files"]
    current_files = iter_curriculum_files()
    current_keys = set()

    added: List[str] = []
    updated: List[str] = []
    skipped: List[str] = []
    failed: List[str] = []
    deleted: List[str] = []
    chunks_written = 0

    store = get_curriculum_store()

    for path in current_files:
        parsed = parse_curriculum_path(path)
        key = parsed["relative_path"]
        current_keys.add(key)
        try:
            file_hash = sha256_file(path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not hash %s: %s", path, exc)
            failed.append(key)
            continue

        previous = known.get(key) or {}
        unchanged = (not force) and previous.get("sha256") == file_hash
        if unchanged:
            skipped.append(key)
            continue

        old_ids = previous.get("chunk_ids") or []
        if old_ids:
            delete_ids(store, old_ids)

        try:
            new_ids = _index_file(path, file_hash)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to index curriculum file %s", path)
            failed.append(f"{key}: {exc}")
            continue

        known[key] = {
            "sha256": file_hash,
            "size": path.stat().st_size,
            "chunk_ids": new_ids,
            "chunk_count": len(new_ids),
            "level": parsed.get("level"),
            "unit_id": parsed.get("unit_id"),
            "doc_type": parsed.get("doc_type"),
        }
        chunks_written += len(new_ids)
        if previous:
            updated.append(key)
        else:
            added.append(key)

    for key in list(known.keys()):
        if key in current_keys:
            continue
        stale_ids = (known[key] or {}).get("chunk_ids") or []
        delete_ids(store, stale_ids)
        del known[key]
        deleted.append(key)

    _save_manifest(manifest)
    invalidate_stores()

    summary = {
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "deleted": deleted,
        "failed": failed,
        "files_on_disk": len(current_files),
        "chunks_written": chunks_written,
        "indexed_files": len(known),
        "force": force,
    }
    logger.info(
        "Curriculum sync: +%d ~%d skip=%d -%d fail=%d chunks=%d",
        len(added), len(updated), len(skipped), len(deleted), len(failed),
        chunks_written,
    )
    return summary


def curriculum_status() -> Dict[str, Any]:
    from app.core.vectorstore import collection_count

    manifest = _load_manifest()
    files = manifest.get("files") or {}
    by_level: Dict[str, int] = {}
    by_type: Dict[str, int] = {}
    for info in files.values():
        level = info.get("level") or "unknown"
        doc_type = info.get("doc_type") or "unknown"
        by_level[level] = by_level.get(level, 0) + 1
        by_type[doc_type] = by_type.get(doc_type, 0) + 1
    return {
        "collection": settings.CURRICULUM_COLLECTION,
        "chunks": collection_count(settings.CURRICULUM_COLLECTION),
        "indexed_files": len(files),
        "files_on_disk": len(iter_curriculum_files()),
        "by_level": by_level,
        "by_doc_type": by_type,
        "manifest": str(settings.CURRICULUM_MANIFEST_PATH),
        "root": str(settings.CURRICULUM_DIR),
    }
