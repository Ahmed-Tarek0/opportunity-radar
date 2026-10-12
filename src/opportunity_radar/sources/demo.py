from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_DNS, uuid4, uuid5

from ..config import get_settings
from ..logging_config import get_logger
from ..schemas.job import (
    DateStatus,
    EmploymentType,
    NormalizedJob,
    RemoteEligibility,
    SeniorityLevel,
    WorkMode,
)
from ..schemas.source import SourceRunResult, SourceStatus
from .base import JobSource

logger = get_logger("sources.demo")

# Look for demo_jobs.json by traversing up to repo root where data/ directory is located
DEMO_DATA_PATH = Path(__file__).resolve().parents[3] / "data" / "demo_jobs.json"


class DemoSource(JobSource):
    """Demo job source that loads fixture data."""

    @property
    def source_name(self) -> str:
        return "demo"

    @property
    def display_name(self) -> str:
        return "Demo (Fixture Data)"

    def is_configured(self) -> bool:
        return DEMO_DATA_PATH.exists()

    def is_enabled(self) -> bool:
        return get_settings().demo_mode

    def _load_jobs(self) -> list[dict]:
        try:
            with open(DEMO_DATA_PATH) as f:
                return json.load(f)
        except Exception as exc:
            logger.error("Failed to load demo jobs", extra={"error": str(exc)})
            return []

    def fetch_jobs(
        self,
        queries: list[str],
        location: str | None = None,
        posted_after: datetime | None = None,
        max_results: int = 50,
    ) -> tuple[list[NormalizedJob], SourceRunResult]:
        started = datetime.now(UTC)
        raw_jobs = self._load_jobs()
        jobs = []

        for raw in raw_jobs:
            try:
                # Parse posted_at
                posted_at = None
                if raw.get("posted_at"):
                    try:
                        posted_at = datetime.fromisoformat(
                            raw["posted_at"].replace("Z", "+00:00")
                        )
                    except ValueError:
                        pass

                raw_id = str(raw.get("id", ""))
                job_id = uuid5(NAMESPACE_DNS, raw_id) if raw_id else uuid4()
                job = NormalizedJob(
                    id=job_id,
                    source_name="demo",
                    source_job_id=raw.get("source_job_id", raw_id),
                    title=raw["title"],
                    company_name=raw["company_name"],
                    description=raw.get("description"),
                    source_url=raw.get("source_url"),
                    apply_url=raw.get("apply_url"),
                    location_text=raw.get("location_text"),
                    country=raw.get("country"),
                    city=raw.get("city"),
                    work_mode=WorkMode(raw.get("work_mode", "unknown")),
                    remote_eligibility=RemoteEligibility(raw.get("remote_eligibility", "unknown")),
                    employment_type=EmploymentType(raw.get("employment_type", "unknown")),
                    seniority_level=SeniorityLevel(raw.get("seniority_level", "unknown")),
                    required_skills=raw.get("required_skills", []),
                    preferred_skills=raw.get("preferred_skills", []),
                    responsibilities=raw.get("responsibilities", []),
                    minimum_experience_years=raw.get("minimum_experience_years"),
                    salary_min=raw.get("salary_min"),
                    salary_max=raw.get("salary_max"),
                    salary_currency=raw.get("salary_currency"),
                    posted_at=posted_at,
                    first_seen_at=started,
                    last_seen_at=started,
                    fetched_at=started,
                    date_status=DateStatus(raw.get("date_status", "unknown")),
                    is_demo=True,
                )
                jobs.append(job)
            except Exception as exc:
                logger.warning("Failed to parse demo job", extra={"error": str(exc)})

        # Apply freshness filter if requested
        if posted_after:
            filtered = []
            for job in jobs:
                if job.posted_at and job.posted_at >= posted_after:
                    filtered.append(job)
                elif not job.posted_at:
                    filtered.append(job)  # keep undated demo jobs
            jobs = filtered

        completed = datetime.now(UTC)
        duration = (completed - started).total_seconds()

        return jobs, SourceRunResult(
            source_name="demo",
            status=SourceStatus.success,
            jobs_fetched=len(jobs),
            duration_seconds=duration,
            message=f"Loaded {len(jobs)} demo job fixtures. These are synthetic examples, not real listings.",
            started_at=started,
            completed_at=completed,
        )

    def search_jobs(self, queries, location=None, posted_after=None, max_results=50):
        _, result = self.fetch_jobs(queries, location, posted_after, max_results)
        return result
