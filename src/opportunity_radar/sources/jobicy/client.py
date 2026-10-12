from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlencode

from ...config import get_settings
from ...exceptions import SourceParseError, SourceTimeoutError
from ...logging_config import get_logger
from ...schemas.job import DateStatus, EmploymentType, NormalizedJob, RemoteEligibility, WorkMode
from ...schemas.source import SourceRunResult, SourceStatus
from ..base import JobSource

logger = get_logger("sources.jobicy")

JOBICY_API_URL = "https://jobicy.com/api/v2/remote-jobs"


class JobicySource(JobSource):
    """Jobicy.com remote job source using their public JSON API.

    API docs: https://jobicy.com/api/v2/remote-jobs
    Supports keyword search, geo, and industry/tag filtering.
    No API key required. All jobs are remote.
    """

    @property
    def source_name(self) -> str:
        return "jobicy"

    @property
    def display_name(self) -> str:
        return "Jobicy"

    def is_configured(self) -> bool:
        return True  # Public API, no key needed

    def is_enabled(self) -> bool:
        return get_settings().enable_jobicy_source

    def fetch_jobs(
        self,
        queries: list[str],
        location: str | None = None,
        posted_after: datetime | None = None,
        max_results: int = 50,
    ) -> tuple[list[NormalizedJob], SourceRunResult]:
        started = datetime.now(UTC)

        if not self.is_enabled():
            return [], SourceRunResult(
                source_name=self.source_name,
                status=SourceStatus.disabled,
                message="Jobicy source is disabled.",
                started_at=started,
            )

        all_jobs: list[NormalizedJob] = []
        seen_ids: set[str] = set()
        warnings: list[str] = []

        # Jobicy tag mapping — only search specific targeted tags, do NOT search generic 'developer'
        tag_map = {
            "data science": "data-science",
            "data scientist": "data-science",
            "data analyst": "analytics",
            "data analytics": "analytics",
            "data": "data",
            "analytics": "analytics",
            "machine learning": "python",
            "deep learning": "python",
            "python": "python",
        }

        # Collect relevant tags from queries
        tags_to_search: set[str] = set()
        for q in queries:
            ql = q.lower()
            for key, tag in tag_map.items():
                if key in ql:
                    tags_to_search.add(tag)

        # Fallback to data tags if none found
        if not tags_to_search:
            tags_to_search = {"data-science", "analytics"}

        for tag in list(tags_to_search)[:3]:
            try:
                jobs = self._fetch_by_tag(
                    tag=tag,
                    posted_after=posted_after,
                    timeout=get_settings().request_timeout_seconds,
                )
                for job in jobs:
                    key = job.source_job_id or job.title
                    if key not in seen_ids:
                        seen_ids.add(key)
                        all_jobs.append(job)
            except SourceTimeoutError:
                warnings.append(f"Timeout for tag '{tag}'")
            except Exception as exc:
                warnings.append(f"Error for tag '{tag}': {type(exc).__name__}")
                logger.debug("Jobicy error", extra={"error": str(exc)[:100]})

        completed = datetime.now(UTC)
        duration = (completed - started).total_seconds()

        if all_jobs:
            status = SourceStatus.success
            message = f"Jobicy: {len(all_jobs)} remote jobs fetched."
        elif warnings:
            status = SourceStatus.failed
            message = "Jobicy: no jobs returned. " + "; ".join(warnings[:2])
        else:
            status = SourceStatus.success
            message = "Jobicy: 0 jobs found for given queries."

        return all_jobs[:max_results], SourceRunResult(
            source_name=self.source_name,
            status=status,
            jobs_fetched=len(all_jobs),
            duration_seconds=duration,
            message=message,
            warnings=warnings,
            started_at=started,
            completed_at=completed,
        )

    def _fetch_by_tag(
        self,
        tag: str,
        posted_after: datetime | None,
        timeout: int,
    ) -> list[NormalizedJob]:
        params = {"count": 50, "tag": tag}
        url = f"{JOBICY_API_URL}?{urlencode(params)}"

        data = None
        # Try curl_cffi first
        try:
            from curl_cffi import requests as cffi_requests
            resp = cffi_requests.get(url, impersonate="chrome124", timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
        except Exception:
            pass

        if data is None:
            import httpx
            try:
                with httpx.Client(timeout=timeout) as client:
                    resp = client.get(url, headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Accept": "application/json",
                    })
                    if resp.status_code != 200:
                        raise SourceParseError(self.source_name, f"HTTP {resp.status_code}")
                    data = resp.json()
            except httpx.TimeoutException as exc:
                raise SourceTimeoutError(self.source_name, "Timeout") from exc

        raw_jobs = data.get("jobs", []) if data else []
        jobs = []
        for raw in raw_jobs:
            try:
                job = self._parse_job(raw)
                if not job:
                    continue
                if posted_after and job.posted_at and job.posted_at < posted_after:
                    continue
                jobs.append(job)
            except Exception as exc:
                logger.debug("Jobicy parse error", extra={"error": str(exc)[:50]})

        return jobs

    def _parse_job(self, raw: dict) -> NormalizedJob | None:
        title = raw.get("jobTitle")
        if not title:
            return None

        company = raw.get("companyName") or "Unknown Company"
        source_url = raw.get("url")
        source_job_id = str(raw.get("id", ""))

        # Parse publication date
        posted_at = None
        pub_date = raw.get("pubDate")
        if pub_date:
            try:
                posted_at = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                if posted_at.tzinfo is None:
                    posted_at = posted_at.replace(tzinfo=UTC)
            except (ValueError, AttributeError):
                pass

        # Location / geo
        location_text = raw.get("jobGeo") or "Remote (Worldwide)"
        loc_lower = location_text.lower()
        if "worldwide" in loc_lower or "anywhere" in loc_lower:
            remote_eligibility = RemoteEligibility.worldwide
        else:
            remote_eligibility = RemoteEligibility.region_restricted

        # Job type — Jobicy returns this as a list e.g. ['Full-Time'] or ['Contract']
        job_type_raw_val = raw.get("jobType") or ""
        if isinstance(job_type_raw_val, list):
            job_type_raw = " ".join(job_type_raw_val).lower()
        else:
            job_type_raw = str(job_type_raw_val).lower()
        if "contract" in job_type_raw:
            employment_type = EmploymentType.contract
        elif "part" in job_type_raw:
            employment_type = EmploymentType.part_time
        elif "freelance" in job_type_raw:
            employment_type = EmploymentType.freelance
        elif "internship" in job_type_raw:
            employment_type = EmploymentType.internship
        else:
            employment_type = EmploymentType.full_time

        # Job level
        job_level = (raw.get("jobLevel") or "").lower()

        # Extract concrete skills from job description text & title
        description_text = (raw.get("jobExcerpt") or "") + " " + (raw.get("jobDescription") or "")
        combined_text = (title + " " + description_text).lower()
        
        TECH_KEYWORDS = [
            "python", "sql", "r", "machine learning", "deep learning", "nlp",
            "computer vision", "pandas", "numpy", "tensorflow", "pytorch", "keras",
            "scikit-learn", "power bi", "tableau", "excel", "aws", "gcp", "azure",
            "docker", "kubernetes", "git", "c++", "data analysis", "data science",
            "spark", "pyspark", "hadoop", "etl", "data warehouse", "statistics"
        ]
        
        extracted_skills = [
            kw.title() for kw in TECH_KEYWORDS
            if kw in combined_text
        ]
        
        # If no specific skills found, use industry only if it has valid tokens
        skills = extracted_skills if extracted_skills else []

        now = datetime.now(UTC)
        return NormalizedJob(
            source_name=self.source_name,
            source_job_id=source_job_id,
            title=title,
            company_name=company,
            description=raw.get("jobExcerpt"),
            source_url=source_url,
            apply_url=source_url,
            location_text=location_text,
            work_mode=WorkMode.remote,
            remote_eligibility=remote_eligibility,
            employment_type=employment_type,
            required_skills=skills,
            posted_at=posted_at,
            first_seen_at=now,
            last_seen_at=now,
            fetched_at=now,
            date_status=DateStatus.verified if posted_at else DateStatus.unknown,
            is_demo=False,
        )

    def search_jobs(self, queries, location=None, posted_after=None, max_results=50):
        _, result = self.fetch_jobs(queries, location, posted_after, max_results)
        return result
