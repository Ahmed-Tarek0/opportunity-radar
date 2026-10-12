from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

from ...logging_config import get_logger
from ...schemas.job import DateStatus, NormalizedJob, RemoteEligibility, WorkMode

logger = get_logger("sources.wuzzuf.parser")


def parse_wuzzuf_jobs(html: str, source_name: str = "wuzzuf") -> list[NormalizedJob]:
    """Parse WUZZUF search results HTML into NormalizedJob objects."""
    if BeautifulSoup is None:
        return []

    soup = BeautifulSoup(html, "html.parser")
    jobs = []

    # Target modern WUZZUF card layout (css-pkv5jc) or legacy article/data-card elements
    job_cards = (
        soup.find_all("div", class_=lambda c: c and "css-pkv5jc" in c if c else False)
        or soup.find_all("div", attrs={"data-card-type": True})
        or soup.find_all("article")
        or [
            h2.find_parent("div", class_=lambda c: c and "css-" in c)
            for h2 in soup.find_all("h2")
            if h2.find("a", href=lambda h: h and "/jobs/p/" in h)
        ]
    )

    for card in job_cards[:30]:
        if not card:
            continue
        try:
            job = _parse_wuzzuf_card(card, source_name)
            if job:
                jobs.append(job)
        except Exception as exc:
            logger.debug("Failed to parse WUZZUF card", extra={"error": str(exc)[:100]})

    logger.info("WUZZUF parse complete", extra={"cards": len(job_cards), "parsed": len(jobs)})
    return jobs


def _parse_wuzzuf_card(card, source_name: str) -> NormalizedJob | None:
    # 1. Title & URL
    h2_el = card.find("h2")
    title = None
    source_url = None
    source_job_id = None

    if h2_el:
        title = h2_el.get_text(strip=True)
        link_a = h2_el.find("a", href=True)
        if link_a:
            href = link_a["href"]
            if href.startswith("/"):
                source_url = f"https://wuzzuf.net{href}"
            else:
                source_url = href
    else:
        # Fallback to any job link
        link_a = card.find("a", href=re.compile(r"/jobs/p/"))
        if link_a:
            title = link_a.get_text(strip=True)
            href = link_a["href"]
            source_url = f"https://wuzzuf.net{href}" if href.startswith("/") else href

    if not title or not source_url:
        return None

    # Extract job ID from URL
    match_id = re.search(r"/p/([a-zA-Z0-9_-]+)", source_url)
    if match_id:
        source_job_id = match_id.group(1)

    # 2. Company Name
    company_el = (
        card.find("a", class_=lambda c: c and "css-ipsyv7" in c if c else False)
        or card.find("a", href=lambda h: h and "/jobs/careers/" in h and card.find(text=True) != "")
        or card.find("span", class_=lambda c: c and "company" in c.lower() if c else False)
    )
    company = "Unknown Company"
    if company_el:
        comp_text = company_el.get_text(strip=True).rstrip("-").strip()
        if comp_text:
            company = comp_text

    # 3. Location
    loc_text = "Cairo, Egypt"
    card_raw = card.get_text(separator=" | ", strip=True)
    for city in ["Cairo", "Giza", "Alexandria", "Maadi", "Nasr City", "New Cairo", "6th of October", "Mansoura"]:
        if city.lower() in card_raw.lower():
            loc_text = f"{city}, Egypt"
            break

    # 4. Work Mode
    work_mode = WorkMode.onsite
    card_lower = card_raw.lower()
    if "remote" in card_lower:
        work_mode = WorkMode.remote
    elif "hybrid" in card_lower:
        work_mode = WorkMode.hybrid

    # 5. Skills & Tags
    skills = []
    skill_tags = card.find_all("a", class_=lambda c: c and "css-5x9pm1" in c if c else False)
    if not skill_tags:
        skill_tags = card.find_all("a", href=lambda h: h and "/a/" in h)

    for tag in skill_tags:
        t_text = tag.get_text(strip=True).lstrip("·").strip()
        if t_text and len(t_text) > 1 and not any(kw in t_text.lower() for kw in ["full time", "part time", "on-site", "remote", "experienced", "entry level"]):
            skills.append(t_text)

    # 6. Posted At relative timestamp parsing
    posted_at = None
    date_status = DateStatus.unknown
    time_match = re.search(r"(\d+)\s+(day|days|hour|hours|week|weeks|month|months)\s+ago", card_raw, re.IGNORECASE)
    if time_match:
        qty = int(time_match.group(1))
        unit = time_match.group(2).lower()
        now = datetime.now(UTC)
        if "hour" in unit:
            posted_at = now - timedelta(hours=qty)
        elif "day" in unit:
            posted_at = now - timedelta(days=qty)
        elif "week" in unit:
            posted_at = now - timedelta(days=qty * 7)
        elif "month" in unit:
            posted_at = now - timedelta(days=qty * 30)
        date_status = DateStatus.verified

    return NormalizedJob(
        source_name=source_name,
        source_job_id=source_job_id,
        title=title,
        company_name=company,
        source_url=source_url,
        apply_url=source_url,
        location_text=loc_text,
        country="Egypt",
        work_mode=work_mode,
        remote_eligibility=RemoteEligibility.egypt_only if work_mode == WorkMode.remote else RemoteEligibility.not_applicable,
        required_skills=skills[:10],
        posted_at=posted_at,
        date_status=date_status,
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
        fetched_at=datetime.now(UTC),
        is_demo=False,
    )
