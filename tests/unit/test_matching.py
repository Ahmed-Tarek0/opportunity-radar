from datetime import UTC, datetime

import pytest

from opportunity_radar.matching.query_generator import generate_search_queries
from opportunity_radar.matching.scorer import compute_match_score
from opportunity_radar.matching.skill_matcher import match_skills
from opportunity_radar.matching.skill_normalizer import are_same_skill, normalize_skill
from opportunity_radar.schemas.job import NormalizedJob, WorkMode
from opportunity_radar.schemas.job import SeniorityLevel as JobSeniority
from opportunity_radar.schemas.matching import EligibilityStatus
from opportunity_radar.schemas.profile import (
    CandidateProfile,
    EvidenceType,
    SeniorityLevel,
    Skill,
    TargetTitle,
)

# === Skill Normalization ===

def test_normalize_javascript_aliases():
    assert normalize_skill("JS") == normalize_skill("JavaScript")
    assert normalize_skill("js") == "javascript"
    assert normalize_skill("JavaScript") == "javascript"


def test_java_not_javascript():
    """Java and JavaScript must not be treated as the same skill."""
    assert not are_same_skill("Java", "JavaScript")
    assert not are_same_skill("java", "js")
    assert not are_same_skill("Java", "JS")


def test_postgres_synonym():
    assert normalize_skill("postgres") == normalize_skill("postgresql")
    assert are_same_skill("Postgres", "PostgreSQL")


def test_react_not_angular():
    assert not are_same_skill("React", "Angular")


def test_kubernetes_k8s_synonym():
    assert are_same_skill("k8s", "Kubernetes")


# === Skill Matching ===

def test_skill_matching_exact():
    result = match_skills(
        candidate_skills=["Python", "Django", "PostgreSQL"],
        job_required=["Python", "Django"],
        job_preferred=["Redis"],
    )
    assert "Python" in result["matched_required"]
    assert "Django" in result["matched_required"]
    assert result["missing_required"] == []
    assert "Redis" in result["missing_preferred"]
    assert result["required_match_rate"] == 1.0


def test_skill_matching_partial():
    result = match_skills(
        candidate_skills=["Python"],
        job_required=["Python", "Java", "Docker"],
        job_preferred=[],
    )
    assert "Python" in result["matched_required"]
    assert "Java" in result["missing_required"]
    assert "Docker" in result["missing_required"]
    assert result["required_match_rate"] == pytest.approx(1/3, abs=0.01)


def test_empty_job_requirements():
    result = match_skills(
        candidate_skills=["Python"],
        job_required=[],
        job_preferred=[],
    )
    assert result["required_match_rate"] == 1.0  # No requirements = all met


# === Scorer ===

def _make_profile(**kwargs):
    defaults = dict(
        skills=[Skill(name="python", original="Python", evidence_type=EvidenceType.explicit)],
        target_titles=[TargetTitle(title="Python Developer", confidence=0.9)],
        seniority_estimate=SeniorityLevel.mid,
    )
    defaults.update(kwargs)
    return CandidateProfile(**defaults)


def _make_job(**kwargs):
    defaults = dict(
        source_name="test",
        title="Python Developer",
        company_name="TestCorp",
        required_skills=["Python"],
        work_mode=WorkMode.hybrid,
        seniority_level=JobSeniority.mid,
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
        fetched_at=datetime.now(UTC),
    )
    defaults.update(kwargs)
    return NormalizedJob(**defaults)


def test_score_deterministic():
    """Same inputs must produce same score every time."""
    profile = _make_profile()
    job = _make_job()
    r1 = compute_match_score(profile, job)
    r2 = compute_match_score(profile, job)
    assert r1.match_score == r2.match_score
    assert r1.matched_skills == r2.matched_skills


def test_score_bounds():
    profile = _make_profile()
    job = _make_job()
    result = compute_match_score(profile, job)
    assert 0 <= result.match_score <= 100


def test_score_breakdown_components():
    profile = _make_profile()
    job = _make_job()
    result = compute_match_score(profile, job)
    assert len(result.score_breakdown) == 4
    # Sum of max_points should be 100
    total_max = sum(c.max_points for c in result.score_breakdown)
    assert total_max == pytest.approx(100.0)


def test_ineligible_job_reduced_score():
    profile = _make_profile()
    eligible_job = _make_job()
    ineligible_job = _make_job()

    r_eligible = compute_match_score(profile, eligible_job, EligibilityStatus.eligible)
    r_ineligible = compute_match_score(profile, ineligible_job, EligibilityStatus.likely_ineligible)

    assert r_eligible.match_score >= r_ineligible.match_score


def test_full_skill_match_higher_than_no_match():
    profile = _make_profile(skills=[
        Skill(name="python", original="Python", evidence_type=EvidenceType.explicit),
        Skill(name="django", original="Django", evidence_type=EvidenceType.explicit),
    ])
    good_job = _make_job(required_skills=["Python", "Django"])
    bad_job = _make_job(required_skills=["Java", "Spring", "Kotlin"])

    good_result = compute_match_score(profile, good_job)
    bad_result = compute_match_score(profile, bad_job)

    assert good_result.match_score > bad_result.match_score


# === Query Generator ===

def test_query_generator_produces_queries():
    profile = _make_profile(
        target_titles=[
            TargetTitle(title="Python Developer", confidence=0.9),
            TargetTitle(title="Backend Engineer", confidence=0.8),
        ]
    )
    queries = generate_search_queries(profile)
    assert len(queries) >= 2
    assert len(queries) <= 8
    # Should not include personal info
    for q in queries:
        assert "@" not in q  # no emails
        assert "phone" not in q.lower()


def test_query_generator_fallback():
    """With no profile data, should still generate something."""
    profile = CandidateProfile()  # empty profile
    queries = generate_search_queries(profile)
    assert len(queries) >= 1
