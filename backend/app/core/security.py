"""Password hashing and JWT access tokens."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

from app.core.config import Settings
from app.core.errors import AuthError

_hasher = PasswordHasher()
_dummy_hash: str | None = None


def hash_password(password: str) -> str:
    """Hash a password with Argon2id."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Return whether the password matches the stored hash."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError):
        return False


def dummy_verify(password: str) -> None:
    """Spend a hash verification when the user does not exist."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = _hasher.hash("not-a-real-password")
    verify_password(password, _dummy_hash)


def create_access_token(user_id: UUID, settings: Settings) -> str:
    """Create a signed JWT that expires according to settings."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_expire_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings) -> UUID:
    """Return the user id from a valid token, or raise AuthError."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return UUID(str(payload["sub"]))
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise AuthError("Invalid or expired token") from exc
