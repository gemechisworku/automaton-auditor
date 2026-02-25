# System Requirement Specification: Automaton Auditor

**Document Version:** 1.0  
**Source of Truth:** FDE Challenge Week 2 — The Automaton Auditor (Challenge Description)  
**Grading Target:** Week 2 Auditor Repository & Architectural Report

---

## 1. Introduction

### 1.1 Purpose

This document specifies the system requirements for the **Automaton Auditor**: an automated quality-assurance swarm that evaluates GitHub repositories and PDF reports using a hierarchical, multi-agent "Digital Courtroom" architecture. The system is the sole source of truth for requirements; no requirement shall be imposed that is not traceable to the challenge description.

### 1.2 Scope

- **In scope:** Design, behavior, and deliverables of the Automaton Auditor system as defined in the challenge description.
- **Out of scope:** Grading policies, submission deadlines, and peer-assignment processes not affecting system behavior.

### 1.3 Definitions and Acronyms

| Term | Definition |
|------|------------|
| **Digital Courtroom** | The overall architecture: Detectives collect evidence, Judges argue by persona, Chief Justice synthesizes a verdict. |
| **Detective Layer** | Forensic sub-agents that collect facts only; they do not opinionate. Output is structured JSON Evidence. |
| **Judicial Layer** | The "Dialectical Bench": Prosecutor, Defense, Tech Lead analyze the same evidence per rubric criterion. |
| **Chief Justice** | Synthesis node that resolves dialectical conflict using hardcoded rules and produces the final Audit Report. |
| **Dialectical Synthesis** | Thesis–Antithesis–Synthesis: three distinct judge personas produce conflicting opinions; synthesis resolves them. |
| **Fan-Out / Fan-In** | Parallel execution: multiple nodes run concurrently (fan-out); a synchronization node collects results (fan-in). |
| **Rubric** | Machine-readable constitution (e.g. `rubric.json`) defining evidence-collection instructions and judicial sentencing guidelines. |
| **Evidence** | Structured forensic finding (e.g. file exists, AST result) produced by a Detective. |
| **JudicialOpinion** | Structured output from a Judge: score, argument, cited evidence, per criterion. |
| **Audit Report** | Final deliverable: executive summary, criterion breakdown, dissent where applicable, remediation plan. |

---

## 2. System Overview

### 2.1 Business Objective

- **Problem:** At scale, human review cannot keep up with code produced by autonomous agents; the bottleneck shifts from generation to evaluation.
- **Solution:** An Automated Auditor Swarm that provides:
  1. **Forensic analysis** — objective verification of existence and structure of code artifacts.
  2. **Nuanced judgment** — application of complex rubrics requiring interpretation (e.g. modularity).
  3. **Constructive feedback** — actionable remediation, not only pass/fail.

### 2.2 High-Level Input/Process/Output

| Aspect | Description |
|--------|-------------|
| **Input** | A single GitHub repository URL and a PDF report. |
| **Process** | Hierarchical swarm: Detectives collect evidence → Judges (Prosecutor, Defense, Tech Lead) deliberate per criterion → Chief Justice synthesizes verdict. |
| **Output** | A production-grade Audit Report (e.g. Markdown) that can stand up to scrutiny. |

### 2.3 Applicability

The same architecture is intended to support:
- Automated security audits (e.g. vulnerability hunting in PRs).
- Compliance governance (e.g. ISO/SOC2).
- Architectural review (e.g. preventing "spaghetti code" before merge).

---

## 3. Architectural Requirements

### 3.1 Mandatory Architecture

The system **shall** implement a **Hierarchical State Graph** using LangGraph. A single LLM **shall not** perform the full evaluation; specialized roles are required.

### 3.2 Layer 1: Detective Layer (Forensic Sub-Agents)

- Detectives **shall not** opinionate; they only collect facts per forensic protocols.
- Output **shall** be a structured JSON Evidence object, untainted by bias.
- The following agents and protocols are required:

#### 3.2.1 RepoInvestigator (Code Detective)

- **Tools (required):** `git clone`, `git log`, `file_read`, `ast_parse` (e.g. Python `ast` or tree-sitter).
- **Forensic Protocol A (State Structure):** Verify existence of typed state (`src/state.py` or `src/graph.py`), valid Pydantic `BaseModel` or `TypedDict` schemas.
- **Forensic Protocol B (Graph Wiring):** Verify graph is functionally wired for parallelism (e.g. AST shows `builder.add_edge()` fan-out), not only string match for "StateGraph".
- **Forensic Protocol C (Git Narrative):** Analyze `git log` for atomic vs monolithic history; extract timestamps.

#### 3.2.2 DocAnalyst (Paperwork Detective)

