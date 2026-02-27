"""
Phase 3 tests: Judicial layer — single Judge, full graph run through Judges.
See docs/implementation_plan.md §3.2.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from src.graph import build_audit_graph, create_initial_state
from src.nodes.judges import (
    _DEFENSE_SYSTEM,
    _PROSECUTOR_SYSTEM,
    _TECH_LEAD_SYSTEM,
    prosecutor_node,
)
from src.state import Evidence, JudicialOpinion


def test_judge_system_prompts_are_distinct():
    """JUDGE-2: The three judge personas have distinct system prompts (no overlap)."""
    assert _PROSECUTOR_SYSTEM != _DEFENSE_SYSTEM
    assert _DEFENSE_SYSTEM != _TECH_LEAD_SYSTEM
    assert _PROSECUTOR_SYSTEM != _TECH_LEAD_SYSTEM
    # Each prompt should contain persona-specific keywords
    assert "Prosecutor" in _PROSECUTOR_SYSTEM and "Vibe Coding" in _PROSECUTOR_SYSTEM
    assert "Defense" in _DEFENSE_SYSTEM and "Spirit of the Law" in _DEFENSE_SYSTEM
    assert "Tech Lead" in _TECH_LEAD_SYSTEM and "maintainable" in _TECH_LEAD_SYSTEM


@pytest.fixture
def mock_state_with_evidence():
    """State with one dimension and evidence for that dimension."""
    return {
        "repo_url": "https://github.com/example/repo",
        "pdf_path": "/path/to/doc.pdf",
        "rubric_dimensions": [
            {
                "id": "graph_orchestration",
                "name": "Graph Orchestration",
                "target_artifact": "github_repo",
                "forensic_instruction": "Verify parallel graph structure.",
                "success_pattern": "StateGraph with fan-out.",
                "failure_pattern": "Linear only.",
            }
        ],
        "evidences": {
            "graph_orchestration": [
                Evidence(
                    goal="Verify parallel graph structure.",
                    found=True,
                    content="StateGraph, add_edge, add_node found.",
                    location="src/graph.py",
                    rationale="AST found nodes and edges.",
                    confidence=0.9,
                )
            ]
        },
        "opinions": [],
        "final_report": None,
    }


def test_prosecutor_node_returns_opinions_with_mocked_llm(mock_state_with_evidence):
    """Single Judge (Prosecutor) with mock state and mocked LLM returns one JudicialOpinion."""
    fake_opinion = JudicialOpinion(
        judge="Prosecutor",
        criterion_id="graph_orchestration",
        score=3,
        argument="Evidence shows graph structure; moderate score.",
        cited_evidence=["[1] AST found nodes and edges."],
    )

    with patch("src.nodes.judges._get_llm") as mock_get_llm:
        mock_llm = mock_get_llm.return_value
        mock_llm.invoke.return_value = fake_opinion

        out = prosecutor_node(mock_state_with_evidence)

    assert "opinions" in out
    assert isinstance(out["opinions"], list)
    assert len(out["opinions"]) >= 1
    o = out["opinions"][0]
    assert isinstance(o, JudicialOpinion)
    assert o.judge == "Prosecutor"
    assert o.criterion_id == "graph_orchestration"
    assert 1 <= o.score <= 5
    assert o.argument
    assert isinstance(o.cited_evidence, list)


def test_parse_failure_does_not_append_invalid_opinion(mock_state_with_evidence):
    """When LLM raises, no invalid object is appended; retries then skip."""
    with patch("src.nodes.judges._get_llm") as mock_get_llm:
        mock_llm = mock_get_llm.return_value
        mock_llm.invoke.side_effect = ValueError("Parse error")

        out = prosecutor_node(mock_state_with_evidence)

    assert "opinions" in out
    assert out["opinions"] == []


def test_full_judicial_graph_opinions_populated_with_mocked_llm(tmp_path, mock_state_with_evidence):
    """Run graph through EvidenceAggregator then Judges (mocked); state['opinions'] has valid JudicialOpinions."""
    from pypdf import PdfWriter

    pdf_path = tmp_path / "report.pdf"
    w = PdfWriter()
    w.add_blank_page(612, 792)
    with open(pdf_path, "wb") as f:
        w.write(f)

    # Use minimal rubric (1 dimension) so we get 3 opinions (P, D, T) for 1 dimension
    state = create_initial_state(
        repo_url="https://github.com/octocat/Hello-World.git",
        pdf_path=str(pdf_path),
    )
    # Reduce dimensions to 1 for faster test
    state["rubric_dimensions"] = [state["rubric_dimensions"][0]] if state["rubric_dimensions"] else [
        {
            "id": "git_forensic_analysis",
            "name": "Git Forensic Analysis",
            "target_artifact": "github_repo",
            "forensic_instruction": "Analyze git history.",
            "success_pattern": "Atomic commits.",
            "failure_pattern": "Monolithic.",
        }
    ]

    fake_opinion = JudicialOpinion(
        judge="Prosecutor",
        criterion_id="git_forensic_analysis",
        score=2,
        argument="Some history found.",
        cited_evidence=[],
    )

    def fake_invoke(msgs):
        # Return opinion with judge set by caller (prosecutor/defense/tech_lead fix it in code)
        return fake_opinion

    with patch("src.nodes.judges._get_llm") as mock_get_llm:
        mock_llm = mock_get_llm.return_value
        mock_llm.invoke.side_effect = fake_invoke

        graph = build_audit_graph().compile()
        final = graph.invoke(state)

    assert "opinions" in final
    # 3 judges × 1 dimension = 3 opinions (if all succeed)
    assert len(final["opinions"]) >= 1
    for o in final["opinions"]:
        assert isinstance(o, JudicialOpinion)
        assert o.judge in ("Prosecutor", "Defense", "TechLead")
        assert 1 <= o.score <= 5
        assert o.criterion_id
