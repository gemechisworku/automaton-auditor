# API Contracts: Automaton Auditor

**Version:** 1.0  
**Governed by:** [System Requirement Specification](./system_requirement_spec.md) (SRS), [Specs Meta](./_meta.md) (_meta), [System Architecture](./system_architecture.md)

This document defines the API contracts for the Automaton Auditor: entry point, state and data types, graph nodes, tools, rubric schema, report output, and environment. Implementations **shall** conform to these contracts so that components integrate correctly.

---

## 1. Document References

| Document | Role |
|----------|------|
| [system_requirement_spec.md](./system_requirement_spec.md) | Requirements authority. |
| [_meta.md](./_meta.md) | Technical standards and API patterns. |
| [system_architecture.md](./system_architecture.md) | Component structure and data flow. |

---

## 2. Public Entry API

### 2.1 Run Audit

The primary way to invoke the system is to compile the LangGraph and invoke it with initial state. The following contract describes the **logical** entry API (whether exposed as a function, CLI, or script).

**Inputs**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `repo_url` | `str` | Yes | GitHub repository URL to audit. Must be cloneable (HTTPS or SSH). |
| `pdf_path` | `str` | Yes | Local path to the PDF report to audit. |
| `rubric_path` | `str` | No | Path to `rubric.json`. If omitted, implementation may use a default path. |
| `output_path` | `str` | No | Directory or file path for the Markdown report. If omitted, use default (e.g. `audit/report_*`). |

**Outputs**

| Output | Type | Description |
|--------|------|-------------|
| Success | `AuditReport` (in state) + file | `state["final_report"]` is populated; report serialized to Markdown at `output_path` (or default). |
| Report file | Markdown | Single `.md` file containing Executive Summary, Criterion Breakdown, Remediation Plan (see §8). |

**Errors**

- **Clone failure** (invalid URL, auth, network): Handled per SRS A2, FR-19; may surface as exception or as error state routed via conditional edge. Caller **shall** be able to distinguish failure from success (e.g. exception or `final_report` absent).
- **Missing PDF / parse failure:** Same as above; DocAnalyst may emit evidence indicating failure.
- **Invalid rubric:** Load failure (e.g. missing file, invalid JSON) **shall** be reported (exception or early exit).

**Contract**

- Implementations **shall** accept at least `repo_url` and `pdf_path`.
- Implementations **shall** write the final report as a Markdown file (SRS FR-15); they **shall not** rely on console output as the only deliverable.

---

## 3. State and Data Type Contracts

All types live in `src/state.py`. Use Pydantic `BaseModel` for structured data and `TypedDict` for graph state (SRS FR-1–FR-5; _meta §2.2).

### 3.1 Evidence (Pydantic BaseModel)

Detective output only; no opinion fields.

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `goal` | `str` | Yes | — | The forensic goal this evidence addresses (e.g. dimension id or goal description). |
| `found` | `bool` | Yes | — | Whether the artifact or fact was found. |
| `content` | `str \| None` | No | Default `None` | Optional snippet or extracted content. |
| `location` | `str` | Yes | — | File path, commit hash, or other location identifier. |
| `rationale` | `str` | Yes | — | Rationale for confidence in this finding. |
| `confidence` | `float` | Yes | — | Confidence score (e.g. 0.0–1.0). |

### 3.2 JudicialOpinion (Pydantic BaseModel)

Judge output per criterion; **shall** be produced via `.with_structured_output(JudicialOpinion)` or `.bind_tools()` (SRS FR-10).

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `judge` | `Literal["Prosecutor", "Defense", "TechLead"]` | Yes | — | Which persona produced this opinion. |
| `criterion_id` | `str` | Yes | — | Rubric dimension id (e.g. `graph_orchestration`). |
| `score` | `int` | Yes | `1 <= score <= 5` | Score for this criterion. |
| `argument` | `str` | Yes | — | Reasoning for the score. |
| `cited_evidence` | `List[str]` | Yes | — | References to evidence (e.g. keys or summaries). |

### 3.3 CriterionResult (Pydantic BaseModel)

