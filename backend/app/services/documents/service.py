"""Upload, list, delete, and reprocess documents."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ConflictError, DuplicateDocumentError, NotFoundError
from app.domain import DocumentStatus
from app.models.document import Document
from app.models.user import User
from app.repositories.documents import ChunkRepository, DocumentRepository
from app.runtime import JobDispatcher
from app.schemas.document import DocumentList, DocumentRead
from app.services.activity import record_activity
from app.services.hashing import sha256_bytes
from app.services.ingestion.files import FileStore
from app.services.ingestion.validation import safe_filename, validate_upload


class DocumentService:
    """Own the document lifecycle. Parsing runs in a background job."""

    def __init__(
        self, session: AsyncSession, settings: Settings, dispatcher: JobDispatcher
    ) -> None:
        self._session = session
        self._settings = settings
        self._dispatcher = dispatcher
        self._documents = DocumentRepository(session)
        self._chunks = ChunkRepository(session)
        self._files = FileStore(settings)

    async def upload(self, user: User, upload: UploadFile) -> DocumentRead:
        """Validate and store a file, then queue processing."""
        data = await _read_limited(upload, self._settings.max_upload_bytes)
        kind = validate_upload(
            upload.filename, upload.content_type, data, self._settings.max_upload_bytes
        )
        digest = sha256_bytes(data)
        existing = await self._documents.get_by_hash(user.id, digest)
        if existing is not None:
            raise DuplicateDocumentError(existing.id, existing.status)
        document = Document(
            user_id=user.id,
            original_filename=safe_filename(upload.filename),
            kind=kind,
            content_type=(upload.content_type or "")[:128],
            size_bytes=len(data),
            sha256=digest,
            status=DocumentStatus.pending.value,
        )
        self._documents.add(document)
        await self._session.flush()
        path = self._files.save(user.id, document.id, data)
        document.storage_path = str(path)
        await record_activity(
            self._session,
            user_id=user.id,
            action="document.upload",
            resource_type="document",
            resource_id=str(document.id),
            detail={"filename": document.original_filename, "bytes": document.size_bytes},
        )
        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            self._files.delete(str(path))
            raced = await self._documents.get_by_hash(user.id, digest)
            if raced is not None:
                raise DuplicateDocumentError(raced.id, raced.status) from None
            raise
        await self._dispatcher.ingest(document.id)
        await self._session.refresh(document)
        return DocumentRead.from_document(document)

    async def list_documents(self, user: User, *, limit: int, offset: int) -> DocumentList:
        rows, total = await self._documents.list_for_user(user.id, limit=limit, offset=offset)
        return DocumentList(items=[DocumentRead.from_document(row) for row in rows], total=total)

    async def get_document(self, user: User, document_id: UUID) -> DocumentRead:
        document = await self._require(user.id, document_id)
        chunks = await self._chunks.list_for_document(document.id, user.id)
        return DocumentRead.from_document(document, chunks)

    async def delete_document(self, user: User, document_id: UUID) -> None:
        document = await self._require(user.id, document_id)
        path = document.storage_path
        await record_activity(
            self._session,
            user_id=user.id,
            action="document.delete",
            resource_type="document",
            resource_id=str(document.id),
        )
        await self._documents.delete(document)
        await self._session.commit()
        self._files.delete(path)

    async def reprocess(self, user: User, document_id: UUID) -> DocumentRead:
        """Queue the document again unless a job is already in progress."""
        document = await self._documents.get_for_update(document_id, user.id)
        if document is None:
            raise NotFoundError("Document not found")
        if self._in_progress(document):
            raise ConflictError("Document is already processing.")
        await self._chunks.delete_for_document(document.id)
        document.status = DocumentStatus.pending.value
        document.error_message = None
        document.chunk_count = 0
        document.processing_started_at = None
        await record_activity(
            self._session,
            user_id=user.id,
            action="document.reprocess",
            resource_type="document",
            resource_id=str(document.id),
        )
        await self._session.commit()
        await self._dispatcher.ingest(document.id)
        await self._session.refresh(document)
        return DocumentRead.from_document(document)

    async def require_owned(self, user_id: UUID, document_ids: list[UUID]) -> None:
        """Reject a scope that includes a missing or another user's document."""
        if not document_ids:
            return
        found = await self._documents.owned_ids(user_id, document_ids)
        if len(found) != len(set(document_ids)):
            raise NotFoundError("Document not found")

    async def _require(self, user_id: UUID, document_id: UUID) -> Document:
        document = await self._documents.get_for_user(document_id, user_id)
        if document is None:
            raise NotFoundError("Document not found")
        return document

    def _in_progress(self, document: Document) -> bool:
        if document.status not in {DocumentStatus.pending.value, DocumentStatus.processing.value}:
            return False
        started = document.processing_started_at or document.created_at
        if started is None:
            return True
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - started).total_seconds()
        return age < self._settings.processing_stale_seconds


async def _read_limited(upload: UploadFile, limit: int) -> bytes:
    blocks: list[bytes] = []
    total = 0
    while True:
        block = await upload.read(1024 * 1024)
        if not block:
            break
        total += len(block)
        if total > limit:
            from app.core.errors import ValidationFailed

            raise ValidationFailed(f"Files must be {limit // (1024 * 1024)} MB or smaller.")
        blocks.append(block)
    return b"".join(blocks)
