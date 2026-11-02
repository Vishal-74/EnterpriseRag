"""Agent run persistence."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.agent import AgentRun, AgentStep


class AgentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add_run(self, run: AgentRun) -> None:
        self._session.add(run)

    def add_step(self, step: AgentStep) -> None:
        self._session.add(step)

    async def get_run(self, run_id: UUID, user_id: UUID) -> AgentRun | None:
        stmt = (
            select(AgentRun)
            .options(selectinload(AgentRun.steps))
            .where(AgentRun.id == run_id, AgentRun.user_id == user_id)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_run_for_job(self, run_id: UUID) -> AgentRun | None:
        stmt = select(AgentRun).where(AgentRun.id == run_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_runs(self, user_id: UUID) -> list[AgentRun]:
        stmt = (
            select(AgentRun)
            .options(selectinload(AgentRun.steps))
            .where(AgentRun.user_id == user_id)
            .order_by(AgentRun.created_at.desc())
        )
        return list((await self._session.execute(stmt)).scalars().all())
