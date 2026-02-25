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

*To be filled in later phases.* The entry API will accept a repository URL and PDF path and produce a Markdown audit report (e.g. `uv run python -m src.run <repo_url> <pdf_path>`).

## Project layout

- `src/state.py` — State and data types (Evidence, JudicialOpinion, AuditReport, AgentState).
- `src/tools/` — Repo, doc, and vision tools (Phase 1).
- `src/nodes/` — Detective, Judge, and Chief Justice nodes (Phases 2–4).
- `src/graph.py` — LangGraph definition (Phases 2–4).
- `rubric.json` — Machine-readable rubric (dimensions, synthesis rules).
- `specs/` — System requirements, architecture, API contracts.

## Testing

```bash
uv run pytest tests/ -v
```

See `docs/implementation_plan.md` for phase-by-phase test guide.
