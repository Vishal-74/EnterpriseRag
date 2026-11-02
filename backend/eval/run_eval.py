"""Run the Northwind question set against retrieval and answering.

Exits without writing scores when OPENAI_API_KEY is missing. Metrics in
results/latest.json come only from the responses of that run.
"""

from __future__ import annotations

import asyncio
import io
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import UUID, uuid4

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging
from app.core.rate_limit import SlidingWindowLimiter
from app.core.security import hash_password
from app.db import session as db_session
from app.models.user import User
from app.runtime import AppRuntime, set_runtime
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat.service import ChatService
from app.services.documents.service import DocumentService
from app.services.jobs import InlineJobDispatcher
from app.services.llm.gemini_client import GeminiChatClient, GeminiEmbedder
from app.services.llm.hf_client import HuggingFaceChatClient
from app.services.llm.router import LLMRouter
from app.services.worker import agent_job, ingest_job
from fastapi import UploadFile

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / "corpus"
RESULTS = ROOT / "results" / "latest.json"


@dataclass
class ScoreRow:
    id: str
    type: str
    hit: bool
    reciprocal_rank: float
    lexical_match: bool
    lexical_applicable: bool
    forbidden_text_present: bool
    insufficient_evidence: bool
    expected_insufficient: bool
    conflict: bool
    expected_conflict: bool
    ungrounded: bool
    latency_ms: int
    total_tokens: int
    answer_origin: str
    expects_retrieval: bool
    error: str | None


async def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    gemini_key = settings.gemini_api_key or settings.gemini
    if not gemini_key:
        print("GEMINI API key is not set. No evaluation results were written.")
        return 2
    dataset = json.loads((ROOT / "dataset.json").read_text())
    db_session.init_engine(settings.async_database_url)
    gemini_client = GeminiChatClient(
        gemini_key,
        settings.gemini_chat_model,
        settings.llm_timeout_seconds,
    )
    hf_client = HuggingFaceChatClient(
        settings.hf_token,
        settings.hf_base_url,
        settings.hf_model_id,
        settings.llm_timeout_seconds,
    )
    router = LLMRouter(
        gemini_client=gemini_client,
        hf_client=hf_client,
        max_attempts=settings.llm_max_attempts,
    )
    embedder = GeminiEmbedder(
        gemini_key,
        "gemini-embedding-001",
        settings.llm_timeout_seconds,
    )
    dispatcher = InlineJobDispatcher(ingest_job, agent_job)
    set_runtime(AppRuntime(settings, embedder, router, dispatcher, SlidingWindowLimiter()))
    factory = db_session.SessionLocal
    if factory is None:
        print("Database session is not configured. No evaluation results were written.")
        return 1
    async with factory() as session:
        user = User(
            email=f"eval-{uuid4()}@example.com",
            password_hash=hash_password(uuid4().hex),
        )
        session.add(user)
        await session.commit()
        documents = DocumentService(session, settings, dispatcher)
        for path in sorted(CORPUS.iterdir()):
            if not path.is_file() or path.name.startswith("."):
                continue
            upload = UploadFile(file=io.BytesIO(path.read_bytes()), filename=path.name)
            try:
                stored = await documents.upload(user, upload)
            except AppError as exc:
                print(f"Ingestion stopped on {path.name}: {exc.message}")
                return 1
            if stored.status != "ready":
                detail = stored.error_message or "no error message"
                print(f"{path.name} is {stored.status}: {detail}")
                print("No evaluation results were written.")
                return 1
        chat = ChatService(session, settings, router, embedder)
        conversations: dict[str, UUID] = {}
        rows: list[ScoreRow] = []
        for item in dataset["questions"]:
            group = item.get("conversation") or ""
            request = ChatRequest(
                message=item["question"],
                conversation_id=conversations.get(group),
            )
            try:
                response = await chat.ask(user, request)
            except AppError as exc:
                rows.append(_failed(item, exc.message))
                continue
            if group:
                conversations[group] = response.conversation_id
            rows.append(_score(item, response.answer, response))
        summary = _summarize(rows)
        RESULTS.parent.mkdir(parents=True, exist_ok=True)
        payload = {"summary": summary, "rows": [asdict(row) for row in rows]}
        RESULTS.write_text(json.dumps(payload, indent=2))
        print(json.dumps(summary, indent=2))
        return 0 if summary["complete"] else 1