- **Tools (required):** `pdf_parse`, `markdown_read`, `cross_reference`.
- **Forensic Protocol A (Citation Check):** Cross-reference report claims (e.g. "We implemented parallel Judges in `src/nodes/judges.py`") with RepoInvestigator data; flag "Hallucination" if cited file does not exist.
- **Forensic Protocol B (Concept Verification):** Check for substantive use of concepts (e.g. "Dialectical Synthesis", "Metacognition") — explanation of how the architecture executes them, not just keyword use.

#### 3.2.3 VisionInspector (Diagram Detective)

- **Tools (required):** `image_analysis` (e.g. Gemini Pro Vision / GPT-4o).
- **Forensic Protocol A (Flow Analysis):** Analyze diagrams for flow: Detectives (Parallel) → Evidence Aggregation → Judges (Parallel) → Synthesis; distinguish from a simple linear pipeline.
- **Note:** Implementation is required; execution at runtime may be optional as specified in the challenge.

### 3.3 Layer 2: Judicial Layer (Dialectical Bench)

- The system **shall** apply the rubric criterion-by-criterion through **three distinct persona lenses** (Thesis–Antithesis–Synthesis).
- For **each** rubric dimension, **all three** judges **shall** submit an opinion on the **same evidence** independently.

#### 3.3.1 Personas

| Persona | Philosophy | Objective |
|---------|------------|-----------|
| **Prosecutor** | "Trust No One. Assume Vibe Coding." | Scrutinize for gaps, security flaws, laziness; argue for low scores when evidence warrants (e.g. linear pipeline → argue Score 1). |
| **Defense Attorney** | "Reward Effort and Intent. Spirit of the Law." | Highlight effort, intent, workarounds; argue for higher scores based on understanding/process even if implementation is imperfect. |
| **Tech Lead** | "Does it actually work? Is it maintainable?" | Evaluate soundness, cleanliness, viability; tie-breaker; provide realistic score (e.g. 1, 3, or 5) and technical remediation. |

#### 3.3.2 Judicial Workflow (per Criterion)

1. **State Input:** Evidence object for that criterion.
2. **Parallel Execution:** Prosecutor, Defense, Tech Lead each produce an opinion (score, argument, citations).
3. **Output:** A list of `JudicialOpinion` objects (three views per criterion).

### 3.4 Layer 3: Supreme Court (Final Verdict)

- **ChiefJusticeNode** **shall** act as the Synthesis Engine: resolve dialectical conflict, not merely average scores.
- **Input:** All `JudicialOpinion` objects (Prosecutor, Defense, Tech Lead) for every criterion.
- **Deliberation:** **Shall** use hardcoded deterministic rules, including:
  - **Rule of Security:** Confirmed security vulnerability (e.g. `os.system` with unsanitized inputs) overrides Defense "effort"; security flaws cap score at 3.
  - **Rule of Evidence:** If Defense claims "Deep Metacognition" but RepoInvestigator found no PDF report, Defense overruled for hallucination.
  - **Rule of Functionality:** If Tech Lead confirms architecture is modular and workable, that carries highest weight for the "Architecture" criterion.
- **Output:** Structured Markdown report containing:
  - **The Verdict:** Final score (1–5) per criterion.
  - **The Dissent:** Summary of conflict (e.g. why Defense was overruled).
  - **The Remediation Plan:** Specific, file-level instructions for the auditee.

---

## 4. Functional Requirements

### 4.1 State and Data Model

- **FR-1** The system **shall** define `AgentState` using Pydantic models and `TypedDict` (no plain Python dicts for core state).
- **FR-2** The system **shall** define and use an `Evidence` model (e.g. goal, found, content, location, rationale, confidence).
- **FR-3** The system **shall** define and use a `JudicialOpinion` model (e.g. judge, criterion_id, score 1–5, argument, cited_evidence).
- **FR-4** The system **shall** define and use `CriterionResult` and `AuditReport` models for the final report.
- **FR-5** The system **shall** use state reducers (e.g. `Annotated[..., operator.add]`, `Annotated[..., operator.ior]`) so parallel agents do not overwrite each other's data.

### 4.2 Detective Layer

- **FR-6** RepoInvestigator **shall** implement sandboxed repo access: e.g. `tempfile` for clone directory; no cloning into the live working directory.
- **FR-7** RepoInvestigator **shall** provide at least: `analyze_graph_structure(path)` and `extract_git_history(path)`; analysis **shall** use AST (or equivalent) where required, not only regex.
- **FR-8** DocAnalyst **shall** support chunked PDF ingestion and querying (e.g. RAG-lite) so the full PDF is not dumped into context.
- **FR-9** VisionInspector **shall** support image extraction from PDF and analysis via a vision-capable model (implementation required; execution may be optional as per challenge).

