# Specs Meta: Technical Standards & Conventions

**Purpose:** Establishes technical standards, architectural style, tech stack, and API design patterns for the Automaton Auditor. All choices align with [System Requirement Specification](./system_requirement_spec.md) (SRS).

---

## 1. Relationship to SRS

- This document is **subordinate** to the SRS. Where the SRS says "shall," implementation **must** comply.
- This meta adds **how** to implement: preferred technologies, patterns, and conventions. It does not introduce new functional or non-functional requirements.

---

## 2. Technical Standards

### 2.1 Language and Runtime

- **Language:** Python 3.11+ (type hints throughout; no `# type: ignore` without justification).
- **Package manager:** [uv](https://docs.astral.sh/uv/) for install, lock, and run. All dependencies declared in `pyproject.toml` with locked versions (e.g. `uv.lock`).
- **Imports:** Prefer standard library and SRS-mandated libraries; avoid ad-hoc scripts or untracked dependencies.

### 2.2 Typing and Data Contracts

- **State and outputs:** All graph state and LLM-structured outputs use **Pydantic** models and **TypedDict** as specified in SRS §4.1 (FR-1–FR-5). No plain `dict` for `AgentState`, `Evidence`, `JudicialOpinion`, or `AuditReport`.
- **Reducers:** Use `typing.Annotated` with `operator.add` (lists) and `operator.ior` (dicts) for state fields updated by parallel nodes to prevent overwrites (SRS FR-5).
- **Validation:** Judge outputs **must** be validated against the `JudicialOpinion` schema; parse failures trigger retry or error handling (SRS FR-10).

### 2.3 Security and Isolation

- **Secrets:** No hardcoded API keys or credentials. Use environment variables; document all required vars in `.env.example` (SRS NFR-2).
- **Git and shell:** Run git and any shell operations in a **sandboxed** directory (e.g. `tempfile.TemporaryDirectory()`). Use `subprocess.run()` with explicit args, capture stdout/stderr, and check return codes. **Do not** use `os.system()` with unsanitized inputs (SRS NFR-4, NFR-5, FR-6).
- **Inputs:** Validate or sanitize repository URL and PDF path before use; handle missing files and auth failures gracefully.

### 2.4 Observability

- **Tracing:** Support LangSmith via `LANGCHAIN_TRACING_V2=true` (and related env vars). Use so that multi-agent runs can be inspected end-to-end (SRS NFR-3).
- **Logging:** Use structured logging (e.g. `logging` with consistent levels); avoid print-only debugging for production paths.

### 2.5 Code Quality

- **Parsing:** Prefer **AST** (Python `ast` or tree-sitter) over regex for code-structure checks (SRS FR-7, forensic protocols).
- **Config over code:** Rubric-driven behavior: load `rubric.json` (or equivalent) and distribute instructions by `target_artifact`; avoid hardcoding rubric text in node logic (SRS FR-12, A1).

---

## 3. Architectural Style

### 3.1 High-Level Pattern

- **Pattern:** Hierarchical multi-agent **State Graph** (LangGraph), styled as a **Digital Courtroom** (SRS §2, §3).
- **Layers:**
  1. **Detective layer** — Forensic sub-agents (RepoInvestigator, DocAnalyst, VisionInspector); facts only; structured `Evidence` output.
  2. **Judicial layer** — Three personas (Prosecutor, Defense, Tech Lead) in parallel per rubric criterion; structured `JudicialOpinion` output.
  3. **Supreme Court** — ChiefJusticeNode: deterministic synthesis rules; produces `AuditReport` serialized to Markdown.

### 3.2 Concurrency and Data Flow

- **Fan-out:** Detectives run in **parallel** from a single entry point; Judges run in **parallel** per criterion after evidence aggregation (SRS FR-16, FR-18).
- **Fan-in:** A single **EvidenceAggregator** (or equivalent) node collects all Detective evidence before any Judge runs; all Judge opinions feed into ChiefJustice (SRS FR-17, FR-18).
- **State:** All shared data flows through the typed `AgentState`; parallel nodes use reducers so concurrent writes merge correctly (SRS FR-5).

### 3.3 Dialectical Model

- **Thesis–Antithesis–Synthesis:** Three distinct judge personas with conflicting prompts; Chief Justice applies **hardcoded** rules (security, evidence, functionality, dissent, variance) to resolve conflicts—not a simple average (SRS §3.4, FR-13, FR-14).

### 3.4 Error and Control Flow

- Use **conditional edges** for error/edge cases (e.g. evidence missing, node failure) where the SRS or rubric requires it (SRS FR-19).
- Synthesis rules (e.g. variance > 2 → re-evaluation, dissent required) are implemented in deterministic Python in `ChiefJusticeNode` (SRS FR-13, FR-14).

---

## 4. Tech Stack

### 4.1 Core (Required)

| Concern | Technology | SRS Reference |
|--------|------------|----------------|
| Orchestration | **LangGraph** (StateGraph, nodes, add_edge, add_conditional_edges, parallel branches) | §3.1, A3, §7.1 |
| LLM integration | **LangChain** (chat models, `.with_structured_output()` / `.bind_tools()`) | FR-10, §7.1 |
| State & schemas | **Pydantic** (BaseModel), **TypedDict**, `typing.Annotated` + `operator` reducers | FR-1–FR-5, §7.1 |
| Package management | **uv** (pyproject.toml, lockfile) | NFR-1, §7.2 |
| Config | **JSON** rubric (e.g. `rubric.json`) loaded at runtime | FR-12, A1, §7.2 |
| Env & secrets | **Environment variables** + `.env.example` | NFR-2, §7.2 |
| Repo / shell | **subprocess**, **tempfile** (sandboxed clone) | NFR-4, NFR-5, FR-6 |
| Code analysis | **Python `ast`** (or **tree-sitter**) for graph/structure checks | FR-7, §3.2.1 |
| Tracing | **LangSmith** (LANGCHAIN_TRACING_V2) | NFR-3 |

### 4.2 Document and Vision (Required Implementation)

| Concern | Technology | Notes |
|--------|------------|--------|
| PDF parsing | **Docling** or equivalent | Chunked ingestion; RAG-lite querying (FR-8). |
| PDF images | Extract images from PDF; pass to vision model | For VisionInspector (FR-9). |
| Vision model | **Gemini Pro Vision** or **GPT-4o** (or equivalent) | Image analysis for diagram flow (SRS §3.2.3). Vision execution at runtime may be optional; implementation is required. |

### 4.3 Optional

- **Docker:** Dockerfile for containerized run (SRS §7.2).
- **Testing:** pytest (or similar) for unit/integration tests; not mandated by SRS but recommended for maintainability.

---

## 5. API and Design Patterns

### 5.1 Graph Node Signature

- **Pattern:** Nodes are functions that accept **(state: AgentState)** (or the relevant state slice) and return a **partial state update** (dict of fields to merge).
- **Naming:** Clear node names (e.g. `repo_investigator_node`, `evidence_aggregator_node`, `prosecutor_node`, `chief_justice_node`).
- **Side effects:** I/O (git, PDF, LLM calls) inside nodes or tools; state updates are the only contract between graph steps.

### 5.2 Tools

- **Pattern:** Tools are callables (or LangChain tools) used by Detective nodes. They do not modify graph state directly; the node reads tool results and writes `Evidence` into state.
- **Repo tools:** e.g. `clone_repo(url) -> path`, `extract_git_history(path) -> structured data`, `analyze_graph_structure(path) -> structured data`. All run in sandboxed dirs; use subprocess + error handling.
- **Doc tools:** e.g. `ingest_pdf(path) -> queryable store`, `query_doc(store, question) -> text`. Chunked; no full-doc dump into context.
- **Vision tools:** e.g. `extract_images_from_pdf(path) -> list[images]`, `analyze_diagram(image, question) -> text`. Used by VisionInspector only.

### 5.3 Structured Output (Judges)

- **Pattern:** Each Judge LLM call uses `.with_structured_output(JudicialOpinion)` or `.bind_tools()` bound to the same Pydantic model. Output is parsed and validated; on failure, retry or error path (SRS FR-10).
- **No freeform-only:** Judges must not return only unstructured text; the schema (score, argument, cited_evidence) is mandatory.

### 5.4 Rubric and Targeting

- **Context builder:** Iterate over `rubric.dimensions`; for each dimension, select instructions by `target_artifact` (e.g. `github_repo`, `pdf_report`, `pdf_images`).
- **Dispatcher:** Send `forensic_instruction` to the Detective whose capability matches `target_artifact`; send `judicial_logic` (and rubric dimension) to Judges. Chief Justice receives `synthesis_rules` (SRS §6.3, rubric JSON).
- **Schema:** Rubric JSON includes at least: `rubric_metadata`, `dimensions[]` (id, name, target_artifact, forensic_instruction, success_pattern, failure_pattern, judicial logic as needed), `synthesis_rules` (e.g. security_override, fact_supremacy, functionality_weight, dissent_requirement, variance_re_evaluation).

### 5.5 Report API

- **Output:** Final deliverable is a **Markdown file**, not only console output (SRS FR-15).
- **Structure:** Serialization of the `AuditReport` Pydantic model: **Executive Summary** → **Criterion Breakdown** (per dimension: score, judge opinions, dissent if variance > 2, remediation) → **Remediation Plan** (SRS §3.4, §7.3).
- **File placement:** Use configured or standard paths (e.g. `audit/report_*`) as per SRS §7.3.

### 5.6 Naming and File Layout

- Align with SRS §7.1:
  - `src/state.py` — All Pydantic/TypedDict state and report models.
  - `src/tools/repo_tools.py` — Repo/git/AST tools.
  - `src/tools/doc_tools.py` — PDF/query tools.
  - `src/nodes/detectives.py` — Detective nodes.
  - `src/nodes/judges.py` — Judge nodes.
  - `src/nodes/justice.py` — ChiefJusticeNode.
  - `src/graph.py` — StateGraph construction (edges, parallel branches, conditional edges).

---

## 6. Summary Checklist

- [ ] Python 3.11+, uv, pyproject.toml + lockfile  
- [ ] Pydantic/TypedDict state; reducers for parallel-written fields  
- [ ] LangGraph: fan-out Detectives → EvidenceAggregator → fan-out Judges → ChiefJustice  
- [ ] Sandboxed git (tempfile + subprocess); no os.system with unsanitized input  
- [ ] Judges: .with_structured_output(JudicialOpinion) or .bind_tools(); retry on parse failure  
- [ ] ChiefJustice: hardcoded synthesis rules; Markdown report from AuditReport  
- [ ] Rubric loaded from JSON; targeting by target_artifact  
- [ ] .env.example; LangSmith support; AST (or equivalent) for code analysis  
- [ ] Docling (or equivalent) + vision model for PDF/images; VisionInspector implemented (execution optional)

---

*This meta is the single place for project-wide technical standards and patterns. Keep it updated when the SRS or implementation choices change.*
