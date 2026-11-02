"""Parse, chunk, embed, and store one document."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ParseError
from app.core.logging import logger
from app.domain import DocumentStatus
from app.models.document import Chunk, Document
from app.repositories.cache import CacheRepository
from app.repositories.documents import ChunkRepository, DocumentRepository
from app.services.hashing import embedding_cache_key, sha256_text
from app.services.ingestion.chunker import (
    ChunkDraft,
    chunk_csv,
    chunk_markdown,
    chunk_pdf,
    chunk_plain,
)
from app.services.ingestion.files import FileStore
from app.services.ingestion.parsers import ParsedDocument, parse_document
from app.services.llm.tokens import count_text
from app.services.llm.types import Embedder, ProviderError


class IngestionPipeline:
    """Turn a stored upload into chunks and embeddings."""

    def __init__(self, session: AsyncSession, settings: Settings, embedder: Embedder) -> None:
        self._session = session
        self._settings = settings
        self._embedder = embedder
        self._documents = DocumentRepository(session)
        self._chunks = ChunkRepository(session)
        self._cache = CacheRepository(session)
        self._files = FileStore(settings)

    async def run(self, document_id: UUID) -> None:
        """Process one document. Failures are stored on the document row."""
        document = await self._session.get(Document, document_id)
        if document is None:
            logger.warning("ingestion skipped missing document %s", document_id)
            return
        if document.status == DocumentStatus.ready.value and document.chunk_count > 0:
            logger.info("ingestion skipped ready document %s", document_id)
            return
        document.status = DocumentStatus.processing.value
        document.processing_started_at = datetime.now(timezone.utc)
        document.error_message = None
        await self._session.commit()
        try:
            data = self._files.read(document.storage_path)
            parsed = parse_document(document.kind, data)  # type: ignore[arg-type]
            drafts = drafts_for(parsed, self._settings)
            if not drafts:
                raise ParseError("No text could be extracted from the file.")
            vectors = await self._embed(drafts)
            await self._chunks.delete_for_document(document.id)
            rows = [
                self._row(document, draft, vector)
                for draft, vector in zip(drafts, vectors, strict=True)
            ]
            self._chunks.add_many(rows)
            document.chunk_count = len(rows)
            document.status = DocumentStatus.ready.value
            document.error_message = None
        except Exception as exc:
            logger.exception("ingestion failed")
            document.status = DocumentStatus.failed.value
            document.error_message = public_error(exc)
            document.chunk_count = 0
        document.updated_at = datetime.now(timezone.utc)
        await self._session.commit()

    async def _embed(self, drafts: list[ChunkDraft]) -> list[list[float]]:
        keys = [embedding_cache_key(self._embedder.model_name, draft.content) for draft in drafts]
        cached = await self._cache.get_embeddings(keys)
        missing = [index for index, key in enumerate(keys) if key not in cached]
        if missing:
            fresh = await self._embedder.embed([drafts[index].content for index in missing])
            if len(fresh) != len(missing):
                raise ProviderError(
                    "Embedding provider returned the wrong number of vectors",
                    provider="openai",
                )
            for index, vector in zip(missing, fresh, strict=True):
                self._check_dimensions(vector)
                cached[keys[index]] = vector
                self._cache.put_embedding(keys[index], self._embedder.model_name, vector)
        ordered = []
        for key in keys:
            vector = cached[key]
            self._check_dimensions(vector)
            ordered.append(vector)
        return ordered

    def _check_dimensions(self, vector: list[float]) -> None:
        if len(vector) != self._settings.embedding_dimensions:
            raise ProviderError(
                "Embedding dimensions did not match the database column",
                provider="openai",
            )

    def _row(self, document: Document, draft: ChunkDraft, vector: list[float]) -> Chunk:
        return Chunk(
            document_id=document.id,
            user_id=document.user_id,
            chunk_index=draft.index,
            content=draft.content,
            content_hash=sha256_text(draft.content),
            page_start=draft.page_start,
            page_end=draft.page_end,
            section=draft.section,
            row_start=draft.row_start,
            row_end=draft.row_end,
            token_count=count_text(draft.content),
            embedding=vector,
        )


def drafts_for(parsed: ParsedDocument, settings: Settings) -> list[ChunkDraft]:
    """Choose the chunker that matches the file kind."""
    if parsed.kind == "pdf":
        return chunk_pdf(parsed.pages or [parsed.text], settings.chunk_size, settings.chunk_overlap)
    if parsed.kind == "md":
        return chunk_markdown(parsed.text, settings.chunk_size, settings.chunk_overlap)
    if parsed.kind == "csv":
        return chunk_csv(parsed.text, settings.csv_rows_per_chunk, settings.csv_row_overlap)
    return chunk_plain(parsed.text, settings.chunk_size, settings.chunk_overlap)


def public_error(exc: Exception) -> str:
    """Return a message that is safe to store and show in the UI."""
    if isinstance(exc, ParseError):
        return exc.message
    if isinstance(exc, ProviderError):
        return "Embedding failed. Check the OpenAI API key and reprocess the document."
    return "Document processing failed. Reprocess the file if it continues."