Per-criterion result produced by Chief Justice.

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `dimension_id` | `str` | Yes | — | Rubric dimension id. |
| `dimension_name` | `str` | Yes | — | Human-readable dimension name. |
| `final_score` | `int` | Yes | `1 <= final_score <= 5` | Resolved score after synthesis. |
| `judge_opinions` | `List[JudicialOpinion]` | Yes | — | The three opinions (Prosecutor, Defense, Tech Lead). |
| `dissent_summary` | `str \| None` | No | Required when score variance > 2 | Summary of why judges disagreed. |
| `remediation` | `str` | Yes | — | File-level or concrete improvement instructions. |

### 3.4 AuditReport (Pydantic BaseModel)

Final report; serialized to Markdown (see §8).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `repo_url` | `str` | Yes | Audited repository URL. |
| `executive_summary` | `str` | Yes | Overall verdict and aggregate summary. |
| `overall_score` | `float` | Yes | Aggregate score (e.g. mean of criterion scores). |
| `criteria` | `List[CriterionResult]` | Yes | One entry per rubric dimension. |
| `remediation_plan` | `str` | Yes | Consolidated remediation guidance. |

### 3.5 AgentState (TypedDict)

Graph state passed between nodes. Reducers apply when merging updates from parallel nodes.

| Field | Type | Reducer | Description |
|-------|------|---------|-------------|
| `repo_url` | `str` | — | Input: target repo URL. |
| `pdf_path` | `str` | — | Input: PDF report path. |
| `rubric_dimensions` | `List[Dict[str, Any]]` | — | Loaded from rubric JSON; list of dimension objects. |
| `evidences` | `Dict[str, List[Evidence]]` | `operator.ior` | Evidence keyed (e.g. by dimension_id); merged from Detectives. |
| `opinions` | `List[JudicialOpinion]` | `operator.add` | All judge opinions; appended by Judge nodes. |
| `final_report` | `AuditReport \| None` | — | Set by ChiefJusticeNode; `None` until synthesis completes. |

**Reducer semantics**

- `evidences`: Each Detective may return a partial dict (e.g. `{dimension_id: [Evidence(...)]}`); LangGraph merges via `operator.ior` so keys are combined, not overwritten.
- `opinions`: Each Judge returns a list of one or more `JudicialOpinion`; LangGraph concatenates via `operator.add`.

---

## 4. Graph Node Contract

All nodes conform to the LangGraph node signature (_meta §5.1; system_architecture §5).

**Signature**

```text
Node: (state: AgentState) -> PartialStateUpdate
```

- **Input:** Full or partial `AgentState` (LangGraph may pass the full state).
- **Output:** A dict containing only the state keys to **update** (merge into state). Keys not present are left unchanged.
- **Side effects:** Nodes may perform I/O (git, PDF, LLM); the **contract** between graph steps is the state update only.

**Examples**

- Detective node returns e.g. `{"evidences": {dimension_id: [Evidence(...)]}}`.
- Judge node returns e.g. `{"opinions": [JudicialOpinion(...)]}`.
- Chief Justice node returns e.g. `{"final_report": AuditReport(...)}`.

**Naming**

- Use clear, consistent names: `repo_investigator_node`, `doc_analyst_node`, `vision_inspector_node`, `evidence_aggregator_node`, `prosecutor_node`, `defense_node`, `tech_lead_node`, `chief_justice_node` (or equivalent).

---

## 5. Tool Contracts

Tools are callables (or LangChain tools) used by Detective nodes. They **shall not** accept or modify `AgentState`; the node is responsible for mapping tool results into `Evidence` and state (_meta §5.2).

### 5.1 Repo Tools (`src/tools/repo_tools.py`)

**Environment:** All git operations **shall** run inside a sandboxed directory (e.g. `tempfile.TemporaryDirectory()`). Use `subprocess.run()` with explicit args; capture stdout/stderr and return codes. **Shall not** use `os.system()` with unsanitized input (SRS NFR-4, NFR-5, FR-6).

