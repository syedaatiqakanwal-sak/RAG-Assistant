"""Core RAG engine: retrieval over Chroma + answer generation with Ollama.

Exposes both a blocking ``answer`` call and a token ``stream`` generator so the
API can offer streaming (typewriter) responses as well as plain JSON.
"""
from __future__ import annotations

import logging
import threading
from typing import Dict, Iterator, List, Optional, Tuple

from app.core.config import settings
from app.core.embeddings import get_embeddings
from app.core.ingestion import CHROMA_COLLECTION

logger = logging.getLogger(__name__)

_vectorstore = None
_lock = threading.Lock()

PROMPT_TEMPLATE = """You are Zeviq AI, a helpful assistant that answers questions \
strictly using the provided context from the user's documents.

Guidelines:
- Answer using ONLY the information in the context below.
- If the answer is not contained in the context, say you don't have enough \
information in the documents to answer.
- Be concise, accurate, and well-structured. Use markdown formatting where helpful.

Context:
{context}

Question: {question}

Answer:"""


def invalidate() -> None:
    """Drop the cached vector store so the next call reloads fresh data."""
    global _vectorstore
    with _lock:
        _vectorstore = None


def _get_vectorstore():
    global _vectorstore
    if _vectorstore is None:
        with _lock:
            if _vectorstore is None:
                from langchain_community.vectorstores import Chroma

                _vectorstore = Chroma(
                    persist_directory=str(settings.CHROMA_DIR),
                    embedding_function=get_embeddings(),
                    collection_name=CHROMA_COLLECTION,
                )
    return _vectorstore


def _build_llm(temperature: float):
    from langchain_ollama import OllamaLLM

    return OllamaLLM(
        model=settings.OLLAMA_MODEL,
        temperature=temperature,
        base_url=settings.OLLAMA_BASE_URL,
    )


def retrieve(question: str, top_k: Optional[int] = None) -> List:
    """Return the most relevant LangChain Documents for a question."""
    top_k = top_k or settings.DEFAULT_TOP_K
    retriever = _get_vectorstore().as_retriever(search_kwargs={"k": top_k})
    return retriever.invoke(question)


def _format_context(docs: List) -> str:
    blocks = []
    for i, doc in enumerate(docs, 1):
        name = doc.metadata.get("filename", "Unknown")
        blocks.append(f"[Source {i}: {name}]\n{doc.page_content}")
    return "\n\n".join(blocks)


def serialize_sources(docs: List) -> List[Dict]:
    """Convert LangChain Documents into JSON-serialisable source dicts."""
    sources = []
    for doc in docs:
        content = doc.page_content or ""
        sources.append({
            "content": content,
            "preview": content[:280] + ("..." if len(content) > 280 else ""),
            "source": doc.metadata.get("source", "Unknown"),
            "filename": doc.metadata.get("filename", "Unknown"),
            "file_type": doc.metadata.get("file_type", "Unknown"),
            "category": doc.metadata.get("category", "Unknown"),
            "page": doc.metadata.get("page"),
        })
    return sources


def answer(question: str, temperature: Optional[float] = None,
           top_k: Optional[int] = None) -> Tuple[str, List[Dict]]:
    """Generate a complete answer plus its source attributions."""
    temperature = settings.DEFAULT_TEMPERATURE if temperature is None else temperature
    docs = retrieve(question, top_k)

    if not docs:
        return (
            "I don't have any indexed documents yet, so I can't answer that. "
            "Please ask an administrator to upload and index some documents.",
            [],
        )

    prompt = PROMPT_TEMPLATE.format(context=_format_context(docs), question=question)
    llm = _build_llm(temperature)
    response = llm.invoke(prompt)
    return response, serialize_sources(docs)


def stream(question: str, temperature: Optional[float] = None,
           top_k: Optional[int] = None) -> Tuple[Iterator[str], List[Dict]]:
    """Return a token generator and the resolved sources.

    Sources are resolved up-front (retrieval is fast) so the caller can emit them
    alongside the streamed tokens.
    """
    temperature = settings.DEFAULT_TEMPERATURE if temperature is None else temperature
    docs = retrieve(question, top_k)
    sources = serialize_sources(docs)

    if not docs:
        def _empty() -> Iterator[str]:
            yield (
                "I don't have any indexed documents yet, so I can't answer that. "
                "Please ask an administrator to upload and index some documents."
            )

        return _empty(), sources

    prompt = PROMPT_TEMPLATE.format(context=_format_context(docs), question=question)
    llm = _build_llm(temperature)

    def _generate() -> Iterator[str]:
        for token in llm.stream(prompt):
            yield token

    return _generate(), sources


def health() -> Dict:
    """Best-effort health snapshot of the RAG dependencies."""
    info: Dict = {"chroma_dir": str(settings.CHROMA_DIR)}
    try:
        info["indexed"] = _get_vectorstore() is not None
    except Exception as exc:  # noqa: BLE001
        info["indexed"] = False
        info["error"] = str(exc)
    return info
