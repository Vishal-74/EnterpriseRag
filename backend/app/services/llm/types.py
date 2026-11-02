"""Shared LLM request and response types."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Protocol


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True)
class CompletionRequest:
    messages: list[ChatMessage]
    model: str | None = None
    temperature: float = 0.0
    max_tokens: int = 1200
    json_mode: bool = False

    def with_repair(self, error: str, previous: str) -> CompletionRequest:
        """Ask the model to correct an invalid JSON response."""
        note = ChatMessage(
            role="user",
            content=(
                "The previous response was not valid JSON for the required schema. "
                f"Error: {error}. Previous response: {previous[:2000]}. "
                "Return only the corrected JSON object."
            ),
        )
        return replace(self, messages=[*self.messages, note])


@dataclass(frozen=True)
class CompletionResult:
    text: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    status: str = "success"
    error: str | None = None


@dataclass
class UsageEvent:
    provider: str
    model: str
    operation: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    status: str
    error: str | None = None
    cost_usd: float = 0.0


class UsageRecorder(Protocol):
    async def record(self, event: UsageEvent) -> None:
        """Persist one model call."""


class ChatClient(Protocol):
    provider_name: str

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        """Return a completion or raise ProviderError."""


class Embedder(Protocol):
    model_name: str

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding per input text."""


@dataclass
class ProviderError(Exception):
    """A provider call failed. The router decides whether to retry or fall back."""

    message: str
    provider: str
    status_code: int | None = None
    retry_same: bool = False
    fallback: bool = False
    retry_after: float | None = None

    def __str__(self) -> str:
        return self.message


@dataclass
class LLMCallLog:
    events: list[UsageEvent] = field(default_factory=list)

    async def record(self, event: UsageEvent) -> None:
        self.events.append(event)
