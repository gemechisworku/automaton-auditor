"""
Supreme Court layer: EvidenceAggregator (Phase 2), judge_collector (Phase 3), ChiefJusticeNode (Phase 4).
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.state import AgentState, AuditReport, CriterionResult, Evidence, JudicialOpinion
from src.tools.doc_tools import (
    cross_reference_report_claims,
    extract_claimed_paths_from_text,
    ingest_pdf,
)


def is_critical_failure(state: AgentState) -> bool:
    """
    True if evidence is entirely placeholder/error (no successful collection).
    Used by graph conditional edge to route to degraded_report (error-handling path).
    """
    evidences = state.get("evidences") or {}
    if not evidences:
        return True
    for dim_id, ev_list in evidences.items():
        for e in ev_list or []:
            ev = e if isinstance(e, Evidence) else Evidence(**e)
            if ev.confidence > 0 and "placeholder" not in (ev.rationale or "").lower():
                return False
    return True


def evidence_aggregator_node(state: AgentState) -> dict:
    """
    Merge/validation of state["evidences"]. Injects placeholder evidence for any dimension
    with no evidence so the graph can terminate cleanly (SRS FR-19, A2). API Contracts §4.
    For report_accuracy dimension: performs cross-reference of PDF claimed paths vs repo_file_list
    (DOC-1, DOC-2) and sets evidence to "Verified paths: ...; Unverified: ...".
    """
    evidences = dict(state.get("evidences") or {})
    dimensions = state.get("rubric_dimensions") or []
    repo_file_list = state.get("repo_file_list") or []
    pdf_path = (state.get("pdf_path") or "").strip()

    # report_accuracy: cross-reference claimed paths from PDF with repo file list
    report_accuracy_dim = next((d for d in dimensions if d.get("id") == "report_accuracy"), None)
    if report_accuracy_dim and repo_file_list and pdf_path:
        try:
            store = ingest_pdf(pdf_path)
            full_text = " ".join(s.text for s in store.segments)
            claimed = extract_claimed_paths_from_text(full_text)
            result = cross_reference_report_claims(claimed, repo_file_list)
            verified = result["verified"]
            unverified = result["unverified"]
            goal = report_accuracy_dim.get("forensic_instruction", "")
            evidences["report_accuracy"] = [
                Evidence(
                    goal=goal,
                    found=len(verified) > 0 or len(claimed) == 0,
                    content=f"Verified paths: {verified[:30]}{'...' if len(verified) > 30 else ''}. Unverified/hallucinated: {unverified[:30]}{'...' if len(unverified) > 30 else ''}.",
                    location=pdf_path,
                    rationale=f"Cross-referenced {len(claimed)} claimed paths with RepoInvestigator file list. Verified: {len(verified)}; Unverified: {len(unverified)}."
                    if claimed
                    else "No path-like claims found in PDF to cross-reference.",
                    confidence=0.85 if claimed else 0.5,
                )
            ]
        except Exception as e:
            evidences["report_accuracy"] = [
                Evidence(
                    goal=report_accuracy_dim.get("forensic_instruction", ""),
                    found=False,
                    location=pdf_path,
                    rationale=f"Cross-reference failed: {e}.",
                    confidence=0.0,
                )
            ]

    for dim in dimensions:
        dim_id = dim.get("id", "unknown")
        if dim_id not in evidences or not evidences[dim_id]:
            goal = dim.get("forensic_instruction", "")
            evidences[dim_id] = [
                Evidence(
                    goal=goal,
                    found=False,
                    location=state.get("repo_url") or state.get("pdf_path") or "",
                    rationale="No evidence collected (placeholder for clean termination).",
                    confidence=0.0,
                )
            ]
    return {"evidences": evidences}


def judge_collector_node(state: AgentState) -> dict:
    """Pass-through after all Judge nodes; opinions already merged via reducer. Returns {}."""
    return {}


def _load_synthesis_rules(state: AgentState) -> dict[str, str]:
    """Load synthesis_rules from rubric JSON."""
    rubric_path = state.get("rubric_path") or "rubric.json"
    path = Path(rubric_path)
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("synthesis_rules", {})


def _opinions_by_criterion(opinions: list[JudicialOpinion]) -> dict[str, list[JudicialOpinion]]:
    """Group opinions by criterion_id."""
    by_criterion: dict[str, list[JudicialOpinion]] = defaultdict(list)
    for o in opinions:
        if isinstance(o, dict):
            o = JudicialOpinion(**o)
        by_criterion[o.criterion_id].append(o)
    return dict(by_criterion)


def _evidence_has_security_issue(evidences: list[Evidence]) -> bool:
    """True if any evidence content suggests security vulnerability (os.system, unsanitized)."""
    for e in evidences:
        content = (e.content or "") + (e.rationale or "")
        if "os.system" in content or "unsanitized" in content.lower():
            return True
    return False


def _evidence_supports_claim(evidences: list[Evidence]) -> bool:
    """True if there is at least one finding (found=True with some content)."""
    return any(e.found and (e.content or e.rationale) for e in evidences)


def _resolve_final_score(
    opinions: list[JudicialOpinion],
    dimension_name: str,
    evidences: list[Evidence],
    synthesis_rules: dict[str, str],
) -> tuple[int, str | None]:
    """
    Apply synthesis rules; return (final_score, dissent_summary).
    Hardcoded deterministic logic only (no LLM). Rules applied (CJ-1):

    - functionality_weight: For dimension names containing "architecture" or "graph", use Tech Lead score.
    - security_override: If evidence indicates security issue (os.system, unsanitized), cap final score at 3.
    - fact_supremacy: If evidence does not support claims and Defense > Prosecutor, reduce final to max(Prosecutor, Tech Lead).
    - variance_re_evaluation: When score variance across the three judges > 2, use Tech Lead as final and set dissent_summary.
    - dissent_requirement: dissent_summary is set when variance > 2 (same as variance_re_evaluation).
    """
    scores = [o.score for o in opinions]
    if not scores:
        return (1, None)
    prosecutor_score = next((o.score for o in opinions if o.judge == "Prosecutor"), 3)
    defense_score = next((o.score for o in opinions if o.judge == "Defense"), 3)
    tech_lead_score = next((o.score for o in opinions if o.judge == "TechLead"), 3)

    variance = max(scores) - min(scores) if scores else 0

    # functionality_weight: Tech Lead carries highest weight for architecture/graph criterion
    if "architecture" in dimension_name.lower() or "graph" in dimension_name.lower():
        final = tech_lead_score
    else:
        # Default: median (or Tech Lead as tie-breaker)
        final = sorted(scores)[len(scores) // 2]

    # security_override: security flaw caps score at 3
    if _evidence_has_security_issue(evidences):
        final = min(final, 3)

    # fact_supremacy: if evidence doesn't support claims, don't reward high Defense
    if not _evidence_supports_claim(evidences) and defense_score > prosecutor_score:
        final = min(final, max(prosecutor_score, tech_lead_score))

    # variance_re_evaluation: when variance > 2, use Tech Lead as tie-breaker
    if variance > 2:
        final = tech_lead_score
        if _evidence_has_security_issue(evidences):
            final = min(final, 3)

    final = max(1, min(5, final))
    dissent_summary = None
    if variance > 2:
        dissent_summary = (
            f"Variance {variance}: Prosecutor {prosecutor_score}, Defense {defense_score}, "
            f"Tech Lead {tech_lead_score}. Re-evaluation applied (Tech Lead weight)."
        )
    return (final, dissent_summary)


def _remediation_from_opinions(opinions: list[JudicialOpinion]) -> str:
    """Extract remediation from Tech Lead argument, or concatenate short recommendations."""
    tech_lead = next((o for o in opinions if o.judge == "TechLead"), None)
    if tech_lead and tech_lead.argument:
        return tech_lead.argument[:1000]
    parts = [o.argument[:300] for o in opinions if o.argument][:3]
    return " ".join(parts) if parts else "No specific remediation provided."


def chief_justice_node(state: AgentState) -> dict[str, Any]:
    """
    Read opinions (group by criterion_id) and evidences; load synthesis_rules; apply hardcoded
    rules; build AuditReport. Return {"final_report": report}. No LLM.
    """
    opinions_raw = state.get("opinions") or []
    opinions = [o if isinstance(o, JudicialOpinion) else JudicialOpinion(**o) for o in opinions_raw]
    evidences_map = state.get("evidences") or {}
    dimensions = state.get("rubric_dimensions") or []
    synthesis_rules = _load_synthesis_rules(state)
    repo_url = state.get("repo_url") or ""

    by_criterion = _opinions_by_criterion(opinions)
    criteria_results: list[CriterionResult] = []

    for dim in dimensions:
        dim_id = dim.get("id", "unknown")
        dim_name = dim.get("name", dim_id)
        dim_opinions = by_criterion.get(dim_id, [])
        ev_list = evidences_map.get(dim_id, [])
        evidence_objs = [
            e if isinstance(e, Evidence) else Evidence(**e)
            for e in ev_list
            if isinstance(e, (Evidence, dict))
        ]

        final_score, dissent_summary = _resolve_final_score(
            dim_opinions, dim_name, evidence_objs, synthesis_rules
        )
        remediation = _remediation_from_opinions(dim_opinions)
        criteria_results.append(
            CriterionResult(
                dimension_id=dim_id,
                dimension_name=dim_name,
                final_score=final_score,
                judge_opinions=dim_opinions,
                dissent_summary=dissent_summary,
                remediation=remediation,
            )
        )

    overall = (
        sum(c.final_score for c in criteria_results) / len(criteria_results)
        if criteria_results
        else 0.0
    )
    executive_summary = (
        f"Audit of {repo_url}: {len(criteria_results)} criteria evaluated. "
        f"Overall score: {overall:.1f}/5. "
        + (
            f"Dissent recorded for {sum(1 for c in criteria_results if c.dissent_summary)} criterion/criteria."
            if any(c.dissent_summary for c in criteria_results)
            else ""
        )
    )
    remediation_plan = "\n\n".join(
        f"**{c.dimension_name}**: {c.remediation}" for c in criteria_results
    ) or "No remediation plan."

    report = AuditReport(
        repo_url=repo_url,
        executive_summary=executive_summary.strip(),
        overall_score=round(overall, 1),
        criteria=criteria_results,
        remediation_plan=remediation_plan,
    )
    return {"final_report": report}


def audit_report_to_markdown(report: AuditReport) -> str:
    """Serialize AuditReport to Markdown per API Contracts §8."""
    lines = [
        "# Audit Report",
        "",
        "## Executive Summary",
        "",
        report.executive_summary,
        "",
        f"**Overall Score:** {report.overall_score}/5",
        "",
        "---",
        "",
        "## Criterion Breakdown",
        "",
    ]
    for c in report.criteria:
        lines.append(f"### {c.dimension_name}")
        lines.append("")
        lines.append(f"- **Final Score:** {c.final_score}/5")
        lines.append("")
        lines.append("**Judge opinions:**")
        for o in c.judge_opinions:
            lines.append(f"- **{o.judge}** (score {o.score}): {o.argument[:500]}{'...' if len(o.argument) > 500 else ''}")
        if c.dissent_summary:
            lines.append("")
            lines.append("**Dissent summary:** " + c.dissent_summary)
        lines.append("")
        lines.append("**Remediation:** " + c.remediation[:800] + ("..." if len(c.remediation) > 800 else ""))
        lines.append("")
    lines.extend([
        "---",
        "",
        "## Remediation Plan",
        "",
        report.remediation_plan,
        "",
    ])
    return "\n".join(lines)


def write_report_to_path(report: AuditReport, output_path: str) -> None:
    """Write AuditReport as Markdown to output_path. Creates parent dirs if needed."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(audit_report_to_markdown(report), encoding="utf-8")


