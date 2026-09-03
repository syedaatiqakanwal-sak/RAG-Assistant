"""Authentication helpers: password hashing (bcrypt) and JWT (stdlib HS256).

We intentionally implement JWT with the standard library (`hmac`, `hashlib`,
`base64`, `json`) so the project has no hard dependency on `python-jose` /
`passlib`, which are not guaranteed to be installed in every environment.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Optional

import bcrypt

from app.core.config import settings


# --------------------------------------------------------------------------- #
# Password hashing
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    """Return a bcrypt hash for the given plaintext password."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Constant-time verification of a plaintext password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# --------------------------------------------------------------------------- #
# JWT (HS256) implemented with the standard library
# --------------------------------------------------------------------------- #
def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _sign(message: bytes) -> bytes:
    return hmac.new(settings.SECRET_KEY.encode("utf-8"), message, hashlib.sha256).digest()


def create_access_token(subject: str, role: str = "admin",
                        expires_minutes: Optional[int] = None) -> str:
    """Create a signed JWT for the given subject."""
    expires_minutes = expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    issued_at = int(time.time())
    payload = {
        "sub": subject,
        "role": role,
        "iat": issued_at,
        "exp": issued_at + expires_minutes * 60,
    }
    header = {"alg": settings.JWT_ALGORITHM, "typ": "JWT"}

    segments = [
        _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8")),
        _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
    ]
    signing_input = ".".join(segments).encode("ascii")
    signature = _sign(signing_input)
    segments.append(_b64url_encode(signature))
    return ".".join(segments)


def decode_access_token(token: str) -> Optional[dict]:
    """Validate signature + expiry and return the payload, or None if invalid."""
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
    except ValueError:
        return None

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected_sig = _sign(signing_input)
    try:
        actual_sig = _b64url_decode(signature_b64)
    except Exception:
        return None

    if not hmac.compare_digest(expected_sig, actual_sig):
        return None

    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception:
        return None

    if int(payload.get("exp", 0)) < int(time.time()):
        return None

    return payload
