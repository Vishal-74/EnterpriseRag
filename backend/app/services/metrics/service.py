"""Read dashboard numbers from the log tables."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.usage import UsageRepository
from app.schemas.metrics import (
    ActivityList,
    ActivityRow,
    MetricsSummary,
    UsageList,
    UsagePoint,
    UsageRow,
)


class MetricsService:
    """User-scoped usage and activity queries."""

    def __init__(self, session: AsyncSession) -> None:
        self._usage = UsageRepository(session)

    async def summary(self, user: User) -> MetricsSummary:
        return MetricsSummary.model_validate(await self._usage.summary(user.id))

    async def timeseries(self, user: User) -> list[UsagePoint]:
        rows = await self._usage.timeseries(user.id)
        return [
            UsagePoint(
                day=day,
                model=model,
                provider=provider,
                requests=requests,
                total_tokens=tokens,
                avg_latency_ms=latency,
                errors=errors,
            )
            for day, model, provider, requests, tokens, latency, errors in rows
        ]

    async def usage(self, user: User, *, status: str | None, limit: int) -> UsageList:
        rows = await self._usage.list_usage(user.id, status=status, limit=limit)
        return UsageList(
            items=[
                UsageRow(
                    id=row.id,
                    created_at=row.created_at,
                    provider=row.provider,
                    model=row.model,
                    operation=row.operation,
                    prompt_tokens=row.prompt_tokens,
                    completion_tokens=row.completion_tokens,
                    total_tokens=row.total_tokens,
                    latency_ms=row.latency_ms,
                    status=row.status,
                    error=row.error,
                    cost_usd=float(row.cost_usd),
                )
                for row in rows
            ]
        )

    async def activity(self, user: User, *, action: str | None, limit: int) -> ActivityList:
        rows = await self._usage.list_activity(user.id, action=action, limit=limit)
        return ActivityList(
            items=[
                ActivityRow(
                    id=row.id,
                    created_at=row.created_at,
                    action=row.action,
                    resource_type=row.resource_type,
                    resource_id=row.resource_id,
                    detail=dict(row.detail or {}),
                )
                for row in rows
            ]
        )
