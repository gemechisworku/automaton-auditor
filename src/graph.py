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
from src.nodes.justice import evidence_aggregator_node, judge_collector_node


def load_rubric_dimensions(rubric_path: str | None = None) -> list[dict]:
    """Load dimensions list from rubric.json."""
    path = Path(rubric_path or "rubric.json")
    if not path.is_file():
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("dimensions", [])


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


def build_audit_graph() -> StateGraph:
    """Build StateGraph through Judges: detectives → EvidenceAggregator → parallel Judges → judge_collector → END."""
    builder = StateGraph(AgentState)

    builder.add_node("repo_investigator", repo_investigator_node)
    builder.add_node("doc_analyst", doc_analyst_node)
    builder.add_node("vision_inspector", vision_inspector_node)
    builder.add_node("evidence_aggregator", evidence_aggregator_node)
    builder.add_node("prosecutor", prosecutor_node)
    builder.add_node("defense", defense_node)
    builder.add_node("tech_lead", tech_lead_node)
    builder.add_node("judge_collector", judge_collector_node)

    builder.add_edge(START, "repo_investigator")
    builder.add_edge(START, "doc_analyst")
    builder.add_edge(START, "vision_inspector")

    builder.add_edge("repo_investigator", "evidence_aggregator")
    builder.add_edge("doc_analyst", "evidence_aggregator")
    builder.add_edge("vision_inspector", "evidence_aggregator")

    # Fan-out from evidence_aggregator to all three judges (parallel)
    builder.add_edge("evidence_aggregator", "prosecutor")
    builder.add_edge("evidence_aggregator", "defense")
    builder.add_edge("evidence_aggregator", "tech_lead")

    # Fan-in: all judges → judge_collector → END
    builder.add_edge("prosecutor", "judge_collector")
    builder.add_edge("defense", "judge_collector")
    builder.add_edge("tech_lead", "judge_collector")
    builder.add_edge("judge_collector", END)

    return builder


def create_initial_state(
    repo_url: str,
    pdf_path: str,
    rubric_path: str | None = None,
) -> AgentState:
    """Build initial AgentState for the graph."""
    dimensions = load_rubric_dimensions(rubric_path)
    return AgentState(
        repo_url=repo_url,
        pdf_path=pdf_path,
        rubric_dimensions=dimensions,
        evidences={},
        opinions=[],
        final_report=None,
    )
