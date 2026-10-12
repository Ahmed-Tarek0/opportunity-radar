from datetime import UTC, datetime

from opportunity_radar.job_processing.deduplicator import deduplicate_jobs
from opportunity_radar.schemas.job import NormalizedJob


def _make_job(source_name="test", source_job_id=None, title="Engineer", company="Corp", location="Cairo", url=None, content_hash=None):
    return NormalizedJob(
        source_name=source_name,
        source_job_id=source_job_id,
        title=title,
        company_name=company,
        location_text=location,
        source_url=url,
        content_hash=content_hash,
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
        fetched_at=datetime.now(UTC),
    )


def test_dedup_by_source_id():
    jobs = [
        _make_job(source_name="linkedin", source_job_id="123"),
        _make_job(source_name="linkedin", source_job_id="123"),  # duplicate
        _make_job(source_name="linkedin", source_job_id="456"),  # different
    ]
    result = deduplicate_jobs(jobs)
    assert len(result) == 2


def test_dedup_by_url():
    jobs = [
        _make_job(url="https://example.com/job/1"),
        _make_job(url="https://example.com/job/1"),  # same URL
        _make_job(url="https://example.com/job/2"),  # different URL
    ]
    result = deduplicate_jobs(jobs)
    assert len(result) == 2


def test_dedup_by_content_hash():
    jobs = [
        _make_job(content_hash="abc123"),
        _make_job(content_hash="abc123"),  # same hash
        _make_job(content_hash="def456"),  # different hash
    ]
    result = deduplicate_jobs(jobs)
    assert len(result) == 2


def test_no_dedup_different_locations():
    """Same title+company at different locations should NOT be deduped."""
    jobs = [
        _make_job(title="Engineer", company="Corp", location="Cairo"),
        _make_job(title="Engineer", company="Corp", location="Alexandria"),
    ]
    result = deduplicate_jobs(jobs)
    # Should keep both (different locations)
    assert len(result) == 2


def test_dedup_empty_list():
    assert deduplicate_jobs([]) == []


def test_dedup_single_item():
    jobs = [_make_job()]
    result = deduplicate_jobs(jobs)
    assert len(result) == 1


def test_dedup_cross_source_same_job():
    """Same job posted on LinkedIn and WUZZUF should be deduplicated."""
    jobs = [
        _make_job(source_name="linkedin", source_job_id="li-1", title="Backend Engineer", company="Tech Corp", location="Cairo"),
        _make_job(source_name="wuzzuf", source_job_id="wz-1", title="Backend Engineer", company="Tech Corp", location="Cairo"),
    ]
    result = deduplicate_jobs(jobs)
    assert len(result) == 1

