from __future__ import annotations

from datetime import UTC, datetime

from ..cv_parser.file_validation import validate_upload
from ..cv_parser.profile_extractor import extract_profile_from_text
from ..cv_parser.text_extractor import extract_text
from ..logging_config import get_logger
from ..schemas.profile import CandidateProfile

logger = get_logger("services.profile")


class ProfileService:
    """Service for CV upload and profile extraction."""

    def __init__(self, llm_provider=None):
        self._llm = llm_provider

    def process_upload(
        self,
        filename: str,
        file_bytes: bytes,
        content_type: str | None = None,
    ) -> tuple[CandidateProfile, str]:
        """Process a CV upload and return (profile, file_hash).

        Args:
            filename: Original filename.
            file_bytes: Raw file bytes.
            content_type: Optional MIME type.

        Returns:
            Tuple of (CandidateProfile, sha256_hex_hash)

        Raises:
            CVValidationError: If validation fails.
            CVParsingError: If text extraction fails.
        """
        # Validate
        file_hash = validate_upload(filename, file_bytes, content_type)
        logger.info("CV validated", extra={"hash_prefix": file_hash[:8]})

        # Extract text (do not store raw bytes)
        cv_text = extract_text(filename, file_bytes)
        logger.info("CV text extracted", extra={"chars": len(cv_text)})

        # Extract profile
        profile = extract_profile_from_text(cv_text, llm_provider=self._llm)
        profile.source_file_hash = file_hash
        profile.created_at = datetime.now(UTC)
        profile.updated_at = datetime.now(UTC)

        logger.info(
            "Profile extracted",
            extra={
                "skills": len(profile.skills),
                "titles": len(profile.target_titles),
                "seniority": profile.seniority_estimate.value,
                "is_demo": profile.is_demo,
            },
        )
        return profile, file_hash

    def get_demo_profile(self) -> CandidateProfile:
        """Return a demo/sample profile for testing."""
        from ..schemas.profile import (
            Education,
            EmploymentPreferences,
            EvidenceType,
            LocationPreference,
            SeniorityLevel,
            Skill,
            TargetTitle,
            WorkExperience,
        )

        return CandidateProfile(
            headline="Senior Python Backend Engineer",
            summary=(
                "Demo profile for testing Opportunity Radar. "
                "This is a synthetic example, not a real person."
            ),
            skills=[
                Skill(name="python", original="Python", evidence_type=EvidenceType.explicit, confidence=1.0),
                Skill(name="django", original="Django", evidence_type=EvidenceType.explicit, confidence=1.0),
                Skill(name="fastapi", original="FastAPI", evidence_type=EvidenceType.explicit, confidence=1.0),
                Skill(name="postgresql", original="PostgreSQL", evidence_type=EvidenceType.explicit, confidence=1.0),
                Skill(name="redis", original="Redis", evidence_type=EvidenceType.experience, confidence=0.9),
                Skill(name="docker", original="Docker", evidence_type=EvidenceType.experience, confidence=0.9),
                Skill(name="aws", original="AWS", evidence_type=EvidenceType.experience, confidence=0.8),
                Skill(name="git", original="Git", evidence_type=EvidenceType.explicit, confidence=1.0),
                Skill(name="sql", original="SQL", evidence_type=EvidenceType.explicit, confidence=1.0),
                Skill(name="rest api", original="REST API", evidence_type=EvidenceType.experience, confidence=0.9),
            ],
            experiences=[
                WorkExperience(
                    title="Senior Python Developer",
                    employer="DemoTech Inc.",
                    start_date="2020-03",
                    end_date="present",
                    description="Built and maintained microservices using FastAPI and Django. Led a team of 3 engineers.",
                    technologies=["Python", "FastAPI", "Django", "PostgreSQL", "Redis", "Docker"],
                    evidence="Senior Python Developer at DemoTech Inc. — demo profile",
                ),
                WorkExperience(
                    title="Python Developer",
                    employer="StartupExample LLC",
                    start_date="2018-06",
                    end_date="2020-02",
                    description="Developed REST APIs and database integrations.",
                    technologies=["Python", "Django", "MySQL", "AWS"],
                    evidence="Python Developer at StartupExample — demo profile",
                ),
            ],
            education=[
                Education(
                    degree="BSc Computer Science",
                    institution="Demo University",
                    graduation_year=2018,
                    field_of_study="Computer Science",
                )
            ],
            target_titles=[
                TargetTitle(title="Senior Python Developer", rationale="Primary role title", confidence=0.95),
                TargetTitle(title="Backend Engineer", rationale="General backend engineering role", confidence=0.9),
                TargetTitle(title="Python Backend Engineer", rationale="Python-focused backend role", confidence=0.9),
                TargetTitle(title="Software Engineer", rationale="General software engineering", confidence=0.8),
            ],
            seniority_estimate=SeniorityLevel.senior,
            years_experience_estimate=6.0,
            location_preference=LocationPreference(
                include_egypt=True,
                include_worldwide_remote=True,
            ),
            employment_preferences=EmploymentPreferences(
                full_time=True,
                hybrid=True,
                remote=True,
                on_site=True,
            ),
            profile_confidence=0.95,
            fields_needing_confirmation=[
                "This is a DEMO PROFILE for testing. Upload your own CV to get personalized results."
            ],
            is_demo=True,
        )
