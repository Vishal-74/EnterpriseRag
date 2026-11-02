"""Create the demo user from DEMO_USER_EMAIL and DEMO_USER_PASSWORD.

The corpus is embedded only when OPENAI_API_KEY is set. This script does not
insert placeholder vectors or canned answers.
"""

from __future__ import annotations

import asyncio
import io
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.rate_limit import SlidingWindowLimiter
from app.core.security import hash_password
from app.db import session as db_session
from app.models.user import User
from app.repositories.users import UserRepository
from app.runtime import AppRuntime, set_runtime
from app.services.documents.service import DocumentService
from app.services.jobs import InlineJobDispatcher
from app.services.llm.anthropic_client import AnthropicChatClient
from app.services.llm.openai_client import OpenAIChatClient, OpenAIEmbedder
from app.services.llm.router import LLMRouter
from app.services.worker import agent_job, ingest_job
from fastapi import UploadFile

CORPUS = Path(__file__).resolve().parents[1] / "eval" / "corpus"


async def main() -> None:
    settings = get_settings()
    if not settings.demo_user_email or not settings.demo_user_password:
        raise SystemExit("Set DEMO_USER_EMAIL and DEMO_USER_PASSWORD before seeding.")
    db_session.init_engine(settings.async_database_url)
    router = LLMRouter(
        OpenAIChatClient(
            settings.openai_api_key,
            settings.openai_chat_model,
            settings.llm_timeout_seconds,
        ),
        AnthropicChatClient(
            settings.anthropic_api_key,
            settings.anthropic_chat_model,
            settings.llm_timeout_seconds,
        ),
    )
    embedder = OpenAIEmbedder(
        settings.openai_api_key,
        settings.embedding_model,
        settings.llm_timeout_seconds,
    )
    dispatcher = InlineJobDispatcher(ingest_job, agent_job)
    set_runtime(AppRuntime(settings, embedder, router, dispatcher, SlidingWindowLimiter()))
    factory = db_session.SessionLocal
    if factory is None:
        raise SystemExit("Database session is not configured.")
    async with factory() as session:
        users = UserRepository(session)
        existing = await users.get_by_email(settings.demo_user_email.lower())
        if existing is None:
            existing = User(
                email=settings.demo_user_email.lower(),
                password_hash=hash_password(settings.demo_user_password),
            )
            users.add(existing)
            await session.commit()
            print("Created the demo user.")
        else:
            print("Demo user already exists.")
        if not settings.openai_api_key:
            print("Corpus was not embedded because OPENAI_API_KEY is empty.")
            return
        documents = DocumentService(session, settings, dispatcher)
        for path in sorted(CORPUS.iterdir()):
            if not path.is_file() or path.name.startswith("."):
                continue
            upload = UploadFile(file=io.BytesIO(path.read_bytes()), filename=path.name)
            try:
                stored = await documents.upload(existing, upload)
            except AppError as exc:
                print(f"skipped {path.name}: {exc.message}")
                continue
            print(f"{path.name}: {stored.status}")


if __name__ == "__main__":
    asyncio.run(main())
