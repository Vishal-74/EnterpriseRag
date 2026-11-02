"""Retrieval results passed to the answerer and agent tools."""

from __future__ import annotations

from dataclasses import dataclass

from app.models.document import Chunk


@dataclass
class ScoredChunk:
    chunk: Chunk
    document_name: str
    vector_similarity: float | None
    keyword_rank: float | None
    fusion_score: float
    relevant: bool = False
