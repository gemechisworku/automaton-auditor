"""
State and data types for the Automaton Auditor graph.
Per API Contracts §3; SRS FR-1–FR-5.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field
from typing_extensions import TypedDict


# ----- Pydantic models (Detective and report data) -----


class Evidence(BaseModel):
    """Detective output only; no opinion fields. API Contracts §3.1."""

    goal: str
    found: bool
    content: str | None = None
    location: str
    rationale: str
    confidence: float = Field(..., ge=0.0, le=1.0)


class JudicialOpinion(BaseModel):
    """Judge output per criterion. API Contracts §3.2."""

    judge: Literal["Prosecutor", "Defense", "TechLead"]
    criterion_id: str
    score: int = Field(..., ge=1, le=5)
    argument: str
    cited_evidence: list[str]


class CriterionResult(BaseModel):
    """Per-criterion result produced by Chief Justice. API Contracts §3.3."""

    dimension_id: str
    dimension_name: str
    final_score: int = Field(..., ge=1, le=5)
    judge_opinions: list[JudicialOpinion]
    dissent_summary: str | None = None
    remediation: str


class AuditReport(BaseModel):
    """Final report; serialized to Markdown. API Contracts §3.4."""

    repo_url: str
    executive_summary: str
    overall_score: float
    criteria: list[CriterionResult]
    remediation_plan: str


# ----- Graph state (TypedDict with reducers for parallel nodes) -----


class AgentState(TypedDict, total=False):
    """
    Graph state passed between nodes.
    Reducers: evidences merged with operator.ior, opinions with operator.add. API Contracts §3.5.
    """

    repo_url: str
    pdf_path: str
    rubric_dimensions: list[dict[str, Any]]
    evidences: Annotated[dict[str, list[Evidence]], operator.ior]
    opinions: Annotated[list[JudicialOpinion], operator.add]
    final_report: AuditReport | None
