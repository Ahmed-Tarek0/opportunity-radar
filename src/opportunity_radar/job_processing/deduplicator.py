from __future__ import annotations

from ..logging_config import get_logger
from ..schemas.job import NormalizedJob

logger = get_logger("job_processing.deduplicator")


def deduplicate_jobs(jobs: list[NormalizedJob]) -> list[NormalizedJob]:
    """Remove duplicate jobs.

    Deduplication strategy:
    1. Exact (source_name, source_job_id) match
    2. Canonical URL match
    3. Content hash match (same title+company+location)
    4. Fuzzy cross-source match using RapidFuzz
    """
    seen_source_ids: dict[str, NormalizedJob] = {}
    seen_urls: dict[str, NormalizedJob] = {}
    seen_hashes: dict[str, NormalizedJob] = {}
    result: list[NormalizedJob] = []

    for job in jobs:
        # 1. Exact source ID dedup
        if job.source_job_id:
            key = f"{job.source_name}::{job.source_job_id}"
            if key in seen_source_ids:
                logger.debug("Deduped by source ID", extra={"key": key})
                continue
            seen_source_ids[key] = job

        # 2. URL dedup
        url = job.canonical_url or job.source_url
        if url:
            if url in seen_urls:
                logger.debug("Deduped by URL")
                continue
            seen_urls[url] = job

        # 3. Content hash dedup
        if job.content_hash:
            if job.content_hash in seen_hashes:
                logger.debug("Deduped by content hash")
                continue
            seen_hashes[job.content_hash] = job

        result.append(job)

    # 4. Fuzzy cross-source dedup
    result = _fuzzy_dedup(result)

    removed = len(jobs) - len(result)
    if removed:
        logger.info("Deduplication complete", extra={"original": len(jobs), "removed": removed})

    return result


def _fuzzy_dedup(jobs: list[NormalizedJob]) -> list[NormalizedJob]:
    """Remove cross-source duplicate jobs using fuzzy matching."""
    try:
        from rapidfuzz import fuzz
    except ImportError:
        return jobs

    result: list[NormalizedJob] = []
    seen: list[tuple[NormalizedJob, str]] = []

    for job in jobs:
        signature = f"{(job.title or '').lower()} {(job.company_name or '').lower()} {(job.location_text or '').lower()}"

        is_dup = False
        for seen_job, seen_sig in seen:
            # Cross-source deduplication only applies across different sources
            if job.source_name != seen_job.source_name:
                if fuzz.ratio(signature, seen_sig) > 90:
                    is_dup = True
                    break

        if not is_dup:
            result.append(job)
            seen.append((job, signature))

    return result
