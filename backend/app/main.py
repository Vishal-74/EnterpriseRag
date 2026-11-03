"""FastAPI application factory."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, logger, request_id_var
from app.core.rate_limit import SlidingWindowLimiter
from app.db.session import dispose_engine, get_session, init_engine
from app.runtime import AppRuntime, set_runtime
from app.services.jobs import AsyncJobDispatcher, InlineJobDispatcher
from app.services.llm.gemini_client import GeminiChatClient, GeminiEmbedder
from app.services.llm.hf_client import HuggingFaceChatClient
from app.services.llm.router import LLMRouter
from app.services.llm.types import Embedder
from app.services.worker import agent_job, ingest_job


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a request id and write one access log line. Bodies are not logged."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        token = request_id_var.set(request_id[:64])
        started = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id[:64]
            logger.info(
                "%s %s %s %sms",
                request.method,
                request.url.path,
                response.status_code,
                int((time.perf_counter() - started) * 1000),
            )
            return response
        finally:
            request_id_var.reset(token)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Configure logging, the database, and provider clients."""
    settings: Settings = app.state.settings_override or get_settings()
    configure_logging(settings.log_level)
    init_engine(settings.async_database_url)
    gemini_key = settings.gemini_api_key or settings.gemini
    gemini_client = GeminiChatClient(
        gemini_key, settings.gemini_chat_model, settings.llm_timeout_seconds
    )
    hf_client = HuggingFaceChatClient(
        settings.hf_token,
        settings.hf_base_url,
        settings.hf_model_id,
        settings.llm_timeout_seconds,
    )

    router = LLMRouter(
        gemini_client=gemini_client,
        hf_client=hf_client,
        max_attempts=settings.llm_max_attempts,
    )
    embedder: Embedder = GeminiEmbedder(
        gemini_key, "gemini-embedding-001", settings.llm_timeout_seconds
    )
    dispatcher_cls = InlineJobDispatcher if app.state.inline_jobs else AsyncJobDispatcher
    dispatcher = dispatcher_cls(ingest_job, agent_job)
    runtime = AppRuntime(
        settings=settings,
        embedder=embedder,
        router=router,
        dispatcher=dispatcher,
        limiter=SlidingWindowLimiter(),
    )
    set_runtime(runtime)
    app.state.runtime = runtime
    yield
    await dispose_engine()


def create_app(settings: Settings | None = None, *, inline_jobs: bool = False) -> FastAPI:
    """Build the API. Tests pass settings and can run jobs inline."""
    app = FastAPI(
        title="Enterprise Intelligence",
        version="1.0.0",
        summary="Document intelligence, retrieval, and a tool-using agent.",
        lifespan=lifespan,
    )
    app.state.settings_override = settings
    app.state.inline_jobs = inline_jobs
    register_exception_handlers(app)
    origins = (settings or _origins_from_env()).allowed_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)
    app.include_router(api_router, prefix="/api")

    @app.get("/", tags=["root"])
    async def root() -> dict[str, str]:
        return {
            "name": "Meridian Enterprise Intelligence Platform API",
            "version": "1.0.0",
            "status": "online",
            "documentation": "/docs",
            "health": "/health",
        }

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    async def ready(session: Annotated[AsyncSession, Depends(get_session)]) -> dict[str, str]:
        await session.execute(text("SELECT 1"))
        return {"status": "ok"}

    return app


def _origins_from_env() -> Settings:
    return get_settings()


app = create_app()
