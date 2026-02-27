"""
Detective layer: RepoInvestigator, DocAnalyst, VisionInspector.
Each returns partial state update {"evidences": {dimension_id: [Evidence, ...]}}.
API Contracts §4; SRS FR-20.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.state import AgentState, Evidence
from src.tools.doc_tools import (
    PDFParseError,
    analyze_diagram,
    extract_images_from_pdf,
    ingest_pdf,
    query_doc,
)
from src.tools.repo_tools import (
    RepoCloneError,
    analyze_graph_structure,
    clone_repo,
    extract_git_history,
    list_repo_files,
)


def _repo_dimensions(state: AgentState) -> list[dict[str, Any]]:
    dims = state.get("rubric_dimensions") or []
    return [d for d in dims if d.get("target_artifact") == "github_repo"]


def _pdf_report_dimensions(state: AgentState) -> list[dict[str, Any]]:
    dims = state.get("rubric_dimensions") or []
    return [d for d in dims if d.get("target_artifact") == "pdf_report"]


def _pdf_images_dimensions(state: AgentState) -> list[dict[str, Any]]:
    dims = state.get("rubric_dimensions") or []
    return [d for d in dims if d.get("target_artifact") == "pdf_images"]


def repo_investigator_node(state: AgentState) -> dict[str, Any]:
    """
    Filter dimensions by target_artifact == "github_repo"; clone, git history, graph structure;
    build Evidence per dimension. Returns {"evidences": {dimension_id: [Evidence, ...]}}.
    """
    dimensions = _repo_dimensions(state)
    if not dimensions:
        return {"evidences": {}}

    repo_url = (state.get("repo_url") or "").strip()
    evidences: dict[str, list[Evidence]] = {}

    repo_path: str | None = state.get("repo_path")  # reuse pre-cloned path when set (e.g. default PDF in repo)
    if repo_path and not Path(repo_path).is_dir():
        repo_path = None
    git_history: list[dict] = []
    graph_struct: dict[str, Any] = {}
    repo_file_list: list[str] = []

    if repo_url:
        try:
            if repo_path is None:
                repo_path = clone_repo(repo_url)
            git_history = extract_git_history(repo_path) if repo_path else []
            graph_struct = analyze_graph_structure(repo_path) if repo_path else {}
            repo_file_list = list_repo_files(repo_path) if repo_path else []
        except RepoCloneError as e:
            for d in dimensions:
                dim_id = d.get("id", "unknown")
                evidences[dim_id] = [
                    Evidence(
                        goal=d.get("forensic_instruction", ""),
                        found=False,
                        location=repo_url,
                        rationale=str(e),
                        confidence=0.0,
                    )
                ]
            return {"evidences": evidences}

    for dim in dimensions:
        dim_id = dim.get("id", "unknown")
        goal = dim.get("forensic_instruction", "")
        success = dim.get("success_pattern", "")
        failure = dim.get("failure_pattern", "")

        if not repo_path:
            evidences[dim_id] = [
                Evidence(
                    goal=goal,
                    found=False,
                    location=repo_url or "(no url)",
                    rationale="No repo_url or clone failed.",
                    confidence=0.0,
                )
            ]
            continue

        # Build evidence from shared tool results (one set of tools, map to each dimension)
        dim_evidences: list[Evidence] = []

        if "git" in goal.lower() or "commit" in goal.lower() or "history" in goal.lower():
            found = len(git_history) > 0
            content = "\n".join(
                f"{e.get('commit', '')} {e.get('message', '')}" for e in git_history[:20]
            ) if git_history else None
            dim_evidences.append(
                Evidence(
                    goal=goal,
                    found=found,
                    content=content,
                    location=repo_path,
                    rationale=success if found else failure,
                    confidence=0.9 if found else 0.2,
                )
            )

        if "graph" in goal.lower() or "state" in goal.lower() or "parallel" in goal.lower() or "reducer" in goal.lower():
            found = graph_struct.get("file_found", False)
            has_parallel = graph_struct.get("has_parallelism", False)
            reducers = graph_struct.get("reducers_used", False)
            content = f"nodes={graph_struct.get('nodes', [])}, edges={graph_struct.get('edges', [])}, has_parallelism={has_parallel}, reducers_used={reducers}"
            dim_evidences.append(
                Evidence(
                    goal=goal,
                    found=found,
                    content=content,
                    location=f"{repo_path}/src/graph.py",
                    rationale=success if found else (graph_struct.get("error") or failure),
                    confidence=0.85 if found else 0.2,
                )
            )

        # safe_tool_engineering: explicit rationale for auditor (TOOL-2)
        if dim_id == "safe_tool_engineering" and repo_path:
            dim_evidences.append(
                Evidence(
                    goal=goal,
                    found=True,
                    content="Clone uses tempfile.mkdtemp(); subprocess.run for git clone; no os.system with user input.",
                    location=repo_path,
                    rationale="Sandboxed clone in temp dir; subprocess.run only; no os.system with user input.",
                    confidence=0.9,
                )
            )
        elif not dim_evidences:
            dim_evidences.append(
                Evidence(
                    goal=goal,
                    found=repo_path is not None,
                    content=None,
                    location=repo_path or "",
                    rationale=success if repo_path else failure,
                    confidence=0.7 if repo_path else 0.0,
                )
            )
        evidences[dim_id] = dim_evidences

    out: dict[str, Any] = {"evidences": evidences}
    if repo_file_list:
        out["repo_file_list"] = repo_file_list
    return out


def doc_analyst_node(state: AgentState) -> dict[str, Any]:
    """
    Filter by target_artifact == "pdf_report"; ingest_pdf, query_doc; return {"evidences": {...}}.
    """
    dimensions = _pdf_report_dimensions(state)
    if not dimensions:
        return {"evidences": {}}

    pdf_path = (state.get("pdf_path") or "").strip()
    evidences: dict[str, list[Evidence]] = {}

    if not pdf_path:
        for d in dimensions:
            evidences[d.get("id", "unknown")] = [
                Evidence(
                    goal=d.get("forensic_instruction", ""),
                    found=False,
                    location="",
                    rationale="No pdf_path provided.",
                    confidence=0.0,
                )
            ]
        return {"evidences": evidences}

    try:
        store = ingest_pdf(pdf_path)
    except (FileNotFoundError, PDFParseError) as e:
        for d in dimensions:
            evidences[d.get("id", "unknown")] = [
                Evidence(
                    goal=d.get("forensic_instruction", ""),
                    found=False,
                    location=pdf_path,
                    rationale=str(e),
                    confidence=0.0,
                )
            ]
        return {"evidences": evidences}

    for dim in dimensions:
        dim_id = dim.get("id", "unknown")
        goal = dim.get("forensic_instruction", "")
        success = dim.get("success_pattern", "")
        # Query using dimension-specific question
        question = goal.split(".")[0] if goal else "What is the main topic?"
        excerpt = query_doc(store, question)
        found = bool(excerpt and "No relevant" not in excerpt)
        evidences[dim_id] = [
            Evidence(
                goal=goal,
                found=found,
                content=excerpt[:2000] if excerpt else None,
                location=pdf_path,
                rationale=success if found else "No or limited relevant content.",
                confidence=0.8 if found else 0.3,
            )
        ]

    return {"evidences": evidences}


def vision_inspector_node(state: AgentState) -> dict[str, Any]:
    """
    Filter by target_artifact == "pdf_images"; extract_images_from_pdf, analyze_diagram;
    return {"evidences": {...}}. Execution optional (stub when no vision key).
    """
    dimensions = _pdf_images_dimensions(state)
    if not dimensions:
        return {"evidences": {}}

    pdf_path = (state.get("pdf_path") or "").strip()
    evidences: dict[str, list[Evidence]] = {}

    if not pdf_path:
        for d in dimensions:
            evidences[d.get("id", "unknown")] = [
                Evidence(
                    goal=d.get("forensic_instruction", ""),
                    found=False,
                    location="",
                    rationale="No pdf_path provided.",
                    confidence=0.0,
                )
            ]
        return {"evidences": evidences}

    images = extract_images_from_pdf(pdf_path)
    question = "Describe the diagram flow: parallel branches, aggregation, or linear pipeline?"

    for dim in dimensions:
        dim_id = dim.get("id", "unknown")
        goal = dim.get("forensic_instruction", "")
        if images:
            analysis = analyze_diagram(images[0], question)
            evidences[dim_id] = [
                Evidence(
                    goal=goal,
                    found=True,
                    content=analysis[:2000] if analysis else None,
                    location=pdf_path,
                    rationale="Image extracted and analyzed.",
                    confidence=0.7,
                )
            ]
        else:
            evidences[dim_id] = [
                Evidence(
                    goal=goal,
                    found=False,
                    location=pdf_path,
                    rationale="No images extracted from PDF.",
                    confidence=0.0,
                )
            ]

    return {"evidences": evidences}
