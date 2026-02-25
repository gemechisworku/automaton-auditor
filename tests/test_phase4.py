"""
Phase 4 tests: Chief Justice, report serialization, full run.
See docs/implementation_plan.md §4.2.
"""

from pathlib import Path

import pytest

from src.graph import build_audit_graph, create_initial_state
from src.nodes.justice import (
    audit_report_to_markdown,
    chief_justice_node,
    write_report_to_path,
)
from src.state import AuditReport, CriterionResult, Evidence, JudicialOpinion


@pytest.fixture
def mock_state_with_opinions():
    """State with opinions (3 per criterion) and evidences for Chief Justice."""
    opinions = [
        JudicialOpinion(judge="Prosecutor", criterion_id="graph_orchestration", score=2, argument="Weak.", cited_evidence=[]),
        JudicialOpinion(judge="Defense", criterion_id="graph_orchestration", score=4, argument="Good effort.", cited_evidence=[]),
        JudicialOpinion(judge="TechLead", criterion_id="graph_orchestration", score=3, argument="Adequate.", cited_evidence=[]),
    ]
    return {
        "repo_url": "https://github.com/example/repo",
        "pdf_path": "/path/to/doc.pdf",
        "rubric_path": str(Path(__file__).resolve().parent.parent / "rubric.json"),
        "rubric_dimensions": [
            {"id": "graph_orchestration", "name": "Graph Orchestration", "target_artifact": "github_repo"}
        ],
        "evidences": {
            "graph_orchestration": [
                Evidence(goal="Check graph.", found=True, content="StateGraph found.", location="src/graph.py", rationale="OK", confidence=0.9)
            ]
        },
        "opinions": opinions,
        "final_report": None,
    }


def test_chief_justice_node_returns_final_report(mock_state_with_opinions):
    """ChiefJusticeNode with mock state returns final_report of type AuditReport."""
    out = chief_justice_node(mock_state_with_opinions)
    assert "final_report" in out
    report = out["final_report"]
    assert isinstance(report, AuditReport)
    assert report.repo_url == "https://github.com/example/repo"
    assert report.overall_score >= 1 and report.overall_score <= 5
    assert len(report.criteria) >= 1
    c = report.criteria[0]
    assert c.dimension_id == "graph_orchestration"
    assert c.final_score in (1, 2, 3, 4, 5)
    assert len(c.judge_opinions) == 3


def test_chief_justice_applies_security_cap():
    """When evidence suggests security issue, final score capped at 3."""
    state = {
        "repo_url": "https://github.com/x/r",
        "pdf_path": "",
        "rubric_path": str(Path(__file__).resolve().parent.parent / "rubric.json"),
        "rubric_dimensions": [{"id": "safe_tool", "name": "Safe Tool", "target_artifact": "github_repo"}],
        "evidences": {
            "safe_tool": [
                Evidence(goal="Check safety.", found=True, content="Uses os.system with user input.", location="tools.py", rationale="Risk.", confidence=0.9)
            ]
        },
        "opinions": [
            JudicialOpinion(judge="Prosecutor", criterion_id="safe_tool", score=1, argument="Bad.", cited_evidence=[]),
            JudicialOpinion(judge="Defense", criterion_id="safe_tool", score=5, argument="Effort.", cited_evidence=[]),
            JudicialOpinion(judge="TechLead", criterion_id="safe_tool", score=5, argument="Works.", cited_evidence=[]),
        ],
        "final_report": None,
    }
    out = chief_justice_node(state)
    report = out["final_report"]
    c = next(cr for cr in report.criteria if cr.dimension_id == "safe_tool")
    assert c.final_score <= 3


def test_variance_gt_2_includes_dissent_summary():
    """Mock opinions with variance > 2; dissent_summary is present."""
    state = {
        "repo_url": "https://github.com/x/r",
        "pdf_path": "",
        "rubric_path": str(Path(__file__).resolve().parent.parent / "rubric.json"),
        "rubric_dimensions": [{"id": "dim1", "name": "Dimension One", "target_artifact": "github_repo"}],
        "evidences": {"dim1": []},
        "opinions": [
            JudicialOpinion(judge="Prosecutor", criterion_id="dim1", score=1, argument="Low.", cited_evidence=[]),
            JudicialOpinion(judge="Defense", criterion_id="dim1", score=5, argument="High.", cited_evidence=[]),
            JudicialOpinion(judge="TechLead", criterion_id="dim1", score=3, argument="Mid.", cited_evidence=[]),
        ],
        "final_report": None,
    }
    out = chief_justice_node(state)
    report = out["final_report"]
    c = report.criteria[0]
    assert c.dissent_summary is not None
    assert "Variance" in c.dissent_summary or "Tech Lead" in c.dissent_summary


def test_report_markdown_structure():
    """Serialize AuditReport to Markdown; assert Executive Summary, Criterion Breakdown, Remediation Plan."""
    report = AuditReport(
        repo_url="https://github.com/a/b",
        executive_summary="Summary.",
        overall_score=3.0,
        criteria=[
            CriterionResult(
                dimension_id="d1",
                dimension_name="Dim 1",
                final_score=3,
                judge_opinions=[],
                dissent_summary=None,
                remediation="Fix it.",
            )
        ],
        remediation_plan="Do the fixes.",
    )
    md = audit_report_to_markdown(report)
    assert "## Executive Summary" in md
    assert "## Criterion Breakdown" in md
    assert "## Remediation Plan" in md
    assert "Summary." in md
    assert "3.0" in md or "3" in md
    assert "Do the fixes." in md


def test_write_report_to_path(tmp_path):
    """write_report_to_path creates file with Markdown content."""
    report = AuditReport(
        repo_url="https://github.com/a/b",
        executive_summary="S.",
        overall_score=3.0,
        criteria=[],
        remediation_plan="P.",
    )
    out = tmp_path / "sub" / "report.md"
    write_report_to_path(report, str(out))
    assert out.is_file()
    assert "Executive Summary" in out.read_text()
    assert "Remediation Plan" in out.read_text()


def test_full_run_produces_report_and_file(tmp_path):
    """Run full graph (with mocked Judges) and assert final_report set and file written."""
    from pypdf import PdfWriter
    from unittest.mock import patch

    pdf_path = tmp_path / "report.pdf"
    w = PdfWriter()
    w.add_blank_page(612, 792)
    with open(pdf_path, "wb") as f:
        w.write(f)

    state = create_initial_state(
        repo_url="https://github.com/octocat/Hello-World.git",
        pdf_path=str(pdf_path),
    )
    state["rubric_dimensions"] = state["rubric_dimensions"][:1] if state["rubric_dimensions"] else [
        {"id": "git_forensic_analysis", "name": "Git Forensic Analysis", "target_artifact": "github_repo"}
    ]

    fake_opinion = JudicialOpinion(
        judge="Prosecutor", criterion_id="git_forensic_analysis", score=3, argument="OK.", cited_evidence=[]
    )

    with patch("src.nodes.judges._get_llm") as mock_llm:
        mock_llm.return_value.invoke.side_effect = lambda _: fake_opinion
        graph = build_audit_graph().compile()
        final = graph.invoke(state)

    assert final.get("final_report") is not None
    report = final["final_report"]
    assert isinstance(report, AuditReport)
    assert report.repo_url
    assert len(report.criteria) >= 1

    out_file = tmp_path / "audit_out.md"
    write_report_to_path(report, str(out_file))
    assert out_file.is_file()
    assert "Executive Summary" in out_file.read_text()
