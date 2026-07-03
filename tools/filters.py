"""
filter_by_constraints

Tool: filter_by_constraints (REQUIRED by spec section 4.3)

Applies every hard constraint present in the parsed Requirement to a list
of candidate records. This is pure Python -- no LLM judgment calls -- so
that "hard constraints must never be silently ignored" (spec 4.1) is
mechanically guaranteed rather than dependent on the model remembering to
check.

For each record we return whether it PASSED or FAILED, and exactly which
constraints were checked / which ones it failed. Nothing is dropped
silently -- failed records are returned too, with reasons, so the
validator and the response generator can report on them (spec: "Missing
information", "Risks or uncertainties").
"""

from typing import List, Dict, Any, Tuple

# Reasonable "is this South India" helper -- used only when the request
# says "South India" broadly rather than naming a specific state.
SOUTH_INDIA_STATES = ["karnataka", "tamil nadu", "kerala", "andhra pradesh", "telangana"]

# Unambiguous city -> state aliases for cities that appear in the dataset
# without their state name attached (e.g. record location = "Bangalore").
# This is intentionally a small, known list -- genuinely ambiguous location
# strings ("South", "south region") are NOT in here and will correctly
# fail to resolve, which is the deliberate ambiguous-location test case.
CITY_TO_STATE = {
    "bangalore": "karnataka", "bengaluru": "karnataka", "mysuru": "karnataka",
    "mangalore": "karnataka", "udupi": "karnataka", "belagavi": "karnataka",
    "karwar": "karnataka", "ballari": "karnataka",
    "chennai": "tamil nadu", "coimbatore": "tamil nadu", "madurai": "tamil nadu",
    "salem": "tamil nadu", "vellore": "tamil nadu", "hosur": "tamil nadu",
    "tiruchirappalli": "tamil nadu", "ooty": "tamil nadu",
    "kochi": "kerala", "kozhikode": "kerala", "thrissur": "kerala",
    "visakhapatnam": "andhra pradesh", "vijayawada": "andhra pradesh",
    "rajahmundry": "andhra pradesh", "tirupati": "andhra pradesh",
    "nellore": "andhra pradesh", "guntur": "andhra pradesh", "anantapur": "andhra pradesh",
    "hyderabad": "telangana", "warangal": "telangana",
}


def _resolve_state(loc: str) -> List[str]:
    """Returns states implied by a location string: explicit state names
    already in the string, plus any resolved from known city aliases."""
    states = [s for s in SOUTH_INDIA_STATES if s in loc]
    for city, state in CITY_TO_STATE.items():
        if city in loc and state not in states:
            states.append(state)
    return states


def _location_matches(record_location: str, wanted: List[str]) -> bool:
    if not record_location:
        return False
    loc = record_location.lower()
    resolved_states = _resolve_state(loc)
    for w in wanted:
        w_lower = w.lower()
        if w_lower == "south india":
            if resolved_states:
                return True
        elif w_lower in loc or w_lower in resolved_states:
            return True
    return False


def filter_by_constraints(records: List[Dict[str, Any]], hard_constraints: Dict[str, Any]
                           ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Returns (passed, failed_with_reasons).
    `failed_with_reasons` items look like: {"record": {...}, "reasons": [...]}
    """
    passed = []
    failed = []

    locations = hard_constraints.get("locations")
    certifications = hard_constraints.get("certifications")
    min_capacity = hard_constraints.get("minimum_capacity")
    max_delivery_days = hard_constraints.get("maximum_delivery_days")
    category = hard_constraints.get("category")
    min_budget = hard_constraints.get("min_budget")
    max_budget = hard_constraints.get("max_budget")
    max_deadline_days = hard_constraints.get("max_deadline_days")
    required_skills = hard_constraints.get("skills")

    for r in records:
        reasons = []

        if category and r.get("category") and r["category"].lower() != category.lower():
            reasons.append(f"category '{r.get('category')}' does not match required '{category}'")

        if locations:
            rec_loc = r.get("location") or r.get("location_preference") or ""
            if not _location_matches(rec_loc, locations):
                reasons.append(f"location '{rec_loc or 'missing'}' not in required {locations}")

        if certifications:
            rec_certs = r.get("certifications")
            if rec_certs is None:
                reasons.append("certification data missing on record (cannot confirm compliance)")
            else:
                missing = [c for c in certifications if c not in rec_certs]
                if missing:
                    reasons.append(f"missing certification(s): {missing}")

        if min_capacity is not None:
            cap = r.get("capacity")
            if cap is None:
                reasons.append("capacity data missing on record")
            elif cap < min_capacity:
                reasons.append(f"capacity {cap} below required minimum {min_capacity}")

        if max_delivery_days is not None:
            dd = r.get("delivery_days")
            if dd is None:
                reasons.append("delivery_days data missing on record")
            elif dd > max_delivery_days:
                reasons.append(f"delivery_days {dd} exceeds maximum {max_delivery_days}")

        if required_skills:
            rec_skills = r.get("skills")
            if rec_skills is None:
                reasons.append("skills data missing on record")
            else:
                missing_skills = [s for s in required_skills if s not in rec_skills]
                if missing_skills:
                    reasons.append(f"missing skill(s): {missing_skills}")

        if min_budget is not None and r.get("budget") is not None and r["budget"] < min_budget:
            reasons.append(f"budget {r['budget']} below minimum {min_budget}")
        if max_budget is not None and r.get("budget") is not None and r["budget"] > max_budget:
            reasons.append(f"budget {r['budget']} exceeds maximum {max_budget}")

        if max_deadline_days is not None and "delivery_days" not in r:
            # deadline_days is a project/procurement concept, not a supplier
            # one -- records that have delivery_days are supplier-shaped and
            # exempt from this check.
            dl = r.get("deadline_days")
            if dl is None:
                reasons.append("deadline_days data missing on record")
            elif dl > max_deadline_days:
                reasons.append(f"deadline_days {dl} exceeds maximum {max_deadline_days}")

        # status/availability -- inactive/closed records fail regardless of other fields
        status = r.get("status")
        if status in ("inactive", "closed"):
            reasons.append(f"record status is '{status}' (not currently active/open)")
        availability = r.get("availability")
        if availability == "unavailable":
            reasons.append("record availability is 'unavailable'")

        if reasons:
            failed.append({"record": r, "reasons": reasons})
        else:
            passed.append(r)

    return passed, failed
