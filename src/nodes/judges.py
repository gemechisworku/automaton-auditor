"""
Judicial layer: Prosecutor, Defense, Tech Lead. Each returns {"opinions": [JudicialOpinion, ...]}.
Uses .with_structured_output(JudicialOpinion); distinct prompts per persona. API Contracts §4, §7.
"""

from __future__ import annotations

import os
from typing import Any, Literal

from src.state import AgentState, Evidence, JudicialOpinion

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


def _invoke_judge_for_dimension(
    dimension: dict[str, Any],
    evidence_list: list[Evidence],
    judge_name: _JUDGE,
    system_prompt: str,
) -> JudicialOpinion | None:
    """Call LLM once for one dimension; return JudicialOpinion or None on failure (after retries)."""
    dim_id = dimension.get("id", "unknown")
    dim_name = dimension.get("name", dim_id)
    forensic = dimension.get("forensic_instruction", "")
    success = dimension.get("success_pattern", "")
    failure = dimension.get("failure_pattern", "")

    evidence_text = _evidence_summary(evidence_list)
    user_content = f"""Criterion: {dim_id} ({dim_name})
Forensic instruction: {forensic}
Success pattern: {success}
Failure pattern: {failure}

Evidence collected:
{evidence_text}

Provide your opinion: score (1-5), argument, and cited_evidence (reference the evidence items above)."""

    from langchain_core.messages import HumanMessage, SystemMessage

    llm = _get_llm()
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_content)]
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            opinion = llm.invoke(messages)
            if not isinstance(opinion, JudicialOpinion):
                continue
            # Ensure judge field matches persona (LLM might return wrong one)
            return JudicialOpinion(
                judge=judge_name,
                criterion_id=dim_id,
                score=max(1, min(5, opinion.score)),
                argument=opinion.argument or "",
                cited_evidence=opinion.cited_evidence if isinstance(opinion.cited_evidence, list) else [],
            )
        except Exception:
            if attempt == max_attempts - 1:
                return None
            continue
    return None


def _run_judge_node(state: AgentState, judge_name: _JUDGE, system_prompt: str) -> dict[str, Any]:
    """Common logic: iterate dimensions, get evidence, call LLM, collect opinions."""
    dimensions = state.get("rubric_dimensions") or []
    evidences_map = state.get("evidences") or {}
    opinions: list[JudicialOpinion] = []

    for dim in dimensions:
        dim_id = dim.get("id", "unknown")
        evidence_list = evidences_map.get(dim_id, [])
        if not isinstance(evidence_list, list):
            evidence_list = []
        # Ensure Evidence instances (state may have dicts after serialization)
        evidence_objs = [
            e if isinstance(e, Evidence) else Evidence(**e)
            for e in evidence_list
            if isinstance(e, (Evidence, dict))
        ]

        opinion = _invoke_judge_for_dimension(dim, evidence_objs, judge_name, system_prompt)
        if opinion is not None:
            opinions.append(opinion)
        # On parse failure we skip this dimension (no invalid append)

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
