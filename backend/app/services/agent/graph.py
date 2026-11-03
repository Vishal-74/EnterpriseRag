"""LangGraph loop: plan, validate, execute, observe, and stop."""

from __future__ import annotations

import asyncio
import time
from typing import Any, TypedDict
from uuid import UUID

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, ValidationError

from app.models.agent import AgentStep
from app.repositories.agent import AgentRepository
from app.services.agent.prompts import PLANNER_INSTRUCTIONS
from app.services.agent.schemas import AnalyzeArgs, PlanDecision, ReportArgs, SearchArgs
from app.services.agent.tools import (
    ToolContext,
    analyze_documents,
    generate_report,
    search_knowledge_base,
)
from app.services.llm.openai_client import messages_from
from app.services.llm.recorder import SqlUsageRecorder
from app.services.llm.structured import complete_structured
from app.services.llm.types import CompletionRequest


class AgentState(TypedDict, total=False):
    task: str
    steps: list[dict[str, Any]]
    observations: list[dict[str, Any]]
    step_count: int
    invalid_retries: int
    next_tool: str
    next_args: dict[str, Any]
    stop_reason: str
    report: dict[str, Any] | None


_TOOLS: dict[str, tuple[type[BaseModel], Any]] = {
    "search_knowledge_base": (SearchArgs, search_knowledge_base),
    "analyze_documents": (AnalyzeArgs, analyze_documents),
    "generate_report": (ReportArgs, generate_report),
}


