"""Document API models."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.document import Chunk, Document


class ChunkPreview(BaseModel):
    id: UUID
    chunk_index: int
    page_start: int | None
    page_end: int | None
    section: str | None
    row_start: int | None
    row_end: int | None
    preview: str

    @classmethod
    def from_chunk(cls, chunk: Chunk) -> ChunkPreview:
        text = " ".join(chunk.content.split())
        if len(text) > 240:
            text = text[:240].rstrip() + "…"
        return cls(
            id=chunk.id,
            chunk_index=chunk.chunk_index,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            section=chunk.section,
            row_start=chunk.row_start,
            row_end=chunk.row_end,
            preview=text,
        )


class DocumentRead(BaseModel):
    id: UUID
    original_filename: str
    kind: str
    content_type: str
    size_bytes: int
    sha256: str
    status: str
    error_message: str | None
    chunk_count: int
    created_at: datetime
    updated_at: datetime
    chunks: list[ChunkPreview] = Field(default_factory=list)

    @classmethod
    def from_document(cls, document: Document, chunks: list[Chunk] | None = None) -> DocumentRead:
        """Copy columns explicitly so a response never lazy-loads relationships."""
        return cls(
            id=document.id,
            original_filename=document.original_filename,
            kind=document.kind,
            content_type=document.content_type,
            size_bytes=document.size_bytes,
            sha256=document.sha256,
            status=document.status,
            error_message=document.error_message,
            chunk_count=document.chunk_count,
            created_at=document.created_at,
            updated_at=document.updated_at,
            chunks=[ChunkPreview.from_chunk(chunk) for chunk in chunks or []],
        )


class DocumentList(BaseModel):
    items: list[DocumentRead]
    total: int
