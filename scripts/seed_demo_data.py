#!/usr/bin/env python
"""Seed SQLite database with demo profile and jobs from demo_jobs.json."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add src to python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from opportunity_radar.logging_config import setup_logging, get_logger
from opportunity_radar.db.session import init_db, get_session
from opportunity_radar.db.models import CandidateProfileModel, JobModel, JobMatchModel
from opportunity_radar.services.profile_service import ProfileService
from opportunity_radar.matching.scorer import compute_match_score
from opportunity_radar.job_processing.location_rules import is_eligible_for_candidate
from opportunity_radar.schemas.matching import EligibilityStatus
from opportunity_radar.schemas.job import (
    NormalizedJob,
    WorkMode,
    RemoteEligibility,
    EmploymentType,
    SeniorityLevel,
    DateStatus,
)

logger = get_logger("scripts.seed_demo_data")


def seed_demo_data() -> None:
    """Initialize DB and insert demo profile and demo jobs."""
    setup_logging()
    init_db()

    data_path = Path(__file__).resolve().parent.parent / "data" / "demo_jobs.json"
    if not data_path.exists():
        logger.error(f"Demo data file not found at {data_path}")
        print(f"Error: Demo data file not found at {data_path}")
        sys.exit(1)

    with open(data_path, "r", encoding="utf-8") as f:
        demo_jobs_raw = json.load(f)

    profile_service = ProfileService()
    demo_profile = profile_service.get_demo_profile()

    with get_session() as session:
        # Check if demo profile already exists
        profile_id_str = str(demo_profile.id)
        existing_profile = session.get(CandidateProfileModel, profile_id_str)
        if not existing_profile:
            profile_model = CandidateProfileModel(
                id=profile_id_str,
                source_file_hash=demo_profile.source_file_hash or "demo_hash_synthetic",
                profile_json=demo_profile.model_dump(mode="json"),
                is_demo=True,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            session.add(profile_model)
            logger.info("Added demo profile to database", extra={"profile_id": profile_id_str})
        else:
            existing_profile.profile_json = demo_profile.model_dump(mode="json")
            existing_profile.updated_at = datetime.now(timezone.utc)
            logger.info("Updated existing demo profile", extra={"profile_id": profile_id_str})

        now_utc = datetime.now(timezone.utc)
        jobs_added = 0
        matches_added = 0

        from uuid import NAMESPACE_DNS, uuid5 as _uuid5
        for raw in demo_jobs_raw:
            raw_id = str(raw.get("id", ""))
            # Convert non-UUID string IDs (like 'demo-001') to deterministic UUIDs
            try:
                from uuid import UUID as _UUID
                job_uuid = _UUID(raw_id)
            except (ValueError, AttributeError):
                job_uuid = _uuid5(NAMESPACE_DNS, raw_id)
            job_id = str(job_uuid)
            existing_job = session.get(JobModel, job_id)

            posted_at = None
            if raw.get("posted_at"):
                try:
                    posted_at = datetime.fromisoformat(raw["posted_at"].replace("Z", "+00:00"))
                except ValueError:
                    pass

            normalized_job = NormalizedJob(
                id=job_uuid,
                source_name=raw.get("source_name", "demo"),
                source_job_id=raw.get("source_job_id", raw_id),
                title=raw["title"],
                company_name=raw["company_name"],
                description=raw.get("description"),
                source_url=raw.get("source_url"),
                apply_url=raw.get("apply_url"),
                location_text=raw.get("location_text"),
                country=raw.get("country"),
                city=raw.get("city"),
                work_mode=WorkMode(raw.get("work_mode", "unknown")),
                remote_eligibility=RemoteEligibility(raw.get("remote_eligibility", "unknown")),
                employment_type=EmploymentType(raw.get("employment_type", "unknown")),
                seniority_level=SeniorityLevel(raw.get("seniority_level", "unknown")),
                required_skills=raw.get("required_skills", []),
                preferred_skills=raw.get("preferred_skills", []),
                responsibilities=raw.get("responsibilities", []),
                minimum_experience_years=raw.get("minimum_experience_years"),
                salary_min=raw.get("salary_min"),
                salary_max=raw.get("salary_max"),
                salary_currency=raw.get("salary_currency"),
                posted_at=posted_at,
                first_seen_at=now_utc,
                last_seen_at=now_utc,
                fetched_at=now_utc,
                date_status=DateStatus(raw.get("date_status", "unknown")),
                is_demo=True,
            )

            if not existing_job:
                job_model = JobModel(
                    id=job_id,
                    source_name=normalized_job.source_name,
                    source_job_id=normalized_job.source_job_id,
                    title=normalized_job.title,
                    company_name=normalized_job.company_name,
                    description=normalized_job.description,
                    source_url=normalized_job.source_url,
                    apply_url=normalized_job.apply_url,
                    location_text=normalized_job.location_text,
                    country=normalized_job.country,
                    city=normalized_job.city,
                    work_mode=normalized_job.work_mode.value,
                    remote_eligibility=normalized_job.remote_eligibility.value,
                    employment_type=normalized_job.employment_type.value,
                    seniority_level=normalized_job.seniority_level.value,
                    required_skills=normalized_job.required_skills,
                    preferred_skills=normalized_job.preferred_skills,
                    responsibilities=normalized_job.responsibilities,
                    minimum_experience_years=normalized_job.minimum_experience_years,
                    salary_min=normalized_job.salary_min,
                    salary_max=normalized_job.salary_max,
                    salary_currency=normalized_job.salary_currency,
                    posted_at=normalized_job.posted_at,
                    first_seen_at=normalized_job.first_seen_at,
                    last_seen_at=normalized_job.last_seen_at,
                    fetched_at=normalized_job.fetched_at,
                    date_status=normalized_job.date_status.value,
                    is_demo=True,
                )
                session.add(job_model)
                jobs_added += 1

            # Compute match and save/update match record
            eligible_flag, elig_reason = is_eligible_for_candidate(normalized_job, demo_profile)
            if eligible_flag is True:
                elig_status = EligibilityStatus.eligible
            elif eligible_flag is False:
                elig_status = EligibilityStatus.likely_ineligible
            else:
                elig_status = EligibilityStatus.unknown

            match = compute_match_score(
                profile=demo_profile,
                job=normalized_job,
                eligibility_status=elig_status,
                eligibility_reasons=[elig_reason] if elig_reason else [],
            )

            existing_match = session.query(JobMatchModel).filter_by(
                profile_id=profile_id_str,
                job_id=job_id,
            ).first()

            if not existing_match:
                match_model = JobMatchModel(
                    id=f"match_{job_id}",
                    profile_id=profile_id_str,
                    job_id=job_id,
                    match_score=match.match_score,
                    score_breakdown=[b.model_dump() for b in match.score_breakdown],
                    matched_skills=match.matched_skills,
                    missing_required_skills=match.missing_required_skills,
                    missing_preferred_skills=match.missing_preferred_skills,
                    uncertain_requirements=match.uncertain_requirements,
                    experience_alignment=match.experience_alignment,
                    title_alignment=match.title_alignment,
                    work_location_alignment=match.work_location_alignment,
                    eligibility_status=match.eligibility_status.value,
                    eligibility_reasons=match.eligibility_reasons,
                    evidence_citations=[c.model_dump() for c in match.evidence_citations],
                    explanation=match.explanation,
                    suggested_next_action=match.suggested_next_action,
                    matching_version=match.matching_version,
                    used_semantic_matching=match.used_semantic_matching,
                    used_llm_explanation=match.used_llm_explanation,
                    fallback_used=match.fallback_used,
                    created_at=now_utc,
                )
                session.add(match_model)
                matches_added += 1

    print(
        f"Seeding completed successfully: "
        f"Profile='{demo_profile.headline}', "
        f"Jobs processed={len(demo_jobs_raw)} (New={jobs_added}), "
        f"Matches recorded={matches_added}."
    )


if __name__ == "__main__":
    seed_demo_data()