def degraded_report_node(state: AgentState) -> dict[str, Any]:
    """
    Produce a minimal AuditReport when repo/PDF unavailable or collection failed.
    Used after conditional edge from evidence_aggregator (error-handling path).
    """
    evidences_map = state.get("evidences") or {}
    dimensions = state.get("rubric_dimensions") or []
    repo_url = state.get("repo_url") or ""
    criteria_results: list[CriterionResult] = []
    for dim in dimensions:
        dim_id = dim.get("id", "unknown")
        dim_name = dim.get("name", dim_id)
        ev_list = evidences_map.get(dim_id, [])
        evidence_objs = [
            e if isinstance(e, Evidence) else Evidence(**e)
            for e in ev_list
            if isinstance(e, (Evidence, dict))
        ]
        remediation = "Re-run audit with valid repo URL and PDF path; fix input errors."
        criteria_results.append(
            CriterionResult(
                dimension_id=dim_id,
                dimension_name=dim_name,
                final_score=1,
                judge_opinions=[],
                dissent_summary="No judicial deliberation (degraded path: inputs missing or failed).",
                remediation=remediation,
            )
        )
    overall = 1.0
    executive_summary = (
        f"Audit of {repo_url}: degraded run. "
        "Repo or PDF unavailable or collection failed. No judge opinions. "
        "Re-run with valid inputs."
    )
    remediation_plan = "\n\n".join(
        f"**{c.dimension_name}**: {c.remediation}" for c in criteria_results
    ) or "No remediation plan."
    report = AuditReport(
        repo_url=repo_url,
        executive_summary=executive_summary.strip(),
        overall_score=overall,
        criteria=criteria_results,
        remediation_plan=remediation_plan,
    )
    return {"final_report": report}
