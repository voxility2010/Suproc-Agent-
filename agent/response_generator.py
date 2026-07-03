"""
Response Generator (spec section 9).

Orchestrates: search -> correction loop (filter+score+validate+correct) ->
draft outreach -> assemble the final structured AgentResponse.

No LLM calls happen here -- this is glue code over the deterministic
tools plus the outputs of parser.py / planner.py.
"""

from typing import List, Dict, Any
from models.schemas import Requirement, AgentResponse, ValidationResult, Candidate, MatchScoreBreakdown
from tools.search import search_entities
from tools.outreach import draft_outreach
from agent.corrector import run_with_correction


def _gather_candidates(requirement: Requirement) -> List[Dict[str, Any]]:
    # category is intentionally NOT used as a search filter here -- the LLM
    # parser fills it with free-text wording that won't exactly match the
    # dataset's fixed category strings. It still feeds relevance scoring
    # in tools/scoring.py, just not this hard gate.
    return search_entities(entity_type=requirement.entity_type)


def generate_response(requirement: Requirement, plan_steps: List[str]) -> AgentResponse:
    req_dict = requirement.model_dump()
    all_candidates = _gather_candidates(requirement)

    correction_result = run_with_correction(all_candidates, requirement.entity_type, req_dict)

    final_candidates_raw = correction_result["final_candidates"]
    final_validation = correction_result["final_validation"]

    candidates: List[Candidate] = []
    outreach_drafts = []
    missing_information = []
    risks = []

    for c in final_candidates_raw:
        score_breakdown = MatchScoreBreakdown(**c["score"])
        candidates.append(Candidate(
            entity_id=c["entity_id"],
            entity_type=c["entity_type"],
            record=c["record"],
            score=score_breakdown,
            constraints_checked=c.get("constraints_checked", []),
            constraints_failed=c.get("constraints_failed", []),
            evidence=c.get("evidence", []),
        ))
        if c["record"].get("certifications") is None:
            missing_information.append(f"{c['entity_id']}: certification documentation not on file")
        if c["record"].get("capacity") is None:
            missing_information.append(f"{c['entity_id']}: capacity not on file")
        if c["score"]["reputation"] < 3.0:
            risks.append(f"{c['entity_id']}: limited or no interaction history to confirm reputation")

        outreach_drafts.append(draft_outreach(c["record"], req_dict))

    if requirement.ambiguities:
        missing_information.extend(requirement.ambiguities)
    if requirement.conflicts:
        risks.extend([f"conflicting requirement: {c}" for c in requirement.conflicts])
    if correction_result["shortfall_explanation"]:
        risks.append(correction_result["shortfall_explanation"])

    if candidates:
        ids = ", ".join(c.entity_id for c in candidates)
        next_action = f"Send a procurement enquiry to {ids}. Status: Awaiting user approval."
    else:
        next_action = (
            "No valid candidates could be confirmed against the dataset and hard constraints. "
            "Recommended action: relax a hard constraint, or manually review the dataset. "
            "Status: No action to approve."
        )

    validation_status = ValidationResult(
        passed=final_validation["passed"],
        errors=final_validation["errors"],
        valid_candidate_ids=final_validation["valid_candidate_ids"],
        requires_human_approval=True,
    )

    constraints_checked = [k for k, v in req_dict.get("hard_constraints", {}).items() if v is not None]

    return AgentResponse(
        interpreted_requirement=requirement,
        plan_followed=plan_steps,
        recommended_matches=candidates,
        constraints_checked=constraints_checked,
        missing_information=missing_information,
        risks_or_uncertainties=risks,
        recommended_next_action=next_action,
        draft_outreach=outreach_drafts if outreach_drafts else None,
        validation_status=validation_status,
        human_approval_required=True,
        correction_attempts=correction_result["attempts"],
    )
