"""Who is acting. Supabase JWTs in production; an X-Dev-User header in ENV=dev only."""

from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.models import User


def current_user(
    session: Session = Depends(get_session),
    x_dev_user: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> User:
    settings = get_settings()
    if settings.env == "dev":
        if not x_dev_user:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "X-Dev-User header required in dev")
        user = session.get(User, x_dev_user)
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown user")
        return user
    if not settings.supabase_jwt_secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "auth not configured (see docs/NEEDS_JAKE.md)")
    # Supabase JWT verification lands when the Supabase project exists.
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")


def require_role(*roles: str) -> Callable[[User], User]:
    def _check(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"requires role {', '.join(roles)}")
        return user

    return _check
