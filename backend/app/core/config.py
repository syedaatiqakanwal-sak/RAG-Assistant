"""Central application configuration.

Values are read from environment variables (optionally via a `.env` file) so the
same code runs in development and production without modification.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import List

from dotenv import load_dotenv

# Load .env from the backend root (one directory above this file's package root).
BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent
load_dotenv(BACKEND_ROOT / ".env")


def _get_bool(key: str, default: bool) -> bool:
    return os.getenv(key, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _get_list(key: str, default: str) -> List[str]:
    raw = os.getenv(key, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


class Settings:
    """Application settings resolved from the environment."""

    # --- General ---------------------------------------------------------
    APP_NAME: str = os.getenv("APP_NAME", "Zeviq AI RAG API")
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = _get_bool("DEBUG", True)

    # --- Paths -----------------------------------------------------------
    # Data and the Chroma DB live at the project root so they stay compatible
    # with the existing ingest.py / chroma_db that already ship with the repo.
    PROJECT_ROOT: Path = PROJECT_ROOT
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", str(PROJECT_ROOT / "data")))
    CHROMA_DIR: Path = Path(os.getenv("CHROMA_DIR", str(PROJECT_ROOT / "chroma_db")))
    STATE_FILE: Path = Path(os.getenv("STATE_FILE", str(BACKEND_ROOT / "app_state.json")))

    # --- RAG / models ----------------------------------------------------
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2")
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    DEFAULT_TEMPERATURE: float = float(os.getenv("DEFAULT_TEMPERATURE", "0.2"))
    DEFAULT_TOP_K: int = int(os.getenv("DEFAULT_TOP_K", "4"))
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "800"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "100"))

    # --- Auth / security -------------------------------------------------
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production-please-32+chars")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "720"))
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin123")

    # --- Networking ------------------------------------------------------
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    CORS_ORIGINS: List[str] = _get_list("CORS_ORIGINS", "*")

    # --- Uploads ---------------------------------------------------------
    MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "50"))
    ALLOWED_EXTENSIONS: List[str] = [".txt", ".pdf", ".docx", ".csv", ".md", ".markdown"]

    # --- Rate limiting ---------------------------------------------------
    RATE_LIMIT_REQUESTS: int = int(os.getenv("RATE_LIMIT_REQUESTS", "30"))
    RATE_LIMIT_WINDOW_SECONDS: int = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

    # Mapping of extension -> sub-folder name inside DATA_DIR.
    EXTENSION_FOLDERS = {
        ".txt": "txt",
        ".pdf": "pdf",
        ".docx": "docx",
        ".csv": "csv",
        ".md": "markdown",
        ".markdown": "markdown",
    }

    # Human friendly category labels keyed by folder name.
    CATEGORY_LABELS = {
        "txt": "Text",
        "pdf": "PDF",
        "docx": "Word",
        "csv": "CSV",
        "markdown": "Markdown",
    }

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_MB * 1024 * 1024

    def folder_for_extension(self, ext: str) -> Path:
        folder = self.EXTENSION_FOLDERS.get(ext.lower())
        if folder is None:
            raise ValueError(f"Unsupported extension: {ext}")
        return self.DATA_DIR / folder

    def ensure_dirs(self) -> None:
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        for folder in self.EXTENSION_FOLDERS.values():
            (self.DATA_DIR / folder).mkdir(parents=True, exist_ok=True)
        self.CHROMA_DIR.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings


settings = get_settings()
