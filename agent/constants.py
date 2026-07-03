"""
Constants with zero external dependencies. Kept separate from planner.py
so that code paths which don't need the LLM (e.g. `app.py ask-json`,
and most of the automated test suite) never require the `ollama` package
to be installed at all.
"""

# Deterministic fallback plan -- used if the LLM planner fails after
# retries, so a formatting glitch in a small model's output doesn't stop
# the whole pipeline. The plan is descriptive text only; it does not
# change what the deterministic tools actually do.
FALLBACK_STEPS = [
    "Search the dataset for candidates matching the requested entity type and category",
    "Inspect candidate records for capacity, certifications, and location",
    "Filter out records that fail any hard constraint",
    "Rank remaining candidates using the transparent match-scoring formula",
    "Validate the top recommendations against the dataset",
    "Run correction if validation fails, up to 3 attempts",
    "Prepare the final response, draft outreach, and await human approval",
]
