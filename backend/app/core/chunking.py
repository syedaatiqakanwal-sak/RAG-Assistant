"""Structure-aware chunking for curriculum documents.

Curriculum files (syllabi, unit briefs, lecture packs) are split on Learning
Outcome / heading / unit markers first so a topic block is not cut mid-sentence.
Each structural section is then size-limited with the existing recursive splitter.

Documents with no detectable structure fall back to RecursiveCharacterTextSplitter
(the same behaviour used for general chat documents and assignment submissions).
"""
from __future__ import annotations

import re
from typing import Iterable, List, Sequence, Tuple

from app.core.config import settings

# Headings / LO / unit markers that should start a new structural section.
_STRUCTURE_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"^#{1,6}\s+\S.+$", re.MULTILINE),
    re.compile(r"^LO\s*\d+\s*[:.\-)]\s*\S.+$", re.MULTILINE | re.IGNORECASE),
    re.compile(
        r"^Learning\s+Outcomes?\s*\d*\s*[:.\-)]\s*\S.+$",
        re.MULTILINE | re.IGNORECASE,
    ),
    re.compile(r"^Unit\s+\d+[A-Za-z]?\s*[:.\-]?\s*\S.+$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\d+(?:\.\d+){0,3}\s+[A-Z][\w].+$", re.MULTILINE),
    re.compile(r"^[A-Z][A-Z0-9][A-Z0-9 \-/&]{6,}$", re.MULTILINE),
)

_LO_EXTRACT = re.compile(
    r"(?:LO\s*\d+|Learning\s+Outcomes?\s*\d*)\s*[:.\-)]\s*(.+)",
    re.IGNORECASE,
)
_TOPIC_HEADING = re.compile(
    r"^(?:#{1,6}\s+)?(?:core\s+)?topics?\s*[:\-]?\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _recursive_splitter(chunk_size: int, chunk_overlap: int):
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ".", " ", ""],
    )


def _find_structure_starts(text: str) -> List[int]:
    starts: set[int] = set()
    for pattern in _STRUCTURE_PATTERNS:
        for match in pattern.finditer(text):
            # Only treat a match as a boundary when it sits at the start of a line.
            if match.start() == 0 or text[match.start() - 1] == "\n":
                starts.add(match.start())
    return sorted(starts)


def has_detectable_structure(text: str) -> bool:
    """True when the document has at least one interior structural boundary."""
    starts = _find_structure_starts(text)
    if not starts:
        return False
    # A single heading at offset 0 with no later markers is not useful structure.
    if starts == [0]:
        return False
    return True


def split_into_sections(text: str) -> List[str]:
    """Split *text* on structural markers, keeping each heading with its body."""
    starts = _find_structure_starts(text)
    if not starts:
        return [text] if text.strip() else []

    bounds = list(starts)
    if bounds[0] != 0:
        bounds.insert(0, 0)
    bounds.append(len(text))

    sections: List[str] = []
    for i in range(len(bounds) - 1):
        piece = text[bounds[i]:bounds[i + 1]].strip()
        if piece:
            sections.append(piece)
    return sections


def chunk_plain_text(
    text: str,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> List[str]:
    """General-purpose recursive character chunking (chat docs, submissions)."""
    splitter = _recursive_splitter(
        chunk_size or settings.CHUNK_SIZE,
        chunk_overlap or settings.CHUNK_OVERLAP,
    )
    return splitter.split_text(text or "")


def chunk_curriculum_text(
    text: str,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> List[str]:
    """Structure-aware chunking with recursive fallback."""
    size = chunk_size or settings.CURRICULUM_CHUNK_SIZE
    overlap = chunk_overlap or settings.CURRICULUM_CHUNK_OVERLAP
    text = text or ""
    if not text.strip():
        return []

    if not has_detectable_structure(text):
        return chunk_plain_text(text, size, overlap)

    splitter = _recursive_splitter(size, overlap)
    chunks: List[str] = []
    for section in split_into_sections(text):
        if len(section) <= size:
            chunks.append(section)
        else:
            chunks.extend(splitter.split_text(section))
    return [c for c in chunks if c.strip()]


def chunk_documents_structured(documents: Sequence, *, curriculum: bool = True) -> List:
    """Split LangChain Documents, preserving metadata on every chunk."""
    from langchain_core.documents import Document

    size = settings.CURRICULUM_CHUNK_SIZE if curriculum else settings.CHUNK_SIZE
    overlap = settings.CURRICULUM_CHUNK_OVERLAP if curriculum else settings.CHUNK_OVERLAP
    out: List = []
    for doc in documents:
        pieces = (
            chunk_curriculum_text(doc.page_content, size, overlap)
            if curriculum
            else chunk_plain_text(doc.page_content, size, overlap)
        )
        for piece in pieces:
            meta = dict(doc.metadata or {})
            out.append(Document(page_content=piece, metadata=meta))
    return out


def extract_learning_outcomes(text: str) -> List[str]:
    found: List[str] = []
    seen: set[str] = set()
    for match in _LO_EXTRACT.finditer(text or ""):
        line = match.group(0).strip()
        key = line.lower()
        if key not in seen:
            seen.add(key)
            found.append(line)
    return found


def extract_core_topics(text: str, extra: Iterable[str] | None = None) -> List[str]:
    topics: List[str] = []
    seen: set[str] = set()

    def _add(raw: str) -> None:
        cleaned = re.sub(r"^[\-\*\u2022\d.\)\s]+", "", raw).strip(" :-")
        if len(cleaned) < 3 or len(cleaned) > 120:
            return
        key = cleaned.lower()
        if key in seen:
            return
        seen.add(key)
        topics.append(cleaned)

    for item in extra or []:
        _add(item)

    # Bullet list immediately under a "Topics" heading.
    heading = _TOPIC_HEADING.search(text or "")
    if heading:
        tail = (text or "")[heading.end():]
        for line in tail.splitlines():
            stripped = line.strip()
            if not stripped:
                if topics:
                    break
                continue
            if _STRUCTURE_PATTERNS[0].match(stripped) and not stripped.startswith(
                ("-", "*", "•")
            ):
                break
            if stripped[0] in "-*•" or re.match(r"^\d+[\.)]", stripped):
                _add(stripped)

    for match in re.finditer(r"^#{2,4}\s+(.+)$", text or "", re.MULTILINE):
        _add(match.group(1))

    return topics
