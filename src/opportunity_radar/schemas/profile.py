from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class EvidenceType(str, Enum):
    explicit = "explicit"
    project = "project"
    experience = "experience"
    inferred = "inferred"


class SeniorityLevel(str, Enum):
    intern = "intern"
    entry = "entry"
    junior = "junior"
    mid = "mid"
    senior = "senior"
    lead = "lead"
    unknown = "unknown"


class Skill(BaseModel):
    name: str = Field(..., description="Normalized skill name")
    original: str = Field(..., description="Original spelling from CV")
    category: str | None = None
    evidence_snippet: str | None = None
    evidence_type: EvidenceType = EvidenceType.explicit
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class WorkExperience(BaseModel):
    title: str
    employer: str | None = None
    start_date: str | None = None  # ISO date string or descriptive
    end_date: str | None = None  # ISO date string, "present", or descriptive
    description: str | None = None
    technologies: list[str] = Field(default_factory=list)
    evidence: str | None = None
    duration_months_estimate: int | None = None


class Project(BaseModel):
    name: str
    description: str | None = None
    role: str | None = None
    stack: list[str] = Field(default_factory=list)
    evidence: str | None = None


class Education(BaseModel):
    degree: str | None = None
    institution: str | None = None
    graduation_year: int | None = None
    graduation_date: str | None = None
    field_of_study: str | None = None


class Certification(BaseModel):
    name: str
    issuer: str | None = None
    year: int | None = None


class TargetTitle(BaseModel):
    title: str
    rationale: str | None = None
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class LocationPreference(BaseModel):
    include_egypt: bool = True
    include_worldwide_remote: bool = True
    preferred_cities: list[str] = Field(default_factory=list)
    additional_countries: list[str] = Field(default_factory=list)


class EmploymentPreferences(BaseModel):
    full_time: bool = True
    part_time: bool = False
    contract: bool = False
    internship: bool = False
    on_site: bool = True
    hybrid: bool = True
    remote: bool = True


class CandidateProfile(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    full_name: str | None = None
    headline: str | None = None
    summary: str | None = None
    skills: list[Skill] = Field(default_factory=list)
    experiences: list[WorkExperience] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    target_titles: list[TargetTitle] = Field(default_factory=list)
    seniority_estimate: SeniorityLevel = SeniorityLevel.unknown
    years_experience_estimate: float | None = None
    location_preference: LocationPreference = Field(default_factory=LocationPreference)
    employment_preferences: EmploymentPreferences = Field(default_factory=EmploymentPreferences)
    profile_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    fields_needing_confirmation: list[str] = Field(default_factory=list)
    source_file_hash: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    is_demo: bool = False

    @field_validator("skills", mode="before")
    @classmethod
    def validate_skills(cls, v: Any) -> Any:
        if isinstance(v, list):
            return [s for s in v if s]  # filter None values
        return v

    def skill_names(self) -> list[str]:
        return [s.name.lower() for s in self.skills]

    def primary_title(self) -> str:
        if self.target_titles:
            return self.target_titles[0].title
        if self.experiences:
            return self.experiences[0].title
        return "Software Developer"
