from __future__ import annotations

from datetime import UTC, datetime

import httpx

from ...config import get_settings
from ...exceptions import SourceParseError, SourceTimeoutError
from ...logging_config import get_logger
from ...schemas.job import DateStatus, EmploymentType, NormalizedJob, RemoteEligibility, WorkMode
from ...schemas.source import SourceRunResult, SourceStatus
from ..base import JobSource

logger = get_logger("sources.remoteok")

REMOTEOK_API_URL = "https://remoteok.com/api"


class RemoteOKSource(JobSource):
    """Remote OK job source using their public JSON API.

    Remote OK provides a public JSON feed at https://remoteok.com/api
    Docs: https://remoteok.com/api (as verified via their published endpoint)
    Rate limiting: be respectful with requests.
    """

    @property
    def source_name(self) -> str:
        return "remoteok"

    @property
    def display_name(self) -> str:
        return "Remote OK"

    def is_configured(self) -> bool:
        return True  # Public API, no key needed

    def is_enabled(self) -> bool:
        return get_settings().enable_remoteok_source

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
                message="Remote OK source is disabled.",
                started_at=started,
            )

        try:
            jobs = self._fetch_all_jobs(
                queries=queries,
                posted_after=posted_after,
                timeout=settings.request_timeout_seconds,
                max_results=max_results,
            )
            completed = datetime.now(UTC)
            return jobs, SourceRunResult(
                source_name=self.source_name,
                status=SourceStatus.success,
                jobs_fetched=len(jobs),
                duration_seconds=(completed - started).total_seconds(),
                message=f"Remote OK: {len(jobs)} jobs fetched.",
                started_at=started,
                completed_at=completed,
            )
        except SourceTimeoutError as exc:
            completed = datetime.now(UTC)
            return [], SourceRunResult(
                source_name=self.source_name,
                status=SourceStatus.failed,
                message=f"Remote OK timed out: {exc}",
                error_category="timeout",
                started_at=started,
                completed_at=completed,
            )
        except Exception as exc:
            completed = datetime.now(UTC)
            logger.error("Remote OK error", extra={"error": str(exc)[:100]})
            return [], SourceRunResult(
                source_name=self.source_name,
                status=SourceStatus.failed,
                message=f"Remote OK fetch failed: {type(exc).__name__}. Check network connectivity.",
                error_category="fetch_error",
                started_at=started,
                completed_at=completed,
            )

    def _fetch_all_jobs(
        self,
        queries: list[str],
        posted_after: datetime | None,
        timeout: int,
        max_results: int,
    ) -> list[NormalizedJob]:
        headers = {
            "User-Agent": "OpportunityRadar/0.1 (portfolio project; contact via github)",
            "Accept": "application/json",
        }

        data = None
        # Try curl_cffi first for fast and cloudflare-friendly fetch
        try:
            from curl_cffi import requests as cffi_requests
            cffi_resp = cffi_requests.get(
                REMOTEOK_API_URL,
                impersonate="chrome124",
                timeout=timeout,
            )
            if cffi_resp.status_code == 200:
                data = cffi_resp.json()
        except Exception as cffi_exc:
            logger.debug("Remote OK curl_cffi fallback", extra={"error": str(cffi_exc)[:80]})

        if data is None:
            try:
                with httpx.Client(timeout=timeout) as client:
                    response = client.get(REMOTEOK_API_URL, headers=headers)
                    if response.status_code != 200:
                        raise SourceParseError(
                            self.source_name,
                            f"HTTP {response.status_code} from Remote OK",
                        )
                    data = response.json()
            except httpx.TimeoutException as exc:
                raise SourceTimeoutError(self.source_name, "Timeout") from exc
            except Exception as exc:
                raise SourceParseError(self.source_name, str(exc)) from exc

        # First element is metadata, skip it
        job_list = [item for item in data if isinstance(item, dict) and item.get("id")]

        jobs = []
        query_lower = [q.lower() for q in queries]

        for raw in job_list[:200]:  # process up to 200, filter by relevance
            try:
                job = self._parse_job(raw)
                if not job:
                    continue

                # Filter by freshness
                if posted_after and job.posted_at:
                    if job.posted_at < posted_after:
                        continue

                # Filter by relevance to queries
                if query_lower:
                    job_text = f"{job.title} {' '.join(job.required_skills)}".lower()
                    tags_text = " ".join(raw.get("tags", [])).lower()
                    all_text = f"{job_text} {tags_text}"
                    keywords = {w for q in query_lower for w in q.split() if len(w) > 3 and w not in {"the", "and", "for", "with", "engineer", "specialist"}}
                    # Must match the full query phrase OR at least 2 distinct domain keywords
                    matches_phrase = any(q in all_text for q in query_lower)
                    matching_kws = [kw for kw in keywords if kw in all_text]
                    if not (matches_phrase or len(matching_kws) >= 2):
                        continue

                jobs.append(job)
                if len(jobs) >= max_results:
                    break
            except Exception as exc:
                logger.debug("RemoteOK parse error", extra={"error": str(exc)[:50]})

        return jobs

    def _parse_job(self, raw: dict) -> NormalizedJob | None:
        title = raw.get("position") or raw.get("title")
        if not title:
            return None

        company = raw.get("company") or "Unknown Company"
        source_job_id = str(raw.get("id", "")) or str(raw.get("slug", ""))
        source_url = raw.get("url")
        if source_url and not source_url.startswith("http"):
            source_url = f"https://remoteok.com{source_url}"

        # Parse epoch timestamp
        posted_at = None
        epoch = raw.get("epoch")
        if epoch:
            try:
                posted_at = datetime.fromtimestamp(int(epoch), tz=UTC)
            except (ValueError, OSError):
                pass

        # Skills from tags
        tags = raw.get("tags", []) or []
        skills = [t for t in tags if isinstance(t, str)]

        # Salary
        salary_min = raw.get("salary_min")
        salary_max = raw.get("salary_max")
        if isinstance(salary_min, str):
            try:
                salary_min = float(salary_min.replace(",", ""))
            except ValueError:
                salary_min = None
        if isinstance(salary_max, str):
            try:
                salary_max = float(salary_max.replace(",", ""))
            except ValueError:
                salary_max = None

        return NormalizedJob(
            source_name=self.source_name,
            source_job_id=source_job_id,
            title=title,
            company_name=company,
            description=raw.get("description"),
            source_url=source_url,
            apply_url=raw.get("apply_url") or source_url,
            location_text="Remote (Worldwide)",
            work_mode=WorkMode.remote,
            remote_eligibility=RemoteEligibility.worldwide,  # RemoteOK is worldwide remote
            employment_type=EmploymentType.full_time,
            required_skills=skills,
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency="USD" if (salary_min or salary_max) else None,
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
