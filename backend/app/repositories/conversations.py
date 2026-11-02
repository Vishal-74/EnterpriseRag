"""Conversation persistence."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, Message


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, conversation: Conversation) -> None:
        self._session.add(conversation)

    async def get_for_user(self, conversation_id: UUID, user_id: UUID) -> Conversation | None:
        stmt = select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_for_user(self, user_id: UUID) -> list[tuple[Conversation, int]]:
        stmt = (
            select(Conversation, func.count(Message.id))
            .outerjoin(Message, Message.conversation_id == Conversation.id)
            .where(Conversation.user_id == user_id)
            .group_by(Conversation.id)
            .order_by(Conversation.updated_at.desc())
        )
        return [(row[0], int(row[1])) for row in (await self._session.execute(stmt)).all()]

    async def delete(self, conversation: Conversation) -> None:
        await self._session.delete(conversation)

    def add_message(self, message: Message) -> None:
        self._session.add(message)

    async def list_messages(self, conversation_id: UUID) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def count_messages(self, conversation_id: UUID) -> int:
        total = await self._session.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.conversation_id == conversation_id)
        )
        return int(total or 0)
