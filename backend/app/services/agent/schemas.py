"""Structured models for the planner, analysis tool, and report tool."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class PlanDecision(BaseModel):
    tool: Literal["search_knowledge_base", "analyze_documents", "generate_report", "finish"]
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class SearchArgs(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    limit: int = Field(default=6, ge=1, le=10)


class AnalyzeArgs(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    mode: Literal["summarize", "themes", "failure_causes"] = "summarize"


class ReportArgs(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    focus: str = Field(min_length=2, max_length=1000)


class AnalysisPoint(BaseModel):
    text: str
    chunk_ids: list[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    summary: str
    points: list[AnalysisPoint] = Field(default_factory=list)


class Finding(BaseModel):
    statement: str
    evidence: list[str] = Field(default_factory=list)
    source_chunk_ids: list[str] = Field(default_factory=list)


class ReportBody(BaseModel):
    title: str
    summary: str
    findings: list[Finding] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
