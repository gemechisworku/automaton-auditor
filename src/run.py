"""
Entry point: run_audit(repo_url, pdf_path, rubric_path?, output_path?).
Loads rubric, builds state, compiles graph, invokes, writes Markdown report.
API Contracts §2.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.graph import build_audit_graph, create_initial_state
from src.nodes.justice import write_report_to_path
from src.state import AuditReport


def _default_output_path(repo_url: str) -> str:
    """Default report path: audit/report_<repo_slug>.md"""
    slug = re.sub(r"[^\w\-]", "_", Path(repo_url.rstrip("/")).name or "repo")[:50]
    return f"audit/report_{slug}.md"


def run_audit(
    repo_url: str,
    pdf_path: str,
    rubric_path: str | None = None,
    output_path: str | None = None,
) -> AuditReport | None:
    """
    Run the full audit graph and write the report to a Markdown file.

    Args:
        repo_url: GitHub (or other) repository URL to audit.
        pdf_path: Local path to the PDF report.
        rubric_path: Path to rubric.json. Defaults to rubric.json.
        output_path: Where to write the Markdown report. Defaults to audit/report_<repo_slug>.md.

    Returns:
        The AuditReport from state, or None if the graph did not produce one (e.g. failure).
    """
    state = create_initial_state(
        repo_url=repo_url,
        pdf_path=pdf_path,
        rubric_path=rubric_path,
    )
    graph = build_audit_graph().compile()
    final = graph.invoke(state)
    report = final.get("final_report")
    if report is None:
        return None
    if not isinstance(report, AuditReport):
        report = AuditReport(**report)
    out = output_path or _default_output_path(repo_url)
    write_report_to_path(report, out)
    return report


def main() -> None:
    """CLI entry: python -m src.run repo_url pdf_path [--rubric path] [--output path]"""
    import argparse
    parser = argparse.ArgumentParser(description="Run Automaton Auditor")
    parser.add_argument("repo_url", help="Repository URL to audit")
    parser.add_argument("pdf_path", help="Path to PDF report")
    parser.add_argument("--rubric", dest="rubric_path", default=None, help="Path to rubric.json")
    parser.add_argument("--output", dest="output_path", default=None, help="Output Markdown path")
    args = parser.parse_args()
    report = run_audit(
        repo_url=args.repo_url,
        pdf_path=args.pdf_path,
        rubric_path=args.rubric_path,
        output_path=args.output_path,
    )
    if report is None:
        raise SystemExit("Audit did not produce a report (check logs or inputs).")
    print(f"Report written to {args.output_path or _default_output_path(args.repo_url)}")


if __name__ == "__main__":
    main()
