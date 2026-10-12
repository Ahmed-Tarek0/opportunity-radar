from __future__ import annotations

from ..logging_config import get_logger
from ..schemas.profile import CandidateProfile, SeniorityLevel

logger = get_logger("matching.query_generator")

# Maximum number of search queries to generate
MAX_QUERIES = 8

# Seniority prefix words for search queries
SENIORITY_PREFIXES = {
    SeniorityLevel.intern: ["", "intern"],
    SeniorityLevel.entry: ["", "entry level", "junior"],
    SeniorityLevel.junior: ["junior", ""],
    SeniorityLevel.mid: ["", "mid-level"],
    SeniorityLevel.senior: ["senior", ""],
    SeniorityLevel.lead: ["lead", "senior"],
    SeniorityLevel.unknown: [""],
}


def generate_search_queries(profile: CandidateProfile) -> list[str]:
    """Generate 4-8 search query variants from a candidate profile.

    Queries are based on target titles and skills only.
    Never includes personal identifiers.

    Returns:
        List of search query strings, deduplicated.
    """
    queries: list[str] = []
    seen: set[str] = set()

    seniority = profile.seniority_estimate
    prefixes = SENIORITY_PREFIXES.get(seniority, [""])

    # 1. Title-based queries (primary)
    import re
    for target in profile.target_titles[:4]:
        title_clean = target.title.strip()
        if title_clean.lower() not in seen and len(queries) < MAX_QUERIES:
            queries.append(title_clean)
            seen.add(title_clean.lower())

        for prefix in prefixes:
            if prefix and prefix.lower() not in title_clean.lower():
                q = f"{prefix} {title_clean}".strip()
                if q.lower() not in seen and len(queries) < MAX_QUERIES:
                    queries.append(q)
                    seen.add(q.lower())

    # For interns, also search for the base role (e.g. Data Scientist / Data Analyst) so junior openings are caught
    if seniority == SeniorityLevel.intern:
        for target in profile.target_titles[:3]:
            base_t = re.sub(r"\b(intern|internship|trainee|junior)\b", "", target.title, flags=re.IGNORECASE).strip()
            if base_t and base_t.lower() not in seen and len(queries) < MAX_QUERIES:
                queries.append(base_t)
                seen.add(base_t.lower())

    # 2. Skill-combination queries adapted to candidate domain
    role_text = f"{profile.headline or ''} {' '.join(t.title for t in profile.target_titles)}".lower()
    if "analyst" in role_text or "analytics" in role_text:
        base_noun = "analyst"
    elif "scientist" in role_text or "science" in role_text:
        base_noun = "data scientist"
    elif "developer" in role_text:
        base_noun = "developer"
    else:
        base_noun = "engineer"

    top_skills = _get_top_skills(profile)
    if top_skills and len(queries) < MAX_QUERIES:
        skill_query = f"{top_skills[0]} {base_noun}"
        if skill_query.lower() not in seen:
            queries.append(skill_query)
            seen.add(skill_query.lower())

    # 3. Fallback
    if not queries:
        queries.append(profile.headline or "software engineer")

    logger.info(
        "Search queries generated",
        extra={"count": len(queries), "seniority": seniority.value},
    )
    return queries[:MAX_QUERIES]


def _get_top_skills(profile: CandidateProfile) -> list[str]:
    """Get the most prominent skills from the profile."""
    # Prioritize industry-standard primary keywords
    PRIMARY_KEYWORDS = {
        "python", "sql", "data science", "machine learning", "power bi",
        "pandas", "tensorflow", "tableau", "excel", "javascript", "react"
    }
    skills = sorted(
        profile.skills,
        key=lambda s: (0 if s.name.lower() in PRIMARY_KEYWORDS else 1, -s.confidence, s.name),
    )
    return [s.name for s in skills[:5]]
