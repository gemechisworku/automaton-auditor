# Automaton Auditor

Automated quality-assurance swarm that audits GitHub repositories and PDF reports using a **Digital Courtroom** architecture: Detectives collect forensic evidence → Judges (Prosecutor, Defense, Tech Lead) deliberate per rubric criterion → Chief Justice synthesizes a verdict.

## Requirements

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** for package management

## Setup

**Prerequisites:** Python 3.11+ and [uv](https://docs.astral.sh/uv/). For reproducible installs, `uv sync` uses the project's **`uv.lock`** (pinned dependency versions).

1. **Install dependencies**

   ```bash
   uv sync
   ```

2. **Environment**

   Copy the example env file and set your API key (required for Judge nodes):

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and set **`OPENAI_API_KEY`** (required). The app loads `.env` automatically when you run the CLI.

## Run

From the project root (so `.env` is found):

```bash
uv run python -m src.run <repo_url> <pdf_path> [--rubric path] [--output path]
```

Example:

```bash
uv run python -m src.run https://github.com/octocat/Hello-World report.pdf --output audit/report.md
```

- **Where the report is written:** To the path given by `--output`, or by default **`audit/report_<repo_slug>.md`** (e.g. `audit/report_Hello-World.md`). The file is Markdown: Executive Summary, Criterion Breakdown, Remediation Plan.
- **Errors:** Missing `OPENAI_API_KEY`, empty `repo_url`/`pdf_path`, or invalid rubric produce a clear error message and exit code 1.

## Observability (LangSmith)

To trace the full flow (Detectives → Judges → Chief Justice) in [LangSmith](https://smith.langchain.com/):

1. Set in `.env`: `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY=<your-key>`.
2. Run the audit as above; open LangSmith to see the trace.

## Docker (optional)

Build and run with Docker:

```bash
docker build -t automaton-auditor .
docker run --env-file .env -v "%cd%\audit:/app/audit" -v "%cd%\report.pdf:/app/report.pdf" automaton-auditor https://github.com/org/repo /app/report.pdf --output /app/audit/report.md
```

On Linux/macOS use `$(pwd)` instead of `%cd%`. Ensure `.env` contains `OPENAI_API_KEY` and any PDF is mounted where `pdf_path` points.

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
