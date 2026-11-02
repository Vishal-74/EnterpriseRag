"""Async engine and session factory."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

engine: AsyncEngine | None = None
SessionLocal: async_sessionmaker[AsyncSession] | None = None


def init_engine(database_url: str | None = None) -> async_sessionmaker[AsyncSession]:
    """Create the global async engine. Safe to call again to retarget tests."""
    global engine, SessionLocal
    url = database_url or get_settings().async_database_url
    engine = create_async_engine(url, pool_pre_ping=True)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    return SessionLocal


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield a session and commit when the request succeeds."""
    if SessionLocal is None:
        init_engine()
    assert SessionLocal is not None
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Close pooled connections."""
    global engine
    if engine is not None:
        await engine.dispose()
        engine = None
