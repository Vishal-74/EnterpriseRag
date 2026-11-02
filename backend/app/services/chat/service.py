"""Conversation-aware RAG. Retrieval, answering, and verification stay in their modules."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import NotFoundError
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.repositories.cache import CacheRepository
from app.repositories.conversations import ConversationRepository
from app.repositories.documents import DocumentRepository
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    Citation,
    ConversationDetail,
    ConversationRead,
    MessageRead,
)
from app.services.activity import record_activity
from app.services.documents.service import DocumentService
from app.services.hashing import sha256_text
from app.services.llm.recorder import SqlUsageRecorder
from app.services.llm.router import LLMRouter
from app.services.llm.types import Embedder
from app.services.memory.context import MemoryContext, build_memory, render_memory
from app.services.memory.summarizer import update_summary
from app.services.rag.answerer import draft_answer
from app.services.rag.citations import citations_for_ids
from app.services.rag.injection_guard import GuardedText, guard_text
from app.services.rag.schemas import ClaimDraft
from app.services.rag.verifier import verify_claims
from app.services.retrieval.hybrid import HybridRetriever
from app.services.retrieval.reranker import rerank
from app.services.retrieval.rewriter import rewrite_query
from app.services.retrieval.types import ScoredChunk

_GATE = (
    "There is not enough information in the selected documents to answer that. "
    "I specialize in answering questions based on your uploaded library. "
    "Please ask a factual question related to your documents (such as system procedures, "
    "equipment specs, or operational metrics)."
)

_GREETINGS = {
    "hi",
    "hello",
    "hey",
    "hey there",
    "hiya",
    "howdy",
    "greetings",
    "good morning",
    "good afternoon",
    "good evening",
    "who are you",
    "what are you",
    "what can you do",
    "how can you help",
    "how can you help me",
    "help",
    "help me",
}

_GREETING_MESSAGE = (
    "Hello! I am your enterprise document intelligence assistant. "
    "How can I help you today? You can ask me factual questions, request summaries, "
    "or investigate operational procedures and technical specifications from the documents in your library."
)


def _is_conversational_greeting(text: str) -> bool:
    cleaned = "".join(ch for ch in text.lower().strip() if ch.isalnum() or ch.isspace()).strip()
    return cleaned in _GREETINGS


class ChatService:
    """Answer a question from the caller's documents and store the turn."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        router: LLMRouter,
        embedder: Embedder,
    ) -> None:
        self._session = session
        self._settings = settings
        self._router = router
        self._conversations = ConversationRepository(session)
        self._documents = DocumentRepository(session)
        self._cache = CacheRepository(session)
        self._retriever = HybridRetriever(session, embedder, settings)
        self._usage = SqlUsageRecorder(None)

    async def ask(self, user: User, payload: ChatRequest) -> ChatResponse:
        """Run retrieval and answering for one user message."""
        started = time.perf_counter()
        self._usage = SqlUsageRecorder(user.id)
        conversation = await self._load_conversation(user, payload)
        prior = await self._conversations.list_messages(conversation.id)
        memory = build_memory(conversation.summary, prior, self._settings)
        user_message = Message(
            conversation_id=conversation.id,
            user_id=user.id,
            role="user",
            content=payload.message.strip(),
            citations=[],
            metadata_json={},
        )
        self._conversations.add_message(user_message)
        if conversation.title == "New conversation":
            conversation.title = payload.message.strip()[:80]
        if _is_conversational_greeting(payload.message):
            response = self._greet(conversation, started)
        else:
            await self._scope(user.id, payload.document_ids)
            rewritten = await rewrite_query(
                self._router,
                payload.message.strip(),
                memory,
                provider=payload.provider,
                usage=self._usage,
                prompt_version=self._settings.prompt_version,
            )
            chunks = await self._retriever.search(
                user_id=user.id,
                query=rewritten,
                document_ids=payload.document_ids,
            )
            if self._settings.rerank_enabled and any(chunk.relevant for chunk in chunks):
                chunks = await rerank(
                    self._router,
                    chunks,
                    rewritten,
                    provider=payload.provider,
                    usage=self._usage,
                    prompt_version=self._settings.prompt_version,
                )
            guarded = [guard_text(chunk.chunk.content) for chunk in chunks]
            flags = _unique([flag for item in guarded for flag in item.flags])
            if not chunks or not any(chunk.relevant for chunk in chunks):
                response = self._gate(conversation, flags, memory.history_tokens, started)
            else:
                response = await self._answer(
                    user,
                    payload,
                    conversation,
                    rewritten,
                    memory,
                    chunks,
                    guarded,
                    flags,
                    started,
                )
        assistant = Message(
            conversation_id=conversation.id,
            user_id=user.id,
            role="assistant",
            content=response.answer,
            citations=[item.model_dump(mode="json") for item in response.citations],
            metadata_json=_metadata(response),
        )
        self._conversations.add_message(assistant)
        await self._session.flush()
        response.message_id = assistant.id
        conversation.updated_at = datetime.now(timezone.utc)
        messages = await self._conversations.list_messages(conversation.id)
        await update_summary(
            self._router,
            conversation,
            messages,
            self._settings,
            provider=payload.provider,
            usage=self._usage,
        )
        await record_activity(
            self._session,
            user_id=user.id,
            action="chat.answer",
            resource_type="conversation",
            resource_id=str(conversation.id),
            detail={
                "insufficient_evidence": response.insufficient_evidence,
                "conflict": response.conflict,
                "cached": response.cached,
                "history_tokens": response.history_tokens,
            },
        )
        await self._session.commit()
        return response

    async def list_conversations(self, user: User) -> list[ConversationRead]:
        rows = await self._conversations.list_for_user(user.id)
        return [
            ConversationRead(
                id=conversation.id,
                title=conversation.title,
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
                message_count=count,
            )
            for conversation, count in rows
        ]

    async def get_conversation(self, user: User, conversation_id: UUID) -> ConversationDetail:
        conversation = await self._require(user.id, conversation_id)
        messages = await self._conversations.list_messages(conversation.id)
        return ConversationDetail(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            message_count=len(messages),
            summary=conversation.summary,
            messages=[_message_read(message) for message in messages],
        )

    async def delete_conversation(self, user: User, conversation_id: UUID) -> None:
        conversation = await self._require(user.id, conversation_id)
        await self._conversations.delete(conversation)
        await record_activity(
            self._session,
            user_id=user.id,
            action="conversation.delete",
            resource_type="conversation",
            resource_id=str(conversation_id),
        )
        await self._session.commit()

    async def _answer(
        self,
        user: User,
        payload: ChatRequest,
        conversation: Conversation,
        rewritten: str,
        memory: MemoryContext,
        chunks: list[ScoredChunk],
        guarded: list[GuardedText],
        flags: list[str],
        started: float,
    ) -> ChatResponse:
        fingerprint = await self._fingerprint(user.id, payload.document_ids)
        cache_key = sha256_text(
            "|".join(
                [
                    self._settings.prompt_version,
                    payload.provider or "openai",
                    rewritten,
                    fingerprint,
                ]
            )
        )
        cached = await self._cache.get_answer(user.id, cache_key, self._settings.answer_cache_days)
        if cached is not None:
            return ChatResponse(
                conversation_id=conversation.id,
                message_id=conversation.id,
                answer=str(cached["answer"]),
                citations=[Citation.model_validate(item) for item in cached.get("citations", [])],
                insufficient_evidence=bool(cached["insufficient_evidence"]),
                conflict=bool(cached["conflict"]),
                conflict_summary=cached.get("conflict_summary"),
                unsupported_claims=list(cached.get("unsupported_claims", [])),
                ungrounded=bool(cached.get("ungrounded", False)),
                injection_flags=flags,
                answer_origin="cache",
                provider=cached.get("provider"),
                model=cached.get("model"),
                history_tokens=memory.history_tokens,
                latency_ms=_elapsed(started),
                cached=True,
            )
        draft, provider_name, model = await draft_answer(
            self._router,
            payload.message.strip(),
            render_memory(memory),
            chunks,
            guarded,
            provider=payload.provider,
            usage=self._usage,
            prompt_version=self._settings.prompt_version,
        )
        claims = list(draft.claims)
        if not draft.insufficient_evidence and not claims and draft.answer.strip():
            claims = [
                ClaimDraft(text=draft.answer.strip(), chunk_ids=list(draft.citation_chunk_ids))
            ]
        unsupported: list[str] = []
        if not draft.insufficient_evidence:
            unsupported = await verify_claims(
                self._router,
                claims,
                chunks,
                provider=payload.provider,
                usage=self._usage,
                prompt_version=self._settings.prompt_version,
            )
        cited_ids = list(draft.citation_chunk_ids)
        for claim in claims:
            cited_ids.extend(claim.chunk_ids)
        citations = citations_for_ids(chunks, cited_ids)
        response = ChatResponse(
            conversation_id=conversation.id,
            message_id=conversation.id,
            answer=draft.answer.strip() or _GATE,
            citations=citations,
            insufficient_evidence=draft.insufficient_evidence,
            conflict=draft.conflict_detected,
            conflict_summary=draft.conflict_notes,
            unsupported_claims=unsupported,
            ungrounded=bool(claims) and len(unsupported) == len(claims),
            injection_flags=flags,
            answer_origin="model",
            provider=provider_name,
            model=model,
            prompt_tokens=self._usage.prompt_tokens,
            completion_tokens=self._usage.completion_tokens,
            total_tokens=self._usage.total_tokens,
            history_tokens=memory.history_tokens,
            latency_ms=_elapsed(started),
        )
        try:
            async with self._session.begin_nested():
                self._cache.put_answer(
                    user.id,
                    cache_key,
                    response.model_dump(
                        mode="json",
                        exclude={"message_id", "conversation_id", "cached", "latency_ms"},
                    ),
                )
                await self._session.flush()
        except IntegrityError:
            pass
        return response

    def _greet(
        self,
        conversation: Conversation,
        started: float,
    ) -> ChatResponse:
        return ChatResponse(
            conversation_id=conversation.id,
            message_id=conversation.id,
            answer=_GREETING_MESSAGE,
            citations=[],
            insufficient_evidence=False,
            conflict=False,
            injection_flags=[],
            answer_origin="retrieval_gate",
            history_tokens=0,
            latency_ms=_elapsed(started),
        )

    def _gate(
        self,
        conversation: Conversation,
        flags: list[str],
        history_tokens: int,
        started: float,
    ) -> ChatResponse:
        return ChatResponse(
            conversation_id=conversation.id,
            message_id=conversation.id,
            answer=_GATE,
            citations=[],
            insufficient_evidence=True,
            conflict=False,
            injection_flags=flags,
            answer_origin="retrieval_gate",
            history_tokens=history_tokens,
            latency_ms=_elapsed(started),
        )

    async def _load_conversation(self, user: User, payload: ChatRequest) -> Conversation:
        if payload.conversation_id is None:
            conversation = Conversation(user_id=user.id, title="New conversation")
            self._conversations.add(conversation)
            await self._session.flush()
            return conversation
        return await self._require(user.id, payload.conversation_id)

    async def _require(self, user_id: UUID, conversation_id: UUID) -> Conversation:
        conversation = await self._conversations.get_for_user(conversation_id, user_id)
        if conversation is None:
            raise NotFoundError("Conversation not found")
        return conversation

    async def _scope(self, user_id: UUID, document_ids: list[UUID] | None) -> None:
        if not document_ids:
            return
        documents = DocumentService(self._session, self._settings, _NoDispatch())
        await documents.require_owned(user_id, document_ids)

    async def _fingerprint(self, user_id: UUID, document_ids: list[UUID] | None) -> str:
        rows, _ = await self._documents.list_for_user(user_id, limit=500, offset=0)
        scoped = [
            row
            for row in rows
            if row.status == "ready" and (not document_ids or row.id in document_ids)
        ]
        raw = "|".join(
            f"{row.id}:{row.updated_at.isoformat()}"
            for row in sorted(scoped, key=lambda item: str(item.id))
        )
        return sha256_text(raw)


