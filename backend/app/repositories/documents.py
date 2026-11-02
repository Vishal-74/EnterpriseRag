"""Document and chunk persistence, including hybrid-search queries."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Chunk, Document


@dataclass
class VectorHit:
    chunk: Chunk
    document_name: str
    distance: float


@dataclass
class KeywordHit:
    chunk: Chunk
    document_name: str
    rank: float


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, document: Document) -> None:
        self._session.add(document)

    async def get_for_user(self, document_id: UUID, user_id: UUID) -> Document | None:
        stmt = select(Document).where(Document.id == document_id, Document.user_id == user_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_for_update(self, document_id: UUID, user_id: UUID) -> Document | None:
        stmt = (
            select(Document)
            .where(Document.id == document_id, Document.user_id == user_id)
            .with_for_update()
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_hash(self, user_id: UUID, digest: str) -> Document | None:
        stmt = select(Document).where(Document.user_id == user_id, Document.sha256 == digest)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_for_user(
        self, user_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[Document], int]:
        total = await self._session.scalar(
            select(func.count()).select_from(Document).where(Document.user_id == user_id)
        )
        stmt = (
            select(Document)
            .where(Document.user_id == user_id)
            .order_by(Document.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = list((await self._session.execute(stmt)).scalars().all())
        return rows, int(total or 0)

    async def owned_ids(self, user_id: UUID, document_ids: list[UUID]) -> list[Document]:
        if not document_ids:
            return []
        stmt = select(Document).where(Document.user_id == user_id, Document.id.in_(document_ids))
        return list((await self._session.execute(stmt)).scalars().all())

    async def delete(self, document: Document) -> None:
        await self._session.delete(document)


class ChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add_many(self, chunks: list[Chunk]) -> None:
        self._session.add_all(chunks)

    async def delete_for_document(self, document_id: UUID) -> None:
        await self._session.execute(delete(Chunk).where(Chunk.document_id == document_id))

    async def list_for_document(self, document_id: UUID, user_id: UUID) -> list[Chunk]:
        stmt = (
            select(Chunk)
            .where(Chunk.document_id == document_id, Chunk.user_id == user_id)
            .order_by(Chunk.chunk_index)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def list_for_documents(
        self, user_id: UUID, document_ids: list[UUID], limit: int
    ) -> list[Chunk]:
        stmt = (
            select(Chunk)
            .where(Chunk.user_id == user_id, Chunk.document_id.in_(document_ids))
            .order_by(Chunk.document_id, Chunk.chunk_index)
            .limit(limit)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def vector_search(
        self,
        *,
        user_id: UUID,
        query_embedding: list[float],
        limit: int,
        document_ids: list[UUID] | None,
    ) -> list[VectorHit]:
        distance = Chunk.embedding.cosine_distance(query_embedding)
        stmt = (
            select(Chunk, Document.original_filename, distance.label("distance"))
            .join(Document, Document.id == Chunk.document_id)
            .where(
                Chunk.user_id == user_id, Chunk.embedding.is_not(None), Document.status == "ready"
            )
            .order_by(distance)
            .limit(limit)
        )
        if document_ids:
            stmt = stmt.where(Chunk.document_id.in_(document_ids))
        rows = (await self._session.execute(stmt)).all()
        return [
            VectorHit(chunk=row[0], document_name=row[1], distance=float(row[2])) for row in rows
        ]

    async def keyword_search(
        self,
        *,
        user_id: UUID,
        query: str,
        limit: int,
        document_ids: list[UUID] | None,
    ) -> list[KeywordHit]:
        cleaned = " ".join(query.split())
        if not cleaned:
            return []
        tsquery = func.plainto_tsquery("english", cleaned)
        rank = func.ts_rank_cd(Chunk.content_tsv, tsquery)
        stmt = (
            select(Chunk, Document.original_filename, rank.label("rank"))
            .join(Document, Document.id == Chunk.document_id)
            .where(
                Chunk.user_id == user_id,
                Document.status == "ready",
                Chunk.content_tsv.op("@@")(tsquery),
            )
            .order_by(rank.desc())
            .limit(limit)
        )
        if document_ids:
            stmt = stmt.where(Chunk.document_id.in_(document_ids))
        rows = (await self._session.execute(stmt)).all()
        return [
            KeywordHit(chunk=row[0], document_name=row[1], rank=float(row[2] or 0)) for row in rows
        ]
