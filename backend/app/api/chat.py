"""Chat and conversation routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_runtime, limit_chat
from app.db.session import get_session
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse, ConversationDetail, ConversationRead
from app.services.chat.service import ChatService

router = APIRouter(tags=["chat"])


def _service(request: Request, session: AsyncSession) -> ChatService:
    runtime = get_runtime(request)
    return ChatService(session, runtime.settings, runtime.router, runtime.embedder)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    request: Request,
    user: Annotated[User, Depends(limit_chat)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ChatResponse:
    """Answer a question from the caller's documents."""
    return await _service(request, session).ask(user, payload)


@router.get("/conversations", response_model=list[ConversationRead])
async def list_conversations(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ConversationRead]:
    """List the caller's conversations."""
    return await _service(request, session).list_conversations(user)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: UUID,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ConversationDetail:
    """Return one conversation and its messages."""
    return await _service(request, session).get_conversation(user, conversation_id)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    """Delete a conversation and its messages."""
    await _service(request, session).delete_conversation(user, conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
