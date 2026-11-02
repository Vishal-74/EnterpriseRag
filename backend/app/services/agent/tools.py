"""Agent tools. Document text never chooses the tool name."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.document import Chunk, Document
from app.services.agent.prompts import ANALYSIS_INSTRUCTIONS, REPORT_INSTRUCTIONS
from app.services.agent.schemas import (
    AnalysisResult,
    AnalyzeArgs,
    Finding,
    ReportArgs,
    ReportBody,
    SearchArgs,
)
from app.services.llm.openai_client import messages_from
from app.services.llm.recorder import SqlUsageRecorder
from app.services.llm.router import LLMRouter
from app.services.llm.structured import complete_structured
from app.services.llm.types import CompletionRequest, Embedder
from app.services.rag.injection_guard import guard_text
from app.services.retrieval.hybrid import HybridRetriever


@dataclass
class ToolContext:
    user_id: UUID
    document_ids: list[UUID]
    session: AsyncSession
    router: LLMRouter
    embedder: Embedder
    settings: Settings
    provider: str | None
    observations: list[dict[str, Any]]


async def search_knowledge_base(args: SearchArgs, ctx: ToolContext) -> dict[str, Any]:
    """Retrieve chunks for a query. The result is data for later tools."""
    retriever = HybridRetriever(ctx.session, ctx.embedder, ctx.settings)
    hits = await retriever.search(
        user_id=ctx.user_id,
        query=args.query,
        document_ids=ctx.document_ids or None,
        limit=args.limit,
    )
    results = []
    for hit in hits:
        if not hit.relevant:
            continue
        snippet = " ".join(hit.chunk.content.split())[:500]
        results.append(
            {
                "chunk_id": str(hit.chunk.id),
                "document_id": str(hit.chunk.document_id),
                "document_name": hit.document_name,
                "page_start": hit.chunk.page_start,
                "section": hit.chunk.section,
                "snippet": snippet,
                "score": round(hit.fusion_score, 4),
            }
        )
    return {"query": args.query, "results": results}


async def analyze_documents(args: AnalyzeArgs, ctx: ToolContext) -> dict[str, Any]:
    """Summarize, find themes, or look for failure causes in the user's documents."""
    chunks = await _load_chunks(ctx, args.question)
    if not chunks:
        return {
            "mode": args.mode,
            "summary": "No relevant document text was available.",
            "points": [],
            "truncated": False,
        }
    limited = chunks[:12]
    excerpts = []
    for chunk in limited:
        safe = guard_text(chunk.content)
        name = await _document_name(ctx.session, chunk.document_id)
        excerpts.append(f"chunk_id={chunk.id} document={name}\n{safe.text}")
    request = CompletionRequest(
        messages=messages_from(
            ANALYSIS_INSTRUCTIONS.format(version=ctx.settings.prompt_version),
            f"Mode: {args.mode}\nQuestion: {args.question}\n\nExcerpts:\n" + "\n\n".join(excerpts),
        ),
        temperature=0,
        max_tokens=900,
        json_mode=True,
    )
    parsed, _, _ = await complete_structured(
        ctx.router,
        request,
        AnalysisResult,
        provider=ctx.provider,
        operation="agent_analyze",
        usage=SqlUsageRecorder(ctx.user_id),
    )
    return {
        "mode": args.mode,
        "summary": parsed.summary,
        "points": [point.model_dump() for point in parsed.points],
        "truncated": len(chunks) > len(limited),
    }


async def generate_report(args: ReportArgs, ctx: ToolContext) -> dict[str, Any]:
    """Build a report from earlier tool observations, not from raw model-supplied evidence."""
    material = _observation_text(ctx.observations)
    request = CompletionRequest(
        messages=messages_from(
            REPORT_INSTRUCTIONS.format(version=ctx.settings.prompt_version),
            f"Title: {args.title}\nFocus: {args.focus}\n\nObservations:\n{material}",
        ),
        temperature=0,
        max_tokens=1200,
        json_mode=True,
    )
    try:
        parsed, _, _ = await complete_structured(
            ctx.router,
            request,
            ReportBody,
            provider=ctx.provider,
            operation="agent_report",
            usage=SqlUsageRecorder(ctx.user_id),
        )
        body = parsed.model_dump()
        body["degraded"] = False
        return body
    except Exception:
        return _degraded_report(args, ctx.observations)


async def _load_chunks(ctx: ToolContext, question: str) -> list[Chunk]:
    if ctx.document_ids:
        stmt = (
            select(Chunk)
            .where(Chunk.user_id == ctx.user_id, Chunk.document_id.in_(ctx.document_ids))
            .order_by(Chunk.document_id, Chunk.chunk_index)
            .limit(16)
        )
        return list((await ctx.session.execute(stmt)).scalars().all())
    retriever = HybridRetriever(ctx.session, ctx.embedder, ctx.settings)
    hits = await retriever.search(user_id=ctx.user_id, query=question, document_ids=None, limit=8)
    return [hit.chunk for hit in hits if hit.relevant]


async def _document_name(session: AsyncSession, document_id: UUID) -> str:
    document = await session.get(Document, document_id)
    return document.original_filename if document else "document"


def _observation_text(observations: list[dict[str, Any]]) -> str:
    if not observations:
        return "No observations were collected."
    import json

    blocks = []
    for item in observations:
        payload = json.dumps(item.get("payload") or {}, default=str)[:3000]
        blocks.append(f"Tool {item.get('tool')}: {item.get('summary', '')}\n{payload}")
    return "\n".join(blocks)[:12000]


def _degraded_report(args: ReportArgs, observations: list[dict[str, Any]]) -> dict[str, Any]:
    """Copy evidence already returned by tools when the report model fails."""
    findings: list[dict[str, Any]] = []
    for item in observations:
        payload = item.get("payload") or {}
        for result in payload.get("results", [])[:4]:
            findings.append(
                Finding(
                    statement=str(result.get("snippet", ""))[:400],
                    evidence=[str(result.get("document_name", ""))],
                    source_chunk_ids=[str(result.get("chunk_id", ""))],
                ).model_dump()
            )
        for point in payload.get("points", [])[:4]:
            findings.append(
                Finding(
                    statement=str(point.get("text", ""))[:400],
                    evidence=["analysis tool"],
                    source_chunk_ids=[str(chunk_id) for chunk_id in point.get("chunk_ids", [])],
                ).model_dump()
            )
    report = ReportBody(
        title=args.title,
        summary=(
            "The report model was unavailable. Findings below are copied from earlier tool outputs."
        ),
        findings=[Finding.model_validate(item) for item in findings[:8]],
        recommendations=[],
        gaps=["Report generation used stored tool output because the model call failed."],
    )
    body = report.model_dump()
    body["degraded"] = True
    return body
