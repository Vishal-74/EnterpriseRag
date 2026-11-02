"""Background entry points. Each job opens its own database session."""

from __future__ import annotations

from uuid import UUID

from app.db import session as db_session
from app.runtime import get_runtime
from app.services.agent.service import AgentService
from app.services.ingestion.pipeline import IngestionPipeline


async def ingest_job(document_id: UUID) -> None:
    """Parse and embed one document."""
    runtime = get_runtime()
    _ensure_engine(runtime.settings.async_database_url)
    assert db_session.SessionLocal is not None
    async with db_session.SessionLocal() as session:
        pipeline = IngestionPipeline(session, runtime.settings, runtime.embedder)
        await pipeline.run(document_id)


async def agent_job(run_id: UUID) -> None:
    """Execute one agent run."""
    runtime = get_runtime()
    _ensure_engine(runtime.settings.async_database_url)
    assert db_session.SessionLocal is not None
    async with db_session.SessionLocal() as session:
        service = AgentService(
            session,
            runtime.settings,
            runtime.router,
            runtime.embedder,
            runtime.dispatcher,
        )
        await service.execute(run_id)


def _ensure_engine(url: str) -> None:
    if db_session.SessionLocal is None:
        db_session.init_engine(url)
