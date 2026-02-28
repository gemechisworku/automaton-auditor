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
    # Points-based rubric (optional)
    points: int | None = None
    excluded_from_total: bool = False
    selected_level_name: str | None = None


class AuditReport(BaseModel):
    """Final report; serialized to Markdown. API Contracts §3.4."""

    repo_url: str
    executive_summary: str
    overall_score: float
    criteria: list[CriterionResult]
    remediation_plan: str
    # Points-based rubric (optional)
    total_points: float | None = None
    max_points: float | None = None


# ----- Explicit reducers for parallel-written state (API Contracts §3.5) -----
#
# LangGraph applies these when merging partial state updates from parallel nodes.
# Named functions make reducer semantics explicit and maintainable.


def merge_evidences(
    current: dict[str, list[Evidence]], update: dict[str, list[Evidence]]
) -> dict[str, list[Evidence]]:
    """
    Reducer for parallel detective outputs: merge evidence dicts by dimension id.
    Each detective returns {"evidences": {dimension_id: [Evidence, ...]}}; this merges
    by key so all dimensions get their lists without overwriting other nodes' results.
    """
    return operator.ior(current, update)


def merge_opinions(
    current: list[JudicialOpinion], update: list[JudicialOpinion]
) -> list[JudicialOpinion]:
    """
    Reducer for parallel judge outputs: concatenate opinion lists.
    Each judge returns {"opinions": [JudicialOpinion, ...]}; this concatenates
    so all judges' opinions are retained for Chief Justice synthesis.
    """
    return operator.add(current, update)


# ----- Graph state (TypedDict with reducers for parallel nodes) -----
#
# Only evidences and opinions use reducers (parallel-written state). All other keys
# (repo_url, pdf_path, rubric_dimensions, final_report, repo_file_list) are overwritten
# by the last writer.


class AgentState(TypedDict, total=False):
    """
    Graph state passed between nodes.
    Reducers: evidences → merge_evidences (ior); opinions → merge_opinions (add). API Contracts §3.5.
    """

    repo_url: str
    repo_path: str | None  # optional; when set, RepoInvestigator reuses this path instead of cloning
    pdf_path: str
    rubric_path: str | None  # optional; Chief Justice loads synthesis_rules from here
    rubric_dimensions: list[dict[str, Any]]
    evidences: Annotated[dict[str, list[Evidence]], merge_evidences]
    opinions: Annotated[list[JudicialOpinion], merge_opinions]
    final_report: AuditReport | None
    repo_file_list: list[str]  # optional; set by RepoInvestigator for cross-reference (report_accuracy)
