"""
Requirement Parser (spec section 4.1).

This is the ONLY place in the pipeline (besides planner.py) where the raw
user request text is sent to the LLM. Dataset record content is NEVER
concatenated into this prompt -- the parser only ever sees what the human
typed, which is why a malicious string sitting inside a supplier's
`description` field (see dataset/generate_dataset.py, SUP016) can't reach
the model at this stage at all.
"""

import json
import os
import re
import ollama
from typing import Optional

from models.schemas import Requirement

MODEL_NAME = os.environ.get("SUPROC_MODEL", "qwen3:1.7b")

PROMPT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "prompts", "parser_prompt.txt")

with open(PROMPT_PATH) as f:
    SYSTEM_PROMPT = f.read()
# Known certification vocabulary, derived from the actual dataset
# (dataset/suppliers.json). This is a deterministic safety net, NOT a
# replacement for the LLM's extraction -- it exists because a small model
# can inconsistently miss a named certification depending on phrasing,
# and spec 4.1 requires hard constraints are never silently dropped.
# It only ADDS a certification if the exact term appears in the user's
# raw text and the model didn't already capture it.
KNOWN_CERTIFICATIONS = ["food-grade", "FSSAI", "ISO9001", "ISO14001", "organic-certified", "RoHS"]
KNOWN_SKILLS = [
    "FSSAI compliance", "ISO audits", "LCA analysis", "biodegradable materials",
    "branding", "budget forecasting", "carbon footprint analysis", "contract negotiation",
    "cost optimization", "food-grade material testing", "logistics planning",
    "material science", "material sourcing", "quality audits", "route planning",
    "sustainable packaging design", "vendor evaluation", "vendor onboarding",
    "warehouse management",
]


def _augment_skills_from_text(user_request: str, requirement: Requirement) -> Requirement:
    text = user_request.lower()
    existing = requirement.hard_constraints.skills or []
    found = list(existing)
    for skill in KNOWN_SKILLS:
        if skill.lower() in text and skill not in found:
            found.append(skill)
    if found and found != existing:
        requirement.hard_constraints.skills = found
    return requirement

def _augment_certifications_from_text(user_request: str, requirement: Requirement) -> Requirement:
    text = user_request.lower()
    existing = requirement.hard_constraints.certifications or []
    found = list(existing)
    for cert in KNOWN_CERTIFICATIONS:
        if cert.lower() in text and cert not in found:
            found.append(cert)
    if found and found != existing:
        requirement.hard_constraints.certifications = found
        if requirement.ambiguities and "certifications" in requirement.ambiguities:
            requirement.ambiguities = [a for a in requirement.ambiguities if a != "certifications"]
    return requirement

def _extract_json(text: str) -> Optional[dict]:
    """Ollama models (especially with reasoning) sometimes wrap JSON in
    markdown fences or add stray text. Strip that defensively before
    parsing. This does NOT relax the requirement that the model's actual
    content be pure JSON -- it just protects against harmless formatting
    noise like ```json fences."""
    text = text.strip()
    text = re.sub(r"^```(json)?", "", text.strip())
    text = re.sub(r"```$", "", text.strip())
    # If there's a <think>...</think> block (qwen3 reasoning), drop it
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = text.strip()
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def parse_requirement(user_request: str, max_retries: int = 2) -> Requirement:
    """
    Calls the local Ollama model to convert natural language into a
    structured Requirement. Raises RuntimeError if the model fails to
    produce valid JSON after retries -- the agent must not silently
    fall back to a guessed/empty requirement.
    """
    last_error = None
    for attempt in range(max_retries + 1):
        response = ollama.chat(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_request},
            ],
            options={"temperature": 0.1},
        )
        raw = response["message"]["content"]
        parsed = _extract_json(raw)
        if parsed is None:
            last_error = f"attempt {attempt+1}: could not extract JSON from model output: {raw[:300]}"
            continue
        try:
            parsed_requirement = Requirement(**parsed)
            parsed_requirement = _augment_certifications_from_text(user_request, parsed_requirement)
            return parsed_requirement
        except Exception as e:
            last_error = f"attempt {attempt+1}: JSON did not match Requirement schema: {e}"
            continue

    raise RuntimeError(
        f"Requirement parser failed after {max_retries + 1} attempts. Last error: {last_error}"
    )
