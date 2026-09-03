"""Convenience launcher: `python run.py` (or use uvicorn directly).

    uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import uvicorn

from app.core.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
