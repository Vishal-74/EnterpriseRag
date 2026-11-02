"""Authentication routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_runtime, limit_login
from app.db.session import get_session
from app.models.user import User
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserRead
from app.services.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(
    payload: RegisterRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuthResponse:
    """Create an account and return a JWT."""
    service = AuthService(session, get_runtime(request).settings)
    return await service.register(payload)


@router.post("/login", response_model=AuthResponse, dependencies=[Depends(limit_login)])
async def login(
    payload: LoginRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuthResponse:
    """Return a JWT for a valid email and password."""
    service = AuthService(session, get_runtime(request).settings)
    return await service.login(payload)


@router.get("/me", response_model=UserRead)
async def me(user: Annotated[User, Depends(get_current_user)]) -> UserRead:
    """Return the signed-in user."""
    return UserRead.model_validate(user)
