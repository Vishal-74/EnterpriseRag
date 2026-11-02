"""Anthropic Messages API adapter."""

from __future__ import annotations

import time

import httpx
from anthropic import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncAnthropic,
    RateLimitError,
)

from app.services.llm.tokens import count_messages, count_text
from app.services.llm.types import CompletionRequest, CompletionResult, ProviderError


class AnthropicChatClient:
    """Chat completions against the Anthropic API."""

    provider_name = "anthropic"

    def __init__(self, api_key: str, default_model: str, timeout_seconds: float) -> None:
        self._default_model = default_model
        self._client = AsyncAnthropic(api_key=api_key, timeout=timeout_seconds) if api_key else None

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        if self._client is None:
            raise ProviderError(
                "Anthropic API key is not configured",
                provider=self.provider_name,
                status_code=401,
                fallback=True,
            )
        system, messages = _split(request)
        if request.json_mode:
            system = f"{system}\nRespond with a single JSON object and no other text."
        model = request.model or self._default_model
        started = time.perf_counter()
        try:
            response = await self._client.messages.create(
                model=model,
                max_tokens=request.max_tokens,
                system=system,
                messages=messages,  # type: ignore[arg-type]
            )
        except Exception as exc:
            raise _translate(exc) from exc
        parts: list[str] = []
        for block in response.content:
            text_part = getattr(block, "text", None)
            if isinstance(text_part, str):
                parts.append(text_part)
        text = "".join(parts)
        usage = response.usage
        prompt_tokens = int(usage.input_tokens) if usage else count_messages(request.messages)
        completion_tokens = int(usage.output_tokens) if usage else count_text(text)
        return CompletionResult(
            text=text,
            provider=self.provider_name,
            model=response.model or model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )


def _split(request: CompletionRequest) -> tuple[str, list[dict[str, str]]]:
    system_parts = [message.content for message in request.messages if message.role == "system"]
    dialogue = [
        {"role": message.role if message.role != "system" else "user", "content": message.content}
        for message in request.messages
        if message.role != "system"
    ]
    if not dialogue:
        dialogue = [{"role": "user", "content": "Follow the system instructions."}]
    return "\n\n".join(system_parts), dialogue


def _translate(exc: Exception) -> ProviderError:
    if isinstance(exc, ProviderError):
        return exc
    status = getattr(exc, "status_code", None)
    retry_after = None
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers and headers.get("retry-after"):
        try:
            retry_after = float(headers["retry-after"])
        except (TypeError, ValueError):
            retry_after = None
    if isinstance(exc, (APITimeoutError, APIConnectionError, httpx.TimeoutException)):
        return ProviderError(
            str(exc), provider="anthropic", status_code=408, retry_same=True, fallback=True
        )
    if isinstance(exc, RateLimitError) or status == 429:
        return ProviderError(
            "Anthropic rate limit",
            provider="anthropic",
            status_code=429,
            retry_same=True,
            fallback=True,
            retry_after=retry_after,
        )
    if status in (401, 403):
        return ProviderError(
            "Anthropic rejected the API key",
            provider="anthropic",
            status_code=status,
            fallback=True,
        )
    if isinstance(exc, APIStatusError) and status is not None and status >= 500:
        return ProviderError(
            "Anthropic server error",
            provider="anthropic",
            status_code=status,
            retry_same=True,
            fallback=True,
        )
    return ProviderError(
        "Anthropic request failed", provider="anthropic", status_code=status, fallback=True
    )
