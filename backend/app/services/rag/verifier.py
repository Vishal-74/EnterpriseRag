"""Second-pass check that each claim is supported by the cited excerpts."""

from __future__ import annotations

from app.services.llm.openai_client import messages_from
from app.services.llm.router import LLMRouter
from app.services.llm.structured import complete_structured
from app.services.llm.types import CompletionRequest, UsageRecorder
from app.services.rag.injection_guard import guard_text
from app.services.rag.prompts import VERIFY_INSTRUCTIONS
from app.services.rag.schemas import ClaimDraft, VerificationReport
from app.services.retrieval.types import ScoredChunk


async def verify_claims(
    router: LLMRouter,
    claims: list[ClaimDraft],
    chunks: list[ScoredChunk],
    *,
    provider: str | None,
    usage: UsageRecorder | None,
    prompt_version: str,
) -> list[str]:
    """Return the text of claims the verifier does not support."""
    if not claims:
        return []
    excerpts = []
    for item in chunks:
        guarded = guard_text(item.chunk.content)
        excerpts.append(f"chunk_id={item.chunk.id} document={item.document_name}\n{guarded.text}")
    claim_lines = "\n".join(
        f"- {claim.text} (chunks: {', '.join(claim.chunk_ids)})" for claim in claims
    )
    request = CompletionRequest(
        messages=messages_from(
            VERIFY_INSTRUCTIONS.format(version=prompt_version),
            "Claims:\n" + claim_lines + "\n\nExcerpts:\n" + "\n\n".join(excerpts),
        ),
        temperature=0,
        max_tokens=800,
        json_mode=True,
    )
    parsed, _, _ = await complete_structured(
        router,
        request,
        VerificationReport,
        provider=provider,
        operation="verify",
        usage=usage,
    )
    return [verdict.claim for verdict in parsed.verdicts if not verdict.supported]
