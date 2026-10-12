from __future__ import annotations

from datetime import UTC, datetime

from ..config import get_settings
from ..logging_config import get_logger
from ..schemas.job import NormalizedJob
from ..schemas.matching import EligibilityStatus, EvidenceCitation, MatchResult, ScoreComponent
from ..schemas.profile import CandidateProfile
from .skill_matcher import match_skills

logger = get_logger("matching.scorer")

# Seniority compatibility matrix — (profile_level, job_level) -> score multiplier
SENIORITY_COMPAT = {
    ("intern", "intern"): 1.0,
    ("intern", "entry"): 0.85,
    ("intern", "junior"): 0.75,
    ("intern", "mid"): 0.25,
    ("intern", "senior"): 0.1,
    ("intern", "lead"): 0.05,
    ("entry", "intern"): 0.85,
    ("entry", "entry"): 1.0,
    ("entry", "junior"): 0.9,
    ("entry", "mid"): 0.4,
    ("entry", "senior"): 0.15,
    ("entry", "lead"): 0.05,
    ("junior", "entry"): 0.9,
    ("junior", "junior"): 1.0,
    ("junior", "mid"): 0.7,
    ("junior", "senior"): 0.25,
    ("junior", "lead"): 0.1,
    ("mid", "junior"): 0.85,
    ("mid", "mid"): 1.0,
    ("mid", "senior"): 0.65,
    ("mid", "lead"): 0.35,
    ("senior", "mid"): 0.9,
    ("senior", "senior"): 1.0,
    ("senior", "lead"): 0.8,
    ("lead", "senior"): 0.9,
    ("lead", "lead"): 1.0,
}


