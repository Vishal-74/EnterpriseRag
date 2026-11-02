"""FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthError
from app.core.security import decode_access_token
from app.db.session import get_session
from app.models.user import User
from app.repositories.users import UserRepository
from app.runtime import AppRuntime


def get_runtime(request: Request) -> AppRuntime:
    """Return the runtime stored on the application."""
    return request.app.state.runtime


async def get_current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """Resolve the bearer token to a user. Every protected query starts here."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError()
    token = authorization.split(" ", 1)[1].strip()
    user_id = decode_access_token(token, get_runtime(request).settings)
    user = await UserRepository(session).get(user_id)
    if user is None:
        raise AuthError("Invalid or expired token")
    return user


async def limit_login(request: Request) -> None:
    """Throttle sign-in attempts by client address."""
    runtime = get_runtime(request)
    host = request.client.host if request.client else "unknown"
    await runtime.limiter.check(
        f"login:{host}",
        runtime.settings.login_rate_limit,
        runtime.settings.login_rate_window_seconds,
    )


async def limit_chat(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Throttle chat and agent calls per user."""
    runtime = get_runtime(request)
    await runtime.limiter.check(
        f"chat:{user.id}",
        runtime.settings.chat_rate_limit,
        runtime.settings.chat_rate_window_seconds,
    )
    return user
