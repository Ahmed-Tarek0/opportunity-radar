from __future__ import annotations

from .skill_normalizer import are_same_skill, is_skill_satisfied, normalize_skill


def match_skills(
    candidate_skills: list[str],
    job_required: list[str],
    job_preferred: list[str],
) -> dict:
    """Match candidate skills against job requirements.

    Returns a dict with:
    - matched_required: required skills found in CV
    - missing_required: required skills NOT found in CV
    - matched_preferred: preferred skills found in CV
    - missing_preferred: preferred skills NOT found in CV
    - required_match_rate: 0.0-1.0
    - preferred_match_rate: 0.0-1.0
    """
    matched_required = []
    missing_required = []
    for req in job_required:
        if is_skill_satisfied(req, candidate_skills):
            matched_required.append(req)
        else:
            missing_required.append(req)

    matched_preferred = []
    missing_preferred = []
    for pref in job_preferred:
        if is_skill_satisfied(pref, candidate_skills):
            matched_preferred.append(pref)
        else:
            missing_preferred.append(pref)

    req_rate = len(matched_required) / len(job_required) if job_required else 1.0
    pref_rate = len(matched_preferred) / len(job_preferred) if job_preferred else 1.0

    return {
        "matched_required": matched_required,
        "missing_required": missing_required,
        "matched_preferred": matched_preferred,
        "missing_preferred": missing_preferred,
        "required_match_rate": req_rate,
        "preferred_match_rate": pref_rate,
    }
