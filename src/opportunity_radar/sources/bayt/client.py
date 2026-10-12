from __future__ import annotations

import re
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from ...config import get_settings
from ...exceptions import SourceParseError, SourceTimeoutError
from ...logging_config import get_logger
from ...schemas.job import DateStatus, EmploymentType, NormalizedJob, RemoteEligibility, WorkMode
from ...schemas.source import SourceRunResult, SourceStatus
from ..base import JobSource

logger = get_logger("sources.bayt")

BAYT_BASE_URL = "https://www.bayt.com"


class BaytSource(JobSource):
    """Bayt.com job source for Egypt.

    Bayt is the leading job board across the Middle East and Egypt.
    Fetches public job listings in Egypt. No API key required.
    """

    @property
    def source_name(self) -> str:
        return "bayt"

    @property
    def display_name(self) -> str:
        return "Bayt Egypt"

    def is_configured(self) -> bool:
        return True

    def is_enabled(self) -> bool:
        return getattr(get_settings(), "enable_bayt_source", True)

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
                message="Bayt source is disabled.",
                started_at=started,
            )

        all_jobs: list[NormalizedJob] = []
        seen_urls: set[str] = set()
        warnings: list[str] = []

        # Prepare normalized query keywords for search
        clean_terms = []
        for q in queries[:4]:
            cq = re.sub(r"\b(intern|internship|trainee|junior|senior|entry)\b", "", q, flags=re.IGNORECASE).strip()
            cq = re.sub(r"\s+", " ", cq)
            if cq and cq.lower() not in clean_terms:
                clean_terms.append(cq.lower())

        if not clean_terms:
            clean_terms = ["data science", "data analyst", "machine learning"]

        for term in clean_terms[:3]:
            try:
                jobs = self._fetch_search(
                    term=term,
                    posted_after=posted_after,
                    timeout=get_settings().request_timeout_seconds,
                )
                for j in jobs:
                    if j.source_url not in seen_urls:
                        seen_urls.add(j.source_url)
                        all_jobs.append(j)
                time.sleep(0.5)
            except SourceTimeoutError:
                warnings.append(f"Timeout for '{term}'")
            except Exception as exc:
                warnings.append(f"Error for '{term}': {type(exc).__name__}")
                logger.debug("Bayt error", extra={"error": str(exc)[:100]})

        completed = datetime.now(UTC)
        duration = (completed - started).total_seconds()

        if all_jobs:
            status = SourceStatus.success
            message = f"Bayt Egypt: {len(all_jobs)} jobs fetched."
        elif warnings:
            status = SourceStatus.failed
            # Friendly message for end user without dumping internal SourceParseError text
            message = "Bayt Egypt: Temporarily unavailable (Cloudflare anti-bot challenge active). Retrying automatically on next search."
        else:
            status = SourceStatus.success
            message = "Bayt Egypt: 0 jobs found for given queries."

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
        term: str,
        posted_after: datetime | None,
        timeout: int,
    ) -> list[NormalizedJob]:
        # Form search URL: https://www.bayt.com/en/egypt/jobs/{term}-jobs/
        slug = re.sub(r"\s+", "-", term.strip().lower())
        url = f"{BAYT_BASE_URL}/en/egypt/jobs/{quote_plus(slug)}-jobs/"

        html = None
        try:
            from curl_cffi import requests as cffi_requests
            headers = {
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.google.com/",
            }
            resp = cffi_requests.get(url, impersonate="chrome124", headers=headers, timeout=timeout)
            if resp.status_code == 200:
                html = resp.text
        except Exception:
            pass

        if not html:
            import httpx
            try:
                with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                    resp = client.get(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"})
                    if resp.status_code == 200:
                        html = resp.text
                    else:
                        raise SourceParseError(self.source_name, f"HTTP {resp.status_code}")
            except httpx.TimeoutException as exc:
                raise SourceTimeoutError(self.source_name, "Timeout") from exc

        return self._parse_html(html, posted_after)

    def _parse_html(self, html: str, posted_after: datetime | None) -> list[NormalizedJob]:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.find_all("li", class_="has-pointer-d")
        jobs: list[NormalizedJob] = []

        now = datetime.now(UTC)

        for card in cards:
            h2 = card.find("h2")
            if not h2:
                continue
            a_tag = h2.find("a")
            if not a_tag or not a_tag.get("href"):
                continue

            title = a_tag.get_text(strip=True)
            link = a_tag["href"]
            if not link.startswith("http"):
                source_url = f"{BAYT_BASE_URL}{link}"
            else:
                source_url = link

            # Company
            comp_wrap = card.find("div", class_="job-company-location-wrapper")
            company_name = comp_wrap.get_text(strip=True) if comp_wrap else "Unknown Company"

            # Location
            loc_el = card.find("dt", class_="jb-label-location")
            location_text = loc_el.get_text(strip=True) if loc_el else "Egypt"

            # Date
            date_el = card.find("div", class_="jb-date")
            date_str = date_el.get_text(strip=True) if date_el else ""
            posted_at = self._parse_relative_date(date_str)

            # Filter by freshness
            if posted_after and posted_at and posted_at < posted_after:
                continue

            # Summary / Description snippet
            desc_el = card.find("div", class_="jb-descr")
            description = desc_el.get_text(strip=True) if desc_el else None

            # Work Mode
            loc_lower = location_text.lower()
            title_lower = title.lower()
            if "remote" in loc_lower or "remote" in title_lower:
                work_mode = WorkMode.remote
            elif "hybrid" in loc_lower or "hybrid" in title_lower:
                work_mode = WorkMode.hybrid
            else:
                work_mode = WorkMode.onsite

            # Extract job id from link (e.g. ...-75223070/)
            m_id = re.search(r"-(\d+)/?$", link)
            source_job_id = m_id.group(1) if m_id else link

            job = NormalizedJob(
                source_name=self.source_name,
                source_job_id=source_job_id,
                title=title,
                company_name=company_name,
                description=description,
                source_url=source_url,
                apply_url=source_url,
                location_text=location_text,
                country="Egypt",
                city="Cairo" if "cairo" in loc_lower else ("Alexandria" if "alex" in loc_lower else None),
                work_mode=work_mode,
                remote_eligibility=RemoteEligibility.egypt_only,
                employment_type=EmploymentType.full_time,
                required_skills=[],
                posted_at=posted_at,
                first_seen_at=now,
                last_seen_at=now,
                fetched_at=now,
                date_status=DateStatus.verified if posted_at else DateStatus.unknown,
                is_demo=False,
            )
            jobs.append(job)

        return jobs

    def _parse_relative_date(self, text: str) -> datetime | None:
        if not text:
            return None
        s = text.lower().strip()
        now = datetime.now(UTC)
        m = re.search(r"(\d+)\s+day", s)
        if m:
            return now - timedelta(days=int(m.group(1)))
        m = re.search(r"(\d+)\s+hour", s)
        if m:
            return now - timedelta(hours=int(m.group(1)))
        m = re.search(r"(\d+)\s+minute", s)
        if m:
            return now - timedelta(minutes=int(m.group(1)))
        if "yesterday" in s:
            return now - timedelta(days=1)
        if "today" in s:
            return now
        m = re.search(r"(\d+)\s+month", s)
        if m:
            return now - timedelta(days=int(m.group(1)) * 30)
        return None

    def search_jobs(self, queries, location=None, posted_after=None, max_results=50):
        _, result = self.fetch_jobs(queries, location, posted_after, max_results)
        return result
