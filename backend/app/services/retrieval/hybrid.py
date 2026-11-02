"""Embed the query, search vectors and keywords, then fuse the lists."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ProviderFailure
from app.repositories.cache import CacheRepository
from app.repositories.documents import ChunkRepository
from app.services.hashing import embedding_cache_key
from app.services.llm.types import Embedder, ProviderError
from app.services.retrieval.rrf import reciprocal_rank_fusion
from app.services.retrieval.types import ScoredChunk


class HybridRetriever:
    """Vector search plus Postgres full-text search, merged with RRF."""

    def __init__(self, session: AsyncSession, embedder: Embedder, settings: Settings) -> None:
        self._session = session
        self._embedder = embedder
        self._settings = settings
        self._chunks = ChunkRepository(session)
        self._cache = CacheRepository(session)

    async def search(
        self,
        *,
        user_id: UUID,
        query: str,
        document_ids: list[UUID] | None,
        limit: int | None = None,
    ) -> list[ScoredChunk]:
        """Return fused chunks for one user. Document ids are an optional scope."""
        top = limit or self._settings.retrieval_k
        vector = await self._embed_query(query)
        vector_hits = await self._chunks.vector_search(
            user_id=user_id,
            query_embedding=vector,
            limit=self._settings.vector_candidates,
            document_ids=document_ids,
        )
        keyword_hits = await self._chunks.keyword_search(
            user_id=user_id,
            query=query,
            limit=self._settings.keyword_candidates,
            document_ids=document_ids,
        )
        fused = reciprocal_rank_fusion(
            [
                [str(hit.chunk.id) for hit in vector_hits],
                [str(hit.chunk.id) for hit in keyword_hits],
            ],
            k=self._settings.rrf_k,
        )
        by_id: dict[str, ScoredChunk] = {}
        for vector_hit in vector_hits:
            similarity = 1.0 - vector_hit.distance
            by_id[str(vector_hit.chunk.id)] = ScoredChunk(
                chunk=vector_hit.chunk,
                document_name=vector_hit.document_name,
                vector_similarity=similarity,
                keyword_rank=None,
                fusion_score=0.0,
                relevant=similarity >= self._settings.relevance_threshold,
            )
        for keyword_hit in keyword_hits:
            existing = by_id.get(str(keyword_hit.chunk.id))
            keyword_relevant = keyword_hit.rank >= self._settings.keyword_rank_floor
            if existing is None:
                by_id[str(keyword_hit.chunk.id)] = ScoredChunk(
                    chunk=keyword_hit.chunk,
                    document_name=keyword_hit.document_name,
                    vector_similarity=None,
                    keyword_rank=keyword_hit.rank,
                    fusion_score=0.0,
                    relevant=keyword_relevant,
                )
            else:
                existing.keyword_rank = keyword_hit.rank
                existing.relevant = existing.relevant or keyword_relevant
        ordered: list[ScoredChunk] = []
        for chunk_id, score in fused:
            item = by_id.get(chunk_id)
            if item is None:
                continue
            item.fusion_score = score
            ordered.append(item)
        relevant = [item for item in ordered if item.relevant]
        chosen = relevant if relevant else ordered
        return chosen[:top]

    async def _embed_query(self, query: str) -> list[float]:
        key = embedding_cache_key(self._embedder.model_name, query)
        cached = await self._cache.get_embeddings([key])
        if key in cached:
            return cached[key]
        try:
            vectors = await self._embedder.embed([query])
        except ProviderError as exc:
            raise ProviderFailure("The embedding provider is unavailable.") from exc
        if len(vectors) != 1:
            raise ProviderFailure("The embedding provider returned an unexpected result.")
        self._cache.put_embedding(key, self._embedder.model_name, vectors[0])
        return vectors[0]
