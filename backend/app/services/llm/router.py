"""Primary model with retry, then a real call to the secondary provider."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable

from app.core.logging import logger
from app.services.llm.tokens import estimate_cost
from app.services.llm.types import (
    ChatClient,
    CompletionRequest,
    CompletionResult,
    ProviderError,
    UsageEvent,
    UsageRecorder,
)


class LLMRouter:
    """Call the preferred provider and fall back on timeout, rate limit, 5xx, or auth failure."""

    def __init__(
        self,
        openai_client: ChatClient,
        anthropic_client: ChatClient,
        hf_client: ChatClient | None = None,
        gemini_client: ChatClient | None = None,
        *,
        max_attempts: int = 2,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._clients: dict[str, ChatClient] = {
            "openai": openai_client,
            "anthropic": anthropic_client,
        }
        if hf_client is not None:
            self._clients["huggingface"] = hf_client
        if gemini_client is not None:
            self._clients["gemini"] = gemini_client
        self._max_attempts = max_attempts
        self._sleep = sleep or asyncio.sleep

    def _fallback_order(self, preferred: str) -> list[str]:
        default_order = (
            ["gemini", "openai", "anthropic", "huggingface"]
            if "gemini" in self._clients
            else ["openai", "anthropic", "huggingface"]
        )
        if preferred in default_order:
            remaining = [p for p in default_order if p != preferred]
            ordered = [preferred, *remaining]
        else:
            ordered = [preferred, *default_order]
        return [p for p in ordered if p in self._clients]

    async def complete(
        self,
        request: CompletionRequest,
        *,
        provider: str | None = None,
        operation: str,
        usage: UsageRecorder | None = None,
    ) -> CompletionResult:
        """Return the first successful completion following the fallback chain."""
        primary_name = provider or "openai"
        chain = self._fallback_order(primary_name)
        if not chain:
            raise ProviderError("No LLM provider available", provider=primary_name, fallback=False)

        last_error: ProviderError | None = None
        for i, current_provider in enumerate(chain):
            try:
                return await self._attempt(current_provider, request, operation, usage)
            except ProviderError as exc:
                last_error = exc
                await self._record_failure(exc, request, operation, usage)
                if not exc.fallback or i == len(chain) - 1:
                    raise
                next_provider = chain[i + 1]
                logger.warning(
                    "llm fallback from %s to %s after status %s",
                    current_provider,
                    next_provider,
                    exc.status_code,
                )
        if last_error is not None:
            raise last_error
        raise ProviderError("LLM call failed", provider=primary_name)

    async def _attempt(
        self,
        provider_name: str,
        request: CompletionRequest,
        operation: str,
        usage: UsageRecorder | None,
    ) -> CompletionResult:
        client = self._clients[provider_name]
        delay = 0.4
        last_error: ProviderError | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                result = await client.complete(request)
            except ProviderError as exc:
                last_error = exc
                if not exc.retry_same or attempt == self._max_attempts:
                    raise
                wait = (
                    exc.retry_after
                    if exc.retry_after is not None
                    else delay + random.random() * 0.2
                )
                logger.warning("llm retry provider=%s attempt=%s", provider_name, attempt)
                await self._sleep(wait)
                delay *= 2
                continue
            if usage is not None:
                await usage.record(_event(result, operation, status="success", error=None))
            return result
        assert last_error is not None
        raise last_error

    async def _record_failure(
        self,
        exc: ProviderError,
        request: CompletionRequest,
        operation: str,
        usage: UsageRecorder | None,
    ) -> None:
        if usage is None:
            return
        model = request.model or "unknown"
        await usage.record(_failure_event(exc, model, operation))


def _event(
    result: CompletionResult, operation: str, *, status: str, error: str | None
) -> UsageEvent:
    return UsageEvent(
        provider=result.provider,
        model=result.model,
        operation=operation,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        latency_ms=result.latency_ms,
        status=status,
        error=error,
        cost_usd=estimate_cost(result.model, result.prompt_tokens, result.completion_tokens),
    )


def _failure_event(exc: ProviderError, model: str, operation: str) -> UsageEvent:
    return UsageEvent(
        provider=exc.provider,
        model=model,
        operation=operation,
        prompt_tokens=0,
        completion_tokens=0,
        latency_ms=0,
        status="error",
        error=exc.message[:300],
        cost_usd=0.0,
    )
