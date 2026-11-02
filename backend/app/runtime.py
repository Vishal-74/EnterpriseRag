"""Process-wide dependencies shared by requests and background jobs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.core.config import Settings
from app.core.rate_limit import SlidingWindowLimiter
from app.services.llm.router import LLMRouter
from app.services.llm.types import Embedder


class JobDispatcher(Protocol):
    async def ingest(self, document_id: UUID) -> None:
        """Process a document."""

    async def run_agent(self, run_id: UUID) -> None:
        """Execute an agent run."""


@dataclass
class AppRuntime:
    settings: Settings
    embedder: Embedder
    router: LLMRouter
    dispatcher: JobDispatcher
    limiter: SlidingWindowLimiter


_runtime: AppRuntime | None = None


def set_runtime(runtime: AppRuntime) -> None:
    """Install the runtime used by background jobs."""
    global _runtime
    _runtime = runtime


def get_runtime() -> AppRuntime:
    """Return the installed runtime."""
    if _runtime is None:
        raise RuntimeError("Application runtime is not configured")
    return _runtime
