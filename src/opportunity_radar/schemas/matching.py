from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EligibilityStatus(str, Enum):
    eligible = "eligible"
    likely_ineligible = "likely_ineligible"
    unknown = "unknown"


class ScoreComponent(BaseModel):
    name: str
    weight: float
    earned_points: float
    max_points: float
    reason: str


class EvidenceCitation(BaseModel):
    claim: str
    cv_evidence: str | None = None
    job_evidence: str | None = None
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class MatchResult(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    profile_id: UUID
    job_id: UUID
    match_score: int = Field(ge=0, le=100)
    score_breakdown: list[ScoreComponent] = Field(default_factory=list)
    matched_skills: list[str] = Field(default_factory=list)
    missing_required_skills: list[str] = Field(default_factory=list)
    missing_preferred_skills: list[str] = Field(default_factory=list)
    uncertain_requirements: list[str] = Field(default_factory=list)
    experience_alignment: str | None = None
    title_alignment: str | None = None
    work_location_alignment: str | None = None
    eligibility_status: EligibilityStatus = EligibilityStatus.unknown
    eligibility_reasons: list[str] = Field(default_factory=list)
    evidence_citations: list[EvidenceCitation] = Field(default_factory=list)
    explanation: str | None = None
    suggested_next_action: str | None = None
    matching_version: str = "1.0.0"
    created_at: datetime | None = None
    used_semantic_matching: bool = False
    used_llm_explanation: bool = False
    fallback_used: bool = False
