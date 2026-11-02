"""Set test environment before the application is imported."""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/enterprise_intel_test",
)
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-long-enough-for-jwt")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
