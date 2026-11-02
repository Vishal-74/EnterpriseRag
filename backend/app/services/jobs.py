"""Schedule ingestion and agent work without blocking the HTTP response."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from uuid import UUID

from app.core.logging import logger, request_id_var

Job = Callable[[UUID], Awaitable[None]]
_pending: set[asyncio.Task[None]] = set()


class AsyncJobDispatcher:
    """Run jobs on the current event loop after the response is produced."""

    def __init__(self, ingest: Job, agent: Job) -> None:
        self._ingest = ingest
        self._agent = agent

    async def ingest(self, document_id: UUID) -> None:
        self._spawn(self._ingest, document_id)

    async def run_agent(self, run_id: UUID) -> None:
        self._spawn(self._agent, run_id)

    def _spawn(self, job: Job, identifier: UUID) -> None:
        task = asyncio.create_task(_guard(job, identifier))
        _pending.add(task)
        task.add_done_callback(_pending.discard)


class InlineJobDispatcher:
    """Run jobs immediately. Tests use this so a follow-up read sees the result."""

    def __init__(self, ingest: Job, agent: Job) -> None:
        self._ingest = ingest
        self._agent = agent

    async def ingest(self, document_id: UUID) -> None:
        await _guard(self._ingest, document_id)

    async def run_agent(self, run_id: UUID) -> None:
        await _guard(self._agent, run_id)


async def _guard(job: Job, identifier: UUID) -> None:
    token = request_id_var.set(f"job:{identifier}")
    try:
        await job(identifier)
    except Exception:
        logger.exception("background job failed")
    finally:
        request_id_var.reset(token)
