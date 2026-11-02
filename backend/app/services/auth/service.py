"""Register and log in users."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AuthError, ConflictError
from app.core.security import create_access_token, dummy_verify, hash_password, verify_password
from app.models.user import User
from app.repositories.users import UserRepository
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserRead
from app.services.activity import record_activity


class AuthService:
    """Create accounts and issue JWTs. Passwords are stored only as Argon2 hashes."""

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._users = UserRepository(session)

    async def register(self, payload: RegisterRequest) -> AuthResponse:
        email = payload.email.lower()
        if await self._users.get_by_email(email) is not None:
            raise ConflictError("An account with that email already exists.")
        user = User(email=email, password_hash=hash_password(payload.password))
        self._users.add(user)
        await self._session.flush()
        await record_activity(
            self._session,
            user_id=user.id,
            action="auth.register",
            resource_type="user",
            resource_id=str(user.id),
        )
        await self._session.commit()
        return self._response(user)

    async def login(self, payload: LoginRequest) -> AuthResponse:
        email = payload.email.lower()
        user = await self._users.get_by_email(email)
        if user is None:
            dummy_verify(payload.password)
            raise AuthError("Invalid email or password")
        if not verify_password(payload.password, user.password_hash):
            raise AuthError("Invalid email or password")
        await record_activity(
            self._session,
            user_id=user.id,
            action="auth.login",
            resource_type="user",
            resource_id=str(user.id),
        )
        await self._session.commit()
        return self._response(user)

    def _response(self, user: User) -> AuthResponse:
        return AuthResponse(
            access_token=create_access_token(user.id, self._settings),
            user=UserRead.model_validate(user),
        )
