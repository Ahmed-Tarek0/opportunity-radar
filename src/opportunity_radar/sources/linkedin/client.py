from __future__ import annotations

import time
from datetime import UTC, datetime
from urllib.parse import urlencode

import httpx

from ...config import get_settings
from ...exceptions import SourceError, SourceParseError, SourceTimeoutError
from ...logging_config import get_logger
from ...schemas.job import NormalizedJob
from ...schemas.source import SourceRunResult, SourceStatus
from ..base import JobSource
from .parser import parse_linkedin_jobs

logger = get_logger("sources.linkedin")

LINKEDIN_JOBS_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"


class LinkedInSource(JobSource):
    """LinkedIn public job listings source.

    NOTE: LinkedIn does not provide an official public job search API.
    This connector uses the public guest job search endpoint which is
    subject to change. It may be blocked or return incomplete results.
    Status is reported honestly via SourceRunResult.
    """

    @property
    def source_name(self) -> str:
        return "linkedin"

    @property
    def display_name(self) -> str:
        return "LinkedIn"

    def is_configured(self) -> bool:
        return True  # No API key required for public search

    def is_enabled(self) -> bool:
        return get_settings().enable_linkedin_source

    def _build_headers(self) -> dict[str, str]:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
        }

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
                message="LinkedIn source is disabled in settings.",
                started_at=started,
            )

        all_jobs: list[NormalizedJob] = []
        warnings: list[str] = []

        # Query top 4 search queries to fetch a healthy pool of jobs without triggering rate limits
        for query in queries[:4]:
            try:
                jobs = self._fetch_for_query(
                    query=query,
                    location=location or "Egypt",
                    timeout=settings.request_timeout_seconds,
                )
                all_jobs.extend(jobs)
                time.sleep(0.5)  # be polite
            except SourceTimeoutError as exc:
                warnings.append(f"Timeout for query '{query}': {exc}")
                logger.warning("LinkedIn timeout", extra={"query": query})
            except SourceParseError as exc:
                warnings.append(f"Parse error for query '{query}': {exc}")
                logger.warning("LinkedIn parse error", extra={"query": query})
            except Exception as exc:
                warnings.append(f"Error for query '{query}': {type(exc).__name__}")
                logger.error("LinkedIn unexpected error", extra={"error": str(exc)[:100]})

        completed = datetime.now(UTC)
        duration = (completed - started).total_seconds()

        # Determine status
        if not all_jobs and warnings:
            status = SourceStatus.failed
            message = (
                "LinkedIn search returned no results. "
                "The public endpoint may be unavailable or blocking requests. "
                "This is expected; LinkedIn does not provide a stable public API. "
                "Enable Demo Mode to see example jobs."
            )
        elif warnings:
            status = SourceStatus.partial
            message = f"LinkedIn: {len(all_jobs)} jobs found with some warnings."
        else:
            status = SourceStatus.success
            message = f"LinkedIn: {len(all_jobs)} jobs fetched."

        return all_jobs, SourceRunResult(
            source_name=self.source_name,
            status=status,
            jobs_fetched=len(all_jobs),
            duration_seconds=duration,
            message=message,
            warnings=warnings,
            started_at=started,
            completed_at=completed,
        )

    def _fetch_for_query(
        self, query: str, location: str, timeout: int
    ) -> list[NormalizedJob]:
        params = {
            "keywords": query,
            "location": location,
            "f_TPR": "r604800",  # last 7 days
            "start": 0,
        }
        url = f"{LINKEDIN_JOBS_URL}?{urlencode(params)}"

        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                response = client.get(url, headers=self._build_headers())
                if response.status_code == 429:
                    raise SourceError(
                        self.source_name,
                        "Rate limited by LinkedIn",
                        category="rate_limit",
                    )
                if response.status_code != 200:
                    raise SourceParseError(
                        self.source_name,
                        f"HTTP {response.status_code} from LinkedIn",
                        category="http_error",
                    )
                return parse_linkedin_jobs(response.text, self.source_name)
        except httpx.TimeoutException as exc:
            raise SourceTimeoutError(
                self.source_name,
                f"Request timed out after {timeout}s",
                category="timeout",
            ) from exc

    def search_jobs(self, queries, location=None, posted_after=None, max_results=50):
        _, result = self.fetch_jobs(queries, location, posted_after, max_results)
        return result
