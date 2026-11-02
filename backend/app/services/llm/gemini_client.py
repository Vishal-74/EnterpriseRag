"""Gemini chat and embedding adapter."""

from __future__ import annotations

import time
from typing import Any

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI, RateLimitError

from app.services.llm.tokens import count_messages, count_text
from app.services.llm.types import CompletionRequest, CompletionResult, ProviderError


class GeminiChatClient:
    """Chat completions against the Gemini OpenAI-compatible API."""

    provider_name = "gemini"

    def __init__(self, api_key: str, default_model: str, timeout_seconds: float) -> None:
        self._api_key = api_key.strip()
        self._default_model = default_model or "gemini-flash-lite-latest"
        self._timeout = timeout_seconds
        self._client = (
            AsyncOpenAI(
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                api_key=self._api_key or "missing",
                timeout=timeout_seconds,
            )
            if self._api_key
            else None
        )

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        if self._client is None:
            raise ProviderError(
                "Gemini API key is not configured",
                provider=self.provider_name,
                status_code=401,
                fallback=True,
            )
        model = request.model or self._default_model
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


class GeminiEmbedder:
    """Embeddings via Gemini batchEmbedContents with outputDimensionality=1536."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-embedding-001",
        timeout_seconds: float = 30.0,
        batch_size: int = 32,
    ) -> None:
        self._api_key = api_key.strip()
        self.model_name = model or "gemini-embedding-001"
        self._timeout = timeout_seconds
        self._batch_size = batch_size

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self._api_key:
            raise ProviderError(
                "Gemini API key is not configured",
                provider="gemini",
                status_code=401,
                fallback=False,
            )

        vectors: list[list[float]] = []
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:batchEmbedContents?key={self._api_key}"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for start in range(0, len(texts), self._batch_size):
                batch = texts[start : start + self._batch_size]
                requests = [
                    {
                        "model": f"models/{self.model_name}",
                        "content": {"parts": [{"text": t}]},
                        "outputDimensionality": 1536,
                    }
                    for t in batch
                ]
                try:
                    response = await client.post(url, json={"requests": requests})
                    response.raise_for_status()
                    data = response.json()
                    for emb in data.get("embeddings", []):
                        vectors.append(emb["values"])
                except Exception as exc:
                    raise ProviderError(
                        f"Gemini embedding failed: {exc}",
                        provider="gemini",
                        fallback=False,
                    ) from exc

        return vectors


def _translate(exc: Exception) -> ProviderError:
    if isinstance(exc, ProviderError):
        return exc
    status = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) if response else None
    retry_after: float | None = None
    if headers and headers.get("retry-after"):
        try:
            retry_after = float(headers["retry-after"])
        except (TypeError, ValueError):
            retry_after = None
    if isinstance(exc, (APITimeoutError, APIConnectionError, httpx.TimeoutException)):
        return ProviderError(
            str(exc), provider="gemini", status_code=408, retry_same=True, fallback=True
        )
    if isinstance(exc, RateLimitError) or status == 429:
        return ProviderError(
            "Gemini rate limit",
            provider="gemini",
            status_code=429,
            retry_same=True,
            fallback=True,
            retry_after=retry_after or 2.5,
        )
    if status in (401, 403):
        return ProviderError(
            "Gemini rejected the API key",
            provider="gemini",
            status_code=status,
            fallback=True,
        )
    if isinstance(exc, APIStatusError) and status is not None and status >= 500:
        return ProviderError(
            "Gemini server error",
            provider="gemini",
            status_code=status,
            retry_same=True,
            fallback=True,
        )
    return ProviderError(
        f"Gemini request failed: {exc}", provider="gemini", fallback=True, retry_same=False
    )