| Function | Input | Output | Description |
|----------|--------|--------|-------------|
| `clone_repo(repo_url: str) -> str` | Valid GitHub URL | Path to cloned repo (inside temp dir) or raise | Clones into a temporary directory; caller is responsible for cleanup or use as context manager. On failure (auth, network, invalid URL), raise or return error result per implementation. |
| `extract_git_history(repo_path: str) -> dict \| list` | Path to git repo | Structured data (e.g. list of `{commit, message, timestamp}`) | Runs `git log --oneline --reverse` (or equivalent); returns parsed commit history. |
| `analyze_graph_structure(repo_path: str) -> dict` | Path to repo | Structured data (e.g. graph nodes, edges, reducer usage) | Uses AST (Python `ast` or tree-sitter) to detect StateGraph, add_edge, parallelism, reducers; **shall not** rely only on regex (SRS FR-7). |

**Error handling:** Clone failures (e.g. invalid URL, auth) **shall** be handled gracefully (raise or return structured error); callers may route via conditional edges (SRS A2).

### 5.2 Doc Tools (`src/tools/doc_tools.py`)

The PDF tool exposes a **RAG-like interface**: ingestion returns **chunked, queryable segments** (e.g. page-bound or character-bound) and a **query function**; it does **not** dump full document text. Missing file and parse failures are handled with clear exceptions.

| Function | Input | Output | Description |
|----------|--------|--------|-------------|
| `ingest_pdf(pdf_path: str, chunk_by: "char" \| "page" = "char") -> PDFIngestionResult` | Path to PDF, optional chunk mode | `PDFIngestionResult` (segments + `.query(question)`) | Chunked, queryable segments (page or char); **not** full-text dump (SRS FR-8). Raises `FileNotFoundError` if missing; `PDFParseError` on corrupt/parse failure. |
| `query_doc(store: DocStore \| PDFIngestionResult, question: str) -> str` | Store from `ingest_pdf`, question | Answer text | RAG retrieval over segments; returns relevant excerpts. |
| `extract_images_from_pdf(pdf_path: str) -> List[Any]` | Path to PDF | List of images (e.g. PIL Image or bytes) | Extracts images for VisionInspector (SRS FR-9). |
| `analyze_diagram(image: Any, question: str) -> str` | Image, question | Answer text | Uses vision-capable LLM (e.g. GPT-4o); optional at runtime. |

### 5.3 Cross-Reference (DocAnalyst)

DocAnalyst **shall** be able to cross-reference report claims (e.g. file paths) with RepoInvestigator evidence. This may be implemented as a tool (e.g. `cross_reference(claimed_paths: List[str], repo_evidence: Dict) -> Dict`) or inside the node using `evidences` from state; the contract is that report accuracy dimensions receive both PDF-derived and repo-derived data to produce Verified vs Hallucinated paths.

---

## 6. Rubric JSON Schema (Contract)

The system loads a single rubric file (e.g. `rubric.json`) at runtime. The following structure is the **minimum** required; implementations may support additional fields (SRS FR-12, A1; _meta §5.4).

### 6.1 Top-Level Keys

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `rubric_metadata` | `object` | Yes | e.g. `rubric_name`, `grading_target`, `version`. |
| `dimensions` | `array` | Yes | List of dimension objects (see below). |
| `synthesis_rules` | `object` | Yes | Keys: `security_override`, `fact_supremacy`, `functionality_weight`, `dissent_requirement`, `variance_re_evaluation` (string values). |

### 6.2 Dimension Object

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `id` | `string` | Yes | Unique dimension id (e.g. `graph_orchestration`). |
| `name` | `string` | Yes | Human-readable name. |
| `target_artifact` | `string` | Yes | One of: `github_repo`, `pdf_report`, `pdf_images`. Used to route to Detectives (FR-20). |
| `forensic_instruction` | `string` | Yes | Instruction for the Detective that handles this artifact. |
| `success_pattern` | `string` | Yes | Description of success for this dimension. |
| `failure_pattern` | `string` | Yes | Description of failure. |
| (optional) | — | — | Implementations may add e.g. `judicial_logic` or persona-specific text for Judges. |

### 6.3 Synthesis Rules Object

| Key | Type | Description |
|-----|------|-------------|
| `security_override` | `string` | Rule text: security flaw caps score; overrides Defense. |
| `fact_supremacy` | `string` | Rule text: Detective evidence overrides unsupported Judge claims. |
| `functionality_weight` | `string` | Rule text: Tech Lead’s “modular and workable” weight for architecture. |
| `dissent_requirement` | `string` | Rule text: dissent summary required when variance > 2. |
| `variance_re_evaluation` | `string` | Rule text: re-evaluate when variance > 2. |

