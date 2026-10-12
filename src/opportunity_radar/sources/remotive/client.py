from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlencode

from ...config import get_settings
from ...exceptions import SourceParseError, SourceTimeoutError
from ...logging_config import get_logger
from ...schemas.job import DateStatus, EmploymentType, NormalizedJob, RemoteEligibility, WorkMode
from ...schemas.source import SourceRunResult, SourceStatus
from ..base import JobSource

logger = get_logger("sources.remotive")

REMOTIVE_API_URL = "https://remotive.com/api/remote-jobs"

# Remotive category slugs relevant to tech/data roles
REMOTIVE_CATEGORIES = [
    "data",
    "software-dev",
    "devops-sysadmin",
    "qa",
]


class RemotiveSource(JobSource):
    """Remotive.com remote job source using their public JSON API.

    API docs: https://remotive.com/api/remote-jobs
    Supports search and category filtering. No API key required.
    All jobs are fully remote.
    """

    @property
    def source_name(self) -> str:
        return "remotive"

    @property
    def display_name(self) -> str:
        return "Remotive"

    def is_configured(self) -> bool:
        return True  # Public API, no key needed

    def is_enabled(self) -> bool:
        return get_settings().enable_remotive_source

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
                message="Remotive source is disabled.",
                started_at=started,
            )

        all_jobs: list[NormalizedJob] = []
        seen_ids: set[str] = set()
        warnings: list[str] = []

        # Prioritize compound search phrases for precision, then individual keywords
        compound_terms = []
        known_compounds = [
            "cybersecurity", "security engineer", "information security", "penetration test", "soc analyst",
            "devops", "cloud engineer", "site reliability", "platform engineer", "infrastructure engineer",
            "frontend", "front end", "full stack", "fullstack", "react", "next.js", "web developer",
            "backend", "back end", "python developer", "java developer", "node.js",
            "mobile developer", "flutter", "react native", "android developer", "ios developer",
            "qa engineer", "test automation", "software testing", "quality assurance",
            "data engineer", "data science", "machine learning", "data analyst", "deep learning",
            "embedded", "firmware",
        ]
        for q in queries[:6]:
            ql = q.lower()
            for compound in known_compounds:
                if compound in ql and compound not in compound_terms:
                    compound_terms.append(compound)

        # Fall back to individual domain keywords from queries
        keyword_terms: list[str] = []
        for q in queries[:6]:
            for word in q.lower().split():
                if (
                    len(word) > 3
                    and word not in {"intern", "internship", "junior", "senior", "entry", "level", "developer", "engineer", "specialist"}
                    and word not in keyword_terms
                ):
                    keyword_terms.append(word)

        search_terms_list = (compound_terms + keyword_terms)[:5]
        if not search_terms_list:
            search_terms_list = ["software engineer", "developer"]

        # Build relevance keyword set for post-fetch filtering
        base_keywords = {
            w for q in queries for w in q.lower().split()
            if len(w) >= 3 and w not in {"the", "and", "for", "with", "junior", "senior", "lead", "intern", "entry"}
        }
        general_tech = {
            "software", "engineer", "developer", "programmer", "engineering", "architect",
        }
        relevance_keywords = base_keywords | set(compound_terms) | general_tech

        for term in search_terms_list:
            try:
                jobs = self._fetch_search(
                    search=term,
                    posted_after=posted_after,
                    timeout=get_settings().request_timeout_seconds,
                )
                for job in jobs:
                    # Post-fetch relevance filter: title OR skills must contain a domain keyword
                    title_lower = job.title.lower()
                    skills_lower = " ".join(job.required_skills).lower()
                    combined_text = f"{title_lower} {skills_lower}"
                    is_relevant = any(kw in combined_text for kw in relevance_keywords)
                    if not is_relevant:
                        continue
                    key = job.source_job_id or job.title
                    if key not in seen_ids:
                        seen_ids.add(key)
                        all_jobs.append(job)
            except SourceTimeoutError:
                warnings.append(f"Timeout for search '{term}'")
            except Exception as exc:
                warnings.append(f"Error for '{term}': {type(exc).__name__}")
                logger.debug("Remotive error", extra={"error": str(exc)[:100]})

        completed = datetime.now(UTC)
        duration = (completed - started).total_seconds()

        if all_jobs:
            status = SourceStatus.success
            message = f"Remotive: {len(all_jobs)} remote jobs fetched."
        elif warnings:
            status = SourceStatus.failed
            message = "Remotive: no jobs returned. " + "; ".join(warnings[:2])
        else:
            status = SourceStatus.success
            message = "Remotive: 0 jobs found for given queries."

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

    def _fetch_search(
        self,
        search: str,
        posted_after: datetime | None,
        timeout: int,
    ) -> list[NormalizedJob]:
        params = {"search": search, "limit": 50}
        url = f"{REMOTIVE_API_URL}?{urlencode(params)}"

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
                logger.debug("Remotive parse error", extra={"error": str(exc)[:50]})

        return jobs

    def _parse_job(self, raw: dict) -> NormalizedJob | None:
        title = raw.get("title")
        if not title:
            return None

        company = raw.get("company_name") or "Unknown Company"
        source_url = raw.get("url")
        source_job_id = str(raw.get("id", ""))

        # Parse publication date
        posted_at = None
        pub_date = raw.get("publication_date")
        if pub_date:
            try:
                # Format: "2026-10-08T21:47:32" (no timezone — treat as UTC)
                posted_at = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                if posted_at.tzinfo is None:
                    posted_at = posted_at.replace(tzinfo=UTC)
            except (ValueError, AttributeError):
                pass

        # Skills from tags
        tags = raw.get("tags", []) or []
        skills = [t for t in tags if isinstance(t, str) and len(t) > 1]

        # Location
        location_text = raw.get("candidate_required_location") or "Remote (Worldwide)"

        # Salary
        salary_text = raw.get("salary") or ""
        salary_min = None
        salary_max = None

        # Determine remote eligibility based on location field
        loc_lower = location_text.lower()
        if "worldwide" in loc_lower or "anywhere" in loc_lower:
            remote_eligibility = RemoteEligibility.worldwide
        else:
            remote_eligibility = RemoteEligibility.region_restricted

        # Job type
        job_type_str = (raw.get("job_type") or "").lower()
        if "contract" in job_type_str:
            employment_type = EmploymentType.contract
        elif "part" in job_type_str:
            employment_type = EmploymentType.part_time
        elif "freelance" in job_type_str:
            employment_type = EmploymentType.freelance
        elif "internship" in job_type_str:
            employment_type = EmploymentType.internship
        else:
            employment_type = EmploymentType.full_time

        now = datetime.now(UTC)
        return NormalizedJob(
            source_name=self.source_name,
            source_job_id=source_job_id,
            title=title,
            company_name=company,
            description=raw.get("description"),
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
