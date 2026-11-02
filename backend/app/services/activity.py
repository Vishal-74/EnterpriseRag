"""Write an activity row inside the current transaction."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usage import ActivityLog


async def record_activity(
    session: AsyncSession,
    *,
    user_id: UUID | None,
    action: str,
    resource_type: str = "",
    resource_id: str = "",
    detail: dict[str, Any] | None = None,
) -> None:
    """Append an activity event. Callers commit the surrounding transaction."""
    session.add(
        ActivityLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=detail or {},
        )
    )
