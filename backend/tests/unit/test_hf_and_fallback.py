"""Unit tests for the Hugging Face provider adapter and 3-way router fallback."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.services.llm.hf_client import HuggingFaceChatClient, _translate
from app.services.llm.router import LLMRouter
from app.services.llm.structured import complete_structured
from app.services.llm.types import (
    ChatMessage,
    CompletionRequest,
    CompletionResult,
    LLMCallLog,
    ProviderError,
)
from openai import APIStatusError, APITimeoutError, RateLimitError
from pydantic import BaseModel


class SampleReport(BaseModel):
    summary: str
    confidence: float


@pytest.mark.asyncio
async def test_hf_client_missing_key_raises_fallback() -> None:
    client = HuggingFaceChatClient(
        api_key="",
        base_url="https://api-inference.huggingface.co/v1",
        default_model="meta-llama/Llama-3.2-3B-Instruct",
        timeout_seconds=30.0,
    )
    request = CompletionRequest(messages=[ChatMessage(role="user", content="hello")])
    with pytest.raises(ProviderError) as exc_info:
        await client.complete(request)
    assert exc_info.value.fallback is True
    assert exc_info.value.status_code == 401
    assert exc_info.value.provider == "huggingface"


@pytest.mark.asyncio
async def test_hf_client_missing_model_raises_fallback() -> None:
    client = HuggingFaceChatClient(
        api_key="hf_test_token",
        base_url="https://api-inference.huggingface.co/v1",
        default_model="",
        timeout_seconds=30.0,
    )
    request = CompletionRequest(messages=[ChatMessage(role="user", content="hello")])
    with pytest.raises(ProviderError) as exc_info:
        await client.complete(request)
    assert exc_info.value.fallback is True
    assert "model ID is not configured" in exc_info.value.message


@pytest.mark.asyncio
async def test_hf_client_translates_sdk_errors() -> None:
    req = MagicMock()
    timeout_err = APITimeoutError(request=req)
    translated_timeout = _translate(timeout_err)
    assert translated_timeout.status_code == 408
    assert translated_timeout.fallback is True
    assert translated_timeout.retry_same is True

    rate_err = RateLimitError(
        message="rate limit exceeded",
        response=MagicMock(status_code=429, headers={"retry-after": "5"}),
        body=None,
    )
    translated_rate = _translate(rate_err)
    assert translated_rate.status_code == 429
    assert translated_rate.fallback is True
    assert translated_rate.retry_after == 5.0

    server_err = APIStatusError(
        message="internal server error",
        response=MagicMock(status_code=503, headers={}),
        body=None,
    )
    translated_server = _translate(server_err)
    assert translated_server.status_code == 503
    assert translated_server.fallback is True


@pytest.mark.asyncio
async def test_hf_client_successful_completion() -> None:
    client = HuggingFaceChatClient(
        api_key="hf_test_token",
        base_url="https://api-inference.huggingface.co/v1",
        default_model="meta-llama/Llama-3.2-3B-Instruct",
        timeout_seconds=30.0,
    )
    mock_choice = MagicMock()
    mock_choice.message.content = '{"summary": "ok", "confidence": 0.95}'
    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 25
    mock_usage.completion_tokens = 15

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = mock_usage
    mock_response.model = "meta-llama/Llama-3.2-3B-Instruct"

    assert client._client is not None
    with patch.object(
        client._client.chat.completions,
        "create",
        new=AsyncMock(return_value=mock_response),
    ):
        request = CompletionRequest(
            messages=[ChatMessage(role="user", content="evaluate system")],
            json_mode=True,
        )
        res = await client.complete(request)
        assert res.provider == "huggingface"
        assert res.model == "meta-llama/Llama-3.2-3B-Instruct"
        assert res.prompt_tokens == 25
        assert res.completion_tokens == 15
        assert res.text == '{"summary": "ok", "confidence": 0.95}'


@pytest.mark.asyncio
async def test_three_way_fallback_openai_anthropic_to_huggingface() -> None:
    """When OpenAI and Anthropic fail, LLMRouter falls back to Hugging Face."""
    openai_mock = MagicMock()
    openai_mock.provider_name = "openai"
    openai_mock.complete = AsyncMock(
        side_effect=ProviderError(
            "OpenAI timed out",
            provider="openai",
            status_code=408,
            fallback=True,
            retry_same=False,
        )
    )

    anthropic_mock = MagicMock()
    anthropic_mock.provider_name = "anthropic"
    anthropic_mock.complete = AsyncMock(
        side_effect=ProviderError(
            "Anthropic 502 bad gateway",
            provider="anthropic",
            status_code=502,
            fallback=True,
            retry_same=False,
        )
    )

    hf_mock = MagicMock()
    hf_mock.provider_name = "huggingface"
    hf_mock.complete = AsyncMock(
        return_value=CompletionResult(
            text='{"summary": "system recovered via HF", "confidence": 0.98}',
            provider="huggingface",
            model="meta-llama/Llama-3.2-3B-Instruct",
            prompt_tokens=40,
            completion_tokens=20,
            latency_ms=150,
            status="success",
        )
    )

    usage_log = LLMCallLog()
    router = LLMRouter(
        openai_client=openai_mock,
        anthropic_client=anthropic_mock,
        hf_client=hf_mock,
        max_attempts=1,
    )

    request = CompletionRequest(
        messages=[ChatMessage(role="user", content="Give status report")],
        json_mode=True,
    )

    result = await router.complete(
        request, provider="openai", operation="chat.answer", usage=usage_log
    )

    assert result.provider == "huggingface"
    assert "system recovered via HF" in result.text
    assert openai_mock.complete.await_count == 1
    assert anthropic_mock.complete.await_count == 1
    assert hf_mock.complete.await_count == 1

    # Verify usage logging: OpenAI failure, Anthropic failure, and HuggingFace success
    assert len(usage_log.events) == 3
    event_openai, event_anthropic, event_hf = usage_log.events

    assert event_openai.provider == "openai"
    assert event_openai.status == "error"
    assert "OpenAI timed out" in (event_openai.error or "")

    assert event_anthropic.provider == "anthropic"
    assert event_anthropic.status == "error"
    assert "Anthropic 502 bad gateway" in (event_anthropic.error or "")

    assert event_hf.provider == "huggingface"
    assert event_hf.status == "success"
    assert event_hf.error is None
    assert event_hf.prompt_tokens == 40
    assert event_hf.completion_tokens == 20


@pytest.mark.asyncio
async def test_complete_structured_with_huggingface_fallback() -> None:
    """complete_structured successfully validates Pydantic model after fallback."""
    openai_mock = MagicMock()
    openai_mock.provider_name = "openai"
    openai_mock.complete = AsyncMock(
        side_effect=ProviderError(
            "OpenAI 429 rate limited",
            provider="openai",
            status_code=429,
            fallback=True,
            retry_same=False,
        )
    )

    anthropic_mock = MagicMock()
    anthropic_mock.provider_name = "anthropic"
    anthropic_mock.complete = AsyncMock(
        side_effect=ProviderError(
            "Anthropic 500 error",
            provider="anthropic",
            status_code=500,
            fallback=True,
            retry_same=False,
        )
    )

    hf_payload = json.dumps({"summary": "operational", "confidence": 0.88})
    hf_mock = MagicMock()
    hf_mock.provider_name = "huggingface"
    hf_mock.complete = AsyncMock(
        return_value=CompletionResult(
            text=hf_payload,
            provider="huggingface",
            model="Qwen/Qwen2.5-7B-Instruct",
            prompt_tokens=30,
            completion_tokens=15,
            latency_ms=85,
            status="success",
        )
    )

    usage_log = LLMCallLog()
    router = LLMRouter(
        openai_client=openai_mock,
        anthropic_client=anthropic_mock,
        hf_client=hf_mock,
        max_attempts=1,
    )

    request = CompletionRequest(
        messages=[ChatMessage(role="user", content="Analyze status")],
        json_mode=True,
    )

    parsed, provider, model = await complete_structured(
        router,
        request,
        SampleReport,
        provider="openai",
        operation="agent_report",
        usage=usage_log,
    )

    assert isinstance(parsed, SampleReport)
    assert parsed.summary == "operational"
    assert parsed.confidence == 0.88
    assert provider == "huggingface"
    assert model == "Qwen/Qwen2.5-7B-Instruct"
