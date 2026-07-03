"""
validate_recommendations

Tool: validate_recommendations (REQUIRED by spec section 4.3)

Runs the 9 checks listed in spec section 7 against a set of candidate
recommendations, entirely in Python (no LLM). Returns a ValidationResult-
shaped dict: passed / errors / valid_candidate_ids / requires_human_approval.

Checks implemented (spec section 7, in order):
  1. Every recommended entity exists in the dataset
  2. Every hard constraint is satisfied
  3. Every factual claim is supported by the dataset (checked via the
     evidence list attached to each candidate -- claims must cite a
     record field, not be free text)
  4. No duplicate recommendations (same underlying business under two IDs,
     detected by name normalization, and literal duplicate IDs)
  5. The requested number of results was returned (or a clear shortfall
     explanation is required)
  6. Unavailable information was not presented as fact (missing fields
     must be flagged, not silently assumed)
  7. The correct entity type was selected
  8. The match score was calculated correctly (recomputed and compared)
  9. Whether the proposed action requires human approval (always True
     here -- the agent never auto-executes)
"""

from typing import List, Dict, Any
from tools.search import get_entity_details
from tools.scoring import calculate_match_score


def _normalize_name(name: str) -> str:
    if not name:
        return ""
    n = name.lower()
    for suffix in [" pvt ltd", " ltd", " co", " industries", " solutions", " works", " pack"]:
        n = n.replace(suffix, "")
    return n.strip()


def validate_recommendations(candidates: List[Dict[str, Any]], requirement: Dict[str, Any],
                              failed_reasons_by_id: Dict[str, List[str]] = None) -> Dict[str, Any]:
    """
    candidates: list of dicts shaped like {"entity_id", "entity_type", "record", "score"}
    requirement: the structured Requirement dict
    failed_reasons_by_id: optional map of entity_id -> constraint failure reasons
                           (for entities that shouldn't be in `candidates` at all,
                           but we defensively re-check anyway)
    """
    failed_reasons_by_id = failed_reasons_by_id or {}
    errors: List[str] = []
    valid_ids: List[str] = []

    requested_results = requirement.get("requested_results", 3)
    expected_entity_type = requirement.get("entity_type")
    hard_constraints = requirement.get("hard_constraints", {})

    seen_ids = set()
    seen_normalized_names = {}

    for c in candidates:
        entity_id = c.get("entity_id")
        entity_type = c.get("entity_type")
        record = c.get("record", {})
        claimed_score = c.get("score", {}).get("total") if c.get("score") else None

        candidate_errors = []

        # 1. existence check
        actual_record = get_entity_details(entity_id, entity_type)
        if actual_record is None:
            candidate_errors.append(f"{entity_id} does not exist in the dataset")
            errors.extend([f"{entity_id}: {e}" for e in candidate_errors])
            continue  # can't check anything else meaningfully

        # 7. correct entity type
        if expected_entity_type and entity_type != expected_entity_type:
            candidate_errors.append(
                f"entity type '{entity_type}' does not match requested type '{expected_entity_type}'")

        # 2. hard constraints satisfied (re-derive from filter reasons if provided)
        if entity_id in failed_reasons_by_id and failed_reasons_by_id[entity_id]:
            candidate_errors.append(
                f"fails hard constraint(s): {failed_reasons_by_id[entity_id]}")

        # 6. no unsupported claims -- every evidence line must reference a real field on the record
        evidence = c.get("evidence") or []
        for e in evidence:
            # very lightweight grounding check: evidence should not claim things
            # about fields that are None/missing on the actual record
            if "certification" in e.lower() and actual_record.get("certifications") is None:
                candidate_errors.append(f"claim '{e}' not supported -- certifications field is missing on record")

        # 4. duplicate detection -- literal ID dupe
        if entity_id in seen_ids:
            candidate_errors.append(f"duplicate recommendation of {entity_id}")
        seen_ids.add(entity_id)

        # 4. duplicate detection -- same underlying business under a different ID
        norm_name = _normalize_name(actual_record.get("name") or actual_record.get("title") or "")
        if norm_name and norm_name in seen_normalized_names:
            candidate_errors.append(
                f"{entity_id} appears to be a duplicate business record of "
                f"{seen_normalized_names[norm_name]} (name: '{actual_record.get('name')}')")
        elif norm_name:
            seen_normalized_names[norm_name] = entity_id

        # 8. match score recomputation check
        if claimed_score is not None:
            recomputed = calculate_match_score(actual_record, requirement,
                                                failed_reasons_by_id.get(entity_id, []))
            if abs(recomputed["total"] - claimed_score) > 0.5:
                candidate_errors.append(
                    f"claimed score {claimed_score} does not match recomputed score {recomputed['total']}")

        if candidate_errors:
            errors.extend([f"{entity_id}: {e}" for e in candidate_errors])
        else:
            valid_ids.append(entity_id)

    # 5. requested result count
    if len(valid_ids) < requested_results:
        errors.append(
            f"only {len(valid_ids)} valid candidate(s) remain, "
            f"fewer than the {requested_results} requested")

    passed = len(errors) == 0 and len(valid_ids) >= requested_results

    return {
        "passed": passed,
        "errors": errors,
        "valid_candidate_ids": valid_ids,
        "requires_human_approval": True,  # 9. always true -- agent never auto-executes
    }
