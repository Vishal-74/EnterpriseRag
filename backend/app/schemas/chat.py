"""Chat API models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class Citation(BaseModel):
    document_id: UUID
    document_name: str
    chunk_id: UUID
    page_start: int | None = None
    page_end: int | None = None
    section: str | None = None
    row_start: int | None = None
    row_end: int | None = None
    snippet: str
    score: float


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: UUID | None = None
    document_ids: list[UUID] | None = None
    provider: Literal["openai", "anthropic", "gemini", "huggingface"] | None = None


class ChatResponse(BaseModel):
    conversation_id: UUID
    message_id: UUID
    answer: str
    citations: list[Citation]
    insufficient_evidence: bool
    conflict: bool
    conflict_summary: str | None = None
    unsupported_claims: list[str] = Field(default_factory=list)
    ungrounded: bool = False
    injection_flags: list[str] = Field(default_factory=list)
    answer_origin: Literal["model", "retrieval_gate", "cache"]
    provider: str | None = None
    model: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: int = 0
    history_tokens: int = 0
    cached: bool = False


class MessageRead(BaseModel):
    id: UUID
    role: str
    content: str
    citations: list[Citation] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class ConversationRead(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ConversationDetail(ConversationRead):
    summary: str = ""
    messages: list[MessageRead]
