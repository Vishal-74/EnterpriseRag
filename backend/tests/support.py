"""Shared settings builder for tests."""

from __future__ import annotations

import os
from pathlib import Path

from app.core.config import Settings, get_settings


def settings_for(upload_dir: Path | None = None, **overrides: object) -> Settings:
    """Build settings without reading a developer machine's secrets into the test."""
    get_settings.cache_clear()
    values: dict[str, object] = {
        "database_url": os.environ["DATABASE_URL"],
        "jwt_secret": os.environ["JWT_SECRET"],
        "environment": "test",
        "upload_dir": str(upload_dir or Path("/tmp/enterprise-intel-test-uploads")),
        "rerank_enabled": False,
        "openai_api_key": "",
        "anthropic_api_key": "",
        "cors_origins": "http://localhost:3000",
        "login_rate_limit": 100,
        "chat_rate_limit": 100,
        "relevance_threshold": 0.0,
        "keyword_rank_floor": 0.0,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]
