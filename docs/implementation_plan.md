# Implementation Plan: Automaton Auditor

**Version:** 1.0  
**References:** [System Requirement Specification](../specs/system_requirement_spec.md), [System Architecture](../specs/system_architecture.md), [API Contracts](../specs/api_contracts.md), [Specs Meta](../specs/_meta.md)

This plan organizes implementation into **phases that can be tested independently**. Each phase delivers a verifiable increment; later phases build on prior ones without blocking on unfinished work (e.g. via mocks or reduced scope).

---

## Overview

| Phase | Name | Goal | Testable outcome |
|-------|------|------|------------------|
| **0** | Foundation & environment | Typed state, project layout, config, rubric | Imports, rubric load, env check |
| **1** | Tool engineering | Repo, doc, and vision tools (sandboxed, AST, RAG-lite) | Unit tests per tool |
| **2** | Detective graph | Detective nodes + fan-out/fan-in graph (no judges) | Graph run → `evidences` populated |
| **3** | Judicial layer | Judge nodes + structured output, wired after evidence | Graph run → `opinions` populated |
| **4** | Supreme Court & report | Chief Justice, synthesis rules, Markdown report | Full run → report file and `final_report` |
| **5** | Hardening & entry API | Conditional edges, CLI/entry, optional Docker | End-to-end and error-path tests |

---

## Phase 0: Foundation & Environment

**Objective:** Establish the project layout, typed state, configuration, and rubric so that all later code can depend on a single source of truth. No graph or LLM yet.

### 0.1 Deliverables

