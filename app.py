"""
Suproc Agent CLI.

Usage:
    python app.py ask "We need 3 biodegradable food-packaging suppliers..."
    python app.py ask "..." --model qwen3:1.7b
    python app.py ask-json requirement.json     # bypass LLM parser/planner for testing

Run `ollama pull qwen3:1.7b` (or qwen3:4b) before using `ask`.
"""

import json
import os
import sys
import typer
from typing import Optional

from models.schemas import Requirement, AgentResponse

app = typer.Typer(add_completion=False)


def _print_response(resp: AgentResponse):
    print("\n" + "=" * 78)
    print("INTERPRETED REQUIREMENT")
    print("=" * 78)
    print(json.dumps(resp.interpreted_requirement.model_dump(), indent=2))

    print("\n" + "=" * 78)
    print("PLAN FOLLOWED")
    print("=" * 78)
    for i, step in enumerate(resp.plan_followed, 1):
        print(f"  {i}. {step}")

    print("\n" + "=" * 78)
    print(f"RECOMMENDED MATCHES ({len(resp.recommended_matches)})")
    print("=" * 78)
    for c in resp.recommended_matches:
        name = c.record.get("name") or c.record.get("title") or c.record.get("business") or c.entity_id
        print(f"\n  [{c.entity_id}] {name}")
        print(f"    Match score: {c.score.total}/100")
        for line in c.score.explanation:
            print(f"      - {line}")

    print("\n" + "=" * 78)
    print("CONSTRAINTS CHECKED")
    print("=" * 78)
    print(" ", resp.constraints_checked or "(none specified)")

    print("\n" + "=" * 78)
    print("MISSING INFORMATION")
    print("=" * 78)
    if resp.missing_information:
        for m in resp.missing_information:
            print("  -", m)
    else:
        print("  (none)")

    print("\n" + "=" * 78)
    print("RISKS / UNCERTAINTIES")
    print("=" * 78)
    if resp.risks_or_uncertainties:
        for r in resp.risks_or_uncertainties:
            print("  -", r)
    else:
        print("  (none)")

    print("\n" + "=" * 78)
    print("VALIDATION STATUS")
    print("=" * 78)
    print(f"  Passed: {resp.validation_status.passed}")
    print(f"  Correction attempts used: {resp.correction_attempts}")
    if resp.validation_status.errors:
        print("  Remaining errors:")
        for e in resp.validation_status.errors:
            print("   -", e)

    print("\n" + "=" * 78)
    print("DRAFT OUTREACH")
    print("=" * 78)
    if resp.draft_outreach:
        for d in resp.draft_outreach:
            print(f"\n  --- to {d['recipient']} ({d['entity_id']}) ---")
            print("  " + d["draft"].replace("\n", "\n  "))
    else:
        print("  (none prepared)")

    print("\n" + "=" * 78)
    print("RECOMMENDED NEXT ACTION")
    print("=" * 78)
    print(" ", resp.recommended_next_action)
    print(f"  Human approval required: {resp.human_approval_required}")
    print("=" * 78 + "\n")


@app.command()
def ask(request: str, model: Optional[str] = typer.Option(None, help="Ollama model name, e.g. qwen3:1.7b")):
    """Full pipeline: NL request -> LLM parser -> LLM planner -> deterministic agent -> response."""
    if model:
        os.environ["SUPROC_MODEL"] = model

    # imported here so `ask-json` doesn't require ollama to be installed/running
    from agent.parser import parse_requirement
    from agent.planner import create_plan
    from agent.response_generator import generate_response

    print(f"Parsing requirement with model={os.environ.get('SUPROC_MODEL', 'qwen3:1.7b')}...")
    requirement = parse_requirement(request)

    print("Creating execution plan...")
    plan = create_plan(requirement)

    print("Running search, filter, ranking, validation, correction...")
    response = generate_response(requirement, plan.steps)

    _print_response(response)


@app.command()
def ask_json(requirement_path: str, plan_path: Optional[str] = None):
    """
    Bypass the LLM parser/planner entirely -- feed a pre-built Requirement
    JSON file (matching models.schemas.Requirement) straight into the
    deterministic pipeline. Used for repeatable testing without Ollama.
    """
    from agent.response_generator import generate_response
    from agent.constants import FALLBACK_STEPS

    with open(requirement_path) as f:
        req_data = json.load(f)
    requirement = Requirement(**req_data)

    if plan_path:
        with open(plan_path) as f:
            steps = json.load(f)["steps"]
    else:
        steps = FALLBACK_STEPS

    response = generate_response(requirement, steps)
    _print_response(response)


if __name__ == "__main__":
    app()
