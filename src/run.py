"""
Entry point: run_audit(repo_url, pdf_path?, rubric_path?, output_path?).
Loads .env so OPENAI_API_KEY is available for Judge nodes; validates inputs and env;
loads rubric, builds state, compiles graph, invokes, writes Markdown report. API Contracts §2.
PDF path is optional: omit for repo-only audit (Doc/Vision evidence will report no PDF).
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env so OPENAI_API_KEY and other vars are available (e.g. for Judges)
load_dotenv()

from src.graph import build_audit_graph, create_initial_state, load_rubric_dimensions
from src.nodes.justice import write_report_to_path
from src.state import AuditReport


def _default_output_path(repo_url: str) -> str:
    """Default report path: audit/report_<repo_slug>.md"""
    slug = re.sub(r"[^\w\-]", "_", Path(repo_url.rstrip("/")).name or "repo")[:50]
    return f"audit/report_{slug}.md"


def _require_llm_key() -> None:
    """Raise clear error if OPENAI_API_KEY is not set (required for Judge nodes)."""
    if os.environ.get("OPENAI_API_KEY", "").strip():
        return
    raise RuntimeError(
        "OPENAI_API_KEY is not set. Copy .env.example to .env and set OPENAI_API_KEY. Required for Judge nodes."
    )


def run_audit(
    repo_url: str,
    pdf_path: str | None = None,
    rubric_path: str | None = None,
    output_path: str | None = None,
) -> AuditReport | None:
    """
    Run the full audit graph and write the report to a Markdown file.

    Args:
        repo_url: GitHub (or other) repository URL to audit.
        pdf_path: Optional local path to a PDF report. Omit for repo-only audit.
        rubric_path: Path to rubric.json. Defaults to rubric.json.
        output_path: Where to write the Markdown report. Defaults to audit/report_<repo_slug>.md.

    Returns:
        The AuditReport from state, or None if the graph did not produce one (e.g. failure).

    Raises:
        ValueError: If repo_url is invalid.
        RuntimeError: If required env (e.g. OPENAI_API_KEY) is missing.
    """
    repo_url = (repo_url or "").strip()
    if not repo_url:
        raise ValueError("repo_url is required and must be non-empty.")
    pdf_path = (pdf_path or "").strip() or None
    _require_llm_key()
    dimensions = load_rubric_dimensions(rubric_path)
    if not dimensions:
        raise ValueError(
            f"Rubric has no dimensions. Check rubric_path (e.g. {rubric_path or 'rubric.json'}) exists and contains 'dimensions'."
        )
    state = create_initial_state(
        repo_url=repo_url,
        pdf_path=pdf_path or "",
        rubric_path=rubric_path,
    )
    graph = build_audit_graph().compile()
    try:
        final = graph.invoke(state)
    except Exception as e:
        raise RuntimeError(f"Audit graph failed: {e}") from e
    report = final.get("final_report")
    if report is None:
        return None
    if not isinstance(report, AuditReport):
        report = AuditReport(**report)
    out = output_path or _default_output_path(repo_url)
    write_report_to_path(report, out)
    return report


def main() -> None:
    """CLI entry: python -m src.run repo_url [pdf_path] [--rubric path] [--output path]"""
    import argparse
    parser = argparse.ArgumentParser(
        description="Run Automaton Auditor: audit a GitHub repo (and optionally a PDF report)."
    )
    parser.add_argument("repo_url", help="Repository URL to audit (e.g. https://github.com/org/repo)")
    parser.add_argument(
        "pdf_path",
        nargs="?",
        default=None,
        help="Optional path to a PDF report. Omit for repo-only audit.",
    )
    parser.add_argument("--rubric", dest="rubric_path", default=None, help="Path to rubric.json (default: rubric.json)")
    parser.add_argument("--output", dest="output_path", default=None, help="Output Markdown path (default: audit/report_<slug>.md)")
    args = parser.parse_args()
    try:
        report = run_audit(
            repo_url=args.repo_url,
            pdf_path=args.pdf_path,
            rubric_path=args.rubric_path,
            output_path=args.output_path,
        )
    except (ValueError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        raise SystemExit(1)
    if report is None:
        print("Error: Audit did not produce a report (check logs or inputs).", file=sys.stderr)
        raise SystemExit(1)
    out = args.output_path or _default_output_path(args.repo_url)
    print(f"Report written to {out}")


if __name__ == "__main__":
    main()
