from __future__ import annotations

from datetime import UTC, datetime

import httpx

from ...config import get_settings
from ...logging_config import get_logger
from ...schemas.job import DateStatus, NormalizedJob, RemoteEligibility, WorkMode
from ...schemas.source import SourceRunResult, SourceStatus
from ..base import JobSource

logger = get_logger("sources.greenhouse")

GREENHOUSE_API_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"


class GreenhouseSource(JobSource):
    """Greenhouse job board source.

    Requires board slugs configured in GREENHOUSE_BOARD_SLUGS.
    Each slug corresponds to a company's Greenhouse board.
    API docs: https://developers.greenhouse.io/job-board.html
    """

    @property
    def source_name(self) -> str:
        return "greenhouse"

    @property
    def display_name(self) -> str:
        return "Greenhouse"

    def is_configured(self) -> bool:
        return bool(get_settings().greenhouse_slugs_list)

    def is_enabled(self) -> bool:
        return get_settings().enable_greenhouse_source

    def fetch_jobs(
        self,
        queries: list[str],
        location: str | None = None,
        posted_after: datetime | None = None,
        max_results: int = 50,
    ) -> tuple[list[NormalizedJob], SourceRunResult]:
        settings = get_settings()
        started = datetime.now(UTC)

        if not self.is_enabled():
            return [], SourceRunResult(
                source_name=self.source_name,
                status=SourceStatus.disabled,
                message="Greenhouse source is disabled. Set ENABLE_GREENHOUSE_SOURCE=true and add GREENHOUSE_BOARD_SLUGS.",
                started_at=started,
            )

        if not self.is_configured():
            return [], SourceRunResult(
                source_name=self.source_name,
                status=SourceStatus.not_configured,
                message="Greenhouse requires GREENHOUSE_BOARD_SLUGS (comma-separated company slugs).",
                started_at=started,
            )

        slugs = settings.greenhouse_slugs_list
        all_jobs: list[NormalizedJob] = []
        warnings: list[str] = []

        for slug in slugs[:5]:
            try:
                jobs = self._fetch_board(slug, queries, settings.request_timeout_seconds)
                all_jobs.extend(jobs)
            except Exception as exc:
                warnings.append(f"Greenhouse board '{slug}' failed: {type(exc).__name__}")
                logger.warning("Greenhouse board error", extra={"slug": slug})

        completed = datetime.now(UTC)
        status = SourceStatus.success if all_jobs else (SourceStatus.failed if warnings else SourceStatus.success)
        if warnings and all_jobs:
            status = SourceStatus.partial

        return all_jobs, SourceRunResult(
            source_name=self.source_name,
            status=status,
            jobs_fetched=len(all_jobs),
            duration_seconds=(completed - started).total_seconds(),
            message=f"Greenhouse: {len(all_jobs)} jobs from {len(slugs)} board(s).",
            warnings=warnings,
            started_at=started,
            completed_at=completed,
        )

    def _fetch_board(self, slug: str, queries: list[str], timeout: int) -> list[NormalizedJob]:
        url = GREENHOUSE_API_URL.format(slug=slug)
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url, params={"content": "true"})
            response.raise_for_status()
            data = response.json()

        jobs_data = data.get("jobs", [])
        query_lower = [q.lower() for q in queries]

        jobs = []
        for raw in jobs_data:
            try:
                job = self._parse_job(raw, slug)
                if not job:
                    continue
                # Filter by query relevance
                if query_lower:
                    job_text = f"{job.title} {job.description or ''}".lower()
                    if not any(q in job_text for q in query_lower):
                        continue
                jobs.append(job)
            except Exception as exc:
                logger.debug("Greenhouse parse error", extra={"error": str(exc)[:50]})

        return jobs

    def _parse_job(self, raw: dict, slug: str) -> NormalizedJob | None:
        title = raw.get("title")
        if not title:
            return None

        job_id = str(raw.get("id", ""))
        source_url = raw.get("absolute_url") or f"https://boards.greenhouse.io/{slug}/jobs/{job_id}"

        # Location from offices
        offices = raw.get("offices", [])
        location_text = None
        country = None
        if offices:
            loc = offices[0]
            location_text = loc.get("name")
            country = loc.get("location") or loc.get("name")

        # Department
        departments = raw.get("departments", [])

        # Posted date
        posted_at = None
        updated_at_str = raw.get("updated_at")
        if updated_at_str:
            try:
                posted_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
            except ValueError:
                pass

        # Content/description
        content = raw.get("content", "")
        if isinstance(content, str):
            # Strip basic HTML tags
            import re
            content = re.sub(r"<[^>]+>", " ", content).strip()

        return NormalizedJob(
            source_name=self.source_name,
            source_job_id=f"{slug}::{job_id}",
            title=title,
            company_name=slug.replace("-", " ").title(),
            description=content[:5000] if content else None,
            source_url=source_url,
            apply_url=source_url,
            location_text=location_text,
            country=country,
            work_mode=WorkMode.unknown,
            remote_eligibility=RemoteEligibility.unknown,
            posted_at=posted_at,
            first_seen_at=datetime.now(UTC),
            last_seen_at=datetime.now(UTC),
            fetched_at=datetime.now(UTC),
            date_status=DateStatus.estimated if posted_at else DateStatus.unknown,
            is_demo=False,
        )

    def search_jobs(self, queries, location=None, posted_after=None, max_results=50):
        _, result = self.fetch_jobs(queries, location, posted_after, max_results)
        return result
