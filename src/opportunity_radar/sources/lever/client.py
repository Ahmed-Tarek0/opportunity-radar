from __future__ import annotations

from datetime import UTC, datetime

import httpx

from ...config import get_settings
from ...logging_config import get_logger
from ...schemas.job import DateStatus, NormalizedJob, RemoteEligibility, WorkMode
from ...schemas.source import SourceRunResult, SourceStatus
from ..base import JobSource

logger = get_logger("sources.lever")

LEVER_API_URL = "https://api.lever.co/v0/postings/{company}"


class LeverSource(JobSource):
    """Lever job postings source.

    Uses the public Lever postings API. Requires LEVER_COMPANY_SLUGS.
    API docs: https://hire.lever.co/developer/postings
    """

    @property
    def source_name(self) -> str:
        return "lever"

    @property
    def display_name(self) -> str:
        return "Lever"

    def is_configured(self) -> bool:
        return bool(get_settings().lever_slugs_list)

    def is_enabled(self) -> bool:
        return get_settings().enable_lever_source

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
                message="Lever source is disabled. Set ENABLE_LEVER_SOURCE=true and LEVER_COMPANY_SLUGS.",
                started_at=started,
            )

        if not self.is_configured():
            return [], SourceRunResult(
                source_name=self.source_name,
                status=SourceStatus.not_configured,
                message="Lever requires LEVER_COMPANY_SLUGS (comma-separated company identifiers).",
                started_at=started,
            )

        slugs = settings.lever_slugs_list
        all_jobs: list[NormalizedJob] = []
        warnings: list[str] = []

        for slug in slugs[:5]:
            try:
                jobs = self._fetch_company(slug, queries, settings.request_timeout_seconds)
                all_jobs.extend(jobs)
            except Exception as exc:
                warnings.append(f"Lever '{slug}' failed: {type(exc).__name__}")

        completed = datetime.now(UTC)
        status = SourceStatus.success if (all_jobs or not warnings) else SourceStatus.failed
        if warnings and all_jobs:
            status = SourceStatus.partial

        return all_jobs, SourceRunResult(
            source_name=self.source_name,
            status=status,
            jobs_fetched=len(all_jobs),
            duration_seconds=(completed - started).total_seconds(),
            message=f"Lever: {len(all_jobs)} jobs from {len(slugs)} company board(s).",
            warnings=warnings,
            started_at=started,
            completed_at=completed,
        )

    def _fetch_company(self, slug: str, queries: list[str], timeout: int) -> list[NormalizedJob]:
        url = LEVER_API_URL.format(company=slug)
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url, params={"mode": "json"})
            response.raise_for_status()
            data = response.json()

        query_lower = [q.lower() for q in queries]
        jobs = []

        for raw in data:
            try:
                job = self._parse_posting(raw, slug)
                if not job:
                    continue
                if query_lower:
                    job_text = f"{job.title} {job.description or ''}".lower()
                    if not any(q in job_text for q in query_lower):
                        continue
                jobs.append(job)
            except Exception as exc:
                logger.debug("Lever parse error", extra={"error": str(exc)[:50]})

        return jobs

    def _parse_posting(self, raw: dict, slug: str) -> NormalizedJob | None:
        text_info = raw.get("text") or raw.get("title")
        if not text_info:
            return None

        job_id = raw.get("id", "")
        posting_url = raw.get("hostedUrl") or raw.get("applyUrl") or f"https://jobs.lever.co/{slug}/{job_id}"
        apply_url = raw.get("applyUrl") or posting_url

        # Location
        categories = raw.get("categories", {})
        location_text = categories.get("location")
        work_type = (categories.get("commitment") or "").lower()
        team = categories.get("team", "")

        # Work mode
        work_mode = WorkMode.unknown
        if location_text:
            loc_lower = location_text.lower()
            if "remote" in loc_lower:
                work_mode = WorkMode.remote
            elif "hybrid" in loc_lower:
                work_mode = WorkMode.hybrid

        # Created timestamp in ms
        posted_at = None
        created_at = raw.get("createdAt")
        if created_at:
            try:
                posted_at = datetime.fromtimestamp(int(created_at) / 1000, tz=UTC)
            except (ValueError, OSError):
                pass

        # Description
        description_data = raw.get("description", "")
        if isinstance(description_data, str):
            import re
            description = re.sub(r"<[^>]+>", " ", description_data).strip()[:5000]
        else:
            description = None

        return NormalizedJob(
            source_name=self.source_name,
            source_job_id=job_id,
            title=text_info,
            company_name=slug.replace("-", " ").title(),
            description=description,
            source_url=posting_url,
            apply_url=apply_url,
            location_text=location_text,
            work_mode=work_mode,
            remote_eligibility=RemoteEligibility.unknown,
            posted_at=posted_at,
            first_seen_at=datetime.now(UTC),
            last_seen_at=datetime.now(UTC),
            fetched_at=datetime.now(UTC),
            date_status=DateStatus.verified if posted_at else DateStatus.unknown,
            is_demo=False,
        )

    def search_jobs(self, queries, location=None, posted_after=None, max_results=50):
        _, result = self.fetch_jobs(queries, location, posted_after, max_results)
        return result
