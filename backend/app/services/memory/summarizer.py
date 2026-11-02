"""Rolling summary of turns that no longer fit in the recent window."""

from __future__ import annotations

from app.core.config import Settings
from app.core.logging import logger
from app.models.conversation import Conversation, Message
from app.services.llm.openai_client import messages_from
from app.services.llm.router import LLMRouter
from app.services.llm.structured import complete_structured
from app.services.llm.types import CompletionRequest, UsageRecorder
from app.services.rag.prompts import SUMMARY_INSTRUCTIONS
from app.services.rag.schemas import SummaryDraft


async def update_summary(
    router: LLMRouter,
    conversation: Conversation,
    messages: list[Message],
    settings: Settings,
    *,
    provider: str | None,
    usage: UsageRecorder | None,
) -> None:
    """Summarize older turns once the conversation grows past the trigger."""
    if len(messages) - conversation.summarized_message_count < settings.summary_trigger_messages:
        return
    older = messages[: max(0, len(messages) - settings.memory_recent_turns)]
    if len(older) <= conversation.summarized_message_count:
        return
    transcript = "\n".join(f"{message.role}: {message.content[:800]}" for message in older)
    prior = f"Previous summary:\n{conversation.summary}\n\n" if conversation.summary else ""
    request = CompletionRequest(
        messages=messages_from(
            SUMMARY_INSTRUCTIONS.format(version=settings.prompt_version),
            prior + transcript,
        ),
        temperature=0,
        max_tokens=400,
        json_mode=True,
    )
    try:
        parsed, _, _ = await complete_structured(
            router,
            request,
            SummaryDraft,
            provider=provider,
            operation="summary",
            usage=usage,
        )
    except Exception:
        logger.warning("conversation summary failed")
        return
    conversation.summary = parsed.summary.strip()[:4000]
    conversation.summarized_message_count = len(older)
