"""
Phase 5 tests: Error paths, CLI validation, placeholder evidence.
See docs/implementation_plan.md §5.2.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from src.graph import create_initial_state
from src.nodes.justice import evidence_aggregator_node
from src.run import _default_output_path, _require_llm_key, run_audit
from src.state import Evidence


def test_require_llm_key_raises_when_unset():
    """Missing OPENAI_API_KEY raises with clear message."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
        with pytest.raises(RuntimeError) as exc_info:
            _require_llm_key()
        assert "OPENAI_API_KEY" in str(exc_info.value)


def test_require_llm_key_passes_when_set():
    """OPENAI_API_KEY set does not raise."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=False):
        _require_llm_key()


def test_run_audit_invalid_repo_url_raises():
    """Empty repo_url raises ValueError (no crash)."""
    with patch("src.run._require_llm_key"):
        with pytest.raises(ValueError) as exc_info:
            run_audit("", "/path/to/pdf.pdf")
        assert "repo_url" in str(exc_info.value).lower()


def test_run_audit_invalid_pdf_path_raises():
    """Empty pdf_path raises ValueError."""
    with patch("src.run._require_llm_key"):
        with pytest.raises(ValueError) as exc_info:
            run_audit("https://github.com/a/b", "")
        assert "pdf_path" in str(exc_info.value).lower()


def test_run_audit_missing_rubric_raises():
    """Rubric with no dimensions raises ValueError."""
    with patch("src.run._require_llm_key"):
        with patch("src.graph.load_rubric_dimensions", return_value=[]):
            with pytest.raises(ValueError) as exc_info:
                run_audit("https://github.com/a/b", "/tmp/x.pdf", rubric_path="/nonexistent/rubric.json")
            assert "dimensions" in str(exc_info.value).lower() or "rubric" in str(exc_info.value).lower()


def test_evidence_aggregator_injects_placeholder_for_missing():
    """When a dimension has no evidence, aggregator injects placeholder so graph can terminate."""
    state = {
        "repo_url": "https://github.com/x/r",
        "pdf_path": "/p.pdf",
        "rubric_dimensions": [
            {"id": "dim_a", "name": "Dim A", "forensic_instruction": "Check A."},
            {"id": "dim_b", "name": "Dim B", "forensic_instruction": "Check B."},
        ],
        "evidences": {"dim_a": [Evidence(goal="Check A.", found=True, location="x", rationale="Ok", confidence=0.8)]},
    }
    out = evidence_aggregator_node(state)
    assert "evidences" in out
    assert "dim_a" in out["evidences"]
    assert "dim_b" in out["evidences"]
    assert len(out["evidences"]["dim_b"]) >= 1
    assert out["evidences"]["dim_b"][0].found is False
    assert "placeholder" in out["evidences"]["dim_b"][0].rationale.lower() or "no evidence" in out["evidences"]["dim_b"][0].rationale.lower()


def test_default_output_path():
    """Default output path uses repo slug."""
    p = _default_output_path("https://github.com/octocat/Hello-World")
    assert "audit" in p
    assert "report_" in p
    assert "Hello-World" in p or "Hello_World" in p
    assert p.endswith(".md")
