"""Dashboard and log routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models.user import User
from app.schemas.metrics import ActivityList, MetricsSummary, UsageList, UsagePoint
from app.services.metrics.service import MetricsService

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/summary", response_model=MetricsSummary)
async def summary(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MetricsSummary:
    """Return totals for the signed-in user."""
    return await MetricsService(session).summary(user)


@router.get("/timeseries", response_model=list[UsagePoint])
async def timeseries(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[UsagePoint]:
    """Return token and latency totals grouped by day and model."""
    return await MetricsService(session).timeseries(user)


@router.get("/usage", response_model=UsageList)
async def usage(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
) -> UsageList:
    """Return recent model calls."""
    return await MetricsService(session).usage(user, status=status, limit=limit)


@router.get("/activity", response_model=ActivityList)
async def activity(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    action: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
) -> ActivityList:
    """Return recent activity events."""
    return await MetricsService(session).activity(user, action=action, limit=limit)
