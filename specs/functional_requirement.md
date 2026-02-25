# Functional Requirements: Automaton Auditor

**Version:** 1.0  
**Source:** [System Requirement Specification](./system_requirement_spec.md) (SRS) §4, §6  
**Aligned with:** [Specs Meta](./_meta.md), [System Architecture](./system_architecture.md), [API Contracts](./api_contracts.md)

This document restates and groups the **functional requirements** for the Automaton Auditor. All requirements originate in the SRS; this document organizes them by capability and adds implementation pointers. Where the SRS says "shall," implementation **must** comply.

---

## 1. Document Role

- **Authority:** The [SRS](./system_requirement_spec.md) is the sole requirements authority. This document does not add or change requirements.
- **Use:** Implementers use this document to see functional requirements by area (entry, state, detectives, judges, synthesis, rubric) with traceability to SRS and pointers to architecture and API contracts.

---

## 2. Entry and Orchestration

| ID | Requirement | SRS | See also |
|----|-------------|-----|----------|
| **FE-1** | The system **shall** accept at least a GitHub repository URL and a PDF report path as inputs. | §2.2 | [api_contracts §2](./api_contracts.md#2-public-entry-api) |
| **FE-2** | The system **shall** implement a Hierarchical State Graph using LangGraph; a single LLM **shall not** perform the full evaluation. | §3.1 | [architecture §6](./system_architecture.md#6-runtime-architecture-stategraph) |
| **FE-3** | Detectives (RepoInvestigator, DocAnalyst, VisionInspector) **shall** run in parallel branches (fan-out). | FR-16 | [architecture §6.1](./system_architecture.md#61-node-topology) |
| **FE-4** | An EvidenceAggregator (or equivalent) **shall** collect all Detective evidence before Judges are invoked (fan-in). | FR-17 | [architecture §6.2](./system_architecture.md#62-simplified-sequential-view) |
| **FE-5** | Judges **shall** run in parallel (fan-out) from the aggregation point and fan-in before ChiefJustice. | FR-18 | [architecture §8](./system_architecture.md#8-judicial-layer-detail) |
| **FE-6** | The graph **shall** support conditional edges for scenarios such as "Evidence Missing" or "Node Failure" where specified. | FR-19 | [architecture §6.3](./system_architecture.md#63-conditional-edges-error-handling) |
| **FE-7** | The system **shall** handle invalid repo URL or missing PDF in a defined way (e.g. error handling, conditional edges). | A2 | [api_contracts §2.1](./api_contracts.md#21-run-audit) (Errors) |

---

## 3. State and Data Model

| ID | Requirement | SRS | See also |
|----|-------------|-----|----------|
| **FS-1** | The system **shall** define `AgentState` using Pydantic models and `TypedDict` (no plain Python dicts for core state). | FR-1 | [api_contracts §3.5](./api_contracts.md#35-agentstate-typeddict), [architecture §4.1](./system_architecture.md#41-agentstate-graph-state) |
| **FS-2** | The system **shall** define and use an `Evidence` model with at least: goal, found, content (optional), location, rationale, confidence. | FR-2 | [api_contracts §3.1](./api_contracts.md#31-evidence-pydantic-basemodel) |
| **FS-3** | The system **shall** define and use a `JudicialOpinion` model with: judge, criterion_id, score (1–5), argument, cited_evidence. | FR-3 | [api_contracts §3.2](./api_contracts.md#32-judicialopinion-pydantic-basemodel) |
| **FS-4** | The system **shall** define and use `CriterionResult` and `AuditReport` models for the final report. | FR-4 | [api_contracts §3.3](./api_contracts.md#33-criterionresult-pydantic-basemodel), [§3.4](./api_contracts.md#34-auditreport-pydantic-basemodel) |
| **FS-5** | The system **shall** use state reducers (`Annotated[..., operator.add]` for lists, `Annotated[..., operator.ior]` for dicts) so parallel agents do not overwrite each other's data. | FR-5 | [architecture §4.1](./system_architecture.md#41-agentstate-graph-state), [_meta §2.2](./_meta.md#22-typing-and-data-contracts) |

---

## 4. Detective Layer

| ID | Requirement | SRS | See also |
|----|-------------|-----|----------|
| **FD-1** | RepoInvestigator **shall** implement sandboxed repo access (e.g. `tempfile` for clone directory); no cloning into the live working directory. | FR-6 | [api_contracts §5.1](./api_contracts.md#51-repo-tools-srctoolsrepo_toolspy) |
| **FD-2** | RepoInvestigator **shall** provide at least `analyze_graph_structure(path)` and `extract_git_history(path)`; analysis **shall** use AST (or equivalent) where required, not only regex. | FR-7 | [api_contracts §5.1](./api_contracts.md#51-repo-tools-srctoolsrepo_toolspy) |
| **FD-3** | DocAnalyst **shall** support chunked PDF ingestion and querying (e.g. RAG-lite) so the full PDF is not dumped into context. | FR-8 | [api_contracts §5.2](./api_contracts.md#52-doc-tools-srctoolsdoc_toolspy) |
| **FD-4** | VisionInspector **shall** support image extraction from PDF and analysis via a vision-capable model (implementation required; execution may be optional). | FR-9 | [api_contracts §5.2](./api_contracts.md#52-doc-tools-srctoolsdoc_toolspy) |
| **FD-5** | Detective nodes **shall** output structured `Evidence` only; they **shall not** opinionate. | §3.2 | [architecture §7](./system_architecture.md#7-detective-layer-detail) |
| **FD-6** | RepoInvestigator **shall** execute evidence classes per rubric: Git Forensic Analysis, State Management Rigor, Graph Orchestration, Safe Tool Engineering, Structured Output (success/failure patterns, required captures). | §6.1 | SRS §6.1 |
| **FD-7** | DocAnalyst **shall** execute Theoretical Depth and Report Accuracy checks: keyword/context checks, cross-reference of file paths with RepoInvestigator, Verified vs Hallucinated paths. | §6.1 | SRS §6.1 |
| **FD-8** | VisionInspector **shall** execute Swarm Visual analysis: diagram type classification, critical flow verification (parallel split and aggregation), classification and flow description. | §6.1 | SRS §6.1 |

---

## 5. Judicial Layer

| ID | Requirement | SRS | See also |
|----|-------------|-----|----------|
| **FJ-1** | Judges **shall** return structured output only: `.with_structured_output()` or `.bind_tools()` bound to the `JudicialOpinion` Pydantic schema (score, argument, cited_evidence). Free-text-only output **shall** be treated as an error and trigger retry/handling. | FR-10 | [api_contracts §7](./api_contracts.md#7-judge-llm-contract) |
| **FJ-2** | Prosecutor, Defense, and Tech Lead **shall** have distinct system prompts and **shall** run in parallel on the same evidence per criterion. | FR-11 | [architecture §8](./system_architecture.md#8-judicial-layer-detail) |
| **FJ-3** | For each rubric dimension, all three judges **shall** submit an opinion on the same evidence independently. | §3.3.2 | [architecture §8.3](./system_architecture.md#83-per-criterion-flow) |
| **FJ-4** | Prosecutor **shall** apply "Statute of Orchestration" (e.g. Orchestration Fraud, Hallucination Liability) and penalties per rubric. | §6.2 | SRS §6.2 |
| **FJ-5** | Tech Lead **shall** apply "Statute of Engineering" (e.g. Pydantic rigor, sandboxed tooling; Security Negligence overrides effort for Forensic Accuracy). | §6.2 | SRS §6.2 |
| **FJ-6** | Defense **shall** apply "Statute of Effort" mitigations (e.g. partial credit for sophisticated logic with minor errors, or strong role separation). | §6.2 | SRS §6.2 |

---

## 6. Supreme Court and Report

| ID | Requirement | SRS | See also |
|----|-------------|-----|----------|
| **FC-1** | ChiefJusticeNode **shall** implement conflict resolution via hardcoded deterministic Python logic (not only an LLM prompt). | FR-13 | [architecture §9](./system_architecture.md#9-supreme-court-chief-justice) |
| **FC-2** | When score variance across the three judges exceeds 2 for a criterion, the system **shall** apply re-evaluation rules (as defined in the rubric) and **shall** include a dissent summary. | FR-14 | [api_contracts §3.3](./api_contracts.md#33-criterionresult-pydantic-basemodel) (dissent_summary) |
| **FC-3** | The Chief Justice **shall** apply the rubric synthesis rules (security_override, fact_supremacy, functionality_weight, dissent_requirement, variance_re_evaluation) when producing the final score and report. | §6.3 | [architecture §9.2](./system_architecture.md#92-synthesis-rules-implemented-in-code) |
| **FC-4** | The final output **shall** be a Markdown file (not only console output), structured as: Executive Summary → Criterion Breakdown → Remediation Plan. | FR-15 | [api_contracts §8](./api_contracts.md#8-report-output-contract) |
| **FC-5** | The report **shall** include: The Verdict (final score 1–5 per criterion), The Dissent (summary of conflict where applicable), The Remediation Plan (specific, file-level instructions). | §3.4 | [api_contracts §8.2](./api_contracts.md#82-markdown-structure-minimum) |

---

## 7. Rubric and Targeting

| ID | Requirement | SRS | See also |
|----|-------------|-----|----------|
| **FQ-1** | The system **shall** load rubric dimensions from a machine-readable source (e.g. `rubric.json`) and distribute `forensic_instruction` and `judicial_logic` by `target_artifact` (github_repo, pdf_report, pdf_images). | FR-12 | [architecture §10](./system_architecture.md#10-rubric-and-configuration), [api_contracts §6](./api_contracts.md#6-rubric-json-schema-contract) |
| **FQ-2** | Detectives **shall** receive only instructions where `target_artifact` matches their capability (RepoInvestigator: github_repo; DocAnalyst: pdf_report; VisionInspector: pdf_images). | FR-20 | [architecture §7.1](./system_architecture.md#71-nodes) |
| **FQ-3** | The system **shall** apply the rubric's forensic evidence-collection standards (Protocol A) and judicial sentencing guidelines (Protocol B) as specified in the challenge and in the machine-readable rubric. | FR-21 | SRS §6.1, §6.2 |
| **FQ-4** | The rubric **shall** be loadable at runtime (e.g. `json.load()`); the system **shall** be designed so rubric changes do not require code redeployment. | A1 | [_meta §2.5](./_meta.md#25-code-quality) |

---

## 8. Traceability Summary

| Area | SRS sections | This document |
|------|--------------|----------------|
| Entry & orchestration | §2.2, §3.1, FR-16–FR-19, A2 | §2 (FE-1–FE-7) |
| State & data model | FR-1–FR-5 | §3 (FS-1–FS-5) |
| Detective layer | §3.2, §6.1, FR-6–FR-9 | §4 (FD-1–FD-8) |
| Judicial layer | §3.3, §6.2, FR-10–FR-11 | §5 (FJ-1–FJ-6) |
| Supreme Court & report | §3.4, §6.3, FR-13–FR-15 | §6 (FC-1–FC-5) |
| Rubric & targeting | FR-12, FR-20–FR-21, A1 | §7 (FQ-1–FQ-4) |

Note: SRS "FR-n" are the numbered functional requirements in the System Requirement Specification. This document uses prefixes FE/FS/FD/FJ/FC/FQ to group requirements by area (Entry, State, Detective, Judicial, Chief Justice, Rubric/Q).

---

## 9. Implementation Notes

- **Node signature:** All graph nodes **shall** conform to `(state: AgentState) -> PartialStateUpdate` per [api_contracts §4](./api_contracts.md#4-graph-node-contract) and [_meta §5.1](./_meta.md#51-graph-node-signature).
- **Tools:** Tools **shall** not modify graph state; nodes map tool results into `Evidence` or state updates. See [api_contracts §5](./api_contracts.md#5-tool-contracts).
- **File layout:** Implement under `src/state.py`, `src/tools/`, `src/nodes/`, `src/graph.py` as in [architecture §5.1](./system_architecture.md#51-module-map) and [_meta §5.6](./_meta.md#56-naming-and-file-layout).

---

*End of Functional Requirements*
