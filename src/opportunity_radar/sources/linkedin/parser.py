from __future__ import annotations

from datetime import UTC, datetime

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

from ...logging_config import get_logger
from ...schemas.job import DateStatus, NormalizedJob, WorkMode

logger = get_logger("sources.linkedin.parser")


def parse_linkedin_jobs(html: str, source_name: str = "linkedin") -> list[NormalizedJob]:
    """Parse LinkedIn job listing HTML into NormalizedJob objects.

    LinkedIn's HTML structure changes frequently. This parser targets
    the public job card structure as of 2024-2026. It may need updates
    if LinkedIn changes its markup.
    """
    if BeautifulSoup is None:
        logger.error("BeautifulSoup4 not installed")
        return []

    soup = BeautifulSoup(html, "html.parser")
    jobs = []

    # Try multiple selectors as LinkedIn changes their HTML
    job_cards = (
        soup.find_all("li", class_=lambda c: c and "job-search-card" in c)
        or soup.find_all("div", class_=lambda c: c and "base-card" in c)
        or soup.find_all("li", recursive=False)  # fallback
    )

    for card in job_cards[:25]:  # cap at 25 per query
        try:
            job = _parse_job_card(card, source_name)
            if job:
                jobs.append(job)
        except Exception as exc:
            logger.debug("Failed to parse LinkedIn job card", extra={"error": str(exc)[:100]})

    logger.info("LinkedIn parse complete", extra={"cards_found": len(job_cards), "parsed": len(jobs)})
    return jobs


def _parse_job_card(card, source_name: str) -> NormalizedJob | None:
    # Title
    title_el = (
        card.find("h3", class_=lambda c: c and "base-search-card__title" in c)
        or card.find("a", class_=lambda c: c and "job-card" in str(c))
        or card.find("h3")
    )
    title = title_el.get_text(strip=True) if title_el else None
    if not title:
        return None

    # Company
    company_el = (
        card.find("h4", class_=lambda c: c and "base-search-card__subtitle" in c)
        or card.find("a", class_=lambda c: c and "company" in str(c))
        or card.find("h4")
    )
    company = company_el.get_text(strip=True) if company_el else "Unknown Company"

    # Location
    location_el = (
        card.find("span", class_=lambda c: c and "job-search-card__location" in c)
        or card.find("span", class_=lambda c: c and "location" in str(c))
    )
    location_text = location_el.get_text(strip=True) if location_el else None

    # URL
    link_el = card.find("a", href=True)
    source_url = None
    source_job_id = None
    if link_el:
        href = link_el["href"]
        if href.startswith("http") and "linkedin.com" in href:
            source_url = href.split("?")[0]  # remove tracking params
            # Extract job ID from URL
            parts = source_url.rstrip("/").split("-")
            if parts:
                source_job_id = parts[-1]

    # Work mode detection from location
    work_mode = WorkMode.unknown
    if location_text:
        loc_lower = location_text.lower()
        if "remote" in loc_lower:
            work_mode = WorkMode.remote
        elif "hybrid" in loc_lower:
            work_mode = WorkMode.hybrid
        elif loc_lower:
            work_mode = WorkMode.onsite

    # Date parsing from <time> element
    time_el = card.find("time")
    posted_at = None
    date_status = DateStatus.unknown
    if time_el:
        dt_val = time_el.get("datetime")
        if dt_val:
            try:
                dt_str = dt_val.replace("Z", "+00:00")
                parsed_dt = datetime.fromisoformat(dt_str)
                if parsed_dt.tzinfo is None:
                    parsed_dt = parsed_dt.replace(tzinfo=UTC)
                posted_at = parsed_dt
                date_status = DateStatus.verified
            except Exception:
                pass

    return NormalizedJob(
        source_name=source_name,
        source_job_id=source_job_id,
        title=title,
        company_name=company,
        source_url=source_url,
        apply_url=source_url,
        location_text=location_text,
        work_mode=work_mode,
        posted_at=posted_at,
        date_status=date_status,
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
        fetched_at=datetime.now(UTC),
        is_demo=False,
    )
