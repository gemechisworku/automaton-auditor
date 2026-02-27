"""
StateGraph: START → parallel detectives → EvidenceAggregator → [optional] parallel Judges → END.
Phase 2: Detective layer only. Phase 3: + Judges (Prosecutor, Defense, Tech Lead).
"""

from __future__ import annotations

import json
from pathlib import Path

from langgraph.graph import END, START, StateGraph

from src.state import AgentState
from src.nodes.detectives import doc_analyst_node, repo_investigator_node, vision_inspector_node
from src.nodes.judges import defense_node, prosecutor_node, tech_lead_node
from src.nodes.justice import (
    chief_justice_node,
    degraded_report_node,
    evidence_aggregator_node,
    is_critical_failure,
    judge_collector_node,
)


def load_rubric_dimensions(rubric_path: str | None = None) -> list[dict]:
    """Load dimensions list from rubric JSON. Dimensions may include optional 'levels' (points-based rubric)."""
    path = Path(rubric_path or "rubric.json")
    if not path.is_file():
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("dimensions", [])


def load_rubric_full(rubric_path: str | None = None) -> dict:
    """Load full rubric JSON (metadata, dimensions, synthesis_rules). Returns {} if file missing."""
    path = Path(rubric_path or "rubric.json")
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def is_points_based_rubric(dimensions: list[dict]) -> bool:
    """True if any dimension has 'levels' (point-based scoring)."""
    return any(d.get("levels") for d in dimensions)


def build_detective_graph() -> StateGraph:
    """Build StateGraph: START → parallel detectives → EvidenceAggregator → END (no Judges)."""
    builder = StateGraph(AgentState)

    builder.add_node("repo_investigator", repo_investigator_node)
    builder.add_node("doc_analyst", doc_analyst_node)
    builder.add_node("vision_inspector", vision_inspector_node)
    builder.add_node("evidence_aggregator", evidence_aggregator_node)

    builder.add_edge(START, "repo_investigator")
    builder.add_edge(START, "doc_analyst")
    builder.add_edge(START, "vision_inspector")

    builder.add_edge("repo_investigator", "evidence_aggregator")
    builder.add_edge("doc_analyst", "evidence_aggregator")
    builder.add_edge("vision_inspector", "evidence_aggregator")

    builder.add_edge("evidence_aggregator", END)

    return builder


def _route_after_aggregator(state: AgentState) -> str:
    """Conditional edge: degraded path when inputs failed; else normal judicial path."""
    return "degraded_report" if is_critical_failure(state) else "judicial_entry"


def _judicial_entry_node(state: AgentState) -> dict:
    """No-op: passes state so conditional can fan out to all three judges."""
    return {}


def build_audit_graph() -> StateGraph:
    """
    Build StateGraph: detectives → EvidenceAggregator → [conditional]
    → either degraded_report → END (error path) or judicial_entry → Judges → judge_collector → ChiefJustice → END.
    """
    builder = StateGraph(AgentState)

    builder.add_node("repo_investigator", repo_investigator_node)
    builder.add_node("doc_analyst", doc_analyst_node)
    builder.add_node("vision_inspector", vision_inspector_node)
    builder.add_node("evidence_aggregator", evidence_aggregator_node)
    builder.add_node("degraded_report", degraded_report_node)
    builder.add_node("judicial_entry", _judicial_entry_node)
    builder.add_node("prosecutor", prosecutor_node)
    builder.add_node("defense", defense_node)
    builder.add_node("tech_lead", tech_lead_node)
    builder.add_node("judge_collector", judge_collector_node)
    builder.add_node("chief_justice", chief_justice_node)

    builder.add_edge(START, "repo_investigator")
    builder.add_edge(START, "doc_analyst")
    builder.add_edge(START, "vision_inspector")

    builder.add_edge("repo_investigator", "evidence_aggregator")
    builder.add_edge("doc_analyst", "evidence_aggregator")
    builder.add_edge("vision_inspector", "evidence_aggregator")

    # Conditional/error-handling edge: skip judges when collection failed
    builder.add_conditional_edges(
        "evidence_aggregator",
        _route_after_aggregator,
        {"degraded_report": "degraded_report", "judicial_entry": "judicial_entry"},
    )
    builder.add_edge("degraded_report", END)

    builder.add_edge("judicial_entry", "prosecutor")
    builder.add_edge("judicial_entry", "defense")
    builder.add_edge("judicial_entry", "tech_lead")

    builder.add_edge("prosecutor", "judge_collector")
    builder.add_edge("defense", "judge_collector")
    builder.add_edge("tech_lead", "judge_collector")
    builder.add_edge("judge_collector", "chief_justice")
    builder.add_edge("chief_justice", END)

    return builder


def create_initial_state(
    repo_url: str,
    pdf_path: str = "",
    rubric_path: str | None = None,
    repo_path: str | None = None,
) -> AgentState:
    """Build initial AgentState for the graph. pdf_path may be empty for repo-only audit.
    When repo_path is set (e.g. pre-cloned for default PDF), RepoInvestigator will reuse it."""
    default_rubric = "rubric.json"
    path = Path(rubric_path or default_rubric)
    dimensions = load_rubric_dimensions(rubric_path)
    state: AgentState = {
        "repo_url": repo_url,
        "pdf_path": pdf_path,
        "rubric_path": str(path.resolve()) if path.is_file() else default_rubric,
        "rubric_dimensions": dimensions,
        "evidences": {},
        "opinions": [],
        "final_report": None,
    }
    if repo_path:
        state["repo_path"] = repo_path
    return state
