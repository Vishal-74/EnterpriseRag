"""Agent API models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AgentRunRequest(BaseModel):
    task: str = Field(min_length=3, max_length=4000)
    document_ids: list[UUID] = Field(default_factory=list)
    provider: Literal["gemini", "huggingface"] | None = None


class AgentStepRead(BaseModel):
    id: UUID
    step_index: int
    tool_name: str
    tool_input: dict[str, Any]
    tool_output: dict[str, Any] | None
    latency_ms: int
    status: str
    error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentRunRead(BaseModel):
    id: UUID
    task: str
    status: str
    stop_reason: str | None
    provider: str | None
    document_ids: list[str]
    final_output: dict[str, Any] | None
    error: str | None
    created_at: datetime
    finished_at: datetime | None
    steps: list[AgentStepRead] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class AgentRunList(BaseModel):
    items: list[AgentRunRead]
