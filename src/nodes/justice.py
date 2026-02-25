"""
Supreme Court layer: EvidenceAggregator (Phase 2), ChiefJusticeNode (Phase 4).
"""

from __future__ import annotations

from src.state import AgentState


def evidence_aggregator_node(state: AgentState) -> dict:
    """
    No-op merge or validation of state["evidences"]. Reducers already merged Detective outputs;
    can return {} or a pass-through. API Contracts §4.
    """
    # Evidences are already merged by LangGraph reducer (operator.ior); nothing to do
    return {}
