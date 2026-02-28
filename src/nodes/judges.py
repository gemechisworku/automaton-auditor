"""
Judicial layer: Prosecutor, Defense, Tech Lead. Each returns {"opinions": [JudicialOpinion, ...]}.
Uses .with_structured_output(JudicialOpinion); distinct prompts per persona. API Contracts §4, §7.
Retry/error-handling for malformed LLM output; criterion-aware prompts with rubric metadata.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Literal

from pydantic import ValidationError

from src.state import AgentState, Evidence, JudicialOpinion

logger = logging.getLogger(__name__)

_JUDGE = Literal["Prosecutor", "Defense", "TechLead"]

_PROSECUTOR_SYSTEM = """You are the Prosecutor in a technical audit. Your philosophy: "Trust No One. Assume Vibe Coding."
Scrutinize the evidence for gaps, security flaws, and laziness.
- Prefer score 1-2 when evidence is missing, contradictory, or shows serious flaws (e.g. linear pipeline, no reducers, os.system with user input).
- Only score 3 or above when evidence clearly supports the success pattern; otherwise argue for lower scores.
Score scale: 1 = Vibe Coder / serious flaws, 3 = Competent, 5 = Master Thinker / exemplary.
You must respond with a valid JudicialOpinion: judge="Prosecutor", criterion_id, score (1-5), argument, cited_evidence (list of short strings referencing the evidence)."""

_DEFENSE_SYSTEM = """You are the Defense Attorney in a technical audit. Your philosophy: "Reward Effort and Intent. Spirit of the Law."
Highlight effort, intent, and workarounds. Argue for higher scores based on understanding and process even if implementation is imperfect.
- Reward partial success and stated intent; consider workarounds and incremental progress.
- When the success pattern is partially met, score 3 or 4; when intent is clear and effort evident, you may argue for 5.
Score scale: 1 = Vibe Coder, 3 = Competent, 5 = Master Thinker.
You must respond with a valid JudicialOpinion: judge="Defense", criterion_id, score (1-5), argument, cited_evidence (list of short strings referencing the evidence)."""

_TECH_LEAD_SYSTEM = """You are the Tech Lead in a technical audit. Your philosophy: "Does it actually work? Is it maintainable?"
Evaluate soundness, cleanliness, and viability. Be the tie-breaker; provide a realistic score (1, 3, or 5) and technical remediation.
- Focus on maintainability, clarity, and whether the implementation is sound and workable in practice.
- For architecture/graph criteria, your assessment carries highest weight; be explicit about fan-out, fan-in, and reducers.
Score scale: 1 = Vibe Coder, 3 = Competent, 5 = Master Thinker.
You must respond with a valid JudicialOpinion: judge="TechLead", criterion_id, score (1-5), argument, cited_evidence (list of short strings referencing the evidence)."""


def _get_llm():
    """Return chat model with structured output binding. Uses OPENAI_API_KEY."""
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        raise RuntimeError("Install langchain-openai for Judge nodes (pip install langchain-openai)")
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("Set OPENAI_API_KEY for Judge nodes")
    # Lower temperature for more consistent scores across runs (VAR-1)
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.1)
    return llm.with_structured_output(JudicialOpinion)


def _evidence_summary(evidences: list[Evidence]) -> str:
    """Summarize evidence list for prompt."""
    parts = []
    for i, e in enumerate(evidences[:15], 1):
        content = (e.content or "")[:500]
        parts.append(f"[{i}] goal={e.goal}; found={e.found}; location={e.location}; rationale={e.rationale}; confidence={e.confidence}; content={content}")
    return "\n".join(parts) if parts else "(no evidence)"


def _synthesis_hint_for_dimension(dimension: dict[str, Any], synthesis_rules: dict[str, str]) -> str:
    """Return a one-line hint for the judge so evaluations are criterion-aware and debuggable."""
    dim_id = dimension.get("id", "")
    dim_name = (dimension.get("name") or "").lower()
    if not synthesis_rules:
        return ""
    hints = []
    if "architecture" in dim_name or "graph" in dim_name or "orchestration" in dim_id:
        h = synthesis_rules.get("functionality_weight", "")
        if h:
            hints.append(f"Tech Lead weight: {h[:150]}.")
    if "security" in dim_id or "safe" in dim_id:
        h = synthesis_rules.get("security_override", "")
        if h:
            hints.append(f"Security rule: {h[:120]}.")
    if hints:
        return " Synthesis (for your awareness): " + " ".join(hints)
    return ""


def _invoke_judge_for_dimension(
    dimension: dict[str, Any],
    evidence_list: list[Evidence],
    judge_name: _JUDGE,
    system_prompt: str,
    synthesis_rules: dict[str, str] | None = None,
) -> JudicialOpinion:
    """
    Call LLM for one dimension with retry/error-handling. Returns JudicialOpinion; on parse
    failure after retries returns a fallback opinion so the dimension remains criterion-aware.
    """
    dim_id = dimension.get("id", "unknown")
    dim_name = dimension.get("name", dim_id)
    forensic = dimension.get("forensic_instruction", "")
    success = dimension.get("success_pattern", "")
    failure = dimension.get("failure_pattern", "")
    judicial_logic = dimension.get("judicial_logic", "")
    synthesis_rules = synthesis_rules or {}
    synthesis_hint = _synthesis_hint_for_dimension(dimension, synthesis_rules)

    evidence_text = _evidence_summary(evidence_list)
    levels = dimension.get("levels") or []
    level_instruction = ""
    if levels:
        level_instruction = "\nThis criterion uses point-based levels. Choose the level that best fits the evidence:\n"
        for i, lev in enumerate(levels):
            score_val = len(levels) - i if i < len(levels) else 1
            level_instruction += f"- Score {score_val}: {lev.get('name', lev.get('id', ''))} ({lev.get('points', 0)} pts) — {lev.get('description', '')[:200]}\n"
        level_instruction += "Provide your opinion: score (1-4 for 4 levels, where 4=best), argument, and cited_evidence.\n\n"

    user_content = f"""Criterion being evaluated — id: {dim_id}, name: {dim_name}
