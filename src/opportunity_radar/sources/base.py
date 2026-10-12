from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from ..schemas.job import NormalizedJob
from ..schemas.source import SourceRunResult, SourceStatus


class JobSource(ABC):
    """Abstract base class for job source adapters."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Unique source identifier."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable source display name."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if source has all required configuration."""

    @abstractmethod
    def is_enabled(self) -> bool:
        """Return True if source is enabled in settings."""

    def health_check(self) -> SourceRunResult:
        """Check if source is reachable. Default implementation."""
        return SourceRunResult(
            source_name=self.source_name,
            status=SourceStatus.success if self.is_configured() else SourceStatus.not_configured,
            message="Health check not implemented",
        )

    @abstractmethod
    def search_jobs(
        self,
        queries: list[str],
        location: str | None = None,
        posted_after: datetime | None = None,
        max_results: int = 50,
    ) -> SourceRunResult:
        """Search for jobs and return a SourceRunResult with embedded jobs.

        The jobs are stored separately; this returns metadata.
        Use fetch_jobs() to get the actual NormalizedJob list.
        """

    @abstractmethod
    def fetch_jobs(
        self,
        queries: list[str],
        location: str | None = None,
        posted_after: datetime | None = None,
        max_results: int = 50,
    ) -> tuple[list[NormalizedJob], SourceRunResult]:
        """Fetch jobs and return (jobs, run_result)."""
