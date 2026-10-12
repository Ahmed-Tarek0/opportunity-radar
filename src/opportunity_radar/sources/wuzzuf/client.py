from __future__ import annotations

import time
from datetime import UTC, datetime
from urllib.parse import urlencode

import httpx

from ...config import get_settings
from ...exceptions import SourceParseError, SourceTimeoutError
from ...logging_config import get_logger
from ...schemas.job import NormalizedJob
from ...schemas.source import SourceRunResult, SourceStatus
from ..base import JobSource
from .parser import parse_wuzzuf_jobs

logger = get_logger("sources.wuzzuf")

WUZZUF_SEARCH_URL = "https://wuzzuf.net/search/jobs/"


class WuzzufSource(JobSource):
    """WUZZUF job source for Egypt-focused roles.

    Uses the public search page. No API key required.
    Results are Egypt-specific (on-site, hybrid, remote in Egypt).
    """

    @property
    def source_name(self) -> str:
        return "wuzzuf"

    @property
    def display_name(self) -> str:
        return "WUZZUF"

    def is_configured(self) -> bool:
        return True

    def is_enabled(self) -> bool:
        return get_settings().enable_wuzzuf_source

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
                message="WUZZUF source is disabled.",
                started_at=started,
            )

        all_jobs: list[NormalizedJob] = []
        warnings: list[str] = []

        # Create persistent session for connection & cookie reuse
        cffi_session = None
        try:
            from curl_cffi import requests as cffi_requests
            cffi_session = cffi_requests.Session(impersonate="chrome124")
        except Exception:
            cffi_session = None

        # Prepare search queries optimized for Wuzzuf's search engine
        import re
        clean_queries = []
        seen_q = set()
        for q in queries:
            cq = re.sub(r"\b(intern|internship|trainee|co-op)\b", "", q, flags=re.IGNORECASE).strip()
            cq = re.sub(r"\s+", " ", cq)
            if cq and cq.lower() not in seen_q:
                clean_queries.append(cq)
                seen_q.add(cq.lower())
            if q.lower() not in seen_q:
                clean_queries.append(q)
                seen_q.add(q.lower())

        for query in clean_queries[:5]:
            try:
                jobs = self._fetch_for_query(
                    query=query,
                    timeout=settings.request_timeout_seconds,
                    session=cffi_session,
                )
                all_jobs.extend(jobs)
                time.sleep(0.5)
            except SourceTimeoutError:
                warnings.append(f"Timeout for '{query}'")
            except SourceParseError as exc:
                warnings.append(f"Parse error for '{query}': {exc}")
            except Exception as exc:
                warnings.append(f"Error for '{query}': {type(exc).__name__}")
                logger.debug("WUZZUF error", extra={"error": str(exc)[:100]})

        # If direct search was blocked by Cloudflare (0 jobs), fallback to sitemap feed
        if not all_jobs:
            try:
                sitemap_jobs = self._fetch_from_sitemap(queries, posted_after, timeout=settings.request_timeout_seconds)
                if sitemap_jobs:
                    all_jobs.extend(sitemap_jobs)
                    warnings = []
            except Exception as sm_err:
                logger.debug("WUZZUF sitemap fallback failed", extra={"error": str(sm_err)[:100]})

        completed = datetime.now(UTC)
        duration = (completed - started).total_seconds()

        if all_jobs:
            status = SourceStatus.success
            message = f"WUZZUF: {len(all_jobs)} jobs fetched."
            warnings = []  # Clear transient query warnings if we got valid results
        elif not all_jobs and warnings:
            status = SourceStatus.failed
            message = (
                "WUZZUF search returned no results. "
                "The page structure may have changed or requests are being blocked."
            )
        else:
            status = SourceStatus.success
            message = "WUZZUF: 0 jobs found for given queries."

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

    def _fetch_from_sitemap(self, queries: list[str], posted_after: datetime | None, timeout: int = 15) -> list[NormalizedJob]:
        """Fetch jobs directly from WUZZUF public sitemap when search HTML is blocked by Cloudflare."""
        import re
        from ...schemas.job import DateStatus, WorkMode

        sitemap_url = "https://wuzzuf.net/sitemap-job-1.xml"
        sitemap_text = ""

        try:
            from curl_cffi import requests as cffi_requests
            resp = cffi_requests.get(sitemap_url, impersonate="chrome124", timeout=timeout)
            if resp.status_code == 200 and len(resp.text) >= 1000:
                sitemap_text = resp.text
        except Exception:
            pass

        if not sitemap_text:
            import httpx
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Accept": "text/xml,application/xml,application/xhtml+xml,text/html;q=0.9",
                }
                with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                    resp = client.get(sitemap_url, headers=headers)
                    if resp.status_code == 200 and len(resp.text) >= 1000:
                        sitemap_text = resp.text
            except Exception:
                pass

        if not sitemap_text:
            return []

        entries = re.findall(r"<url>\s*<loc>(.*?)</loc>\s*<lastmod>(.*?)</lastmod>", sitemap_text)
        
        # Build query keywords pattern
        target_tokens = set()
        for q in queries:
            for word in q.lower().split():
                if len(word) > 2 and word not in {"intern", "junior", "engineer", "specialist"}:
                    target_tokens.add(word)
        # Compile patterns with word boundaries (handling hyphens)
        clean_tokens = [re.escape(t) for t in target_tokens if t != "ai"]
        patterns = [rf"(?:^|-){t}(?:-|$)" for t in clean_tokens]
        # For ai, explicitly require ai- or -ai-
        patterns.append(r"(?:^|-)ai(?:-|$)")
        match_regex = re.compile("|".join(patterns), re.IGNORECASE)

        matched_jobs: list[NormalizedJob] = []
        now = datetime.now(UTC)

        for loc, lastmod_str in entries:
            slug = loc.split("/")[-1].lower()
            without_id = re.sub(r"^[a-z0-9]+-", "", slug)
            
            # Check if any target token is in slug with word boundary
            if not match_regex.search(without_id):
                continue

            # Parse date
            posted_at = None
            try:
                posted_at = datetime.fromisoformat(lastmod_str)
                if posted_at.tzinfo is None:
                    posted_at = posted_at.replace(tzinfo=UTC)
            except Exception:
                pass

            if posted_after and posted_at and posted_at < posted_after:
                continue

            # Clean title
            cleaned = re.sub(r"-(cairo|giza|alexandria|egypt)+$", "", without_id)
            title = cleaned.replace("-", " ").title()

            city = "Cairo" if "cairo" in slug else ("Giza" if "giza" in slug else ("Alexandria" if "alexandria" in slug else None))
            loc_text = f"{city}, Egypt" if city else "Egypt"

            job = NormalizedJob(
                source_name=self.source_name,
                source_job_id=loc.split("/")[-1].split("-")[0],
                title=title,
                company_name="Company via WUZZUF",
                location_text=loc_text,
                country="Egypt",
                city=city,
                work_mode=WorkMode.remote if "remote" in slug else WorkMode.onsite,
                source_url=loc,
                apply_url=loc,
                posted_at=posted_at,
                date_status=DateStatus.verified if posted_at else DateStatus.unknown,
                first_seen_at=now,
                last_seen_at=now,
                fetched_at=now,
                is_demo=False,
            )
            matched_jobs.append(job)
            if len(matched_jobs) >= 25:
                break

        return matched_jobs

    def _fetch_for_query(self, query: str, timeout: int, session=None) -> list[NormalizedJob]:
        params = {"q": query, "a[country][]": "Egypt"}
        url = f"{WUZZUF_SEARCH_URL}?{urlencode(params)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml",
        }
        # Try curl_cffi first to bypass Cloudflare anti-bot checks
        try:
            cffi_headers = {
                "Referer": "https://www.google.com/",
                "Accept-Language": "en-US,en;q=0.9",
            }
            if session:
                resp = session.get(url, headers=cffi_headers, timeout=timeout)
            else:
                from curl_cffi import requests as cffi_requests
                resp = cffi_requests.get(
                    url,
                    impersonate="chrome124",
                    headers=cffi_headers,
                    timeout=timeout,
                )
            if resp.status_code == 200 and len(resp.text) > 1000:
                parsed = parse_wuzzuf_jobs(resp.text, self.source_name)
                if parsed:
                    return parsed
        except Exception as cffi_err:
            logger.debug("curl_cffi fetch fallback", extra={"error": str(cffi_err)[:100]})

        # Fallback to standard httpx client
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                response = client.get(url, headers=headers)
                if response.status_code != 200:
                    raise SourceParseError(
                        self.source_name,
                        f"HTTP {response.status_code} from WUZZUF",
                    )
                return parse_wuzzuf_jobs(response.text, self.source_name)
        except httpx.TimeoutException as exc:
            raise SourceTimeoutError(
                self.source_name, f"Timeout after {timeout}s"
            ) from exc

    def search_jobs(self, queries, location=None, posted_after=None, max_results=50):
        _, result = self.fetch_jobs(queries, location, posted_after, max_results)
        return result
