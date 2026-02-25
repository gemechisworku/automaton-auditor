"""
Phase 1 tests: repo tools — clone_repo, extract_git_history, analyze_graph_structure.
"""

import os
import shutil
from pathlib import Path

import pytest

from src.tools.repo_tools import (
    RepoCloneError,
    analyze_graph_structure,
    clone_repo,
    extract_git_history,
)


def test_clone_repo_success():
    """Clone a small public repo; path exists, contains .git, under temp (not cwd)."""
    repo_path = clone_repo("https://github.com/octocat/Hello-World.git")
    try:
        assert os.path.isdir(repo_path)
        assert os.path.isdir(os.path.join(repo_path, ".git"))
        # Should be under system temp (sandboxed), not cwd
        assert "automaton_auditor_clone_" in repo_path
    finally:
        # Cleanup: remove parent temp dir (clone_repo uses mkdtemp; repo is inside or is the dir)
        parent = os.path.dirname(repo_path)
        if "automaton_auditor_clone_" in parent:
            shutil.rmtree(parent, ignore_errors=True)
        elif "automaton_auditor_clone_" in repo_path:
            shutil.rmtree(repo_path, ignore_errors=True)


def test_clone_repo_invalid_url_raises():
    """Invalid URL or auth failure raises; no silent success."""
    with pytest.raises(RepoCloneError):
        clone_repo("https://github.com/this-repo-does-not-exist-xyz-12345/none.git")
    with pytest.raises(RepoCloneError):
        clone_repo("")
    with pytest.raises(RepoCloneError):
        clone_repo("not-a-url")


def test_extract_git_history():
    """On a real repo, return is list-like; entries have message/timestamp-like fields."""
    # Use this project as the repo
    repo_path = Path(__file__).resolve().parent.parent
    history = extract_git_history(str(repo_path))
    assert isinstance(history, list)
    if history:
        entry = history[0]
        assert "commit" in entry
        assert "message" in entry
        assert "timestamp" in entry


def test_analyze_graph_structure_with_fixture():
    """Run on fixture with minimal graph.py; result reflects structure (nodes, edges)."""
    fixture_dir = Path(__file__).resolve().parent / "fixtures"
    # Create a temp repo layout: fixture_dir/minimal_repo/src/graph.py
    minimal_src = fixture_dir / "minimal_repo" / "src"
    minimal_src.mkdir(parents=True, exist_ok=True)
    graph_py = minimal_src / "graph.py"
    graph_py.write_text(
        "from langgraph.graph import StateGraph\n"
        "builder = StateGraph({})\n"
        "builder.add_node('a', lambda s: s)\n"
        "builder.add_node('b', lambda s: s)\n"
        "builder.add_edge('a', 'b')\n"
    )
    try:
        result = analyze_graph_structure(str(fixture_dir / "minimal_repo"))
        assert result["file_found"] is True
        assert "nodes" in result
        assert "edges" in result
        assert "a" in result["nodes"] or "b" in result["nodes"]
        assert ("a", "b") in result["edges"] or ("b", "a") in result["edges"]
    finally:
        shutil.rmtree(fixture_dir / "minimal_repo", ignore_errors=True)


def test_analyze_graph_structure_no_graph_safe():
    """Repo with no graph file returns safe structure (file_found False)."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        result = analyze_graph_structure(tmp)
    assert result["file_found"] is False
    assert result["nodes"] == []
    assert "error" in result
