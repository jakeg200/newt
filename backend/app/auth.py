"""Who is acting.

Production: a Supabase Auth access token (`Authorization: Bearer …`), verified either with the
project's JWT secret (HS256) or its published signing keys (JWKS). The token's email must belong
to a user provisioned in this app (`python -m app.admin`); there is no self-signup.

Development (ENV=dev): an `X-Dev-User` header names the acting user. It is refused anywhere else.
"""

from collections.abc import Callable
from functools import lru_cache

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.models import User


@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, cache_keys=True, lifespan=3600)


def verify_token(token: str) -> dict:
    """Return the token's claims, or raise HTTPException(401)."""
    settings = get_settings()
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") == "HS256":
            if not settings.supabase_jwt_secret:
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
            key = settings.supabase_jwt_secret
        else:
            if not settings.supabase_url:
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
            key = _jwks_client(f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json").get_signing_key_from_jwt(token).key
        return jwt.decode(token, key, algorithms=["HS256", "RS256", "ES256"], audience="authenticated",
                          options={"require": ["exp", "sub"]})
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session expired; sign in again") from exc
    except (jwt.PyJWTError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials") from exc


def current_user(
    session: Session = Depends(get_session),
    x_dev_user: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> User:
    settings = get_settings()
    if settings.env == "dev" and x_dev_user:
        user = session.get(User, x_dev_user)
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown user")
        return user
    if not authorization or not authorization.lower().startswith("bearer "):
        if settings.env == "dev":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "X-Dev-User header required in dev")
        if not (settings.supabase_jwt_secret or settings.supabase_url):
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "auth not configured (see docs/NEEDS_JAKE.md)")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign in first")
    claims = verify_token(authorization.split(" ", 1)[1].strip())
    email = (claims.get("email") or "").strip().lower()
    user = session.scalar(select(User).where(func.lower(User.email) == email)) if email else None
    if user is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "no account for this email here; ask your administrator")
    return user


def require_role(*roles: str) -> Callable[[User], User]:
    def _check(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"requires role {', '.join(roles)}")
        return user

    return _check
