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
        return True

    def is_enabled(self) -> bool:
        return get_settings().enable_linkedin_source

    def _build_headers(self) -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.google.com/",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
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

        cffi_session = None
        try:
            from curl_cffi import requests as cffi_requests

            cffi_session = cffi_requests.Session(impersonate="chrome124")
        except Exception:
            cffi_session = None

        for query in queries[:5]:
            try:
                jobs = self._fetch_for_query(
                    query=query,
                    location=location or "Egypt",
                    timeout=settings.request_timeout_seconds,
                    cffi_session=cffi_session,
                )
                all_jobs.extend(jobs)
                time.sleep(0.8)
            except SourceTimeoutError as exc:
                warnings.append(f"Timeout for query '{query}': {exc}")
                logger.warning("LinkedIn timeout", extra={"query": query})
            except SourceParseError as exc:
                warnings.append(f"Parse error for query '{query}': {exc}")
                logger.warning("LinkedIn parse error", extra={"query": query})
            except Exception as exc:
                warnings.append(f"Error for query '{query}': {type(exc).__name__}")
                logger.error("LinkedIn unexpected error", extra={"error": str(exc)[:100]})

        if cffi_session is not None:
            try:
                cffi_session.close()
            except Exception:
                pass

        completed = datetime.now(UTC)
        duration = (completed - started).total_seconds()

        if not all_jobs and warnings:
            status = SourceStatus.failed
            message = (
                "LinkedIn search returned no results. "
                "The public endpoint may be unavailable or blocking requests. "
                "This is expected; LinkedIn does not provide a stable public API."
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
        self,
        query: str,
        location: str,
        timeout: int,
        cffi_session: object | None = None,
    ) -> list[NormalizedJob]:
        settings = get_settings()
        lookback_seconds = max(86400, settings.job_lookback_days * 86400)
        tpr = f"r{lookback_seconds}"
        pages_to_fetch = min(settings.max_pages_per_source, 2)

        all_query_jobs: list[NormalizedJob] = []

        for page_idx in range(pages_to_fetch):
            start_offset = page_idx * 25
            params = {
                "keywords": query,
                "location": location,
                "f_TPR": tpr,
                "start": start_offset,
            }
            url = f"{LINKEDIN_JOBS_URL}?{urlencode(params)}"
            cffi_headers = {
                "Referer": "https://www.google.com/",
                "Accept-Language": "en-US,en;q=0.9",
            }

            page_jobs: list[NormalizedJob] | None = None

            if cffi_session is not None:
                try:
                    resp = cffi_session.get(url, headers=cffi_headers, timeout=timeout)
                    if resp.status_code == 429:
                        time.sleep(3)
                        resp = cffi_session.get(url, headers=cffi_headers, timeout=timeout)
                    if resp.status_code == 200 and len(resp.text) > 200:
                        parsed = parse_linkedin_jobs(resp.text, self.source_name)
                        if parsed is not None:
                            page_jobs = parsed
                except Exception as cffi_err:
                    logger.debug(
                        "curl_cffi LinkedIn attempt failed, falling back to httpx",
                        extra={"error": str(cffi_err)[:100]},
                    )

            if page_jobs is None:
                try:
                    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                        response = client.get(url, headers=self._build_headers())
                        if response.status_code == 429:
                            time.sleep(3)
                            response = client.get(url, headers=self._build_headers())
                        if response.status_code == 429:
                            if all_query_jobs:
                                break
                            raise SourceError(
                                self.source_name,
                                "Rate limited by LinkedIn",
                                category="rate_limit",
                            )
                        if response.status_code != 200:
                            if all_query_jobs:
                                break
                            raise SourceParseError(
                                self.source_name,
                                f"HTTP {response.status_code} from LinkedIn",
                                category="http_error",
                            )
                        page_jobs = parse_linkedin_jobs(response.text, self.source_name)
                except httpx.TimeoutException as exc:
                    if all_query_jobs:
                        break
                    raise SourceTimeoutError(
                        self.source_name,
                        f"Request timed out after {timeout}s",
                        category="timeout",
                    ) from exc

            if page_jobs:
                all_query_jobs.extend(page_jobs)
                if len(page_jobs) < 10:
                    break
                time.sleep(0.5)
            else:
                break

        return all_query_jobs

    def search_jobs(self, queries, location=None, posted_after=None, max_results=50):
        _, result = self.fetch_jobs(queries, location, posted_after, max_results)
        return result