def compute_match_score(
    profile: CandidateProfile,
    job: NormalizedJob,
    eligibility_status: EligibilityStatus = EligibilityStatus.eligible,
    eligibility_reasons: list[str] | None = None,
) -> MatchResult:
    """Compute a deterministic match score for a profile-job pair.

    Scoring weights (sum = 1.0):
    - Skill alignment: 40%
    - Experience/seniority: 25%
    - Role/title alignment: 20%
    - Work arrangement: 15%
    """
    settings = get_settings()
    now = datetime.now(UTC)

    # Build comprehensive candidate knowledge base:
    # 1. Direct skills (normalized + original)
    candidate_knowledge: set[str] = {s.name for s in profile.skills} | {s.original for s in profile.skills}

    # 2. Education (degree titles + fields of study)
    for edu in profile.education:
        if edu.degree:
            candidate_knowledge.add(edu.degree)
        if edu.field_of_study:
            candidate_knowledge.add(edu.field_of_study)

    # 3. Projects (names + tech stack + project descriptions)
    for proj in profile.projects:
        candidate_knowledge.add(proj.name)
        candidate_knowledge.update(proj.stack)
        if proj.description:
            candidate_knowledge.add(proj.description)

    # 4. Work Experience (titles + technologies + descriptions)
    for exp in profile.experiences:
        candidate_knowledge.add(exp.title)
        candidate_knowledge.update(exp.technologies)
        if exp.description:
            candidate_knowledge.add(exp.description)

    # 5. Certifications (names + issuers)
    for cert in profile.certifications:
        candidate_knowledge.add(cert.name)
        if cert.issuer:
            candidate_knowledge.add(cert.issuer)

    candidate_skills = list(candidate_knowledge)

    # === TITLE/ROLE ALIGNMENT (25 pts) ===
    candidate_titles = [t.title.lower() for t in profile.target_titles]
    if profile.headline and profile.headline.lower() not in candidate_titles:
        candidate_titles.append(profile.headline.lower())

    # Infer secondary roles from candidate skills to ensure relevant jobs aren't penalized
    cand_skills_lower = {s.lower() for s in candidate_skills}
    has_ai_skills = bool(cand_skills_lower & {
        "machine learning", "deep learning", "artificial intelligence",
        "pytorch", "tensorflow", "keras", "scikit-learn",
        "nlp", "natural language processing", "computer vision",
        "llm", "langchain", "huggingface", "mlops",
    })
    has_python_skills = bool(cand_skills_lower & {"python", "django", "fastapi", "flask"})
    has_web_skills = bool(cand_skills_lower & {"react", "javascript", "typescript", "frontend", "vue", "angular", "node.js"})


    if has_ai_skills:
        for extra in ["ai software engineer", "ai engineer", "machine learning engineer"]:
            if extra not in candidate_titles:
                candidate_titles.append(extra)
    if has_python_skills and not has_ai_skills:
        for extra in ["python developer", "backend engineer", "python software engineer"]:
            if extra not in candidate_titles:
                candidate_titles.append(extra)
    if has_web_skills:
        for extra in ["frontend developer", "software engineer"]:
            if extra not in candidate_titles:
                candidate_titles.append(extra)

    job_title_lower = job.title.lower()

    title_score = 0.0
    title_reason = ""

    # AI/ML/Data-specific domain words — overlap with these = real domain match
    ai_domain_keywords = {
        "ai", "ml", "machine", "learning", "deep", "nlp", "data", "analyst",
        "analytics", "scientist", "science", "intelligence", "vision", "llm",
        "language", "model", "neural", "computer", "genai", "generative",
    }
    # Broad tech words — valid domain context but NOT sufficient alone for strong match
    tech_keywords = {
        "python", "backend", "frontend", "fullstack", "devops", "cloud",
        "software", "developer", "qa", "testing", "architect",
    }
    # Non-AI domains — penalize when these appear in job title
    non_ai_domain_keywords = {
        "electrical", "mechanical", "solar", "power", "hardware", "embedded",
        "helpdesk", "service desk", "tier", "telecom", "civil", "structural",
        "hvac", "piping", "maintenance", "manufacturing", "industrial", "field",
        "network", "radio", "rf", "optical", "biomedical", "chemical", "material",
    }
    all_domain_keywords = ai_domain_keywords | tech_keywords | {"engineer", "engineering"}

    # Check if job title is in a completely different domain
    job_title_words_raw = set(job_title_lower.replace("-", " ").replace("/", " ").split())
    is_non_ai_domain = bool(job_title_words_raw & non_ai_domain_keywords)

    for target in candidate_titles:
        target_words = set(target.split())
        job_words = set(job_title_lower.split())
        overlap = (target_words & job_words) - {
            "and", "&", "the", "in", "for", "with",
            "senior", "junior", "lead", "mid", "intern", "associate",
        }
        domain_overlap = overlap & all_domain_keywords
        ai_overlap = overlap & ai_domain_keywords

        if len(overlap) >= 2:
            # Strong 2+ word overlap — but only award full 25 if at least one is AI-domain specific
            # AND the job is not in a completely different engineering domain.
            # e.g. "machine" in "Electrical Power Machine" ≠ "Machine Learning"
            generic_only = (overlap <= {"software", "engineer", "engineering", "developer"})
            if ai_overlap and not is_non_ai_domain:
                # Real AI/data domain match with no conflicting domain signals
                title_score = 25.0
                title_reason = f"Strong AI-domain title match: '{target}' aligns with '{job.title}'."
                break
            elif ai_overlap and is_non_ai_domain:
                # AI word appears but job domain is clearly non-AI (e.g. "machine" in "Power Machine")
                title_score = max(title_score, 7.0)
                title_reason = (
                    f"AI keyword ('{', '.join(ai_overlap)}') in job title, but job is in a non-AI domain."
                )
            elif generic_only or is_non_ai_domain:
                # Only generic words or job is in a different domain — soft partial match
                title_score = max(title_score, 10.0)
                title_reason = (
                    f"Generic title overlap ('{', '.join(overlap)}') — job domain may differ from '{target}'."
                )
            else:
                # Tech overlap (backend, devops, etc.) without AI words
                title_score = max(title_score, 18.0)
                title_reason = f"Tech-domain title match: '{target}' aligns with '{job.title}'."
        elif len(overlap) == 1:
            matched_word = list(overlap)[0]
            if matched_word in ai_domain_keywords and not is_non_ai_domain:
                title_score = max(title_score, 18.0)
                title_reason = f"AI-domain keyword '{matched_word}' aligns with target '{target}'."
            elif matched_word in tech_keywords and not is_non_ai_domain:
                title_score = max(title_score, 10.0)
                title_reason = f"Tech keyword '{matched_word}' aligns with target '{target}'."
            elif matched_word in {"engineer", "engineering"} and not is_non_ai_domain:
                # "engineer" alone is too generic — give minimal points only if domain looks OK
                title_score = max(title_score, 6.0)
                title_reason = f"Generic word '{matched_word}' partially matches '{target}' (weak signal)."
            else:
                title_score = max(title_score, 4.0)
                title_reason = f"Weak/generic overlap ('{matched_word}') with '{target}'."

    # Extra penalty if the job title is clearly in a non-AI engineering domain
    if is_non_ai_domain and title_score > 0 and not any(w in job_title_words_raw for w in ai_domain_keywords):
        title_score = min(title_score, 5.0)
        title_reason = (
            title_reason + f" [Penalized: job title contains non-AI domain keywords]"
        )

    if not candidate_titles:
        title_score = 12.5
        title_reason = "No target titles specified in profile."

    title_component = ScoreComponent(
        name="Role & Title Alignment",
        weight=0.25,
        earned_points=round(title_score, 1),
        max_points=25.0,
        reason=title_reason or "No title match found.",
    )

    # === SKILL ALIGNMENT (50 pts) ===
    skill_result = match_skills(
        candidate_skills=candidate_skills,
        job_required=job.required_skills,
        job_preferred=job.preferred_skills,
    )

    req_rate = skill_result["required_match_rate"]
    pref_rate = skill_result["preferred_match_rate"]

    if job.required_skills or job.preferred_skills:
        skill_pts = (req_rate * 38) + (pref_rate * 12)
        # If the job has only 1 generic requirement (e.g. 'Software Engineering') and title has 0 alignment, don't award full pts!
        if len(job.required_skills) == 1 and title_score < 7.0:
            skill_pts = min(skill_pts, 15.0)
    else:
        # If no skills listed in job: only award neutral points if the title actually aligns!
        skill_pts = 20.0 if title_score >= 15.0 else 0.0

    skill_component = ScoreComponent(
        name="Skill Alignment",
        weight=0.50,
        earned_points=round(skill_pts, 1),
        max_points=50.0,
        reason=(
            f"Matched {len(skill_result['matched_required'])} of {len(job.required_skills)} "
            f"required skills and {len(skill_result['matched_preferred'])} of "
            f"{len(job.preferred_skills)} preferred skills."
        )
    )

    # === EXPERIENCE/SENIORITY (25 pts) ===
    profile_level = profile.seniority_estimate.value
    job_level = job.seniority_level.value

    seniority_multiplier = SENIORITY_COMPAT.get(
        (profile_level, job_level),
        0.7 if job_level != "unknown" else 1.0,
    )

    if job.minimum_experience_years and profile.years_experience_estimate:
        years_gap = profile.years_experience_estimate - job.minimum_experience_years
        if years_gap >= 0:
            years_factor = min(1.0, 1.0 + years_gap * 0.05)
        else:
            years_factor = max(0.3, 1.0 + years_gap * 0.15)
    else:
        years_factor = 1.0

    experience_pts = 25 * seniority_multiplier * years_factor

    seniority_reason = f"Profile level: {profile_level}, Job level: {job_level}. "
    if job.minimum_experience_years and profile.years_experience_estimate:
        seniority_reason += (
            f"Required: {job.minimum_experience_years}y, "
            f"Estimated from CV: {profile.years_experience_estimate}y."
        )
    elif job_level == "unknown":
        seniority_reason += "Job does not specify seniority level."

    experience_component = ScoreComponent(
        name="Experience & Seniority",
        weight=0.25,
        earned_points=round(experience_pts, 1),
        max_points=25.0,
        reason=seniority_reason,
    )

    # === WORK ARRANGEMENT / ELIGIBILITY (Eligibility Gate / Informational) ===
    # Work arrangement & location eligibility is kept as an essential filter / gate,
    # but does not grant artificial score points so scores reflect actual technical fit.
    work_pts = 0.0
    work_reason = "Candidate is eligible for this job location / work arrangement."

    if eligibility_status == EligibilityStatus.likely_ineligible:
        work_reason = "Work arrangement does not match candidate eligibility."
    elif eligibility_status == EligibilityStatus.unknown:
        work_reason = "Work arrangement eligibility is uncertain."

    work_component = ScoreComponent(
        name="Work Arrangement & Location",
        weight=0.0,
        earned_points=work_pts,
        max_points=0.0,
        reason=work_reason,
    )

    # === TOTAL SCORE & RELEVANCE GATES ===
    total = skill_pts + experience_pts + title_score + work_pts

    # 1. Zero evidence gate: if neither title nor skills match, cap at 30
    has_skill_match = bool(skill_result["matched_required"] or skill_result["matched_preferred"])
    if title_score < 6.0 and not has_skill_match:
        total = min(total, 25.0)

    # 2. Weak title gate: if title has NO real domain match (score < 10 means only generic
    # words like 'engineer' alone, or a penalized non-AI domain job), cap at 45.
    # This prevents jobs like "Solar Energy Engineer" from scoring 70+ just due to
    # experience/location points even when the domain is completely wrong.
    if title_score < 10.0:
        total = min(total, 45.0)

    # 3. Seniority mismatch gate: interns and entry candidates cannot match Manager/Director/Lead/Architect roles
    is_senior_or_mgmt = (
        any(w in job_title_lower for w in ["manager", "director", "head of", "principal", "vp", "architect", "staff", "lead"])
        or job_level in ("lead", "senior")
    )
    if profile_level in ("intern", "entry") and is_senior_or_mgmt:
        total = min(total, 35.0)

    match_score = max(0, min(100, round(total)))

    # Build evidence
    evidence = []
    if skill_result["matched_required"]:
        evidence.append(EvidenceCitation(
            claim="Required skills matched",
            cv_evidence=f"CV contains: {', '.join(skill_result['matched_required'][:5])}",
            job_evidence=f"Job requires: {', '.join(job.required_skills[:5])}",
            confidence=0.9,
        ))

    # Build explanation
    explanation = _build_explanation(
        profile=profile,
        job=job,
        skill_result=skill_result,
        match_score=match_score,
        seniority_multiplier=seniority_multiplier,
    )

    return MatchResult(
        profile_id=profile.id,
        job_id=job.id,
        match_score=match_score,
        score_breakdown=[skill_component, experience_component, title_component, work_component],
        matched_skills=skill_result["matched_required"] + skill_result["matched_preferred"],
        missing_required_skills=skill_result["missing_required"],
        missing_preferred_skills=skill_result["missing_preferred"],
        uncertain_requirements=[],
        experience_alignment=seniority_reason,
        title_alignment=title_reason or "No title match.",
        work_location_alignment=work_reason,
        eligibility_status=eligibility_status,
        eligibility_reasons=eligibility_reasons or [],
        evidence_citations=evidence,
        explanation=explanation,
        suggested_next_action=_suggest_next_action(match_score, skill_result),
        matching_version=settings.matching_version,
        created_at=now,
        used_semantic_matching=False,
        used_llm_explanation=False,
        fallback_used=False,
    )


