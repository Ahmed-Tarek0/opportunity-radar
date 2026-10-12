from __future__ import annotations

import time
from collections.abc import Callable

from ..config import get_settings
from ..job_processing.deduplicator import deduplicate_jobs
from ..job_processing.freshness import filter_by_freshness, get_lookback_cutoff
from ..job_processing.location_rules import is_eligible_for_candidate
from ..job_processing.normalizer import normalize_job
from ..logging_config import get_logger
from ..matching.query_generator import generate_search_queries
from ..matching.scorer import compute_match_score
from ..schemas.job import NormalizedJob
from ..schemas.matching import EligibilityStatus, MatchResult
from ..schemas.profile import CandidateProfile
from ..schemas.source import SourceRunResult, SourceStatus
from ..sources.registry import SourceRegistry

logger = get_logger("services.search_workflow")


class SearchProgress:
    """Tracks and reports search progress."""
    def __init__(self, callback: Callable[[str, str], None] | None = None):
        self._callback = callback

    def update(self, stage: str, detail: str = "") -> None:
        logger.info(f"[Search] {stage}: {detail}")
        if self._callback:
            self._callback(stage, detail)


class SearchResult:
    """Result of a complete search workflow run."""
    def __init__(
        self,
        jobs: list[NormalizedJob],
        matches: list[MatchResult],
        source_results: list[SourceRunResult],
        queries_used: list[str],
        counts: dict[str, int],
        warnings: list[str],
        search_run_id: str | None = None,
    ):
        self.jobs = jobs
        self.matches = matches
        self.source_results = source_results
        self.queries_used = queries_used
        self.counts = counts
        self.warnings = warnings
        self.search_run_id = search_run_id

    @property
    def total_jobs(self) -> int:
        return len(self.jobs)

    @property
    def has_partial_failures(self) -> bool:
        return any(
            r.status in (SourceStatus.failed, SourceStatus.partial)
            for r in self.source_results
        )


class SearchWorkflowService:
    """Orchestrates the complete job search workflow.

    This is a deterministic orchestrator, not an autonomous agent.
    It coordinates: query generation → source fetch → normalize →
    deduplicate → filter → score → persist.
    """

    def __init__(
        self,
        registry: SourceRegistry,
        progress_callback: Callable[[str, str], None] | None = None,
    ):
        self._registry = registry
        self._progress = SearchProgress(progress_callback)

    def run(
        self,
        profile: CandidateProfile,
        include_undated: bool = False,
        lookback_days: int | None = None,
        max_results_per_source: int = 50,
        demo_mode: bool | None = None,
    ) -> SearchResult:
        """Execute the full search workflow for a candidate profile."""
        settings = get_settings()
        if demo_mode is None:
            demo_mode = settings.demo_mode
        if lookback_days is None:
            lookback_days = settings.job_lookback_days

        start_time = time.monotonic()
        warnings: list[str] = []

        # Step 1: Generate queries
        self._progress.update("Generating search queries", "")
        queries = generate_search_queries(profile)
        logger.info("Queries generated", extra={"queries": queries})

        # Step 2: Determine sources to search
        if demo_mode:
            sources = [s for s in self._registry.all_sources() if s.source_name == "demo"]
        else:
            sources = self._registry.enabled_sources()
            # Exclude demo source in live mode
            sources = [s for s in sources if s.source_name != "demo"]

        if not sources:
            warnings.append("No job sources are available. Check your configuration.")

        self._progress.update(
            "Searching sources",
            f"Querying {len(sources)} source(s): {', '.join(s.display_name for s in sources)}",
        )

        # Step 3: Fetch from all sources
        all_raw_jobs: list[NormalizedJob] = []
        source_results: list[SourceRunResult] = []
        cutoff = get_lookback_cutoff(days=lookback_days)

        for source in sources:
            self._progress.update(f"Fetching from {source.display_name}", "")
            try:
                jobs, run_result = source.fetch_jobs(
                    queries=queries,
                    location="Egypt",
                    posted_after=cutoff,
                    max_results=max_results_per_source,
                )
                all_raw_jobs.extend(jobs)
                source_results.append(run_result)
                if run_result.status in (SourceStatus.failed, SourceStatus.partial):
                    warnings.append(f"{source.display_name}: {run_result.message}")
            except Exception as exc:
                logger.error(
                    "Source fetch error",
                    extra={"source": source.source_name, "error": str(exc)[:100]},
                )
                source_results.append(SourceRunResult(
                    source_name=source.source_name,
                    status=SourceStatus.failed,
                    message=f"Unexpected error: {type(exc).__name__}",
                    error_category="unexpected",
                ))
                warnings.append(f"{source.display_name} failed unexpectedly.")

        total_fetched = len(all_raw_jobs)
        self._progress.update(
            "Normalizing and deduplicating",
            f"{total_fetched} jobs fetched",
        )

        # Step 4: Normalize
        normalized = [normalize_job(j) for j in all_raw_jobs]

        # Step 5: Deduplicate
        deduped = deduplicate_jobs(normalized)

        # Step 6: Apply freshness filter
        fresh_jobs = filter_by_freshness(
            deduped,
            cutoff=cutoff,
            include_undated=include_undated,
        )

        # Add undated jobs if include_undated=True (already handled in filter)
        # If demo mode, include all demo jobs regardless (they have verified dates)
        if demo_mode:
            fresh_jobs = deduped  # Use all demo jobs, they have dates in fixture

        self._progress.update(
            "Filtering by location",
            f"{len(fresh_jobs)} jobs after freshness filter",
        )

        # Step 7: Location eligibility filter
        eligible_jobs: list[NormalizedJob] = []
        ineligible_count = 0
        for job in fresh_jobs:
            eligible, reason = is_eligible_for_candidate(job, profile)
            if eligible is True:
                eligible_jobs.append(job)
            elif eligible is None:
                eligible_jobs.append(job)  # uncertain — include with flag
            else:
                ineligible_count += 1

        if ineligible_count:
            logger.info("Ineligible jobs filtered", extra={"count": ineligible_count})

        self._progress.update(
            "Computing match scores",
            f"{len(eligible_jobs)} jobs to score",
        )

        # Step 8: Compute match scores
        matches: list[MatchResult] = []
        for job in eligible_jobs:
            eligible_flag, elig_reason = is_eligible_for_candidate(job, profile)
            if eligible_flag is True:
                elig_status = EligibilityStatus.eligible
            elif eligible_flag is False:
                elig_status = EligibilityStatus.likely_ineligible
            else:
                elig_status = EligibilityStatus.unknown

            match = compute_match_score(
                profile=profile,
                job=job,
                eligibility_status=elig_status,
                eligibility_reasons=[elig_reason] if elig_reason else [],
            )
            matches.append(match)

        # Sort by score descending
        matches.sort(key=lambda m: m.match_score, reverse=True)
        # Keep jobs in same order as matches
        job_by_id = {str(j.id): j for j in eligible_jobs}
        sorted_jobs = [
            job_by_id[str(m.job_id)] for m in matches if str(m.job_id) in job_by_id
        ]

        elapsed = time.monotonic() - start_time
        self._progress.update(
            "Complete",
            f"{len(sorted_jobs)} results in {elapsed:.1f}s",
        )

        counts = {
            "fetched": total_fetched,
            "after_dedup": len(deduped),
            "after_freshness": len(fresh_jobs),
            "after_location": len(eligible_jobs),
            "matched": len(matches),
        }

        return SearchResult(
            jobs=sorted_jobs,
            matches=matches,
            source_results=source_results,
            queries_used=queries,
            counts=counts,
            warnings=warnings,
        )