### 4.3 Judicial Layer

- **FR-10** Judges **shall** return structured output only: `.with_structured_output()` or `.bind_tools()` bound to the `JudicialOpinion` Pydantic schema (score, reasoning, citations). Free-text-only output **shall** be treated as an error and trigger retry/handling.
- **FR-11** Prosecutor, Defense, and Tech Lead **shall** have distinct system prompts and **shall** run in parallel on the same evidence per criterion.
- **FR-12** The system **shall** load rubric dimensions from a machine-readable source (e.g. `rubric.json`) and distribute `forensic_instruction` and `judicial_logic` by `target_artifact` (e.g. github_repo, pdf_report, pdf_images).

### 4.4 Chief Justice and Report

- **FR-13** ChiefJusticeNode **shall** implement conflict resolution via hardcoded deterministic Python logic (not only an LLM prompt).
- **FR-14** When score variance across the three judges exceeds 2 for a criterion, the system **shall** apply re-evaluation rules (as defined in the rubric) and **shall** include a dissent summary.
- **FR-15** The final output **shall** be a Markdown file (not only console output), structured as: Executive Summary → Criterion Breakdown → Remediation Plan.

### 4.5 Graph Orchestration

- **FR-16** Detectives (RepoInvestigator, DocAnalyst, VisionInspector) **shall** run in parallel branches (fan-out).
- **FR-17** An EvidenceAggregator (or equivalent) **shall** collect all Detective evidence before Judges are invoked (fan-in).
- **FR-18** Judges **shall** run in parallel (fan-out) from the aggregation point and fan-in before ChiefJustice.
- **FR-19** The graph **shall** support conditional edges for scenarios such as "Evidence Missing" or "Node Failure" where specified by the challenge.

### 4.6 Rubric and Targeting

- **FR-20** Detectives **shall** receive only instructions where `target_artifact` matches their capability (e.g. RepoInvestigator: github_repo; DocAnalyst: pdf_report; VisionInspector: pdf_images).
- **FR-21** The system **shall** apply the rubric's forensic evidence-collection standards (Protocol A) and judicial sentencing guidelines (Protocol B) as specified in the challenge and in the machine-readable rubric.

---

## 5. Non-Functional Requirements

### 5.1 Environment and Dependencies

- **NFR-1** The project **shall** use the `uv` package manager for dependency management; dependencies **shall** be strictly managed and locked (e.g. in `pyproject.toml`).
- **NFR-2** API keys and secrets **shall** not be hardcoded; **shall** be supplied via environment variables (e.g. `.env`); **shall** provide an `.env.example` listing required variables.

### 5.2 Observability

- **NFR-3** The system **shall** support LangSmith tracing (e.g. `LANGCHAIN_TRACING_V2=true`) for debugging the multi-agent flow.

### 5.3 Safety and Security

- **NFR-4** Git operations **shall** run in a sandboxed temporary directory; git authentication failures **shall** be handled gracefully.
- **NFR-5** The system **shall** avoid raw `os.system` with unsanitized inputs for repository cloning or other sensitive operations; use of subprocess with error handling (e.g. stdout/stderr, return codes) is required where specified.

### 5.4 Quality and Maintainability

- **NFR-6** State and structured outputs **shall** use typed structures (e.g. Pydantic `BaseModel`) rather than untyped dicts for complex nested state and report data.

---

## 6. Forensic and Judicial Protocols (Normative)

*These are binding on the agent swarm; Detectives must follow evidence-collection protocols, and Judges must cite these standards.*

### 6.1 Protocol A: Forensic Evidence Collection (Detectives)

- **RepoInvestigator:** Execute evidence classes as specified in the rubric (e.g. Git Forensic Analysis, State Management Rigor, Graph Orchestration, Safe Tool Engineering, Structured Output), including success/failure patterns and required captures (e.g. commit list, code snippets, graph block).
- **DocAnalyst:** Execute Theoretical Depth and Report Accuracy (Host Analysis) checks: keyword and context checks, cross-reference of file paths with RepoInvestigator, list of Verified vs Hallucinated paths.
- **VisionInspector:** Execute Swarm Visual analysis: diagram type classification, critical flow verification (parallel split and aggregation), classification string and flow description.

### 6.2 Protocol B: Judicial Sentencing Guidelines (Judges)

