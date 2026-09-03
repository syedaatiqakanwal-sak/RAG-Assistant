"""Document ingestion: load files from the data folders, chunk them, and (re)build
the Chroma vector store.

This module rebuilds the general-chat Chroma collection (``settings.CHAT_COLLECTION``).
Curriculum documents are indexed separately via ``app.core.curriculum.sync_curriculum``.
"""
from __future__ import annotations

import logging
import warnings
from pathlib import Path
from typing import Dict, List

from app.core.config import settings
from app.core.embeddings import get_embeddings

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

# General-chat collection. Curriculum / grading memory use their own collections.
CHROMA_COLLECTION = settings.CHAT_COLLECTION


def _loader_for(ext: str):
    """Return the appropriate LangChain loader class for a file extension."""
    from langchain_community.document_loaders import (
        CSVLoader,
        PyPDFLoader,
        TextLoader,
        UnstructuredWordDocumentLoader,
    )

    return {
        ".txt": TextLoader,
        ".pdf": PyPDFLoader,
        ".docx": UnstructuredWordDocumentLoader,
        ".csv": CSVLoader,
        ".md": TextLoader,
        ".markdown": TextLoader,
    }[ext]


def load_file(path: Path) -> List:
    """Load one file into LangChain Documents without assuming DATA_DIR type folders."""
    ext = path.suffix.lower()
    loader_cls = _loader_for(ext)
    if ext in {".txt", ".md", ".markdown"}:
        loader = loader_cls(str(path), encoding="utf-8", autodetect_encoding=True)
    else:
        loader = loader_cls(str(path))
    docs = loader.load()
    for doc in docs:
        doc.metadata["source"] = str(path)
        doc.metadata["filename"] = path.name
        doc.metadata["file_type"] = ext
        if "page" in doc.metadata:
            try:
                doc.metadata["page"] = int(doc.metadata["page"])
            except (TypeError, ValueError):
                pass
    return docs


def extract_text(path: Path) -> str:
    """Join every loaded page/document from *path* into a single string."""
    docs = load_file(path)
    return "\n\n".join(doc.page_content or "" for doc in docs).strip()


def _load_single(path: Path) -> List:
    """Load one document file into a list of LangChain Document objects."""
    docs = load_file(path)
    folder = settings.EXTENSION_FOLDERS.get(path.suffix.lower(), path.parent.name)
    for doc in docs:
        doc.metadata["category"] = settings.CATEGORY_LABELS.get(folder, folder)
    return docs


def load_all_documents() -> List:
    """Load every supported document across all data sub-folders."""
    all_docs: List = []
    for ext, folder_name in settings.EXTENSION_FOLDERS.items():
        folder = settings.DATA_DIR / folder_name
        if not folder.exists():
            continue
        for file_path in sorted(folder.glob(f"*{ext}")):
            try:
                all_docs.extend(_load_single(file_path))
            except Exception as exc:  # noqa: BLE001 - keep ingesting other files
                logger.warning("Failed to load %s: %s", file_path, exc)
    return all_docs


def chunk_documents(documents: List, chunk_size: int | None = None,
                    chunk_overlap: int | None = None) -> List:
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size or settings.CHUNK_SIZE,
        chunk_overlap=chunk_overlap or settings.CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", ".", " ", ""],
    )
    return splitter.split_documents(documents)


def _clear_collection() -> None:
    """Drop the existing Chroma collection so re-indexing doesn't duplicate data."""
    try:
        import chromadb

        client = chromadb.PersistentClient(path=str(settings.CHROMA_DIR))
        try:
            client.delete_collection(CHROMA_COLLECTION)
        except Exception:
            pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not clear existing collection: %s", exc)


def reindex(chunk_size: int | None = None, chunk_overlap: int | None = None) -> Dict:
    """Rebuild the entire vector store from the documents on disk.

    Returns a summary dict with document/chunk counts.
    """
    from langchain_community.vectorstores import Chroma

    # Invalidate any cached retriever/chain before mutating the store.
    from app.core import rag as rag_module

    documents = load_all_documents()
    _clear_collection()
    rag_module.invalidate()

    if not documents:
        return {"documents": 0, "chunks": 0, "files": _file_counts()}

    chunks = chunk_documents(documents, chunk_size, chunk_overlap)
    embeddings = get_embeddings()

    Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(settings.CHROMA_DIR),
        collection_name=CHROMA_COLLECTION,
    )

    rag_module.invalidate()
    logger.info("Re-indexed %d documents into %d chunks", len(documents), len(chunks))
    return {"documents": len(documents), "chunks": len(chunks), "files": _file_counts()}


def _file_counts() -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for ext, folder_name in settings.EXTENSION_FOLDERS.items():
        folder = settings.DATA_DIR / folder_name
        counts[folder_name] = len(list(folder.glob(f"*{ext}"))) if folder.exists() else 0
    return counts


def total_chunks() -> int:
    """Return the number of chunks currently stored in Chroma (0 if empty)."""
    try:
        import chromadb

        client = chromadb.PersistentClient(path=str(settings.CHROMA_DIR))
        try:
            collection = client.get_collection(CHROMA_COLLECTION)
            return collection.count()
        except Exception:
            return 0
    except Exception:
        return 0
