"""Embedding and answer caches."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cache import AnswerCache, EmbeddingCache


class CacheRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_embeddings(self, keys: list[str]) -> dict[str, list[float]]:
        if not keys:
            return {}
        stmt = select(EmbeddingCache).where(EmbeddingCache.cache_key.in_(keys))
        rows = (await self._session.execute(stmt)).scalars().all()
        return {row.cache_key: list(row.embedding) for row in rows}

    def put_embedding(self, key: str, model: str, embedding: list[float]) -> None:
        self._session.add(EmbeddingCache(cache_key=key, model=model, embedding=embedding))

    async def get_answer(
        self, user_id: UUID, cache_key: str, max_age_days: int
    ) -> dict[str, Any] | None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        stmt = select(AnswerCache).where(
            AnswerCache.user_id == user_id,
            AnswerCache.cache_key == cache_key,
            AnswerCache.created_at >= cutoff,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return dict(row.payload) if row else None

    def put_answer(self, user_id: UUID, cache_key: str, payload: dict[str, Any]) -> None:
        self._session.add(AnswerCache(user_id=user_id, cache_key=cache_key, payload=payload))
