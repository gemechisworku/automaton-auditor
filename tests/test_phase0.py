"""
Phase 0 tests: imports, rubric load, env check, reducers.
See docs/implementation_plan.md §0.2.
"""

import json
import operator
import os
from pathlib import Path

import pytest

# 1. Imports — no errors
def test_imports():
    from src.state import (
        AgentState,
        AuditReport,
        Evidence,
        JudicialOpinion,
    )
    assert Evidence is not None
    assert JudicialOpinion is not None
    assert AuditReport is not None
    assert AgentState is not None


# 2. Rubric load
def test_rubric_load():
    path = Path(__file__).resolve().parent.parent / "rubric.json"
    with open(path, encoding="utf-8") as f:
        rubric = json.load(f)
    assert "dimensions" in rubric
    assert "synthesis_rules" in rubric
    dimensions = rubric["dimensions"]
    assert len(dimensions) >= 1
    allowed = {"github_repo", "pdf_report", "pdf_images"}
    targets = {d["target_artifact"] for d in dimensions}
    assert targets.issubset(allowed), f"target_artifact must be in {allowed}, got {targets}"
    assert len(targets) >= 1


# 3. Env — fail clearly if required vars missing
def test_env_check_fails_when_no_llm_key():
    """With no LLM API key set, a required-env check should fail clearly."""
    env_example = Path(__file__).resolve().parent.parent / ".env.example"
    assert env_example.exists()
    with open(env_example, encoding="utf-8") as f:
        content = f.read()
    # .env.example should document at least one LLM key name
    llm_keys = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"]
    mentioned = [k for k in llm_keys if k in content]
    assert len(mentioned) >= 1, ".env.example should list at least one LLM key"

    # Simulate check: at least one of these must be set (and non-empty)
    def require_at_least_one_llm_key(env=None):
        env = os.environ if env is None else env
        for k in llm_keys:
            if env.get(k, "").strip():
                return True
        raise ValueError(
            f"Missing required env: set at least one of {llm_keys}. "
            "Copy .env.example to .env and set your API key."
        )

    # With none set, should raise
    with pytest.raises(ValueError) as exc_info:
        require_at_least_one_llm_key(env={})
    assert "Missing required env" in str(exc_info.value) or "at least one" in str(exc_info.value).lower()

    # With one set, should pass
    require_at_least_one_llm_key(env={"OPENAI_API_KEY": "sk-placeholder"})


# 4. Reducers — merge behavior matches operator.ior / operator.add
def test_reducer_evidences_ior():
    from src.state import Evidence

    e1 = Evidence(goal="g1", found=True, location="l1", rationale="r1", confidence=0.9)
    e2 = Evidence(goal="g2", found=False, location="l2", rationale="r2", confidence=0.5)
    update_a = {"dim_a": [e1]}
    update_b = {"dim_b": [e2]}
    merged = operator.ior(update_a.copy(), update_b)
    assert merged == {"dim_a": [e1], "dim_b": [e2]}


def test_reducer_partial_state_updates_merge_correctly():
    """Simulate two parallel nodes returning partial evidences; merge matches operator.ior."""
    from src.state import Evidence

    e_repo = Evidence(goal="repo", found=True, location="/tmp/repo", rationale="Clone OK", confidence=0.9)
    e_doc = Evidence(goal="doc", found=True, location="report.pdf", rationale="PDF OK", confidence=0.8)
    # Node A returns {"evidences": {"git_forensic_analysis": [e_repo]}}
    # Node B returns {"evidences": {"theoretical_depth": [e_doc]}}
    update_a = {"git_forensic_analysis": [e_repo]}
    update_b = {"theoretical_depth": [e_doc]}
    merged = operator.ior(update_a.copy(), update_b)
    assert "git_forensic_analysis" in merged
    assert "theoretical_depth" in merged
    assert len(merged["git_forensic_analysis"]) == 1
    assert len(merged["theoretical_depth"]) == 1
    assert merged["git_forensic_analysis"][0].goal == "repo"
    assert merged["theoretical_depth"][0].goal == "doc"


def test_reducer_opinions_add():
    from src.state import JudicialOpinion

    o1 = JudicialOpinion(
        judge="Prosecutor", criterion_id="c1", score=2, argument="a1", cited_evidence=[]
    )
    o2 = JudicialOpinion(
        judge="Defense", criterion_id="c1", score=4, argument="a2", cited_evidence=[]
    )
    list_a = [o1]
    list_b = [o2]
    merged = operator.add(list_a, list_b)
    assert len(merged) == 2
    assert merged[0].judge == "Prosecutor"
    assert merged[1].judge == "Defense"


def test_agent_state_can_hold_empty_evidences_opinions():
    """AgentState with empty evidences/opinions is valid (TypedDict total=False)."""
    from src.state import AgentState

    state: AgentState = {
        "repo_url": "https://github.com/org/repo",
        "pdf_path": "/path/to/report.pdf",
        "rubric_dimensions": [],
        "evidences": {},
        "opinions": [],
        "final_report": None,
    }
    assert state["evidences"] == {}
    assert state["opinions"] == []