class _NoDispatch:
    async def ingest(self, document_id: UUID) -> None:
        return None

    async def run_agent(self, run_id: UUID) -> None:
        return None


def _elapsed(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _unique(items: list[str]) -> list[str]:
    seen: list[str] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen


def _metadata(response: ChatResponse) -> dict[str, Any]:
    return {
        "answer_origin": response.answer_origin,
        "insufficient_evidence": response.insufficient_evidence,
        "conflict": response.conflict,
        "conflict_summary": response.conflict_summary,
        "unsupported_claims": response.unsupported_claims,
        "ungrounded": response.ungrounded,
        "injection_flags": response.injection_flags,
        "provider": response.provider,
        "model": response.model,
        "prompt_tokens": response.prompt_tokens,
        "completion_tokens": response.completion_tokens,
        "total_tokens": response.total_tokens,
        "history_tokens": response.history_tokens,
        "latency_ms": response.latency_ms,
        "cached": response.cached,
    }


def _message_read(message: Message) -> MessageRead:
    citations = []
    for raw in message.citations or []:
        try:
            citations.append(Citation.model_validate(raw))
        except Exception:
            continue
    return MessageRead(
        id=message.id,
        role=message.role,
        content=message.content,
        citations=citations,
        metadata=dict(message.metadata_json or {}),
        created_at=message.created_at,
    )
