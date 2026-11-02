"""Dashboard metric models."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class MetricsSummary(BaseModel):
    documents: int
    conversations: int
    agent_runs: int
    requests: int
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float
    avg_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    error_rate: float


class UsagePoint(BaseModel):
    day: datetime
    model: str
    provider: str
    requests: int
    total_tokens: int
    avg_latency_ms: float
    errors: int


class UsageRow(BaseModel):
    id: UUID
    created_at: datetime
    provider: str
    model: str
    operation: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: int
    status: str
    error: str | None
    cost_usd: float


class ActivityRow(BaseModel):
    id: UUID
    created_at: datetime
    action: str
    resource_type: str
    resource_id: str
    detail: dict[str, Any] = Field(default_factory=dict)


class UsageList(BaseModel):
    items: list[UsageRow]


class ActivityList(BaseModel):
    items: list[ActivityRow]