Forensic instruction: {forensic}
Success pattern: {success}
Failure pattern: {failure}
{f'Judicial logic for this criterion: {judicial_logic}' if judicial_logic else ''}{synthesis_hint}

{level_instruction}
Evidence collected:
{evidence_text}

Provide your opinion for this criterion only: score (1-5), argument, and cited_evidence (reference the evidence items above)."""

    from langchain_core.messages import HumanMessage, SystemMessage

    llm = _get_llm()
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_content)]
    max_attempts = 3
    last_error: Exception | None = None
    for attempt in range(max_attempts):
        try:
            opinion = llm.invoke(messages)
            if not isinstance(opinion, JudicialOpinion):
                last_error = ValueError("LLM did not return JudicialOpinion")
                continue
            return JudicialOpinion(
                judge=judge_name,
                criterion_id=dim_id,
                score=max(1, min(5, opinion.score)),
                argument=opinion.argument or "",
                cited_evidence=opinion.cited_evidence if isinstance(opinion.cited_evidence, list) else [],
            )
        except ValidationError as e:
            last_error = e
            logger.warning("Judge %s criterion %s attempt %s: ValidationError %s", judge_name, dim_id, attempt + 1, e)
        except Exception as e:
            last_error = e
            logger.warning("Judge %s criterion %s attempt %s: %s", judge_name, dim_id, attempt + 1, e)
    # Fallback: valid JudicialOpinion so dimension is not dropped; Chief Justice can still synthesize
    return JudicialOpinion(
        judge=judge_name,
        criterion_id=dim_id,
        score=3,
        argument=f"Structured output parse failure after {max_attempts} retries; neutral score. Last error: {last_error!s}"[:500],
        cited_evidence=[],
    )


def _load_synthesis_rules(state: AgentState) -> dict[str, str]:
    """Load synthesis_rules from rubric JSON for criterion-aware judge prompts."""
    import json
    from pathlib import Path
    rubric_path = state.get("rubric_path") or "rubric.json"
    path = Path(rubric_path)
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("synthesis_rules", {})
    except Exception:
        return {}


def _run_judge_node(state: AgentState, judge_name: _JUDGE, system_prompt: str) -> dict[str, Any]:
    """Common logic: iterate dimensions, get evidence, call LLM with criterion metadata, collect opinions."""
    dimensions = state.get("rubric_dimensions") or []
    evidences_map = state.get("evidences") or {}
    synthesis_rules = _load_synthesis_rules(state)
    opinions: list[JudicialOpinion] = []

    for dim in dimensions:
        dim_id = dim.get("id", "unknown")
        evidence_list = evidences_map.get(dim_id, [])
        if not isinstance(evidence_list, list):
            evidence_list = []
        evidence_objs = [
            e if isinstance(e, Evidence) else Evidence(**e)
            for e in evidence_list
            if isinstance(e, (Evidence, dict))
        ]

        opinion = _invoke_judge_for_dimension(
            dim, evidence_objs, judge_name, system_prompt, synthesis_rules
        )
        opinions.append(opinion)

    return {"opinions": opinions}


def prosecutor_node(state: AgentState) -> dict[str, Any]:
    """Prosecutor persona: adversarial; argue low when evidence warrants. Returns {"opinions": [JudicialOpinion, ...]}."""
    return _run_judge_node(state, "Prosecutor", _PROSECUTOR_SYSTEM)


def defense_node(state: AgentState) -> dict[str, Any]:
    """Defense persona: forgiving; reward effort and intent. Returns {"opinions": [JudicialOpinion, ...]}."""
    return _run_judge_node(state, "Defense", _DEFENSE_SYSTEM)


def tech_lead_node(state: AgentState) -> dict[str, Any]:
    """Tech Lead persona: pragmatic; soundness and maintainability. Returns {"opinions": [JudicialOpinion, ...]}."""
    return _run_judge_node(state, "TechLead", _TECH_LEAD_SYSTEM)
