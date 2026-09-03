"""Authentication endpoints."""
from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import LoginRequest, TokenResponse, UserInfo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

# Hash the configured admin password once at import time so we never compare
# plaintext at request time.
_ADMIN_PASSWORD_HASH = hash_password(settings.ADMIN_PASSWORD)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest) -> TokenResponse:
    username_ok = hmac.compare_digest(payload.username, settings.ADMIN_USERNAME)
    password_ok = verify_password(payload.password, _ADMIN_PASSWORD_HASH)

    if not (username_ok and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token = create_access_token(subject=payload.username, role="admin")
    logger.info("Admin '%s' logged in", payload.username)
    return TokenResponse(
        access_token=token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        role="admin",
        username=payload.username,
    )


@router.post("/logout")
async def logout(user: dict = Depends(get_current_user)) -> dict:
    # Tokens are stateless; logout is handled client-side by discarding the token.
    return {"success": True, "message": "Logged out"}


@router.get("/me", response_model=UserInfo)
async def me(user: dict = Depends(get_current_user)) -> UserInfo:
    return UserInfo(username=user.get("sub", "unknown"), role=user.get("role", "user"))