- **Prosecutor:** Apply "Statute of Orchestration" (e.g. Orchestration Fraud, Hallucination Liability) and penalties (e.g. max score 1 or 2 for specified violations).
- **Tech Lead:** Apply "Statute of Engineering" (e.g. Pydantic rigor vs dicts, sandboxed tooling; Security Negligence overrides effort for Forensic Accuracy).
- **Defense:** Apply "Statute of Effort" mitigations (e.g. partial credit for sophisticated logic with minor errors, or for strong role separation with weaker synthesis).

### 6.3 Synthesis Rules (Chief Justice)

The Chief Justice **shall** apply the synthesis rules defined in the rubric (e.g. security_override, fact_supremacy, functionality_weight, dissent_requirement, variance_re_evaluation) when producing the final score and report.

---

## 7. Deliverables (System Artifacts)

The system **shall** produce or support the following artifacts as specified in the challenge:

### 7.1 Source Code Structure

- `src/state.py` — Pydantic/TypedDict state definitions (`Evidence`, `JudicialOpinion`, `AgentState`, etc.) with appropriate reducers.
- `src/tools/repo_tools.py` — Sandboxed git clone, git log extraction, AST-based graph structure analysis.
- `src/tools/doc_tools.py` — PDF ingestion and chunked querying (RAG-lite).
- `src/nodes/detectives.py` — RepoInvestigator, DocAnalyst, VisionInspector as LangGraph nodes outputting structured `Evidence`.
- `src/nodes/judges.py` — Prosecutor, Defense, Tech Lead with distinct prompts and structured output bound to `JudicialOpinion`.
- `src/nodes/justice.py` — ChiefJusticeNode with hardcoded conflict-resolution rules, producing `AuditReport` serialized to Markdown.
- `src/graph.py` — Complete StateGraph: parallel fan-out/fan-in for Detectives and Judges, conditional edges, flow from repo URL (+ PDF) to Markdown report.

### 7.2 Infrastructure and Configuration

- `pyproject.toml` — Locked dependencies (e.g. via `uv`).
- `.env.example` — Required API keys and environment variables (no secrets).
- `README.md` — Setup, install, and run instructions (e.g. run against target repo URL and PDF).
- `Dockerfile` — Optional but recommended for containerized runtime.
- `rubric.json` (or equivalent) — Machine-readable rubric for context building and dispatcher.

### 7.3 Report Outputs

- Audit reports as Markdown serialization of `AuditReport`: Executive Summary, Criterion Breakdown (per rubric dimension, with scores, judge opinions, dissent where applicable), Remediation Plan.
- Reports may be placed in specified directories (e.g. `audit/report_onself_generated/`, `audit/report_onpeer_generated/`, `audit/report_bypeer_received/`) as per challenge deliverables.

---

## 8. Rubric Dimensions (Summary)

The system **shall** evaluate (at least) the following dimensions as defined in the challenge and in the machine-readable rubric:

| ID | Name | Target Artifact |
|----|------|-----------------|
| git_forensic_analysis | Git Forensic Analysis | github_repo |
| state_management_rigor | State Management Rigor | github_repo |
| graph_orchestration | Graph Orchestration Architecture | github_repo |
| safe_tool_engineering | Safe Tool Engineering | github_repo |
| structured_output_enforcement | Structured Output Enforcement | github_repo |
| judicial_nuance | Judicial Nuance and Dialectics | github_repo |
| chief_justice_synthesis | Chief Justice Synthesis Engine | github_repo |
| theoretical_depth | Theoretical Depth (Documentation) | pdf_report |
| report_accuracy | Report Accuracy (Cross-Reference) | pdf_report |
| swarm_visual | Architectural Diagram Analysis | pdf_images |

Scoring scale: 1–5 per criterion, with definitions (e.g. 1 = Vibe Coder, 3 = Competent, 5 = Master Thinker) as given in the challenge's evaluation rubric table.

---

## 9. Assumptions and Constraints

- **A1** The machine-readable rubric (e.g. `rubric.json`) is the updatable "Constitution"; the system **shall** be designed to load it (e.g. via `json.load()`) and distribute instructions without requiring code redeployment for rubric changes.
- **A2** Inputs are a valid (or handleable) GitHub repository URL and a PDF report path; the system **shall** handle invalid URLs or missing files in a defined way (e.g. error handling, conditional edges).
- **A3** LangGraph (StateGraph, nodes, parallel execution, conditional_edges) is the chosen orchestration framework.
- **C1** VisionInspector execution at runtime may be optional as stated in the challenge; implementation of the node and tools is still required.

---

## 10. Traceability

All requirements in this document are derived exclusively from the FDE Challenge Week 2 document: **"The Automaton Auditor — Orchestrating Deep LangGraph Swarms for Autonomous Governance"** (challenge description). No external sources have been used for mandatory requirements.

---

*End of System Requirement Specification*
