from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytz

from ..config import get_settings
from ..logging_config import get_logger
from ..schemas.job import DateStatus, NormalizedJob

logger = get_logger("job_processing.freshness")

CAIRO_TZ = pytz.timezone("Africa/Cairo")


def get_lookback_cutoff(
    days: int | None = None,
    reference: datetime | None = None,
) -> datetime:
    """Return UTC cutoff datetime for the lookback period."""
    if days is None:
        days = get_settings().job_lookback_days
    if reference is None:
        reference = datetime.now(UTC)
    return reference - timedelta(days=days)


def is_fresh(job: NormalizedJob, cutoff: datetime) -> bool:
    """Return True if job's posted_at is within the lookback period.

    Only verified/estimated dates are used for filtering.
    Jobs with unknown dates return False by default.
    """
    if job.date_status == DateStatus.unknown or job.date_status == DateStatus.source_unavailable:
        return False  # Excluded by default; user can toggle to include

    if not job.posted_at:
        return False

    # Ensure timezone-aware comparison
    posted = job.posted_at
    if posted.tzinfo is None:
        posted = posted.replace(tzinfo=UTC)

    cutoff_aware = cutoff
    if cutoff_aware.tzinfo is None:
        cutoff_aware = cutoff_aware.replace(tzinfo=UTC)

    # Reject future dates
    now = datetime.now(UTC)
    if posted > now:
        logger.warning("Job has future posted_at date, treating as unknown")
        return False

    return posted >= cutoff_aware


def filter_by_freshness(
    jobs: list[NormalizedJob],
    cutoff: datetime,
    include_undated: bool = False,
) -> list[NormalizedJob]:
    """Filter jobs by freshness.

    Args:
        jobs: Jobs to filter.
        cutoff: Minimum posted_at datetime (UTC).
        include_undated: If True, include jobs with unknown/missing dates.
    """
    fresh = []
    undated_count = 0
    stale_count = 0

    for job in jobs:
        if job.date_status in (DateStatus.unknown, DateStatus.source_unavailable) or not job.posted_at:
            if include_undated:
                fresh.append(job)
            else:
                undated_count += 1
        elif is_fresh(job, cutoff):
            fresh.append(job)
        else:
            stale_count += 1

    logger.info(
        "Freshness filter applied",
        extra={
            "kept": len(fresh),
            "stale": stale_count,
            "undated_excluded": undated_count,
        },
    )
    return fresh


def format_posted_date_cairo(posted_at: datetime | None) -> str:
    """Format a UTC datetime as Cairo local date string."""
    if not posted_at:
        return "Date unknown"
    if posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=UTC)
    cairo_dt = posted_at.astimezone(CAIRO_TZ)
    return cairo_dt.strftime("%b %d, %Y")
