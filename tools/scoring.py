"""
calculate_match_score

Tool: calculate_match_score (OPTIONAL, spec section 4.3, but implemented
as an explicit callable tool -- not buried in a class -- so it shows up
as its own step in the execution trace).

Implements the weighted scoring method from spec section 6:
  - Product/skill relevance:      30%
  - Location suitability:         20%
  - Hard-constraint compliance:   25%
  - Availability/capacity:        15%
  - Reputation/previous perf:     10%

Every sub-score is derived from a concrete dataset field or from the
output of filter_by_constraints / get_interaction_history -- never
guessed. `explanation` lists exactly which evidence produced each number,
which is what spec section 6 means by "the calculation and supporting
evidence must be clearly explained."
"""

from typing import Dict, Any, List
from tools.search import get_interaction_history

WEIGHTS = {
    "relevance": 30,
    "location": 20,
    "constraint_compliance": 25,
    "availability_capacity": 15,
    "reputation": 10,
}


def _relevance_score(record: Dict[str, Any], requirement: Dict[str, Any]) -> (float, str):
    """Keyword overlap between the requirement's objective and whichever
    text-bearing fields the record actually has."""
    objective = (requirement.get("objective") or "").lower()

    text_parts = []
    fields_used = []
    for key in ("products", "skills"):
        val = record.get(key)
        if val:
            text_parts.append(" ".join(val) if isinstance(val, list) else str(val))
            fields_used.append(key)
    for key in ("description", "requirement", "title", "role", "category"):
        val = record.get(key)
        if val:
            text_parts.append(str(val))
            fields_used.append(key)

    combined_text = " ".join(text_parts).lower()
    hits = sum(1 for word in objective.split() if len(word) > 3 and word in combined_text)
    max_possible = max(1, sum(1 for word in objective.split() if len(word) > 3))
    frac = min(1.0, hits / max_possible) if max_possible else 0.5
    score = round(frac * WEIGHTS["relevance"], 1)
    fields_note = "/".join(fields_used) if fields_used else "no text fields available"
    return score, f"{hits}/{max_possible} objective keywords matched against {fields_note}"


def _location_score(record: Dict[str, Any], hard_constraints: Dict[str, Any]) -> (float, str):
    wanted = hard_constraints.get("locations")
    loc = record.get("location") or record.get("location_preference") or ""
    if not wanted:
        return WEIGHTS["location"] * 0.5, "no location constraint given, neutral score applied"
    from tools.filters import _location_matches
    if _location_matches(loc, wanted):
        return WEIGHTS["location"], f"location '{loc}' matches requirement {wanted}"
    return 0.0, f"location '{loc}' does not match requirement {wanted}"


def _constraint_score(failed_reasons: List[str]) -> (float, str):
    if not failed_reasons:
        return WEIGHTS["constraint_compliance"], "all hard constraints satisfied (0 violations)"
    return 0.0, f"{len(failed_reasons)} hard constraint violation(s): {failed_reasons}"

def _availability_capacity_score(record: Dict[str, Any], hard_constraints: Dict[str, Any]) -> (float, str):
    cap = record.get("capacity")
    min_cap = hard_constraints.get("minimum_capacity")
    availability = record.get("availability")
    status = record.get("status")

    if status in ("inactive", "closed"):
        return 0.0, f"status is '{status}'"
    if availability == "unavailable":
        return 0.0, "availability is 'unavailable'"

    if cap is not None:
        if min_cap:
            ratio = min(1.5, cap / min_cap) / 1.5
            score = round(ratio * WEIGHTS["availability_capacity"], 1)
            return score, f"capacity {cap} vs required minimum {min_cap}"
        return WEIGHTS["availability_capacity"] * 0.75, f"capacity {cap}, no minimum specified"

    if availability is not None:
        if availability == "available":
            return WEIGHTS["availability_capacity"], "availability = 'available'"
        elif availability == "busy":
            return WEIGHTS["availability_capacity"] * 0.4, "availability = 'busy' (partially available)"
        return WEIGHTS["availability_capacity"] * 0.2, f"availability = '{availability}'"

    if status == "open":
        return WEIGHTS["availability_capacity"] * 0.85, "status = 'open'"

    return WEIGHTS["availability_capacity"] * 0.4, "no capacity/availability/status field on this record type, partial credit only"


def _reputation_score(entity_id: str, fallback_rating: float = None) -> (float, str):
    history = get_interaction_history(entity_id)
    ratings = [h["rating_given"] for h in history if h.get("rating_given") is not None]
    if ratings:
        avg = sum(ratings) / len(ratings)
        score = round((avg / 5.0) * WEIGHTS["reputation"], 1)
        return score, f"avg rating {avg:.1f}/5 across {len(ratings)} interaction record(s)"
    if fallback_rating is not None:
        score = round((fallback_rating / 5.0) * WEIGHTS["reputation"], 1)
        return score, f"no interaction history; using listed rating {fallback_rating}/5"
    return WEIGHTS["reputation"] * 0.3, "no interaction history and no listed rating; low-confidence default"


def calculate_match_score(record: Dict[str, Any], requirement: Dict[str, Any],
                           failed_constraint_reasons: List[str] = None) -> Dict[str, Any]:
    """
    Returns a dict matching models.schemas.MatchScoreBreakdown.
    """
    failed_constraint_reasons = failed_constraint_reasons or []
    hard_constraints = requirement.get("hard_constraints", {})

    rel_score, rel_note = _relevance_score(record, requirement)
    loc_score, loc_note = _location_score(record, hard_constraints)
    con_score, con_note = _constraint_score(failed_constraint_reasons)
    avail_score, avail_note = _availability_capacity_score(record, hard_constraints)
    rep_score, rep_note = _reputation_score(record.get("id"), record.get("rating"))

    total = round(rel_score + loc_score + con_score + avail_score + rep_score, 1)

    return {
        "relevance": rel_score,
        "location": loc_score,
        "constraint_compliance": con_score,
        "availability_capacity": avail_score,
        "reputation": rep_score,
        "total": total,
        "explanation": [rel_note, loc_note, con_note, avail_note, rep_note],
    }
