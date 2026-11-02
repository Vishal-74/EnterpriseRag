"""Shared enums and literals."""

from __future__ import annotations

from enum import Enum
from typing import Literal

DocumentKind = Literal["pdf", "txt", "md", "csv"]
ProviderName = Literal["openai", "anthropic"]


class DocumentStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class RunStatus(str, Enum):
    running = "running"
    completed = "completed"
    failed = "failed"