def _build_explanation(
    profile: CandidateProfile,
    job: NormalizedJob,
    skill_result: dict,
    match_score: int,
    seniority_multiplier: float,
) -> str:
    parts = []

    if skill_result["matched_required"]:
        parts.append(
            f"✅ Matched required skills: {', '.join(skill_result['matched_required'][:5])}"
        )

    if skill_result["missing_required"]:
        parts.append(
            f"⚠️ Required skills not found in CV: {', '.join(skill_result['missing_required'][:5])}"
        )

    if skill_result["matched_preferred"]:
        parts.append(
            f"✅ Matched preferred skills: {', '.join(skill_result['matched_preferred'][:3])}"
        )

    if seniority_multiplier < 0.7:
        parts.append(
            "⚠️ Seniority mismatch: the role may expect a different experience level than indicated in your CV."
        )

    if match_score >= 70:
        parts.append("This role is a strong match based on available information.")
    elif match_score >= 50:
        parts.append("This role is a moderate match. Review missing skills before applying.")
    else:
        parts.append("This role is a partial match. Significant skill or seniority gaps exist.")

    return " | ".join(parts) if parts else "Unable to generate detailed explanation."


def _suggest_next_action(score: int, skill_result: dict) -> str:
    missing = skill_result.get("missing_required", [])
    if score >= 70 and not missing:
        return "Strong match — review the full job description and apply if it aligns with your goals."
    elif score >= 70 and missing:
        return f"Good match with gaps. Address missing skills: {', '.join(missing[:3])} before applying."
    elif score >= 50:
        return "Moderate match — read the job description carefully and assess the missing requirements."
    else:
        return "Significant gaps found. Consider applying only if you can address the key missing skills."
