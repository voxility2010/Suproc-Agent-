"""
draft_outreach

Tool: draft_outreach (OPTIONAL, spec section 4.3)

Prepares an outreach message draft for a validated candidate. This tool
NEVER sends anything -- it has no network/email capability at all, by
design, so "the agent must not automatically send messages" (spec
section 8) is enforced structurally, not just by prompt instruction.
"""

from typing import Dict, Any


def draft_outreach(record: Dict[str, Any], requirement: Dict[str, Any]) -> Dict[str, str]:
    entity_name = record.get("name") or record.get("title") or record.get("business") or record.get("id")
    objective = requirement.get("objective", "a procurement requirement")
    hard_constraints = requirement.get("hard_constraints", {})

    detail_lines = []
    if hard_constraints.get("minimum_capacity"):
        detail_lines.append(f"an initial order of approximately {hard_constraints['minimum_capacity']} units")
    if hard_constraints.get("maximum_delivery_days"):
        detail_lines.append(f"delivery within {hard_constraints['maximum_delivery_days']} days")
    if hard_constraints.get("certifications"):
        detail_lines.append(f"certification in: {', '.join(hard_constraints['certifications'])}")

    detail_text = "; ".join(detail_lines) if detail_lines else "the requirements outlined below"

    body = (
        f"Subject: Procurement Enquiry - {objective}\n\n"
        f"Dear {entity_name},\n\n"
        f"We are reaching out regarding {objective}. We are evaluating suppliers/partners "
        f"who can support {detail_text}.\n\n"
        f"Could you confirm current availability, certification documentation, and lead times "
        f"for an order of this scale? We would appreciate a response at your earliest convenience "
        f"so we can proceed with next steps.\n\n"
        f"Regards,\n"
        f"[Your name / business name]\n\n"
        f"--- DRAFT ONLY. Not sent. Requires human review and approval before sending. ---"
    )

    return {"entity_id": record.get("id"), "recipient": entity_name, "draft": body}
