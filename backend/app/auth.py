"""Entra ID (Azure AD) JWT authentication.

Validates bearer tokens against the tenant's JWKS, auto-provisions a User row
on first sight, and exposes a `current_user` FastAPI dependency.

When `settings.dev_bypass_auth` is True (or required Azure config is missing),
auth is bypassed and a synthetic local user is used. This keeps the app usable
before an Entra app registration is set up.
"""
import logging
import time
import uuid

import httpx
from cachetools import TTLCache
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from jose.exceptions import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.models import User

logger = logging.getLogger(__name__)

DEV_USER_ID = "dev-local-user"
DEV_USER_EMAIL = "dev@local"
DEV_USER_NAME = "Local Dev"

_bearer = HTTPBearer(auto_error=False)
_jwks_cache: TTLCache = TTLCache(maxsize=4, ttl=3600)


def _auth_enabled() -> bool:
    if settings.dev_bypass_auth:
        return False
    return bool(settings.azure_tenant_id and settings.azure_client_id)


def _issuer() -> str:
    return f"https://login.microsoftonline.com/{settings.azure_tenant_id}/v2.0"


def _jwks_url() -> str:
    return f"https://login.microsoftonline.com/{settings.azure_tenant_id}/discovery/v2.0/keys"


async def _get_jwks() -> dict:
    key = settings.azure_tenant_id
    cached = _jwks_cache.get(key)
    if cached:
        return cached
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(_jwks_url())
        resp.raise_for_status()
        jwks = resp.json()
    _jwks_cache[key] = jwks
    return jwks


async def _decode_token(token: str) -> dict:
    try:
        unverified = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Malformed token: {exc}")
    kid = unverified.get("kid")
    if not kid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing kid in token header")

    jwks = await _get_jwks()
    key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if not key:
        # Refresh once in case of rotation.
        _jwks_cache.clear()
        jwks = await _get_jwks()
        key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if not key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Signing key not found")

    try:
        # Accept both `api://<client_id>` and bare client_id as audience.
        audiences = [settings.azure_client_id, f"api://{settings.azure_client_id}"]
        return jwt.decode(
            token,
            key,
            algorithms=[key.get("alg", "RS256")],
            audience=audiences,
            issuer=_issuer(),
        )
    except JWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {exc}")


async def _upsert_user(
    session: AsyncSession,
    *,
    entra_oid: str | None,
    email: str,
    display_name: str | None,
) -> User:
    user: User | None = None
    if entra_oid:
        res = await session.execute(select(User).where(User.entra_oid == entra_oid))
        user = res.scalar_one_or_none()
    if not user:
        res = await session.execute(select(User).where(User.email == email))
        user = res.scalar_one_or_none()
    now = int(time.time())
    if user:
        if entra_oid and not user.entra_oid:
            user.entra_oid = entra_oid
        if display_name and user.display_name != display_name:
            user.display_name = display_name
        user.last_seen_at = now
    else:
        user = User(
            id=str(uuid.uuid4()),
            entra_oid=entra_oid,
            email=email,
            display_name=display_name,
            created_at=now,
            last_seen_at=now,
        )
        session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _ensure_dev_user(session: AsyncSession) -> User:
    user = await session.get(User, DEV_USER_ID)
    now = int(time.time())
    if user:
        user.last_seen_at = now
        await session.commit()
        await session.refresh(user)
        return user
    user = User(
        id=DEV_USER_ID,
        entra_oid=None,
        email=DEV_USER_EMAIL,
        display_name=DEV_USER_NAME,
        created_at=now,
        last_seen_at=now,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    if not _auth_enabled():
        return await _ensure_dev_user(session)

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")

    claims = await _decode_token(credentials.credentials)
    entra_oid = claims.get("oid") or claims.get("sub")
    email = (
        claims.get("preferred_username")
        or claims.get("email")
        or claims.get("upn")
        or f"{entra_oid}@unknown"
    )
    name = claims.get("name") or email
    return await _upsert_user(session, entra_oid=entra_oid, email=email, display_name=name)


async def optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User | None:
    """Variant used for websocket-like or background endpoints that should not 401."""
    if not _auth_enabled():
        return await _ensure_dev_user(session)
    if credentials is None:
        return None
    try:
        claims = await _decode_token(credentials.credentials)
    except HTTPException:
        return None
    entra_oid = claims.get("oid") or claims.get("sub")
    email = (
        claims.get("preferred_username")
        or claims.get("email")
        or claims.get("upn")
        or f"{entra_oid}@unknown"
    )
    name = claims.get("name") or email
    return await _upsert_user(session, entra_oid=entra_oid, email=email, display_name=name)
