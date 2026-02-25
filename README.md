# Automaton Auditor

Automated quality-assurance swarm that audits GitHub repositories and PDF reports using a **Digital Courtroom** architecture: Detectives collect forensic evidence → Judges (Prosecutor, Defense, Tech Lead) deliberate per rubric criterion → Chief Justice synthesizes a verdict.

## Requirements

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** for package management

## Setup

1. **Install dependencies with uv**

   ```bash
   uv sync
   ```

2. **Environment**

   Copy the example env file and set your API keys (no real secrets in the example):

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and set at least one LLM API key (e.g. `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `GEMINI_API_KEY`) for the Judicial layer. Optionally set `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY` for LangSmith tracing.

## Run

Run a full audit (requires `OPENAI_API_KEY` for Judges):

```bash
uv run python -m src.run <repo_url> <pdf_path> [--rubric path] [--output path]
```

Example:

```bash
uv run python -m src.run https://github.com/octocat/Hello-World report.pdf --output audit/report.md
```

The report is written as Markdown (Executive Summary, Criterion Breakdown, Remediation Plan) to the given path or default `audit/report_<repo_slug>.md`.

## Project layout

- `src/state.py` — State and data types (Evidence, JudicialOpinion, AuditReport, AgentState).
- `src/tools/repo_tools.py` — Sandboxed clone, git history, AST-based graph structure analysis.
- `src/tools/doc_tools.py` — PDF ingest (chunked/RAG-lite), query_doc, image extraction, analyze_diagram (vision optional).
- `src/nodes/detectives.py` — RepoInvestigator, DocAnalyst, VisionInspector (return evidences per dimension).
- `src/nodes/judges.py` — Prosecutor, Defense, Tech Lead (structured output per dimension; OPENAI_API_KEY).
- `src/nodes/justice.py` — EvidenceAggregator, judge_collector; ChiefJusticeNode (Phase 4).
- `src/graph.py` — `build_detective_graph()`, `build_audit_graph()` (through Chief Justice), `create_initial_state`, `run_audit`.
- `src/run.py` — Entry point `run_audit(repo_url, pdf_path, rubric_path?, output_path?)` and CLI `python -m src.run`.
- `rubric.json` — Machine-readable rubric (dimensions, synthesis rules).
- `specs/` — System requirements, architecture, API contracts.

## Testing

```bash
uv run pytest tests/ -v
```
