"""Document routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_runtime
from app.db.session import get_session
from app.models.user import User
from app.schemas.document import DocumentList, DocumentRead
from app.services.documents.service import DocumentService

router = APIRouter(prefix="/documents", tags=["documents"])


def _service(request: Request, session: AsyncSession) -> DocumentService:
    runtime = get_runtime(request)
    return DocumentService(session, runtime.settings, runtime.dispatcher)


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    file: Annotated[UploadFile, File()],
) -> DocumentRead:
    """Store a document and queue parsing. The response status is the accepted state."""
    return await _service(request, session).upload(user, file)


@router.get("", response_model=DocumentList)
async def list_documents(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> DocumentList:
    """List the caller's documents."""
    return await _service(request, session).list_documents(user, limit=limit, offset=offset)


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(
    document_id: UUID,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DocumentRead:
    """Return one document and short chunk previews."""
    return await _service(request, session).get_document(user, document_id)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    """Delete a document, its chunks, and the stored file."""
    await _service(request, session).delete_document(user, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{document_id}/reprocess", response_model=DocumentRead)
async def reprocess_document(
    document_id: UUID,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DocumentRead:
    """Queue processing again. A document that is already running is rejected."""
    return await _service(request, session).reprocess(user, document_id)
