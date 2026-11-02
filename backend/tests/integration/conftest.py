"""Postgres-backed API fixtures. Skips the module when the database is down."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from app.db import session as db_session
from app.main import create_app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from tests.fakes import FakeEmbedder, FakeRouter
from tests.support import settings_for


def _sync_url() -> str:
    return os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")


@pytest.fixture(scope="session")
def migrated_database() -> None:
    if "enterprise_intel_test" not in os.environ["DATABASE_URL"]:
        pytest.fail("Refusing to migrate a database whose name is not enterprise_intel_test")
    try:
        import psycopg

        with psycopg.connect(_sync_url()) as connection:
            connection.execute("SELECT 1")
    except Exception as exc:
        pytest.skip(f"Postgres is not available: {exc}")
    from alembic import command
    from alembic.config import Config

    backend_dir = Path(__file__).resolve().parents[2]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    command.upgrade(config, "head")


@pytest.fixture
async def api(
    migrated_database, tmp_path
) -> AsyncIterator[tuple[AsyncClient, FakeRouter, FakeEmbedder]]:
    settings = settings_for(tmp_path / "uploads")
    app = create_app(settings, inline_jobs=True)
    embedder = FakeEmbedder()
    router = FakeRouter(lambda _operation, _request: "{}")
    async with app.router.lifespan_context(app):
        app.state.runtime.embedder = embedder
        app.state.runtime.router = router
        db_session.init_engine(settings.async_database_url)
        await _truncate()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, router, embedder
        await _truncate()


async def _truncate() -> None:
    assert db_session.SessionLocal is not None
    async with db_session.SessionLocal() as session:
        await session.execute(
            text(
                "TRUNCATE TABLE agent_steps, agent_runs, messages, conversations, chunks, "
                "documents, usage_logs, activity_logs, answer_cache, embedding_cache, users CASCADE"
            )
        )
        await session.commit()
