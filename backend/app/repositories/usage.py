"""Usage, activity, and dashboard queries."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentRun
from app.models.conversation import Conversation
from app.models.document import Document
from app.models.usage import ActivityLog, UsageLog


class UsageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add_usage(self, row: UsageLog) -> None:
        self._session.add(row)

    def add_activity(self, row: ActivityLog) -> None:
        self._session.add(row)

    async def summary(self, user_id: UUID) -> dict[str, float | int]:
        documents = await self._session.scalar(
            select(func.count()).select_from(Document).where(Document.user_id == user_id)
        )
        conversations = await self._session.scalar(
            select(func.count()).select_from(Conversation).where(Conversation.user_id == user_id)
        )
        runs = await self._session.scalar(
            select(func.count()).select_from(AgentRun).where(AgentRun.user_id == user_id)
        )
        stmt = select(
            func.count(UsageLog.id),
            func.coalesce(func.sum(UsageLog.total_tokens), 0),
            func.coalesce(func.sum(UsageLog.prompt_tokens), 0),
            func.coalesce(func.sum(UsageLog.completion_tokens), 0),
            func.coalesce(func.sum(UsageLog.cost_usd), 0),
            func.coalesce(func.avg(UsageLog.latency_ms), 0),
            func.coalesce(
                func.sum(case((UsageLog.status != "success", 1), else_=0)),
                0,
            ),
        ).where(UsageLog.user_id == user_id)
        row = (await self._session.execute(stmt)).one()
        requests = int(row[0] or 0)
        errors = int(row[6] or 0)
        percentiles = await self._percentiles(user_id)
        return {
            "documents": int(documents or 0),
            "conversations": int(conversations or 0),
            "agent_runs": int(runs or 0),
            "requests": requests,
            "total_tokens": int(row[1] or 0),
            "prompt_tokens": int(row[2] or 0),
            "completion_tokens": int(row[3] or 0),
            "estimated_cost_usd": float(row[4] or 0),
            "avg_latency_ms": float(row[5] or 0),
            "error_rate": (errors / requests) if requests else 0.0,
            "p50_latency_ms": percentiles[0],
            "p95_latency_ms": percentiles[1],
        }

    async def _percentiles(self, user_id: UUID) -> tuple[float, float]:
        stmt = select(
            func.percentile_cont(0.5).within_group(UsageLog.latency_ms),
            func.percentile_cont(0.95).within_group(UsageLog.latency_ms),
        ).where(UsageLog.user_id == user_id)
        row = (await self._session.execute(stmt)).one()
        return float(row[0] or 0), float(row[1] or 0)

    async def timeseries(
        self, user_id: UUID
    ) -> list[tuple[datetime, str, str, int, int, float, int]]:
        day = func.date_trunc("day", UsageLog.created_at)
        stmt = (
            select(
                day,
                UsageLog.model,
                UsageLog.provider,
                func.count(UsageLog.id),
                func.coalesce(func.sum(UsageLog.total_tokens), 0),
                func.coalesce(func.avg(UsageLog.latency_ms), 0),
                func.coalesce(func.sum(case((UsageLog.status != "success", 1), else_=0)), 0),
            )
            .where(UsageLog.user_id == user_id)
            .group_by(day, UsageLog.model, UsageLog.provider)
            .order_by(day.asc())
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            (row[0], row[1], row[2], int(row[3]), int(row[4]), float(row[5]), int(row[6]))
            for row in rows
        ]

    async def list_usage(self, user_id: UUID, *, status: str | None, limit: int) -> list[UsageLog]:
        stmt = select(UsageLog).where(UsageLog.user_id == user_id)
        if status:
            stmt = stmt.where(UsageLog.status == status)
        stmt = stmt.order_by(UsageLog.created_at.desc()).limit(limit)
        return list((await self._session.execute(stmt)).scalars().all())

    async def list_activity(
        self, user_id: UUID, *, action: str | None, limit: int
    ) -> list[ActivityLog]:
        stmt = select(ActivityLog).where(ActivityLog.user_id == user_id)
        if action:
            stmt = stmt.where(ActivityLog.action == action)
        stmt = stmt.order_by(ActivityLog.created_at.desc()).limit(limit)
        return list((await self._session.execute(stmt)).scalars().all())
