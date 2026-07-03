"""
search_entities / get_entity_details

These are pure Python. They NEVER receive raw LLM prompt text from a
dataset record's free-text fields and pass it back into another LLM call
unescaped -- retrieval is structured JSON in, structured JSON out. This is
the primary prompt-injection defense described in the README: a record's
`description` field (e.g. SUP016's injected instructions) is treated as
inert data, never as an instruction, anywhere in this file.
"""

import json
import os
from typing import List, Dict, Any, Optional

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dataset")

_ENTITY_FILES = {
    "supplier": "suppliers.json",
    "professional": "professionals.json",
    "project": "projects.json",
    "opportunity": "projects.json",
    "bounty": "projects.json",
    "procurement_request": "procurement_requests.json",
}


def _load(entity_type: str) -> List[Dict[str, Any]]:
    fname = _ENTITY_FILES.get(entity_type)
    if not fname:
        return []
    path = os.path.join(DATA_DIR, fname)
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def load_interactions() -> List[Dict[str, Any]]:
    path = os.path.join(DATA_DIR, "interactions.json")
    with open(path) as f:
        return json.load(f)


def search_entities(entity_type: str, category: Optional[str] = None,
                     keyword: Optional[str] = None,
                     location_contains: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Tool: search_entities (REQUIRED by spec section 4.3)

    Pure keyword/category/location search over the local dataset.
    Returns full records (not IDs only) so downstream tools don't need a
    second round trip for common fields, but get_entity_details remains
    the canonical single-record lookup.
    """
    records = _load(entity_type)
    results = []
    for r in records:
        if category and r.get("category", "").lower() != category.lower():
            continue
        if location_contains:
            loc = (r.get("location") or r.get("location_preference") or "").lower()
            if location_contains.lower() not in loc:
                continue
        if keyword:
            haystack = json.dumps(r).lower()
            if keyword.lower() not in haystack:
                continue
        results.append(r)
    return results


def get_entity_details(entity_id: str, entity_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Tool: get_entity_details (REQUIRED by spec section 4.3)

    Looks up a single record by ID. If entity_type is omitted, searches
    all known entity tables. Returns None if the entity does not exist --
    callers (validator, corrector) must treat that as "entity does not
    exist in dataset", never invent a placeholder record.
    """
    if entity_type:
        for r in _load(entity_type):
            if r.get("id") == entity_id:
                return r
        return None

    checked_files = set()
    for t, fname in _ENTITY_FILES.items():
        if fname in checked_files:
            continue
        checked_files.add(fname)
        for r in _load(t):
            if r.get("id") == entity_id:
                return r
    return None


def get_interaction_history(entity_id: str) -> List[Dict[str, Any]]:
    """
    Tool: get_interaction_history (OPTIONAL, spec section 4.3)

    Returns all interaction/reputation records for a given entity ID.
    Used by the ranking engine for the reputation component of the score.
    """
    return [i for i in load_interactions() if i.get("entity_id") == entity_id]


def check_availability(entity_id: str, entity_type: Optional[str] = None) -> Dict[str, Any]:
    """
    Tool: check_availability (OPTIONAL, spec section 4.3)

    Normalizes the various "is this thing usable right now" fields
    (status / availability) across entity types into one shape.
    """
    record = get_entity_details(entity_id, entity_type)
    if record is None:
        return {"entity_id": entity_id, "exists": False, "available": False}

    if "status" in record:
        available = record["status"] == "active" or record["status"] == "open"
        reason = f"status={record['status']}"
    elif "availability" in record:
        available = record["availability"] == "available"
        reason = f"availability={record['availability']}"
    else:
        available = True
        reason = "no availability field on record"

    return {"entity_id": entity_id, "exists": True, "available": available, "reason": reason}
