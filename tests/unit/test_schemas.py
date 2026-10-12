from uuid import UUID

import pytest

from opportunity_radar.schemas.job import NormalizedJob, validate_url
from opportunity_radar.schemas.matching import MatchResult
from opportunity_radar.schemas.profile import CandidateProfile, EvidenceType, SeniorityLevel, Skill


def test_candidate_profile_defaults():
    profile = CandidateProfile()
    assert isinstance(profile.id, UUID)
    assert profile.seniority_estimate == SeniorityLevel.unknown
    assert profile.skills == []
    assert profile.is_demo is False


def test_candidate_profile_with_skills():
    profile = CandidateProfile(
        skills=[
            Skill(name="python", original="Python", evidence_type=EvidenceType.explicit)
        ]
    )
    assert len(profile.skills) == 1
    assert profile.skill_names() == ["python"]


def test_normalized_job_url_validation():
    job = NormalizedJob(
        source_name="test",
        title="Dev",
        company_name="Corp",
        source_url="https://example.com/job/1",
        apply_url="javascript:alert('xss')",  # should be rejected
    )
    assert job.source_url == "https://example.com/job/1"
    assert job.apply_url is None  # javascript: URL rejected


def test_normalized_job_http_url_accepted():
    job = NormalizedJob(
        source_name="test",
        title="Dev",
        company_name="Corp",
        source_url="http://example.com/job/1",
    )
    assert job.source_url == "http://example.com/job/1"


def test_validate_url_rejects_bad_schemes():
    assert validate_url("javascript:alert(1)") is None
    assert validate_url("ftp://example.com") is None
    assert validate_url("") is None
    assert validate_url(None) is None
    assert validate_url("https://example.com") == "https://example.com"


def test_match_result_score_bounds():
    result = MatchResult(
        profile_id="00000000-0000-0000-0000-000000000001",
        job_id="00000000-0000-0000-0000-000000000002",
        match_score=75,
    )
    assert result.match_score == 75


def test_match_result_score_out_of_bounds():
    with pytest.raises(Exception):
        MatchResult(
            profile_id="00000000-0000-0000-0000-000000000001",
            job_id="00000000-0000-0000-0000-000000000002",
            match_score=150,  # out of bounds
        )
