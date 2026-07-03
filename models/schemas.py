"""
Pydantic schemas shared across the agent, tools, and CLI.
Keeping these centralized is what gives the pipeline "structured inputs
and outputs" between the LLM and the deterministic tool layer.
"""

from __future__ import annotations
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class HardConstraints(BaseModel):
    locations: Optional[List[str]] = None
    certifications: Optional[List[str]] = None
    minimum_capacity: Optional[int] = None
    maximum_delivery_days: Optional[int] = None
    category: Optional[str] = None
    min_budget: Optional[int] = None
    max_budget: Optional[int] = None
    max_deadline_days: Optional[int] = None
    skills: Optional[List[str]] = None


class Preferences(BaseModel):
    sustainable_materials: Optional[bool] = None
    startup_friendly: Optional[bool] = None
    prefer_high_rating: Optional[bool] = None
    other: Optional[Dict[str, Any]] = None


class Requirement(BaseModel):
    """Structured output of the Requirement Parser (Step 4.1 of the spec)."""
    objective: str
    entity_type: str = Field(description="supplier | professional | project | procurement_request")
    hard_constraints: HardConstraints = Field(default_factory=HardConstraints)
    preferences: Preferences = Field(default_factory=Preferences)
    requested_results: int = 3
    ambiguities: Optional[List[str]] = None  # things the parser wasn't sure about
    conflicts: Optional[List[str]] = None    # contradictory requirements it noticed


class ExecutionPlan(BaseModel):
    """Output of the Planner (Step 4.2 of the spec)."""
    steps: List[str]


class MatchScoreBreakdown(BaseModel):
    relevance: float = 0.0
    location: float = 0.0
    constraint_compliance: float = 0.0
    availability_capacity: float = 0.0
    reputation: float = 0.0
    total: float = 0.0
    explanation: List[str] = Field(default_factory=list)


class Candidate(BaseModel):
    entity_id: str
    entity_type: str
    record: Dict[str, Any]
    score: Optional[MatchScoreBreakdown] = None
    constraints_checked: Optional[List[str]] = None
    constraints_failed: Optional[List[str]] = None
    evidence: Optional[List[str]] = None


class ValidationResult(BaseModel):
    passed: bool
    errors: List[str] = Field(default_factory=list)
    valid_candidate_ids: List[str] = Field(default_factory=list)
    requires_human_approval: bool = True


class AgentResponse(BaseModel):
    interpreted_requirement: Requirement
    plan_followed: List[str]
    recommended_matches: List[Candidate]
    constraints_checked: List[str]
    missing_information: List[str]
    risks_or_uncertainties: List[str]
    recommended_next_action: str
    draft_outreach: Optional[List[Dict[str, str]]] = None
    validation_status: ValidationResult
    human_approval_required: bool = True
    correction_attempts: int = 0
