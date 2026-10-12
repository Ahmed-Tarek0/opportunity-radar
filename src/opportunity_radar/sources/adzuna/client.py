from __future__ import annotations

from datetime import UTC, datetime

import httpx

from ...config import get_settings
from ...logging_config import get_logger
from ...schemas.job import DateStatus, NormalizedJob, RemoteEligibility, WorkMode
from ...schemas.source import SourceRunResult, SourceStatus
from ..base import JobSource

logger = get_logger("sources.adzuna")

ADZUNA_API_URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"


class AdzunaSource(JobSource):
    """Adzuna job search API source.

    Requires ADZUNA_APP_ID and ADZUNA_APP_KEY.
    API docs: https://developer.adzuna.com/
    """

    @property
    def source_name(self) -> str:
        return "adzuna"

    @property
    def display_name(self) -> str:
        return "Adzuna"

    def is_configured(self) -> bool:
        settings = get_settings()
        return bool(settings.adzuna_app_id and settings.adzuna_app_key)

    def is_enabled(self) -> bool:
        return get_settings().enable_adzuna_source

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
                message="Adzuna is disabled. Set ENABLE_ADZUNA_SOURCE=true and configure ADZUNA_APP_ID/KEY.",
                started_at=started,
            )

        if not self.is_configured():
            return [], SourceRunResult(
                source_name=self.source_name,
                status=SourceStatus.not_configured,
                message="Adzuna requires ADZUNA_APP_ID and ADZUNA_APP_KEY environment variables.",
                started_at=started,
            )

        all_jobs: list[NormalizedJob] = []
        warnings: list[str] = []

        for query in queries[:2]:
            try:
                jobs = self._search(
                    query=query,
                    country="gb",  # Use GB as proxy; Egypt coverage may be limited
                    timeout=settings.request_timeout_seconds,
                )
                all_jobs.extend(jobs)
            except Exception as exc:
                warnings.append(f"Adzuna query '{query}' failed: {type(exc).__name__}")
                logger.warning("Adzuna error", extra={"error": str(exc)[:100]})

        completed = datetime.now(UTC)
        return all_jobs, SourceRunResult(
            source_name=self.source_name,
            status=SourceStatus.success if all_jobs else SourceStatus.partial,
            jobs_fetched=len(all_jobs),
            duration_seconds=(completed - started).total_seconds(),
            message=f"Adzuna: {len(all_jobs)} jobs fetched.",
            warnings=warnings,
            started_at=started,
            completed_at=completed,
        )

    def _search(self, query: str, country: str, timeout: int) -> list[NormalizedJob]:
        settings = get_settings()
        url = ADZUNA_API_URL.format(country=country, page=1)
        params = {
            "app_id": settings.adzuna_app_id,
            "app_key": settings.adzuna_app_key,
            "results_per_page": 20,
            "what": query,
            "content-type": "application/json",
        }

        with httpx.Client(timeout=timeout) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        jobs = []
        for raw in data.get("results", []):
            try:
                job = self._parse_job(raw)
                if job:
                    jobs.append(job)
            except Exception:
                pass
        return jobs

    def _parse_job(self, raw: dict) -> NormalizedJob | None:
        title = raw.get("title")
        if not title:
            return None

        company_data = raw.get("company", {})
        company = company_data.get("display_name") or "Unknown Company"

        location_data = raw.get("location", {})
        location_text = location_data.get("display_name")

        redirect_url = raw.get("redirect_url")
        source_url = redirect_url

        # Date
        posted_at = None
        created = raw.get("created")
        if created:
            try:
                posted_at = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except ValueError:
                pass

        return NormalizedJob(
            source_name=self.source_name,
            source_job_id=str(raw.get("id", "")),
            title=title,
            company_name=company,
            description=raw.get("description"),
            source_url=source_url,
            apply_url=source_url,
            location_text=location_text,
            work_mode=WorkMode.unknown,
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