def _score(item: dict[str, object], answer: str, response: ChatResponse) -> ScoreRow:
    expected_files = item["expected_files"]
    expected = set(expected_files if isinstance(expected_files, list) else [])
    ordered = [citation.document_name for citation in response.citations]
    rank = next((index for index, name in enumerate(ordered, start=1) if name in expected), None)
    lowered = answer.lower()
    fragments = _strings(item["expected_contains"])
    lexical = all(fragment.lower() in lowered for fragment in fragments)
    blocked = any(fragment.lower() in lowered for fragment in _strings(item["must_not_contain"]))
    return ScoreRow(
        id=str(item["id"]),
        type=str(item["type"]),
        hit=not expected or bool(expected.intersection(ordered)),
        reciprocal_rank=0.0 if rank is None else 1 / rank,
        lexical_match=lexical,
        lexical_applicable=bool(fragments),
        forbidden_text_present=blocked,
        insufficient_evidence=bool(response.insufficient_evidence),
        expected_insufficient=bool(item["insufficient_evidence"]),
        conflict=bool(response.conflict),
        expected_conflict=bool(item["conflict"]),
        ungrounded=bool(response.ungrounded),
        latency_ms=int(response.latency_ms),
        total_tokens=int(response.total_tokens),
        answer_origin=str(response.answer_origin),
        expects_retrieval=bool(expected),
        error=None,
    )


def _failed(item: dict[str, object], message: str) -> ScoreRow:
    return ScoreRow(
        id=str(item["id"]),
        type=str(item["type"]),
        hit=False,
        reciprocal_rank=0.0,
        lexical_match=False,
        lexical_applicable=bool(item["expected_contains"]),
        forbidden_text_present=False,
        insufficient_evidence=False,
        expected_insufficient=bool(item["insufficient_evidence"]),
        conflict=False,
        expected_conflict=bool(item["conflict"]),
        ungrounded=False,
        latency_ms=0,
        total_tokens=0,
        answer_origin="error",
        expects_retrieval=bool(item["expected_files"]),
        error=message,
    )


def _summarize(rows: list[ScoreRow]) -> dict[str, object]:
    retrieved = [row for row in rows if row.expects_retrieval and row.error is None]
    lexical = [row for row in rows if row.lexical_applicable and row.error is None]
    withheld = [row for row in rows if row.expected_insufficient and row.error is None]
    conflicts = [row for row in rows if row.expected_conflict and row.error is None]
    injections = [row for row in rows if row.type == "injection" and row.error is None]
    return {
        "questions": len(rows),
        "complete": all(row.error is None for row in rows),
        "retrieval_hit_rate": _mean(1 if row.hit else 0 for row in retrieved),
        "mrr": _mean(row.reciprocal_rank for row in retrieved),
        "lexical_match_rate": _mean(1 if row.lexical_match else 0 for row in lexical),
        "insufficient_evidence_rate": _mean(
            1 if row.insufficient_evidence else 0 for row in withheld
        ),
        "conflict_flag_rate": _mean(1 if row.conflict else 0 for row in conflicts),
        "injection_block_rate": _mean(0 if row.forbidden_text_present else 1 for row in injections),
        "mean_latency_ms": _mean(row.latency_ms for row in rows if row.error is None),
        "total_tokens": sum(row.total_tokens for row in rows),
    }


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _mean(values: Iterable[float]) -> float:
    material = [float(value) for value in values]
    if not material:
        return 0.0
    return sum(material) / len(material)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
