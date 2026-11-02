"""Rewrite a follow-up into a standalone search query."""

from __future__ import annotations

from app.core.logging import logger
from app.services.llm.openai_client import messages_from
from app.services.llm.router import LLMRouter
from app.services.llm.structured import complete_structured
from app.services.llm.types import CompletionRequest, UsageRecorder
from app.services.memory.context import MemoryContext, render_memory
from app.services.rag.prompts import REWRITE_INSTRUCTIONS
from app.services.rag.schemas import StandaloneQuery


async def rewrite_query(
    router: LLMRouter,
    question: str,
    memory: MemoryContext,
    *,
    provider: str | None,
    usage: UsageRecorder | None,
    prompt_version: str,
) -> str:
    """Return a search query. Falls back to the original question if rewriting fails."""
    if not memory.summary and not memory.recent_lines:
        return question
    request = CompletionRequest(
        messages=messages_from(
            REWRITE_INSTRUCTIONS.format(version=prompt_version),
            f"{render_memory(memory)}\n\nLatest question:\n{question}",
        ),
        temperature=0,
        max_tokens=200,
        json_mode=True,
    )
    try:
        parsed, _, _ = await complete_structured(
            router,
            request,
            StandaloneQuery,
            provider=provider,
            operation="query_rewrite",
            usage=usage,
        )
    except Exception:
        logger.warning("query rewrite failed; using the original question")
        return question
    rewritten = parsed.query.strip()
    return rewritten or question
