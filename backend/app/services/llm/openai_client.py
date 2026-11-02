"""OpenAI chat and embedding adapter."""

from __future__ import annotations

import time
from typing import Any

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI, RateLimitError

from app.services.llm.tokens import count_messages, count_text
from app.services.llm.types import ChatMessage, CompletionRequest, CompletionResult, ProviderError


class OpenAIChatClient:
    """Chat completions against the OpenAI API."""

    provider_name = "openai"

    def __init__(self, api_key: str, default_model: str, timeout_seconds: float) -> None:
        self._api_key = api_key
        self._default_model = default_model
        self._timeout = timeout_seconds
        self._client = (
            AsyncOpenAI(api_key=api_key or "missing", timeout=timeout_seconds) if api_key else None
        )

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        if self._client is None:
            raise ProviderError(
                "OpenAI API key is not configured",
                provider=self.provider_name,
                status_code=401,
                fallback=True,
            )
        model = request.model or self._default_model
        messages = [
            {"role": message.role, "content": message.content} for message in request.messages
        ]
        started = time.perf_counter()
        try:
            response = await _create_completion(
                self._client,
                model=model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                messages=messages,
                response_format={"type": "json_object"} if request.json_mode else None,
            )
        except Exception as exc:
            raise _translate(exc) from exc
        text = response.choices[0].message.content or ""
        usage = response.usage
        prompt_tokens = int(usage.prompt_tokens) if usage else count_messages(request.messages)
        completion_tokens = int(usage.completion_tokens) if usage else count_text(text)
        return CompletionResult(
            text=text,
            provider=self.provider_name,
            model=response.model or model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )


async def _create_completion(client: AsyncOpenAI, **kwargs: Any) -> Any:
    """Call chat completions. The SDK overloads reject a plain message dict."""
    if kwargs.get("response_format") is None:
        kwargs.pop("response_format", None)
    return await client.chat.completions.create(**kwargs)


class OpenAIEmbedder:
    """Batched embeddings from text-embedding-3-small, or the configured model."""

    def __init__(
        self, api_key: str, model: str, timeout_seconds: float, batch_size: int = 64
    ) -> None:
        self.model_name = model
        self._batch_size = batch_size
        self._client = AsyncOpenAI(api_key=api_key, timeout=timeout_seconds) if api_key else None

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self._client is None:
            raise ProviderError(
                "OpenAI API key is not configured",
                provider="openai",
                status_code=401,
                fallback=False,
            )
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            try:
                response = await self._client.embeddings.create(model=self.model_name, input=batch)
            except Exception as exc:
                raise _translate(exc) from exc
            ordered = sorted(response.data, key=lambda item: item.index)
            vectors.extend(list(item.embedding) for item in ordered)
        return vectors


def _translate(exc: Exception) -> ProviderError:
    if isinstance(exc, ProviderError):
        return exc
    status = getattr(exc, "status_code", None)
    retry_after = _retry_after(exc)
    if isinstance(exc, (APITimeoutError, APIConnectionError, httpx.TimeoutException)):
        return ProviderError(
            str(exc), provider="openai", status_code=408, retry_same=True, fallback=True
        )
    if isinstance(exc, RateLimitError) or status == 429:
        return ProviderError(
            "OpenAI rate limit",
            provider="openai",
            status_code=429,
            retry_same=True,
            fallback=True,
            retry_after=retry_after,
        )
    if status in (401, 403):
        return ProviderError(
            "OpenAI rejected the API key", provider="openai", status_code=status, fallback=True
        )
    if isinstance(exc, APIStatusError) and status is not None and status >= 500:
        return ProviderError(
            "OpenAI server error",
            provider="openai",
            status_code=status,
            retry_same=True,
            fallback=True,
        )
    if isinstance(exc, APIStatusError):
        return ProviderError(
            "OpenAI request failed", provider="openai", status_code=status, fallback=False
        )
    return ProviderError(
        "OpenAI request failed", provider="openai", fallback=True, retry_same=False
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


def messages_from(system: str, user: str) -> list[ChatMessage]:
    return [ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)]
