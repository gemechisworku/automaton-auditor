"""
Repo and graph forensic tools. Sandboxed git; AST-based structure analysis.
API Contracts §5.1; SRS FR-6, FR-7, NFR-4, NFR-5.
"""

from __future__ import annotations

import ast
import os
import subprocess
import tempfile
from pathlib import Path


class RepoCloneError(Exception):
    """Raised when git clone fails (invalid URL, auth, network)."""


def clone_repo(repo_url: str) -> str:
    """
    Clone repository into a temporary directory. Uses subprocess only; no os.system.
    Caller is responsible for cleanup of the temp directory (or process exit).

    Args:
        repo_url: Valid GitHub (or other) clone URL (HTTPS or SSH).

    Returns:
        Path to the cloned repo (directory containing .git).

    Raises:
        RepoCloneError: On invalid URL, auth failure, or network error.
    """
    if not repo_url or not isinstance(repo_url, str):
        raise RepoCloneError("repo_url must be a non-empty string")
    url = repo_url.strip()
    if not url:
        raise RepoCloneError("repo_url must be a non-empty string")

    tmp_dir = tempfile.mkdtemp(prefix="automaton_auditor_clone_")
    try:
        # Clone into empty tmp_dir; repo root is tmp_dir (contents + .git live there)
        result = subprocess.run(
            ["git", "clone", "--depth", "1", url, tmp_dir],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError as e:
        raise RepoCloneError("git not found (is Git installed and on PATH?)") from e
    except subprocess.TimeoutExpired as e:
        raise RepoCloneError(f"git clone timed out after {e.timeout}s") from e

    if result.returncode != 0:
        msg = result.stderr or result.stdout or "Unknown git error"
        raise RepoCloneError(f"git clone failed: {msg.strip()}")

    repo_path = os.path.abspath(tmp_dir)
    if not os.path.isdir(os.path.join(repo_path, ".git")):
        raise RepoCloneError("Clone completed but .git not found")
    return repo_path


def list_repo_files(repo_path: str, relative: bool = True) -> list[str]:
    """
    List file paths in the repository (for cross-reference with report claims).
    Uses git ls-files; no os.system, subprocess.run only.

    Args:
        repo_path: Path to cloned repo root.
        relative: If True, return paths relative to repo root; else absolute.

    Returns:
        List of file paths (strings). Empty on error or non-dir.
    """
    path = Path(repo_path)
    if not path.is_dir():
        return []
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    lines = [line.strip() for line in (result.stdout or "").strip().splitlines() if line.strip()]
    if relative:
        return lines
    return [str(path / p) for p in lines]


def extract_git_history(repo_path: str) -> list[dict]:
    """
    Run git log --oneline --reverse with format for commit, message, timestamp.
    Returns structured list of dicts.
    """
    path = Path(repo_path)
    if not path.is_dir():
        return []
    try:
        result = subprocess.run(
            [
                "git",
                "log",
                "--format=%h %s %ci",
                "--reverse",
                "-z",
            ],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        return []
    except subprocess.TimeoutExpired:
        return []
    if result.returncode != 0:
        return []

    entries = []
    for block in (result.stdout or "").strip("\0").split("\0"):
        block = block.strip()
        if not block:
            continue
        parts = block.split()
        if len(parts) < 2:
            continue
        commit = parts[0]
        # %ci is YYYY-MM-DD HH:MM:SS +tz (3 tokens at end)
        if len(parts) >= 4 and parts[-3][:1].isdigit() and parts[-2][:1].isdigit():
            timestamp = " ".join(parts[-3:])
            message = " ".join(parts[1:-3])
        else:
            timestamp = ""
            message = " ".join(parts[1:])
        entries.append({"commit": commit, "message": message, "timestamp": timestamp})
    return entries


def analyze_graph_structure(repo_path: str) -> dict:
    """
    Use Python AST to detect StateGraph, add_edge, add_node, parallelism, reducers
    in src/graph.py (or graph.py). Does not rely on regex for structure (SRS FR-7).

    Returns dict with keys: nodes, edges, has_parallelism, reducers_used, file_found, error.
    """
    path = Path(repo_path)
    candidates = [
        path / "src" / "graph.py",
        path / "graph.py",
    ]
    graph_file = None
    for p in candidates:
        if p.is_file():
            graph_file = p
            break
    if not graph_file:
        return {
            "file_found": False,
            "nodes": [],
            "edges": [],
            "has_parallelism": False,
            "reducers_used": False,
            "error": "no graph file found",
        }

    try:
        source = graph_file.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return {
            "file_found": True,
            "nodes": [],
            "edges": [],
            "has_parallelism": False,
            "reducers_used": False,
            "error": str(e),
        }

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return {
            "file_found": True,
            "nodes": [],
            "edges": [],
            "has_parallelism": False,
            "reducers_used": False,
            "error": f"syntax error: {e}",
        }

    nodes: list[str] = []
    edges: list[tuple[str, str]] = []
    add_edge_calls: list[tuple[str, str]] = []
    add_node_calls: list[str] = []
    has_state_graph = False
    has_add_conditional_edges = False
    reducers_seen = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = _call_name(func)
            if name and "StateGraph" in name:
                has_state_graph = True
            if name and "add_edge" in name:
                src, tgt = _edge_args(node)
                if src and tgt:
                    add_edge_calls.append((src, tgt))
            if name and "add_node" in name:
                node_name = _add_node_arg(node)
                if node_name:
                    add_node_calls.append(node_name)
            if name and "add_conditional" in name.lower():
                has_add_conditional_edges = True
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "reducer":
                    reducers_seen = True
                # Annotated with operator.ior or operator.add
                if isinstance(t, ast.Tuple):
                    pass  # could scan for reducer usage in state def
        if isinstance(node, ast.FunctionDef):
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Call):
                    n = _call_name(stmt.func)
                    if n in ("operator.ior", "operator.add", "ior", "add"):
                        reducers_seen = True

    # Dedupe nodes from add_node calls
    nodes = list(dict.fromkeys(add_node_calls))
    edges = list(dict.fromkeys(add_edge_calls))
    # Parallelism: multiple edges from same source, or conditional edges
    sources = [e[0] for e in edges]
    has_parallelism = has_add_conditional_edges or any(sources.count(s) > 1 for s in set(sources))

    return {
        "file_found": True,
        "nodes": nodes,
        "edges": edges,
        "has_parallelism": has_parallelism,
        "reducers_used": reducers_seen or _has_reducer_in_source(source),
        "error": None,
    }


def _call_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return f"{_call_name(func.value) or ''}.{func.attr}"
    return None


def _edge_args(node: ast.Call) -> tuple[str | None, str | None]:
    if len(node.args) >= 2:
        src = _arg_value(node.args[0])
        tgt = _arg_value(node.args[1])
        return (src, tgt)
    return (None, None)


def _arg_value(arg: ast.expr) -> str | None:
    if isinstance(arg, ast.Constant):
        return str(arg.value) if arg.value is not None else None
    if isinstance(arg, ast.Str):
        return arg.s
    return None


def _add_node_arg(node: ast.Call) -> str | None:
    if len(node.args) >= 1:
        return _arg_value(node.args[0])
    return None


def _has_reducer_in_source(source: str) -> bool:
    """Heuristic: reducer usage often appears as operator.ior or operator.add in state."""
    return "operator.ior" in source or "operator.add" in source
