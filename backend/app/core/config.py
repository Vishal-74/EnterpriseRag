"""Environment configuration. The rest of the app reads settings from here."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent


def to_async_url(url: str) -> str:
    """Return a SQLAlchemy asyncio URL using asyncpg."""
    if "+asyncpg" in url:
        return url
    if "+psycopg" in url:
        return url.replace("+psycopg", "+asyncpg", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    return url


def to_sync_url(url: str) -> str:
    """Return a synchronous SQLAlchemy URL using psycopg."""
    return to_async_url(url).replace("+asyncpg", "+psycopg", 1)


class Settings(BaseSettings):
    """Runtime settings loaded from the environment and an optional .env file."""

    model_config = SettingsConfigDict(
        env_file=(str(REPO_ROOT / ".env"), str(BACKEND_ROOT / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Enterprise Intelligence"
    environment: str = "development"
    log_level: str = "INFO"
    database_url: str = ""
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    cors_origins: str = "http://localhost:3000"

    openai_api_key: str = ""
    anthropic_api_key: str = ""
    openai_chat_model: str = "gpt-4o-mini"
    anthropic_chat_model: str = "claude-3-5-haiku-latest"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    hf_token: str = ""
    hf_base_url: str = ""
    hf_model_id: str = ""

    gemini: str = ""
    gemini_api_key: str = ""

    upload_dir: str = ""
    max_upload_bytes: int = 10 * 1024 * 1024
    chunk_size: int = 1000
    chunk_overlap: int = 150
    csv_rows_per_chunk: int = 40
    csv_row_overlap: int = 5

    retrieval_k: int = 8
    vector_candidates: int = 20
    keyword_candidates: int = 20
    rrf_k: int = 60
    relevance_threshold: float = 0.32
    keyword_rank_floor: float = 0.05
    rerank_enabled: bool = True

    memory_recent_turns: int = 6
    memory_token_budget: int = 1800
    summary_trigger_messages: int = 8

    agent_max_steps: int = 6
    agent_tool_timeout_seconds: float = 45
    agent_total_timeout_seconds: float = 120
    llm_timeout_seconds: float = 60
    llm_max_attempts: int = 2

    login_rate_limit: int = 10
    login_rate_window_seconds: int = 60
    chat_rate_limit: int = 30
    chat_rate_window_seconds: int = 60

    answer_cache_days: int = 7
    processing_stale_seconds: int = 900

    demo_user_email: str = ""
    demo_user_password: str = ""

    prompt_version: str = "2026-11-02"

    @field_validator("database_url", "jwt_secret")
    @classmethod
    def must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def check_consistency(self) -> Settings:
        if len(self.jwt_secret) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        if self.chunk_overlap < 0 or self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be >= 0 and smaller than CHUNK_SIZE")
        if self.csv_row_overlap >= self.csv_rows_per_chunk:
            raise ValueError("CSV_ROW_OVERLAP must be smaller than CSV_ROWS_PER_CHUNK")
        if not self.upload_dir:
            self.upload_dir = str(BACKEND_ROOT / "data" / "uploads")
        return self

    @property
    def async_database_url(self) -> str:
        return to_async_url(self.database_url)

    @property
    def sync_database_url(self) -> str:
        return to_sync_url(self.database_url)

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings object."""
    return Settings()
