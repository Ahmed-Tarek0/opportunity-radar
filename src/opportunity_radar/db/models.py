from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class CandidateProfileModel(Base):
    __tablename__ = "candidate_profiles"

    id = Column(String(36), primary_key=True)
    source_file_hash = Column(String(64), index=True, nullable=True)
    profile_json = Column(JSON, nullable=False)
    is_demo = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    matches = relationship("JobMatchModel", back_populates="profile", cascade="all, delete-orphan")
    saved_jobs = relationship("SavedJobModel", back_populates="profile", cascade="all, delete-orphan")


class JobModel(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True)
    source_name = Column(String(100), nullable=False, index=True)
    source_job_id = Column(String(255), nullable=True)
    title = Column(String(500), nullable=False, index=True)
    company_name = Column(String(500), nullable=False, index=True)
    description = Column(Text, nullable=True)
    source_url = Column(Text, nullable=True)
    apply_url = Column(Text, nullable=True)
    location_text = Column(String(500), nullable=True)
    country = Column(String(100), nullable=True, index=True)
    city = Column(String(200), nullable=True)
    work_mode = Column(String(20), default="unknown", nullable=False)
    remote_eligibility = Column(String(30), default="unknown", nullable=False)
    employment_type = Column(String(30), default="unknown", nullable=False)
    seniority_level = Column(String(20), default="unknown", nullable=False)
    required_skills = Column(JSON, default=list)
    preferred_skills = Column(JSON, default=list)
    responsibilities = Column(JSON, default=list)
    minimum_experience_years = Column(Float, nullable=True)
    salary_min = Column(Float, nullable=True)
    salary_max = Column(Float, nullable=True)
    salary_currency = Column(String(10), nullable=True)
    posted_at = Column(DateTime, nullable=True, index=True)
    first_seen_at = Column(DateTime, default=_utcnow, nullable=False)
    last_seen_at = Column(DateTime, default=_utcnow, nullable=False)
    fetched_at = Column(DateTime, default=_utcnow, nullable=False)
    date_status = Column(String(30), default="unknown", nullable=False)
    content_hash = Column(String(64), nullable=True, index=True)
    canonical_url = Column(Text, nullable=True)
    raw_metadata = Column(JSON, default=dict)
    is_demo = Column(Boolean, default=False, nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("source_name", "source_job_id", name="uq_job_source"),
        Index("ix_jobs_work_mode", "work_mode"),
    )

    matches = relationship("JobMatchModel", back_populates="job", cascade="all, delete-orphan")
    saved_by = relationship("SavedJobModel", back_populates="job", cascade="all, delete-orphan")


class JobMatchModel(Base):
    __tablename__ = "job_matches"

    id = Column(String(36), primary_key=True)
    profile_id = Column(String(36), ForeignKey("candidate_profiles.id"), nullable=False, index=True)
    job_id = Column(String(36), ForeignKey("jobs.id"), nullable=False, index=True)
    match_score = Column(Integer, nullable=False)
    score_breakdown = Column(JSON, default=list)
    matched_skills = Column(JSON, default=list)
    missing_required_skills = Column(JSON, default=list)
    missing_preferred_skills = Column(JSON, default=list)
    uncertain_requirements = Column(JSON, default=list)
    experience_alignment = Column(Text, nullable=True)
    title_alignment = Column(Text, nullable=True)
    work_location_alignment = Column(Text, nullable=True)
    eligibility_status = Column(String(30), default="unknown", nullable=False)
    eligibility_reasons = Column(JSON, default=list)
    evidence_citations = Column(JSON, default=list)
    explanation = Column(Text, nullable=True)
    suggested_next_action = Column(Text, nullable=True)
    matching_version = Column(String(20), nullable=False)
    used_semantic_matching = Column(Boolean, default=False)
    used_llm_explanation = Column(Boolean, default=False)
    fallback_used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("profile_id", "job_id", name="uq_match_profile_job"),
    )

    profile = relationship("CandidateProfileModel", back_populates="matches")
    job = relationship("JobModel", back_populates="matches")


class SavedJobModel(Base):
    __tablename__ = "saved_jobs"

    id = Column(String(36), primary_key=True)
    profile_id = Column(String(36), ForeignKey("candidate_profiles.id"), nullable=False, index=True)
    job_id = Column(String(36), ForeignKey("jobs.id"), nullable=False, index=True)
    status = Column(String(30), default="interested", nullable=False)
    notes = Column(Text, nullable=True)
    saved_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("profile_id", "job_id", name="uq_saved_job"),
    )

    profile = relationship("CandidateProfileModel", back_populates="saved_jobs")
    job = relationship("JobModel", back_populates="saved_by")


class SearchRunModel(Base):
    __tablename__ = "search_runs"

    id = Column(String(36), primary_key=True)
    profile_id = Column(String(36), ForeignKey("candidate_profiles.id"), nullable=True, index=True)
    queries_used = Column(JSON, default=list)
    sources_searched = Column(JSON, default=list)
    total_fetched = Column(Integer, default=0)
    total_after_dedup = Column(Integer, default=0)
    total_after_filter = Column(Integer, default=0)
    total_matched = Column(Integer, default=0)
    settings_snapshot = Column(JSON, default=dict)
    final_status = Column(String(30), default="completed", nullable=False)
    started_at = Column(DateTime, default=_utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)


class SourceRunLogModel(Base):
    __tablename__ = "source_run_logs"

    id = Column(String(36), primary_key=True)
    search_run_id = Column(String(36), ForeignKey("search_runs.id"), nullable=True, index=True)
    source_name = Column(String(100), nullable=False)
    status = Column(String(30), nullable=False)
    jobs_fetched = Column(Integer, default=0)
    duration_seconds = Column(Float, default=0.0)
    message = Column(Text, nullable=True)
    error_category = Column(String(100), nullable=True)
    warnings = Column(JSON, default=list)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)


class EmbeddingCacheModel(Base):
    __tablename__ = "embedding_cache"

    id = Column(String(36), primary_key=True)
    cache_key = Column(String(128), nullable=False, unique=True, index=True)
    model_name = Column(String(200), nullable=False)
    text_hash = Column(String(64), nullable=False)
    embedding = Column(JSON, nullable=False)  # list of floats
    created_at = Column(DateTime, default=_utcnow, nullable=False)
