"""Agent routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_runtime, limit_chat
from app.db.session import get_session
from app.models.user import User
from app.schemas.agent import AgentRunList, AgentRunRead, AgentRunRequest
from app.services.agent.service import AgentService

router = APIRouter(prefix="/agent/runs", tags=["agent"])


def _service(request: Request, session: AsyncSession) -> AgentService:
    runtime = get_runtime(request)
    return AgentService(
        session,
        runtime.settings,
        runtime.router,
        runtime.embedder,
        runtime.dispatcher,
    )


@router.post("", response_model=AgentRunRead, status_code=status.HTTP_202_ACCEPTED)
async def start_run(
    payload: AgentRunRequest,
    request: Request,
    user: Annotated[User, Depends(limit_chat)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AgentRunRead:
    """Start an agent run. Poll the run to see steps as they are stored."""
    return await _service(request, session).start(user, payload)


@router.get("", response_model=AgentRunList)
async def list_runs(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AgentRunList:
    """List the caller's agent runs."""
    return await _service(request, session).list_runs(user)


@router.get("/{run_id}", response_model=AgentRunRead)
async def get_run(
    run_id: UUID,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AgentRunRead:
    """Return one run and its step timeline."""
    return await _service(request, session).get_run(user, run_id)
