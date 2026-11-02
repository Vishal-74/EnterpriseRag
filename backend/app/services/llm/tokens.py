"""Token estimates and published price estimates.

Provider usage fields are preferred when a call returns them. Prices are
estimates for the dashboard and should be updated when vendor prices change.
"""

from __future__ import annotations

from typing import Any

from app.services.llm.types import ChatMessage

# USD per 1M tokens: (input, output). Embeddings use the input price only.
_PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "claude-3-5-haiku-latest": (0.80, 4.00),
    "claude-3-5-sonnet-latest": (3.00, 15.00),
    "text-embedding-3-small": (0.02, 0.0),
}

_encoder = None


def _encoding() -> Any:
    global _encoder
    if _encoder is None:
        import tiktoken

        try:
            _encoder = tiktoken.get_encoding("o200k_base")
        except Exception:
            _encoder = tiktoken.get_encoding("cl100k_base")
    return _encoder


def count_text(text: str) -> int:
    """Estimate tokens for a string."""
    if not text:
        return 0
    return len(_encoding().encode(text))


def count_messages(messages: list[ChatMessage]) -> int:
    """Estimate prompt tokens, including a small per-message overhead."""
    return sum(count_text(message.content) + 4 for message in messages)


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate USD cost from the local price table."""
    input_price, output_price = _PRICES.get(model, (0.0, 0.0))
    return (prompt_tokens * input_price + completion_tokens * output_price) / 1_000_000
