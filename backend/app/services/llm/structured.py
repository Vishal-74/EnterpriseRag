"""Ask for JSON and validate it with a Pydantic model. Retry once."""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.core.errors import ProviderFailure
from app.services.llm.json_text import extract_json_object
from app.services.llm.router import LLMRouter
from app.services.llm.types import CompletionRequest, UsageRecorder

T = TypeVar("T", bound=BaseModel)


async def complete_structured(
    router: LLMRouter,
    request: CompletionRequest,
    schema: type[T],
    *,
    provider: str | None,
    operation: str,
    usage: UsageRecorder | None,
) -> tuple[T, str, str]:
    """Return the validated model, provider name, and model name."""
    current = request
    last_error = "invalid JSON"
    for _ in range(2):
        try:
            result = await router.complete(
                current, provider=provider, operation=operation, usage=usage
            )
        except ProviderFailure:
            raise
        except Exception as exc:
            raise ProviderFailure() from exc
        try:
            payload = extract_json_object(result.text)
            return schema.model_validate(payload), result.provider, result.model
        except (ValueError, ValidationError) as exc:
            last_error = str(exc)
            current = current.with_repair(last_error, result.text)
    raise ProviderFailure("The model returned an invalid response.")