- [ ] **`pyproject.toml`** — Python 3.11+, uv-managed; dependencies: pydantic, langgraph, langchain, typing_extensions; dev: pytest (optional). Lock with `uv lock`.
- [ ] **`.env.example`** — Placeholder entries for: LLM API key(s), `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY` (optional). No real secrets.
- [ ] **`src/state.py`** — All Pydantic and state types per [API Contracts §3](../specs/api_contracts.md#3-state-and-data-type-contracts):
  - `Evidence`, `JudicialOpinion`, `CriterionResult`, `AuditReport` (BaseModel).
  - `AgentState` (TypedDict) with `evidences` and `opinions` using `Annotated[..., operator.ior]` and `Annotated[..., operator.add]`.
- [ ] **`rubric.json`** — Minimal or full rubric per [API Contracts §6](../specs/api_contracts.md#6-rubric-json-schema-contract): `rubric_metadata`, `dimensions[]` (id, name, target_artifact, forensic_instruction, success_pattern, failure_pattern), `synthesis_rules`.
- [ ] **`README.md`** — Setup: install (uv), copy `.env.example` to `.env`, run instructions (to be filled in later phases).

### 0.2 How to Test (Independently)

1. **Imports:** `from src.state import Evidence, JudicialOpinion, AuditReport, AgentState` — no errors.
2. **Rubric load:** Load `rubric.json` with `json.load()`; assert `dimensions` and `synthesis_rules` exist; assert at least one dimension has `target_artifact` in `["github_repo","pdf_report","pdf_images"]`.
3. **Env:** Script or test that reads required env vars (e.g. from `.env.example`) and fails clearly if missing (no secret values needed for this check).
4. **Reducers:** Instantiate `AgentState` with empty `evidences`/`opinions`; merge two partial updates (e.g. two dicts for evidences, two lists for opinions) and assert merge behavior matches `operator.ior` / `operator.add`.

### 0.3 Exit Criteria

- All state types and rubric schema match the API contracts.
- Project installs with `uv sync` and passes Phase 0 tests above.

---

## Phase 1: Tool Engineering

**Objective:** Implement forensic tools used by the Detective layer. Each tool is stateless and testable without the graph or LLMs (except vision, which can be mocked).

### 1.1 Deliverables

- [ ] **`src/tools/repo_tools.py`**
  - `clone_repo(repo_url: str) -> str` — Clone into `tempfile.TemporaryDirectory()`; return repo path; use `subprocess.run()` for git; handle auth/network errors; **no** `os.system()` with unsanitized input.
  - `extract_git_history(repo_path: str)` — Run `git log --oneline --reverse`; return structured list (e.g. commit, message, timestamp).
  - `analyze_graph_structure(repo_path: str)` — Use Python `ast` (or tree-sitter) to detect StateGraph, add_edge, parallelism, reducers in `src/graph.py` (or equivalent); return structured dict; **no** regex-only for structure.
- [ ] **`src/tools/doc_tools.py`**
  - `ingest_pdf(pdf_path: str)` — Chunk PDF (e.g. Docling); return queryable store (RAG-lite); do not dump full text into a single string.
  - `query_doc(store, question: str) -> str` — Query store; return answer or excerpt.
  - `extract_images_from_pdf(pdf_path: str) -> List` — Extract images for diagrams.
  - `analyze_diagram(image, question: str) -> str` — Call vision-capable LLM (optional at runtime); can be stub/mock for Phase 1 tests.
- [ ] **Tests** — Unit tests for each tool (see §1.2).

### 1.2 How to Test (Independently)

1. **clone_repo:** Use a small public repo URL; assert return path exists, contains `.git`, and is under a temp directory (not cwd). Assert invalid URL or auth failure raises or returns error (no silent success).
2. **extract_git_history:** On a cloned repo (or fixture), assert return is list-like; entries have message/timestamp-like fields.
3. **analyze_graph_structure:** Run on a fixture repo that contains a minimal `src/graph.py` with StateGraph/add_edge; assert result reflects structure (e.g. nodes, parallel branches); run on repo with no graph and assert safe behavior.
4. **ingest_pdf + query_doc:** Use a small fixture PDF; ingest; query e.g. "What is the main topic?"; assert non-empty string and that full raw text was not passed as single blob (chunked).
5. **extract_images_from_pdf:** Fixture PDF with at least one image; assert list length ≥ 1 and elements are image-like.
6. **analyze_diagram:** Mock vision LLM or skip if optional; or call with real API and assert string return.

### 1.3 Exit Criteria

- All tools match [API Contracts §5](../specs/api_contracts.md#5-tool-contracts).
- Repo tools use sandbox + subprocess only; no `os.system()` with unsanitized input.
- Phase 1 unit tests pass without running the graph or Judge nodes.

---

## Phase 2: Detective Graph

**Objective:** Implement Detective nodes and a StateGraph that runs RepoInvestigator, DocAnalyst, and VisionInspector in parallel, then EvidenceAggregator (fan-in). No Judicial layer yet; graph ends after aggregation.

### 2.1 Deliverables

- [ ] **`src/nodes/detectives.py`**
  - `repo_investigator_node(state: AgentState) -> dict` — Filter dimensions by `target_artifact == "github_repo"`; call clone_repo, extract_git_history, analyze_graph_structure; build `Evidence` list per dimension; return `{"evidences": {dimension_id: [Evidence, ...]}}`.
  - `doc_analyst_node(state: AgentState) -> dict` — Filter by `target_artifact == "pdf_report"`; ingest_pdf, query_doc (and cross-reference if needed); return `{"evidences": {...}}`.
  - `vision_inspector_node(state: AgentState) -> dict` — Filter by `target_artifact == "pdf_images"`; extract_images_from_pdf, analyze_diagram; return `{"evidences": {...}}`. Execution may be optional (stub or skip if no vision key).
- [ ] **`src/nodes/justice.py`** (partial)
  - `evidence_aggregator_node(state: AgentState) -> dict` — No-op merge or validation of `state["evidences"]`; can return `{}` if reducers already merged everything.
- [ ] **`src/graph.py`** (partial)
  - Build StateGraph with: START → parallel(RepoInvestigator, DocAnalyst, VisionInspector) → EvidenceAggregator → END.
  - Initial state: `repo_url`, `pdf_path`, `rubric_dimensions` (from rubric.json), empty `evidences`/`opinions`, no `final_report`.
  - Use LangGraph’s parallel node invocation and reducer semantics for `evidences`.

### 2.2 How to Test (Independently)

1. **Single Detective:** Run only `repo_investigator_node` with mock state (repo_url, rubric_dimensions with one github_repo dimension); assert return has `evidences` with at least one key and list of `Evidence` objects.
2. **Full Detective graph:** Invoke compiled graph with real repo URL and PDF path (and rubric_path). Run to completion (END). Assert:
   - `state["evidences"]` is non-empty and keyed by dimension id (or equivalent).
   - Each value is list of `Evidence` (Pydantic); no crash from reducer merge.
3. **Optional:** Conditional edge from START on invalid URL → error node or placeholder evidence; assert behavior per design.

### 2.3 Exit Criteria

- Detective nodes and EvidenceAggregator match [API Contracts §4](../specs/api_contracts.md#4-graph-node-contract) (state in → partial state out).
- Graph runs from START to END with `evidences` populated; no Judges or Chief Justice required.

---

## Phase 3: Judicial Layer

**Objective:** Add Prosecutor, Defense, and Tech Lead nodes that consume aggregated evidence and produce `JudicialOpinion` per rubric dimension. Wire them into the graph after EvidenceAggregator (parallel per criterion). No synthesis or report yet.

### 3.1 Deliverables

- [ ] **`src/nodes/judges.py`**
  - Per-persona logic (or one dispatcher): given `(state, dimension_id)` (or dimension object), build prompt with dimension’s forensic result and rubric text; call LLM with `.with_structured_output(JudicialOpinion)` (or `.bind_tools()` to same schema).
  - **Prosecutor**, **Defense**, **Tech Lead** — Distinct system prompts (adversarial, forgiving, pragmatic); same `JudicialOpinion` schema; retry or error on parse failure.
  - Nodes return `{"opinions": [JudicialOpinion, ...]}` (one per judge per dimension, or batched).
- [ ] **Graph extension in `src/graph.py`**
  - After EvidenceAggregator: for each dimension (or in one parallel block), run Prosecutor, Defense, Tech Lead in parallel; append their opinions to state via reducer.
  - Graph ends after all Judge outputs are collected (no Chief Justice yet); or add a “judge_collector” node that just passes through.

### 3.2 How to Test (Independently)

1. **Single Judge:** Call one Judge node with mock state containing `evidences` and one dimension; assert return has `opinions` with one `JudicialOpinion`; validate schema (judge, criterion_id, score 1–5, argument, cited_evidence).
2. **Parse failure:** If LLM returns free text, assert retry or error path; no invalid object appended to state.
3. **Full Judicial run:** Run graph through EvidenceAggregator then all Judges (for at least one dimension). Assert:
   - `state["opinions"]` has 3 opinions per dimension (Prosecutor, Defense, Tech Lead); all valid `JudicialOpinion`.
   - Personas produce different scores/arguments for same evidence (sanity check).

### 3.3 Exit Criteria

- Judges use only structured output bound to `JudicialOpinion`; parse failures handled.
- Graph run through Judges populates `opinions`; no Chief Justice or report file required for this phase.

---

## Phase 4: Supreme Court & Report

**Objective:** Implement ChiefJusticeNode (synthesis rules, build `AuditReport`), serialize to Markdown, write to disk. Complete the graph: EvidenceAggregator → Judges → ChiefJustice → END.

### 4.1 Deliverables

- [ ] **`src/nodes/justice.py`** (complete)
  - **ChiefJusticeNode(state: AgentState) -> dict**
    - Read `opinions` (group by criterion_id) and `evidences`; load `synthesis_rules` from rubric.
    - Apply hardcoded rules: security_override, fact_supremacy, functionality_weight, dissent_requirement, variance_re_evaluation (see [SRS §6.3](../specs/system_requirement_spec.md#63-synthesis-rules-chief-justice), [API Contracts §6.3](../specs/api_contracts.md#63-synthesis-rules-object)).
    - Build `AuditReport` (repo_url, executive_summary, overall_score, criteria with final_score, judge_opinions, dissent_summary where variance > 2, remediation; remediation_plan).
    - Return `{"final_report": report}`.
  - **Report serialization:** Convert `AuditReport` to Markdown per [API Contracts §8](../specs/api_contracts.md#8-report-output-contract): Executive Summary → Criterion Breakdown → Remediation Plan.
  - **Write file:** Write Markdown to configured path (e.g. `audit/` or CLI arg).
- [ ] **`src/graph.py`** (complete)
  - Wire: … → EvidenceAggregator → [Judges in parallel per criterion] → ChiefJusticeNode → END.
  - Optional: conditional edges for error handling (e.g. evidence missing) per SRS FR-19.
- [ ] **Entry point:** A single function or CLI that: loads rubric, builds initial state, compiles graph, invokes, writes report. Signature aligns with [API Contracts §2](../specs/api_contracts.md#2-public-entry-api) (repo_url, pdf_path, optional rubric_path, output_path).

### 4.2 How to Test (Independently)

1. **ChiefJustice only:** With mock state containing `opinions` (e.g. 3 per criterion) and `evidences`, call ChiefJusticeNode; assert return has `final_report` of type `AuditReport`; assert synthesis rules applied (e.g. security cap, dissent when variance > 2).
2. **Report structure:** Serialize a known `AuditReport` to Markdown; assert sections exist: Executive Summary, Criterion Breakdown (with scores and remediation), Remediation Plan.
3. **Full run:** Invoke entry API with real repo URL and PDF; assert run completes; assert `state["final_report"]` is set; assert Markdown file exists at expected path and contains the three sections.
4. **Variance > 2:** Use mock opinions with high variance; assert `dissent_summary` is present in the criterion result and in the report.

### 4.3 Exit Criteria

- Chief Justice uses only hardcoded deterministic logic (no LLM for synthesis).
- Final output is a Markdown file; structure matches API Contracts §8.
- Full graph run: repo_url + pdf_path → report file + `final_report` in state.

---

## Phase 5: Hardening & Entry API

**Objective:** Production-ready entry API, error handling, optional Docker, and observability. No new features; stabilize and document.

### 5.1 Deliverables

- [ ] **Conditional edges** — On clone failure, missing PDF, or optional “evidence missing” branch: route to error handler or inject placeholder evidence so graph can terminate cleanly (SRS FR-19, A2).
- [ ] **CLI or script** — Documented way to run audit: e.g. `uv run python -m src.run repo_url pdf_path [--rubric path] [--output path]`; clear errors for missing env or invalid args.
- [ ] **README.md** — Update with: install (uv), env setup (.env from .env.example), how to run (CLI/entry), where report is written, optional LangSmith setup.
- [ ] **Optional: Dockerfile** — Containerized run; document how to build and run with env vars.
- [ ] **Observability** — Ensure `LANGCHAIN_TRACING_V2=true` is documented and used so full trace (Detectives → Judges → Chief Justice) is visible in LangSmith.

### 5.2 How to Test (Independently)

1. **Error paths:** Invalid repo URL → no crash; missing PDF → defined behavior (error message or placeholder evidence).
2. **CLI:** Run with valid args → report file created; run with missing required env → clear error.
3. **Trace:** Run with LangSmith enabled; confirm trace shows all node steps.

### 5.3 Exit Criteria

- Entry API matches API Contracts §2; README and .env.example are complete.
- Error handling and optional Docker satisfy SRS §7.2 and NFR-2, NFR-3.

---

## Phase Summary Table

| Phase | Artifacts | Test focus |
|-------|-----------|------------|
| 0 | state.py, rubric.json, pyproject.toml, .env.example, README | Imports, rubric load, env, reducers |
| 1 | tools/repo_tools.py, tools/doc_tools.py | Unit tests per tool; sandbox; AST; RAG-lite |
| 2 | nodes/detectives.py, evidence_aggregator_node, graph (detective-only) | Graph run → evidences populated |
| 3 | nodes/judges.py, graph (through judges) | Graph run → opinions populated; structured output |
| 4 | ChiefJusticeNode, report serialization, full graph, entry | Full run → report file + final_report |
| 5 | Conditional edges, CLI, README, Dockerfile (optional), tracing | E2E, error paths, docs |

---

## Dependency Order

```
Phase 0 (Foundation)
    → Phase 1 (Tools)           [no graph]
    → Phase 2 (Detective graph) [uses state, rubric, tools]
    → Phase 3 (Judicial)       [uses state, rubric, evidences]
    → Phase 4 (Supreme Court)  [uses state, opinions, rubric]
    → Phase 5 (Hardening)      [wraps Phase 4]
```

Each phase can be validated before starting the next; mocks (e.g. fake evidence for Phase 3, fake opinions for Phase 4) allow testing nodes in isolation.

---

*End of Implementation Plan*
