"""Create agent runs and execute the graph on a background session."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.core.logging import logger
from app.domain import RunStatus
from app.models.agent import AgentRun
from app.models.user import User
from app.repositories.agent import AgentRepository
from app.runtime import JobDispatcher
from app.schemas.agent import AgentRunList, AgentRunRead, AgentRunRequest, AgentStepRead
from app.services.activity import record_activity
from app.services.agent.graph import AgentGraph
from app.services.agent.tools import ToolContext
from app.services.documents.service import DocumentService
from app.services.llm.router import LLMRouter
from app.services.llm.types import Embedder


class AgentService:
    """Start a run and, when called from a job, execute it to completion."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        router: LLMRouter,
        embedder: Embedder,
        dispatcher: JobDispatcher,
    ) -> None:
        self._session = session
        self._settings = settings
        self._router = router
        self._embedder = embedder
        self._dispatcher = dispatcher
        self._runs = AgentRepository(session)

    async def start(self, user: User, payload: AgentRunRequest) -> AgentRunRead:
        """Persist a run and hand it to the dispatcher."""
        documents = DocumentService(self._session, self._settings, _IdleDispatcher())
        await documents.require_owned(user.id, payload.document_ids)
        run = AgentRun(
            user_id=user.id,
            task=payload.task.strip(),
            provider=payload.provider,
            document_ids=[str(document_id) for document_id in payload.document_ids],
            status=RunStatus.running.value,
        )
        self._runs.add_run(run)
        await self._session.flush()
        await record_activity(
            self._session,
            user_id=user.id,
            action="agent.start",
            resource_type="agent_run",
            resource_id=str(run.id),
        )
        await self._session.commit()
        run_id = run.id
        user_id = user.id
        await self._dispatcher.run_agent(run_id)
        self._session.expire_all()
        fresh = await self._runs.get_run(run_id, user_id)
        assert fresh is not None
        return _read(fresh)

    async def execute(self, run_id: UUID) -> None:
        """Run the graph. Called by the worker, not by the request that created the run."""
        run = await self._runs.get_run_for_job(run_id)
        if run is None or run.status != RunStatus.running.value:
            return
        context = ToolContext(
            user_id=run.user_id,
            document_ids=[UUID(value) for value in run.document_ids],
            session=self._session,
            router=self._router,
            embedder=self._embedder,
            settings=self._settings,
            provider=run.provider,
            observations=[],
        )
        graph = AgentGraph(context, self._runs, run.id)
        try:
            state = await graph.run(run.task)
            run.status = RunStatus.completed.value
            run.stop_reason = state.get("stop_reason")
            run.final_output = {
                "report": state.get("report"),
                "stop_reason": run.stop_reason,
            }
            run.error = None
        except TimeoutError:
            run.status = RunStatus.failed.value
            run.stop_reason = "timeout"
            run.error = "Agent timed out before it could finish."
        except AppError as exc:
            logger.warning("agent run stopped: %s", exc.code)
            run.status = RunStatus.failed.value
            run.stop_reason = "error"
            run.error = exc.message
        except Exception:
            logger.exception("agent run failed")
            run.status = RunStatus.failed.value
            run.stop_reason = "error"
            run.error = "Agent failed before it could finish."
        run.finished_at = datetime.now(timezone.utc)
        await self._session.commit()

    async def get_run(self, user: User, run_id: UUID) -> AgentRunRead:
        run = await self._runs.get_run(run_id, user.id)
        if run is None:
            from app.core.errors import NotFoundError

            raise NotFoundError("Agent run not found")
        return _read(run)

    async def list_runs(self, user: User) -> AgentRunList:
        runs = await self._runs.list_runs(user.id)
        return AgentRunList(items=[_read(run) for run in runs])


class _IdleDispatcher:
    async def ingest(self, document_id: UUID) -> None:
        return None

    async def run_agent(self, run_id: UUID) -> None:
        return None


def _read(run: AgentRun) -> AgentRunRead:
    return AgentRunRead(
        id=run.id,
        task=run.task,
        status=run.status,
        stop_reason=run.stop_reason,
        provider=run.provider,
        document_ids=list(run.document_ids or []),
        final_output=run.final_output,
        error=run.error,
        created_at=run.created_at,
        finished_at=run.finished_at,
        steps=[AgentStepRead.model_validate(step) for step in run.steps],
    )
