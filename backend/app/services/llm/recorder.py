"""Persist usage events in their own transaction so a failed request still keeps them."""

from __future__ import annotations

from uuid import UUID

from app.db import session as db_session
from app.models.usage import UsageLog
from app.runtime import get_runtime
from app.services.llm.types import UsageEvent


class SqlUsageRecorder:
    """Write each model call into usage_logs and commit immediately."""

    def __init__(self, user_id: UUID | None) -> None:
        self._user_id = user_id

    async def record(self, event: UsageEvent) -> None:
        if db_session.SessionLocal is None:
            db_session.init_engine(get_runtime().settings.async_database_url)
        assert db_session.SessionLocal is not None
        async with db_session.SessionLocal() as session:
            session.add(
                UsageLog(
                    user_id=self._user_id,
                    provider=event.provider,
                    model=event.model,
                    operation=event.operation,
                    prompt_tokens=event.prompt_tokens,
                    completion_tokens=event.completion_tokens,
                    total_tokens=event.prompt_tokens + event.completion_tokens,
                    latency_ms=event.latency_ms,
                    status=event.status,
                    error=event.error,
                    cost_usd=event.cost_usd,
                )
            )
            await session.commit()
