"""Test doubles. These are not used by the running application."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

from app.services.llm.types import CompletionRequest, CompletionResult, UsageEvent, UsageRecorder


def unit_vector(seed: str, dimensions: int = 1536) -> list[float]:
    """Build a deterministic unit vector so tests do not call an embedding API."""
    material = seed.encode("utf-8")
    values: list[float] = []
    counter = 0
    while len(values) < dimensions:
        digest = hashlib.sha256(material + counter.to_bytes(4, "big")).digest()
        counter += 1
        values.extend(((byte / 127.5) - 1.0) for byte in digest)
    clipped = values[:dimensions]
    norm = sum(value * value for value in clipped) ** 0.5 or 1.0
    return [value / norm for value in clipped]


class FakeEmbedder:
    """Return one stable vector per input string."""

    model_name = "text-embedding-3-small"

    def __init__(self, dimensions: int = 1536) -> None:
        self._dimensions = dimensions
        self.calls: list[list[str]] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [unit_vector(text, self._dimensions) for text in texts]


class FakeRouter:
    """Router stand-in that records calls and returns scripted completions."""

    def __init__(self, handler: Callable[[str, CompletionRequest], str]) -> None:
        self._handler = handler
        self.calls: list[tuple[str, CompletionRequest]] = []

    async def complete(
        self,
        request: CompletionRequest,
        *,
        provider: str | None = None,
        operation: str,
        usage: UsageRecorder | None = None,
    ) -> CompletionResult:
        self.calls.append((operation, request))
        text = self._handler(operation, request)
        result = CompletionResult(
            text=text,
            provider=provider or "openai",
            model="fake-model",
            prompt_tokens=12,
            completion_tokens=6,
            latency_ms=4,
        )
        if usage is not None:
            await usage.record(
                UsageEvent(
                    provider=result.provider,
                    model=result.model,
                    operation=operation,
                    prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.completion_tokens,
                    latency_ms=result.latency_ms,
                    status="success",
                    cost_usd=0,
                )
            )
        return result


def json_for(payload: dict[str, Any]) -> str:
    return json.dumps(payload)
