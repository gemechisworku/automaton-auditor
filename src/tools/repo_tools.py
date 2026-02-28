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

    Returns dict with keys: nodes, edges, has_parallelism, reducers_used, file_found, error,
    wiring_summary, parallel_sources, fan_in_targets (AST-based structural analysis for Evidence).
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
            "wiring_summary": "",
            "parallel_sources": [],
            "fan_in_targets": [],
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
            "wiring_summary": "",
            "parallel_sources": [],
            "fan_in_targets": [],
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
            "wiring_summary": "",
            "parallel_sources": [],
            "fan_in_targets": [],
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
        if isinstance(node, ast.FunctionDef):
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Call):
                    n = _call_name(stmt.func)
                    if n in ("operator.ior", "operator.add", "ior", "add"):
                        reducers_seen = True

    nodes = list(dict.fromkeys(add_node_calls))
    edges = list(dict.fromkeys(add_edge_calls))
    sources = [e[0] for e in edges]
    targets = [e[1] for e in edges]
    has_parallelism = has_add_conditional_edges or any(sources.count(s) > 1 for s in set(sources))

    # Parallelism pattern: nodes that fan out (multiple outgoing edges)
    parallel_sources = [s for s in set(sources) if sources.count(s) > 1]
    # Fan-in: nodes that receive from multiple predecessors
    fan_in_targets = [t for t in set(targets) if targets.count(t) > 1]
    # Human-readable wiring summary for Evidence content/rationale
    wiring_summary = _build_wiring_summary(
        has_state_graph=has_state_graph,
        nodes=nodes,
        edges=edges,
        has_parallelism=has_parallelism,
        reducers_used=reducers_seen or _has_reducer_in_source(source),
        parallel_sources=parallel_sources,
        fan_in_targets=fan_in_targets,
        has_conditional=has_add_conditional_edges,
    )

    return {
        "file_found": True,
        "nodes": nodes,
        "edges": edges,
        "has_parallelism": has_parallelism,
        "reducers_used": reducers_seen or _has_reducer_in_source(source),
        "error": None,
        "wiring_summary": wiring_summary,
        "parallel_sources": parallel_sources,
        "fan_in_targets": fan_in_targets,
    }


def _build_wiring_summary(
    *,
    has_state_graph: bool,
    nodes: list[str],
    edges: list[tuple[str, str]],
    has_parallelism: bool,
    reducers_used: bool,
    parallel_sources: list[str],
    fan_in_targets: list[str],
    has_conditional: bool,
) -> str:
    """Build a criterion-aware, debuggable summary of graph wiring from AST."""
    parts = []
    parts.append(f"StateGraph present: {has_state_graph}. Nodes ({len(nodes)}): {nodes}.")
    parts.append(f"Edges: {edges}.")
    parts.append(f"Parallelism (fan-out): {has_parallelism}; sources with multiple edges: {parallel_sources}.")
    parts.append(f"Fan-in targets (multiple incoming edges): {fan_in_targets}.")
    parts.append(f"Conditional edges: {has_conditional}. Reducers used in state: {reducers_used}.")
    return " ".join(parts)


def analyze_state_schema(repo_path: str) -> dict:
    """
    AST-based analysis of src/state.py: Pydantic models (Evidence, JudicialOpinion, etc.)
    and TypedDict/Annotated reducer usage. Integrates with Evidence for state_management_rigor.

    Returns dict with keys: file_found, models_found, reducer_keys, has_evidence, has_judicial_opinion,
    has_agent_state, error.
    """
    path = Path(repo_path)
    state_file = path / "src" / "state.py"
    if not state_file.is_file():
        return {
            "file_found": False,
            "models_found": [],
            "reducer_keys": [],
            "has_evidence": False,
            "has_judicial_opinion": False,
            "has_agent_state": False,
            "error": "src/state.py not found",
        }
    try:
        source = state_file.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return {
            "file_found": True,
            "models_found": [],
            "reducer_keys": [],
            "has_evidence": False,
            "has_judicial_opinion": False,
            "has_agent_state": False,
            "error": str(e),
        }
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return {
            "file_found": True,
            "models_found": [],
            "reducer_keys": [],
            "has_evidence": False,
            "has_judicial_opinion": False,
            "has_agent_state": False,
            "error": f"syntax error: {e}",
        }

    models_found: list[str] = []
    reducer_keys: list[str] = []
    has_evidence = False
    has_judicial_opinion = False
    has_agent_state = False

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            name = node.name
            if name:
                models_found.append(name)
            if name == "Evidence":
                has_evidence = True
            if name == "JudicialOpinion":
                has_judicial_opinion = True
            if name == "AgentState":
                has_agent_state = True
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            # Annotated[..., reducer] pattern: target id is the state key
            key_name = node.target.id
            if isinstance(node.annotation, ast.Subscript):
                ann = node.annotation
                if isinstance(ann.slice, ast.Tuple) or hasattr(ann.slice, "elts"):
                    # Annotated[dict[str, list[Evidence]], merge_evidences] -> key_name
                    reducer_keys.append(key_name)
            # Also check for simple Name annotation that might be Annotated alias
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    n = _call_name(child.func)
                    if n and ("merge" in n.lower() or "ior" in str(n) or "add" in str(n)):
                        if key_name not in reducer_keys:
                            reducer_keys.append(key_name)

    if not reducer_keys and ("merge_evidences" in source or "merge_opinions" in source):
        if "evidences" in source:
            reducer_keys.append("evidences")
        if "opinions" in source:
            reducer_keys.append("opinions")

    return {
        "file_found": True,
        "models_found": models_found,
        "reducer_keys": list(dict.fromkeys(reducer_keys)),
        "has_evidence": has_evidence,
        "has_judicial_opinion": has_judicial_opinion,
        "has_agent_state": has_agent_state,
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
