"""Stable hashes for file bytes, chunk text, and cache keys."""

from __future__ import annotations

import hashlib


def sha256_bytes(data: bytes) -> str:
    """Hex digest of raw file bytes."""
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    """Hex digest of a UTF-8 string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def embedding_cache_key(model: str, text: str) -> str:
    """Cache key that changes when the embedding model changes."""
    return sha256_text(f"{model}\n{text}")
