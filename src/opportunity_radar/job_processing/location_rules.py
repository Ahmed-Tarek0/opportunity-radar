from __future__ import annotations

from ..logging_config import get_logger
from ..schemas.job import NormalizedJob, RemoteEligibility, WorkMode
from ..schemas.profile import CandidateProfile

logger = get_logger("job_processing.location_rules")


def is_eligible_for_candidate(job: NormalizedJob, profile: CandidateProfile) -> tuple[bool, str]:
    """Check if a job is geographically eligible for the candidate.

    Returns:
        (is_eligible, reason)
    """
    pref = profile.location_preference
    work_mode = job.work_mode
    country = (job.country or "").lower()
    remote_elig = job.remote_eligibility

    # Egypt-based roles
    if "egypt" in country or _is_egypt_city(job.location_text or ""):
        if pref.include_egypt:
            return True, "Role is based in Egypt."
        else:
            return False, "Role is in Egypt but candidate prefers non-Egypt roles."

    # Remote roles
    if work_mode == WorkMode.remote:
        if remote_elig == RemoteEligibility.worldwide:
            if pref.include_worldwide_remote:
                return True, "Role is remote (worldwide) — open to Egypt-based candidates."
            else:
                return False, "Role is worldwide remote but candidate did not request worldwide remote."
        elif remote_elig == RemoteEligibility.egypt_only:
            if pref.include_egypt:
                return True, "Role is remote but restricted to Egypt — eligible."
            else:
                return False, "Role is Egypt-only remote but candidate prefers non-Egypt."
        elif remote_elig == RemoteEligibility.region_restricted:
            # Region-restricted remote — could be Africa-wide (Egypt eligible) or other
            return None, "Role is region-restricted remote — eligibility unclear. Verify before applying."
        elif remote_elig in (RemoteEligibility.country_restricted, RemoteEligibility.not_applicable):
            return False, "Role is remote but restricted to a country other than Egypt."
        else:
            # unknown remote eligibility
            return None, "Remote role with unknown geographic restrictions — eligibility uncertain."

    # Hybrid role — check if Egypt location
    if work_mode == WorkMode.hybrid:
        if pref.include_egypt:
            return None, "Hybrid role — verify Egypt location before applying."
        return False, "Hybrid role likely requires physical presence; not matching Egypt preference."

    # On-site in a non-Egypt country
    if work_mode == WorkMode.onsite and country and "egypt" not in country:
        return False, f"On-site role in {job.country or 'unknown country'} — not eligible for Egypt-based candidate."

    # Unknown work mode or location
    return None, "Work location/arrangement unknown — cannot determine eligibility."


def _is_egypt_city(location_text: str) -> bool:
    """Check if location text refers to an Egyptian city."""
    from .normalizer import EGYPT_INDICATORS
    loc_lower = location_text.lower()
    return any(city in loc_lower for city in EGYPT_INDICATORS)