---

## 7. Judge LLM Contract

- **Binding:** Every Judge LLM call **shall** use `.with_structured_output(JudicialOpinion)` or `.bind_tools()` bound to the **same** Pydantic `JudicialOpinion` model (SRS FR-10; _meta §5.3).
- **Validation:** Output **shall** be parsed and validated against `JudicialOpinion`. On parse/validation failure: retry or error path; **shall not** append invalid or freeform-only output to `opinions`.
- **Fields:** Response **must** include `judge`, `criterion_id`, `score` (1–5), `argument`, `cited_evidence` (list of strings).

---

## 8. Report Output Contract

### 8.1 Deliverable

- The final deliverable **shall** be a **Markdown file** (not only console output) (SRS FR-15).
- Content **shall** be the serialization of the `AuditReport` Pydantic model into Markdown.

### 8.2 Markdown Structure (Minimum)

1. **Executive Summary**  
   - Overall verdict and aggregate score.  
   - Corresponds to `AuditReport.executive_summary` and `AuditReport.overall_score`.

2. **Criterion Breakdown**  
   - One section per rubric dimension (per `AuditReport.criteria`).  
   - Each section **shall** include: dimension name, final score, the three judge opinions (Prosecutor, Defense, Tech Lead) with score and argument, and **if** score variance > 2, a dissent summary.  
   - Each section **shall** include remediation (file-level or concrete instructions).

3. **Remediation Plan**  
   - Consolidated remediation guidance.  
   - Corresponds to `AuditReport.remediation_plan`.

### 8.3 File Placement

- Reports **may** be written to configured paths (e.g. `audit/report_onself_generated/`, `audit/report_onpeer_generated/`, `audit/report_bypeer_received/`) as per SRS §7.3.  
- The entry API **may** accept an `output_path` (file or directory); if directory, implementation defines the filename (e.g. timestamp or repo slug).

---

## 9. Environment Variables Contract

All secrets and environment-specific configuration **shall** be supplied via environment variables. The project **shall** provide an `.env.example` listing every required variable with no actual secrets (SRS NFR-2; _meta §4.1).

### 9.1 Minimum Required (Example)

| Variable | Purpose | Example (no real secrets) |
|----------|---------|---------------------------|
| `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` or provider-specific | LLM calls for Judges (and optional Vision) | `sk-...` |
| `LANGCHAIN_TRACING_V2` | Enable LangSmith tracing | `true` |
| `LANGCHAIN_API_KEY` | LangSmith (if used) | (optional) |
| (Vision) | Vision model API key if using Gemini/GPT-4o | Per provider |

Implementations **shall** document in `.env.example` all variables they read; naming may follow provider conventions (e.g. `GEMINI_API_KEY`).

### 9.2 Contract

- Application code **shall not** hardcode API keys or secrets.  
- Missing required variables **shall** result in a clear error at startup or at first use (e.g. before invoking the graph).

---

## 10. Traceability

| Contract | SRS | _meta | Architecture |
|----------|-----|--------|----------------|
| Entry API (repo_url, pdf_path, report file) | §2.2, FR-15 | §5.5 | §2 |
| Evidence, JudicialOpinion, AuditReport, AgentState | FR-1–FR-5, §7.1 | §2.2, §5.6 | §4 |
| Node signature (state → partial update) | — | §5.1 | §5, §6 |
| Repo tools (sandbox, AST, no os.system) | FR-6, FR-7, NFR-4, NFR-5 | §5.2 | §7.2 |
| Doc tools (chunked, RAG-lite, vision) | FR-8, FR-9 | §5.2 | §7.2 |
| Rubric schema and targeting | FR-12, FR-20–FR-21, A1 | §2.5, §5.4 | §10 |
| Judge structured output | FR-10 | §5.3 | §8.2 |
| Report Markdown structure | FR-15, §7.3 | §5.5 | §9.3 |
| Environment variables | NFR-2 | §2.3, §4.1 | §12 |

---

*End of API Contracts*
