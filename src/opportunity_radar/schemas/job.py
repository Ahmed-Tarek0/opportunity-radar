from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class WorkMode(str, Enum):
    onsite = "onsite"
    hybrid = "hybrid"
    remote = "remote"
    unknown = "unknown"


class RemoteEligibility(str, Enum):
    worldwide = "worldwide"
    egypt_only = "egypt_only"
    region_restricted = "region_restricted"
    country_restricted = "country_restricted"
    not_applicable = "not_applicable"
    unknown = "unknown"


class EmploymentType(str, Enum):
    full_time = "full_time"
    part_time = "part_time"
    contract = "contract"
    internship = "internship"
    freelance = "freelance"
    unknown = "unknown"


class SeniorityLevel(str, Enum):
    intern = "intern"
    entry = "entry"
    junior = "junior"
    mid = "mid"
    senior = "senior"
    lead = "lead"
    unknown = "unknown"


class DateStatus(str, Enum):
    verified = "verified"
    estimated = "estimated"
    source_unavailable = "source_unavailable"
    unknown = "unknown"


def validate_url(url: str | None) -> str | None:
    """Validate that a URL uses HTTP/HTTPS only."""
    if not url:
        return None
    url = url.strip()
    if not re.match(r'^https?://', url, re.IGNORECASE):
        return None
    return url


class NormalizedJob(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    source_name: str
    source_job_id: str | None = None
    title: str
    company_name: str
    description: str | None = None
    source_url: str | None = None
    apply_url: str | None = None
    location_text: str | None = None
    country: str | None = None
    city: str | None = None
    work_mode: WorkMode = WorkMode.unknown
    remote_eligibility: RemoteEligibility = RemoteEligibility.unknown
    employment_type: EmploymentType = EmploymentType.unknown
    seniority_level: SeniorityLevel = SeniorityLevel.unknown
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    minimum_experience_years: float | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    posted_at: datetime | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    fetched_at: datetime | None = None
    date_status: DateStatus = DateStatus.unknown
    content_hash: str | None = None
    canonical_url: str | None = None
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
    is_demo: bool = False

    @field_validator("source_url", "apply_url", "canonical_url", mode="before")
    @classmethod
    def validate_url_field(cls, v: Any) -> Any:
        if isinstance(v, str):
            return validate_url(v)
        return v

    def unique_key(self) -> str:
        """Generate a deduplication key."""
        return f"{self.source_name}::{self.source_job_id or self.source_url or self.title}"
