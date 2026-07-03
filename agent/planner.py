"""
Execution Planner (spec section 4.2).

Same isolation principle as parser.py: only the structured Requirement
(already sanitized JSON, not raw dataset text) is sent to the model here.
"""

import json
import os
import re
import ollama
from typing import Optional

from models.schemas import Requirement, ExecutionPlan
from agent.constants import FALLBACK_STEPS

MODEL_NAME = os.environ.get("SUPROC_MODEL", "qwen3:1.7b")

PROMPT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "prompts", "planner_prompt.txt")

with open(PROMPT_PATH) as f:
    SYSTEM_PROMPT = f.read()


def _extract_json(text: str) -> Optional[dict]:
    text = text.strip()
    text = re.sub(r"^```(json)?", "", text.strip())
    text = re.sub(r"```$", "", text.strip())
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = text.strip()
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def create_plan(requirement: Requirement, max_retries: int = 2) -> ExecutionPlan:
    payload = requirement.model_dump_json()
    for attempt in range(max_retries + 1):
        response = ollama.chat(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": payload},
            ],
            options={"temperature": 0.1},
        )
        raw = response["message"]["content"]
        parsed = _extract_json(raw)
        if parsed is None:
            continue
        try:
            return ExecutionPlan(**parsed)
        except Exception:
            continue

    return ExecutionPlan(steps=FALLBACK_STEPS)
