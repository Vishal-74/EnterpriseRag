"""Structured outputs for answering, verification, rewriting, and summaries."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ClaimDraft(BaseModel):
    text: str
    chunk_ids: list[str] = Field(default_factory=list)


class DraftAnswer(BaseModel):
    insufficient_evidence: bool = False
    conflict_detected: bool = False
    conflict_notes: str | None = None
    answer: str = ""
    claims: list[ClaimDraft] = Field(default_factory=list)
    citation_chunk_ids: list[str] = Field(default_factory=list)


class ClaimVerdict(BaseModel):
    claim: str
    supported: bool
    reason: str = ""


class VerificationReport(BaseModel):
    verdicts: list[ClaimVerdict] = Field(default_factory=list)


class StandaloneQuery(BaseModel):
    query: str


class SummaryDraft(BaseModel):
    summary: str
