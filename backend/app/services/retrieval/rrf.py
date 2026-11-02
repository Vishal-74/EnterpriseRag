"""Reciprocal rank fusion for two or more ranked lists."""

from __future__ import annotations


def reciprocal_rank_fusion(rankings: list[list[str]], *, k: int = 60) -> list[tuple[str, float]]:
    """Merge rankings. Earlier positions contribute more. `k` is the RRF constant."""
    if k <= 0:
        raise ValueError("rrf k must be positive")
    scores: dict[str, float] = {}
    for ranking in rankings:
        for position, item_id in enumerate(ranking):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + position + 1)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)