class AgentGraph:
    """Run the tool loop for one saved agent run."""

    def __init__(self, context: ToolContext, repository: AgentRepository, run_id: UUID) -> None:
        self._context = context
        self._repository = repository
        self._run_id = run_id
        self._graph = self._compile()

    async def run(self, task: str) -> AgentState:
        """Execute until the planner finishes, the step limit is hit, or the timeout fires."""
        initial: AgentState = {
            "task": task,
            "steps": [],
            "observations": [],
            "step_count": 0,
            "invalid_retries": 0,
            "report": None,
        }
        result = await asyncio.wait_for(
            self._graph.ainvoke(initial, config={"recursion_limit": 30}),
            timeout=self._context.settings.agent_total_timeout_seconds,
        )
        return result

    def _compile(self) -> Any:
        builder = StateGraph(AgentState)
        builder.add_node("plan", self._plan)
        builder.add_node("act", self._act)
        builder.add_node("finish", self._finish)
        builder.set_entry_point("plan")
        builder.add_conditional_edges("plan", self._after_plan, {"act": "act", "finish": "finish"})
        builder.add_conditional_edges("act", self._after_act, {"plan": "plan", "finish": "finish"})
        builder.add_edge("finish", END)
        return builder.compile()

    async def _plan(self, state: AgentState) -> dict[str, Any]:
        step_count = state.get("step_count", 0)
        if step_count >= self._context.settings.agent_max_steps:
            return {"next_tool": "finish", "stop_reason": "step_limit"}
        if (
            step_count == self._context.settings.agent_max_steps - 1
            and not state.get("report")
            and state.get("observations")
        ):
            return {
                "next_tool": "generate_report",
                "next_args": {
                    "title": state.get("task", "Investigation Report")[:100],
                    "focus": state.get("task", "")[:200],
                },
            }
        observations = _render_observations(state.get("observations", []))
        request = CompletionRequest(
            messages=messages_from(
                PLANNER_INSTRUCTIONS.format(version=self._context.settings.prompt_version),
                f"Task:\n{state.get('task', '')}\n\nObservations so far:\n{observations}",
            ),
            temperature=0,
            max_tokens=400,
            json_mode=True,
        )
        decision, _, _ = await complete_structured(
            self._context.router,
            request,
            PlanDecision,
            provider=self._context.provider,
            operation="agent_plan",
            usage=_recorder(self._context),
        )
        return {"next_tool": decision.tool, "next_args": decision.arguments}

    async def _act(self, state: AgentState) -> dict[str, Any]:
        tool_name = state.get("next_tool", "")
        spec = _TOOLS.get(tool_name)
        started = time.perf_counter()
        if spec is None:
            return await self._record(
                state,
                tool_name or "unknown",
                state.get("next_args", {}),
                None,
                "error",
                "Unknown tool",
                started,
                stop="invalid_parameters",
            )
        model, function = spec
        try:
            args = model.model_validate(state.get("next_args") or {})
        except ValidationError as exc:
            retries = state.get("invalid_retries", 0) + 1
            stop = "invalid_parameters" if retries >= 2 else None
            return await self._record(
                state,
                tool_name,
                state.get("next_args", {}),
                {"error": exc.errors()[:3]},
                "invalid_parameters",
                "Tool arguments were invalid",
                started,
                invalid_retries=retries,
                stop=stop,
            )
        self._context.observations = list(state.get("observations", []))
        try:
            payload = await asyncio.wait_for(
                function(args, self._context),
                timeout=self._context.settings.agent_tool_timeout_seconds,
            )
            status = "success"
            error = None
        except TimeoutError:
            payload = {"error": "Tool timed out"}
            status = "timeout"
            error = "Tool timed out"
        except Exception as exc:
            payload = {"error": "Tool failed"}
            status = "error"
            error = exc.__class__.__name__
        update = await self._record(
            state,
            tool_name,
            args.model_dump(mode="json"),
            _shrink(payload),
            status,
            error,
            started,
            invalid_retries=0,
        )
        if tool_name == "generate_report" and status == "success":
            update["report"] = payload
        return update

    async def _finish(self, state: AgentState) -> dict[str, Any]:
        stop_reason = state.get("stop_reason")
        if not stop_reason:
            if state.get("step_count", 0) >= self._context.settings.agent_max_steps:
                stop_reason = "step_limit"
            else:
                stop_reason = "finished"

        report = state.get("report")
        if report is None and state.get("observations"):
            try:
                self._context.observations = list(state.get("observations", []))
                report = await generate_report(
                    ReportArgs(
                        title=state.get("task", "Investigation Report")[:100],
                        focus=state.get("task", "")[:200],
                    ),
                    self._context,
                )
            except Exception:
                pass
        return {"stop_reason": stop_reason, "report": report}

    async def _record(
        self,
        state: AgentState,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_output: dict[str, Any] | None,
        status: str,
        error: str | None,
        started: float,
        *,
        invalid_retries: int | None = None,
        stop: str | None = None,
    ) -> dict[str, Any]:
        latency_ms = int((time.perf_counter() - started) * 1000)
        index = state.get("step_count", 0)
        step = AgentStep(
            run_id=self._run_id,
            step_index=index,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output,
            latency_ms=latency_ms,
            status=status,
            error=error,
        )
        self._repository.add_step(step)
        await self._context.session.commit()
        observation = {
            "tool": tool_name,
            "summary": _summarize(tool_name, tool_output, error),
            "payload": tool_output or {},
        }
        update: dict[str, Any] = {
            "steps": [*state.get("steps", []), {"tool": tool_name, "status": status}],
            "observations": [*state.get("observations", []), observation],
            "step_count": index + 1,
            "invalid_retries": state.get("invalid_retries", 0)
            if invalid_retries is None
            else invalid_retries,
        }
        if stop:
            update["stop_reason"] = stop
            update["next_tool"] = "finish"
        return update

    def _after_plan(self, state: AgentState) -> str:
        if state.get("next_tool") == "finish":
            return "finish"
        return "act"

    def _after_act(self, state: AgentState) -> str:
        if state.get("next_tool") == "finish":
            return "finish"
        if state.get("step_count", 0) >= self._context.settings.agent_max_steps:
            return "finish"
        return "plan"


def _recorder(ctx: ToolContext) -> SqlUsageRecorder:
    return SqlUsageRecorder(ctx.user_id)


def _render_observations(observations: list[dict[str, Any]]) -> str:
    if not observations:
        return "None yet."
    return "\n".join(f"- {item.get('tool')}: {item.get('summary', '')}" for item in observations)[
        :8000
    ]


def _summarize(tool_name: str, payload: dict[str, Any] | None, error: str | None) -> str:
    if error:
        return f"{tool_name} {error}"
    if not payload:
        return tool_name
    if "results" in payload:
        return f"{len(payload['results'])} search results"
    if "summary" in payload:
        return str(payload["summary"])[:500]
    if "title" in payload:
        return f"Report: {payload['title']}"
    return tool_name


def _shrink(payload: dict[str, Any]) -> dict[str, Any]:
    import json

    encoded = json.dumps(payload, default=str)
    if len(encoded) <= 20000:
        return payload
    return {"truncated": True, "preview": encoded[:8000]}
