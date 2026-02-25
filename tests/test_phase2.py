"""
Phase 2 tests: Detective nodes and graph — single detective, full graph run.
See docs/implementation_plan.md §2.2.
"""

from pathlib import Path

import pytest

from src.graph import build_detective_graph, create_initial_state
from src.nodes.detectives import doc_analyst_node, repo_investigator_node, vision_inspector_node
from src.state import AgentState, Evidence


def test_repo_investigator_node_returns_evidences():
    """Run repo_investigator_node with mock state (one github_repo dimension); assert evidences with Evidence objects."""
    rubric_path = Path(__file__).resolve().parent.parent / "rubric.json"
    import json
    with open(rubric_path, encoding="utf-8") as f:
        rubric = json.load(f)
    repo_dims = [d for d in rubric["dimensions"] if d.get("target_artifact") == "github_repo"]
    assert len(repo_dims) >= 1

    state: AgentState = {
        "repo_url": "https://github.com/octocat/Hello-World.git",
        "pdf_path": "",
        "rubric_dimensions": repo_dims[:1],
        "evidences": {},
        "opinions": [],
        "final_report": None,
    }
    out = repo_investigator_node(state)
    assert "evidences" in out
    assert isinstance(out["evidences"], dict)
    assert len(out["evidences"]) >= 1
    for dim_id, ev_list in out["evidences"].items():
        assert isinstance(ev_list, list)
        for e in ev_list:
            assert isinstance(e, Evidence)


def test_doc_analyst_node_returns_evidences(tmp_path):
    """Doc analyst with a minimal PDF and one pdf_report dimension returns evidences."""
    from pypdf import PdfWriter
    pdf_path = tmp_path / "doc.pdf"
    w = PdfWriter()
    w.add_blank_page(612, 792)
    with open(pdf_path, "wb") as f:
        w.write(f)

    state: AgentState = {
        "repo_url": "",
        "pdf_path": str(pdf_path),
        "rubric_dimensions": [
            {
                "id": "theoretical_depth",
                "name": "Theoretical Depth",
                "target_artifact": "pdf_report",
                "forensic_instruction": "Check for substantive concepts.",
                "success_pattern": "Concepts explained.",
                "failure_pattern": "Keyword only.",
            }
        ],
        "evidences": {},
        "opinions": [],
        "final_report": None,
    }
    out = doc_analyst_node(state)
    assert "evidences" in out
    assert "theoretical_depth" in out["evidences"]
    for e in out["evidences"]["theoretical_depth"]:
        assert isinstance(e, Evidence)


def test_vision_inspector_node_returns_evidences(tmp_path):
    """Vision inspector with one pdf_images dimension returns evidences dict."""
    state: AgentState = {
        "repo_url": "",
        "pdf_path": str(tmp_path / "nonexistent.pdf"),
        "rubric_dimensions": [
            {
                "id": "swarm_visual",
                "name": "Swarm Visual",
                "target_artifact": "pdf_images",
                "forensic_instruction": "Analyze diagram flow.",
                "success_pattern": "Flow identified.",
                "failure_pattern": "No flow.",
            }
        ],
        "evidences": {},
        "opinions": [],
        "final_report": None,
    }
    out = vision_inspector_node(state)
    assert "evidences" in out
    assert "swarm_visual" in out["evidences"]
    for e in out["evidences"]["swarm_visual"]:
        assert isinstance(e, Evidence)


def test_full_detective_graph_evidences_populated(tmp_path):
    """Invoke compiled graph with real repo URL and PDF path; state['evidences'] non-empty, keyed by dimension."""
    from pypdf import PdfWriter
    repo_url = "https://github.com/octocat/Hello-World.git"
    pdf_path = tmp_path / "report.pdf"
    w = PdfWriter()
    w.add_blank_page(612, 792)
    with open(pdf_path, "wb") as f:
        w.write(f)

    state = create_initial_state(repo_url=repo_url, pdf_path=str(pdf_path))
    graph = build_detective_graph().compile()
    final = graph.invoke(state)

    assert "evidences" in final
    assert isinstance(final["evidences"], dict)
    assert len(final["evidences"]) >= 1
    for dim_id, ev_list in final["evidences"].items():
        assert isinstance(ev_list, list)
        for e in ev_list:
            assert isinstance(e, Evidence)
