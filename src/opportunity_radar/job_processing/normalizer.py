from __future__ import annotations

import hashlib
import re

from ..logging_config import get_logger
from ..schemas.job import NormalizedJob, RemoteEligibility, WorkMode

logger = get_logger("job_processing.normalizer")


EGYPT_INDICATORS = frozenset({
    "egypt", "eg", "cairo", "alexandria", "giza", "hurghada",
    "luxor", "aswan", "mansoura", "tanta", "zagazig", "ismailia",
})

WORLDWIDE_INDICATORS = frozenset({
    "worldwide", "anywhere", "global", "international", "all countries",
    "any country", "any location", "location independent",
})

REMOTE_INDICATORS = frozenset({"remote", "wfh", "work from home", "distributed"})
HYBRID_INDICATORS = frozenset({"hybrid", "flex", "flexible"})


def normalize_job(job: NormalizedJob) -> NormalizedJob:
    """Apply normalization rules to a raw NormalizedJob."""
    # Normalize title
    title = _clean_text(job.title)

    # Detect work mode from text if unknown
    work_mode = job.work_mode
    location_text = job.location_text or ""
    text_to_check = f"{title} {location_text} {job.description or ''}".lower()

    if work_mode == WorkMode.unknown:
        if any(ind in text_to_check for ind in REMOTE_INDICATORS):
            if any(ind in text_to_check for ind in HYBRID_INDICATORS):
                work_mode = WorkMode.hybrid
            else:
                work_mode = WorkMode.remote
        elif location_text.strip():
            work_mode = WorkMode.onsite

    # Detect remote eligibility
    remote_eligibility = job.remote_eligibility
    if remote_eligibility == RemoteEligibility.unknown and work_mode == WorkMode.remote:
        desc_lower = (job.description or "").lower()
        if any(ind in desc_lower for ind in WORLDWIDE_INDICATORS):
            remote_eligibility = RemoteEligibility.worldwide
        elif any(ind in desc_lower for ind in EGYPT_INDICATORS):
            remote_eligibility = RemoteEligibility.egypt_only

    # Normalize country
    country = job.country
    if not country and location_text:
        location_lower = location_text.lower()
        if any(eg in location_lower for eg in EGYPT_INDICATORS):
            country = "Egypt"

    # Detect seniority level from title if unknown
    from ..schemas.job import SeniorityLevel
    seniority_level = job.seniority_level
    if seniority_level == SeniorityLevel.unknown:
        title_lower = title.lower()
        if any(w in title_lower for w in ["manager", "lead", "director", "head of", "principal", "vp", "architect", "staff"]):
            seniority_level = SeniorityLevel.lead
        elif any(w in title_lower for w in ["senior", "sr.", "sr "]):
            seniority_level = SeniorityLevel.senior
        elif any(w in title_lower for w in ["mid-level", "mid level", "intermediate"]):
            seniority_level = SeniorityLevel.mid
        elif any(w in title_lower for w in ["junior", "jr.", "jr ", "entry level", "entry-level", "associate"]):
            seniority_level = SeniorityLevel.junior
        elif any(w in title_lower for w in ["intern", "internship", "trainee", "co-op", "student"]):
            seniority_level = SeniorityLevel.intern

    # Extract skills from title and description if job has no required skills
    required_skills = list(job.required_skills)
    if not required_skills:
        source_text = f"{title} {job.description or ''}".lower()
        # Remove common non-tech acronyms like (GIT) for Graduate In Training before extracting tech skills
        clean_source_text = re.sub(r"\(git\)|graduate in training", " ", source_text)
        KNOWN_TECH_KEYWORDS = [
            ("python", "Python"),
            ("machine learning", "Machine Learning"),
            ("deep learning", "Deep Learning"),
            ("artificial intelligence", "Artificial Intelligence"),
            ("ai", "AI"),
            ("computer vision", "Computer Vision"),
            ("data analysis", "Data Analysis"),
            ("data analyst", "Data Analyst"),
            ("data science", "Data Science"),
            ("data scientist", "Data Scientist"),
            ("sql", "SQL"),
            ("c++", "C++"),
            ("tensorflow", "TensorFlow"),
            ("pytorch", "PyTorch"),
            ("keras", "Keras"),
            ("scikit-learn", "Scikit-Learn"),
            ("power bi", "Power BI"),
            ("tableau", "Tableau"),
            ("excel", "Excel"),
            ("pandas", "Pandas"),
            ("numpy", "NumPy"),
            ("docker", "Docker"),
            ("git", "Git"),
            ("nlp", "NLP"),
            ("aws", "AWS"),
            ("gcp", "GCP"),
            ("azure", "Azure"),
            ("software engineering", "Software Engineering"),
            ("computer science", "Computer Science"),
        ]
        extracted = []
        for kw, canonical in KNOWN_TECH_KEYWORDS:
            # Word boundary check to avoid false positives (e.g. 'ai' in 'cairo' or 'said', or 'git' inside other words)
            if kw in ("ai", "r", "c", "git", "nlp", "sql", "aws", "gcp"):
                pattern = rf"\b{re.escape(kw)}\b"
            else:
                pattern = rf"\b{re.escape(kw)}"
            if re.search(pattern, clean_source_text):
                extracted.append(canonical)
        if extracted:
            required_skills = extracted

    # Compute content hash
    content_hash = _compute_content_hash(job)

    # Build normalized job
    data = job.model_dump()
    data.update({
        "title": title,
        "work_mode": work_mode,
        "remote_eligibility": remote_eligibility,
        "country": country,
        "seniority_level": seniority_level,
        "required_skills": required_skills,
        "content_hash": content_hash,
    })
    return NormalizedJob(**data)


def _clean_text(text: str) -> str:
    """Clean and normalize text."""
    if not text:
        return text
    # Remove excessive whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Remove HTML entities
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    text = re.sub(r"&#\d+;", " ", text)
    return text


def _compute_content_hash(job: NormalizedJob) -> str:
    """Compute a stable hash for deduplication."""
    parts = [
        (job.title or "").lower().strip(),
        (job.company_name or "").lower().strip(),
        (job.location_text or "").lower().strip(),
    ]
    content = "|".join(parts)
    return hashlib.md5(content.encode()).hexdigest()
