"""Generate a cited answer from guarded excerpts."""

from __future__ import annotations

from app.services.llm.openai_client import messages_from
from app.services.llm.router import LLMRouter
from app.services.llm.structured import complete_structured
from app.services.llm.types import CompletionRequest, UsageRecorder
from app.services.rag.injection_guard import GuardedText
from app.services.rag.prompts import ANSWER_INSTRUCTIONS
from app.services.rag.schemas import DraftAnswer
from app.services.retrieval.types import ScoredChunk


async def draft_answer(
    router: LLMRouter,
    question: str,
    memory_text: str,
    chunks: list[ScoredChunk],
    guarded: list[GuardedText],
    *,
    provider: str | None,
    usage: UsageRecorder | None,
    prompt_version: str,
) -> tuple[DraftAnswer, str, str]:
    """Call the model once (plus one repair) and return the validated draft."""
    excerpts = []
    for item, safe in zip(chunks, guarded, strict=True):
        location = _location(item)
        excerpts.append(
            f"chunk_id={item.chunk.id} document={item.document_name} {location}\n{safe.text}"
        )
    request = CompletionRequest(
        messages=messages_from(
            ANSWER_INSTRUCTIONS.format(version=prompt_version),
            f"Conversation:\n{memory_text}\n\nQuestion:\n{question}\n\nExcerpts:\n"
            + "\n\n".join(excerpts),
        ),
        temperature=0,
        max_tokens=1200,
        json_mode=True,
    )
    parsed, provider_name, model = await complete_structured(
        router,
        request,
        DraftAnswer,
        provider=provider,
        operation="answer",
        usage=usage,
    )
    return parsed, provider_name, model


def _location(item: ScoredChunk) -> str:
    chunk = item.chunk
    parts: list[str] = []
    if chunk.page_start is not None:
        parts.append(f"pages={chunk.page_start}-{chunk.page_end or chunk.page_start}")
    if chunk.section:
        parts.append(f"section={chunk.section}")
    if chunk.row_start is not None:
        parts.append(f"rows={chunk.row_start}-{chunk.row_end or chunk.row_start}")
    return " ".join(parts)
