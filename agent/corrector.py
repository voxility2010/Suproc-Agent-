"""
Correction loop (spec section 7).

Deterministic -- no LLM calls. Given an initial candidate pool (already
category/keyword-searched), this:
  1. filters by hard constraints
  2. scores + ranks the survivors
  3. takes the top N (requested_results)
  4. validates
  5. if validation fails because of specific bad candidates, drops them
     and promotes the next-best scored candidate from the remaining pool,
     then re-validates
  6. repeats up to MAX_ATTEMPTS times
  7. if it still can't produce `requested_results` valid candidates, it
     stops and returns whatever valid candidates it has, WITH an explicit
     "fewer than requested" explanation rather than inventing more.
"""

from typing import List, Dict, Any
from tools.filters import filter_by_constraints
from tools.scoring import calculate_match_score
from tools.validator import validate_recommendations
from tools.search import get_entity_details

MAX_ATTEMPTS = 3


def _build_candidate(record: Dict[str, Any], entity_type: str, requirement: Dict[str, Any],
                      failed_reasons: List[str]) -> Dict[str, Any]:
    score = calculate_match_score(record, requirement, failed_reasons)
    return {
        "entity_id": record["id"],
        "entity_type": entity_type,
        "record": record,
        "score": score,
        "evidence": score["explanation"],
        "constraints_checked": list(requirement.get("hard_constraints", {}).keys()),
        "constraints_failed": failed_reasons,
    }


def run_with_correction(all_candidates: List[Dict[str, Any]], entity_type: str,
                         requirement: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns:
      {
        "final_candidates": [...],       # Candidate-shaped dicts that passed validation
        "attempts": int,
        "validation_history": [ValidationResult dicts per attempt],
        "final_validation": ValidationResult dict,
        "shortfall_explanation": str or None,
      }
    """
    requested = requirement.get("hard_constraints", {})
    passed_records, failed_records = filter_by_constraints(all_candidates, requested)

    failed_reasons_by_id = {f["record"]["id"]: f["reasons"] for f in failed_records}

    # rank all passed records by score, best first
    scored_pool = []
    for r in passed_records:
        c = _build_candidate(r, entity_type, requirement, [])
        scored_pool.append(c)
    scored_pool.sort(key=lambda c: -c["score"]["total"])

    requested_results = requirement.get("requested_results", 3)
    validation_history = []
    attempt = 0
    working_set = scored_pool[:requested_results]
    remaining_pool = scored_pool[requested_results:]

    while attempt < MAX_ATTEMPTS:
        attempt += 1
        result = validate_recommendations(working_set, requirement, failed_reasons_by_id)
        validation_history.append(result)

        if result["passed"]:
            return {
                "final_candidates": working_set,
                "attempts": attempt,
                "validation_history": validation_history,
                "final_validation": result,
                "shortfall_explanation": None,
            }

        # Drop invalid candidates, promote next-best from remaining pool
        valid_ids = set(result["valid_candidate_ids"])
        working_set = [c for c in working_set if c["entity_id"] in valid_ids]

        while len(working_set) < requested_results and remaining_pool:
            working_set.append(remaining_pool.pop(0))

        if not remaining_pool and len(working_set) < requested_results:
            # nothing left to promote; one more validation pass then stop
            final_result = validate_recommendations(working_set, requirement, failed_reasons_by_id)
            validation_history.append(final_result)
            shortfall = (
                f"Only {len(final_result['valid_candidate_ids'])} valid {entity_type}(s) "
                f"could be found after {attempt} correction attempt(s), fewer than the "
                f"{requested_results} requested. All other candidates in the dataset failed "
                f"hard constraints or validation checks."
            )
            return {
                "final_candidates": [c for c in working_set if c["entity_id"] in final_result["valid_candidate_ids"]],
                "attempts": attempt,
                "validation_history": validation_history,
                "final_validation": final_result,
                "shortfall_explanation": shortfall,
            }

    # exhausted MAX_ATTEMPTS
    final_result = validation_history[-1]
    shortfall = None
    if not final_result["passed"]:
        shortfall = (
            f"Validation still failing after the maximum of {MAX_ATTEMPTS} correction attempts. "
            f"Returning best available valid candidates ({len(final_result['valid_candidate_ids'])} "
            f"of {requested_results} requested)."
        )
    return {
        "final_candidates": [c for c in working_set if c["entity_id"] in final_result["valid_candidate_ids"]],
        "attempts": attempt,
        "validation_history": validation_history,
        "final_validation": final_result,
        "shortfall_explanation": shortfall,
    }
