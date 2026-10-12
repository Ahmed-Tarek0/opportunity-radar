from datetime import UTC, datetime, timedelta

from opportunity_radar.job_processing.freshness import (
    filter_by_freshness,
    format_posted_date_cairo,
    is_fresh,
)
from opportunity_radar.schemas.job import DateStatus, NormalizedJob


def _make_job(posted_at=None, date_status=DateStatus.verified):
    return NormalizedJob(
        source_name="test",
        title="Engineer",
        company_name="Corp",
        posted_at=posted_at,
        date_status=date_status,
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
        fetched_at=datetime.now(UTC),
    )


def test_fresh_job_within_7_days():
    cutoff = datetime.now(UTC) - timedelta(days=7)
    job = _make_job(posted_at=datetime.now(UTC) - timedelta(days=3))
    assert is_fresh(job, cutoff) is True


def test_stale_job_older_than_7_days():
    cutoff = datetime.now(UTC) - timedelta(days=7)
    job = _make_job(posted_at=datetime.now(UTC) - timedelta(days=10))
    assert is_fresh(job, cutoff) is False


def test_job_exactly_on_cutoff_is_fresh():
    cutoff = datetime.now(UTC) - timedelta(days=7)
    job = _make_job(posted_at=cutoff)  # exactly on cutoff
    assert is_fresh(job, cutoff) is True


def test_job_without_date_not_fresh():
    cutoff = datetime.now(UTC) - timedelta(days=7)
    job = _make_job(posted_at=None, date_status=DateStatus.unknown)
    assert is_fresh(job, cutoff) is False


def test_job_with_unknown_date_status_not_fresh():
    cutoff = datetime.now(UTC) - timedelta(days=7)
    job = _make_job(
        posted_at=datetime.now(UTC) - timedelta(days=1),
        date_status=DateStatus.unknown,
    )
    assert is_fresh(job, cutoff) is False


def test_future_dated_job_not_fresh():
    cutoff = datetime.now(UTC) - timedelta(days=7)
    job = _make_job(posted_at=datetime.now(UTC) + timedelta(days=1))
    assert is_fresh(job, cutoff) is False


def test_filter_by_freshness_excludes_undated_by_default():
    cutoff = datetime.now(UTC) - timedelta(days=7)
    jobs = [
        _make_job(posted_at=datetime.now(UTC) - timedelta(days=2)),  # fresh
        _make_job(posted_at=None, date_status=DateStatus.unknown),  # undated
        _make_job(posted_at=datetime.now(UTC) - timedelta(days=10)),  # stale
    ]
    result = filter_by_freshness(jobs, cutoff, include_undated=False)
    assert len(result) == 1
    assert result[0].posted_at is not None


def test_filter_by_freshness_includes_undated_when_requested():
    cutoff = datetime.now(UTC) - timedelta(days=7)
    jobs = [
        _make_job(posted_at=datetime.now(UTC) - timedelta(days=2)),  # fresh
        _make_job(posted_at=None, date_status=DateStatus.unknown),  # undated
    ]
    result = filter_by_freshness(jobs, cutoff, include_undated=True)
    assert len(result) == 2


def test_format_posted_date_cairo():
    dt = datetime(2026, 10, 8, 10, 0, 0, tzinfo=UTC)
    formatted = format_posted_date_cairo(dt)
    assert "Oct" in formatted
    assert "2026" in formatted


def test_format_posted_date_none():
    result = format_posted_date_cairo(None)
    assert "unknown" in result.lower() or result == "Date unknown"
