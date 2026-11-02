"""Hugging Face chat completions adapter using the OpenAI-compatible SDK."""

from __future__ import annotations

import time
from typing import Any

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI, RateLimitError

from app.services.llm.tokens import count_messages, count_text
from app.services.llm.types import CompletionRequest, CompletionResult, ProviderError


class HuggingFaceChatClient:
    """Chat completions against a Hugging Face OpenAI-compatible endpoint."""

    provider_name = "huggingface"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        default_model: str,
        timeout_seconds: float,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.strip() if base_url else ""
        self._default_model = default_model.strip() if default_model else ""
        self._timeout = timeout_seconds
        self._client = (
            AsyncOpenAI(
                api_key=api_key or "missing",
                base_url=self._base_url or None,
                timeout=timeout_seconds,
            )
            if api_key
            else None
        )

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        if self._client is None:
            raise ProviderError(
                "Hugging Face API token is not configured",
                provider=self.provider_name,
                status_code=401,
                fallback=True,
            )
        model = request.model or self._default_model
        if not model:
            raise ProviderError(
                "Hugging Face model ID is not configured",
                provider=self.provider_name,
                fallback=True,
            )
        messages = [
            {"role": message.role, "content": message.content} for message in request.messages
        ]
        started = time.perf_counter()
        kwargs: dict[str, Any] = {
            "model": model,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "messages": messages,
        }
        if request.json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = await self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            raise _translate(exc) from exc

        choices = getattr(response, "choices", None)
        first_choice = choices[0] if choices else None
        text = ""
        if first_choice and hasattr(first_choice, "message"):
            text = first_choice.message.content or ""

        usage = getattr(response, "usage", None)
        prompt_tokens = (
            int(usage.prompt_tokens)
            if usage and getattr(usage, "prompt_tokens", None) is not None
            else count_messages(request.messages)
        )
        completion_tokens = (
            int(usage.completion_tokens)
            if usage and getattr(usage, "completion_tokens", None) is not None
            else count_text(text)
        )

        return CompletionResult(
            text=text,
            provider=self.provider_name,
            model=getattr(response, "model", None) or model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )


def _translate(exc: Exception) -> ProviderError:
    if isinstance(exc, ProviderError):
        return exc
    status = getattr(exc, "status_code", None)
    retry_after = _retry_after(exc)
    if isinstance(exc, (APITimeoutError, APIConnectionError, httpx.TimeoutException)):
        return ProviderError(
            str(exc), provider="huggingface", status_code=408, retry_same=True, fallback=True
        )
    if isinstance(exc, RateLimitError) or status == 429:
        return ProviderError(
            "Hugging Face rate limit",
            provider="huggingface",
            status_code=429,
            retry_same=True,
            fallback=True,
            retry_after=retry_after,
        )
    if status in (401, 403):
        return ProviderError(
            "Hugging Face rejected the API token",
            provider="huggingface",
            status_code=status,
            fallback=True,
        )
    if isinstance(exc, APIStatusError) and status is not None and status >= 500:
        return ProviderError(
            "Hugging Face server error",
            provider="huggingface",
            status_code=status,
            retry_same=True,
            fallback=True,
        )
    if isinstance(exc, APIStatusError):
        return ProviderError(
            "Hugging Face request failed",
            provider="huggingface",
            status_code=status,
            fallback=True,
        )
    return ProviderError(
        "Hugging Face request failed", provider="huggingface", fallback=True, retry_same=False
    )


def _retry_after(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    raw = headers.get("retry-after")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None

