from __future__ import annotations

from ..config import get_settings
from ..logging_config import get_logger
from ..schemas.source import SourceRunResult, SourceStatus
from .base import JobSource

logger = get_logger("sources.registry")


class SourceRegistry:
    """Registry of all available job source adapters."""

    def __init__(self) -> None:
        self._sources: dict[str, JobSource] = {}

    def register(self, source: JobSource) -> None:
        self._sources[source.source_name] = source
        logger.info("Source registered", extra={"source": source.source_name})

    def get(self, name: str) -> JobSource | None:
        return self._sources.get(name)

    def all_sources(self) -> list[JobSource]:
        return list(self._sources.values())

    def enabled_sources(self) -> list[JobSource]:
        return [
            s for s in self._sources.values()
            if s.is_enabled() and s.is_configured()
        ]

    def source_statuses(self) -> list[SourceRunResult]:
        statuses = []
        for source in self._sources.values():
            if not source.is_enabled():
                statuses.append(SourceRunResult(
                    source_name=source.source_name,
                    status=SourceStatus.disabled,
                    message=f"{source.display_name} is disabled in settings.",
                ))
            elif not source.is_configured():
                statuses.append(SourceRunResult(
                    source_name=source.source_name,
                    status=SourceStatus.not_configured,
                    message=f"{source.display_name} requires additional configuration.",
                ))
            else:
                statuses.append(SourceRunResult(
                    source_name=source.source_name,
                    status=SourceStatus.success,
                    message=f"{source.display_name} is ready.",
                ))
        return statuses


def build_registry() -> SourceRegistry:
    """Build and populate the source registry from settings."""
    settings = get_settings()
    registry = SourceRegistry()

    # Demo source (always available)
    from .demo import DemoSource
    registry.register(DemoSource())

    # LinkedIn
    if True:  # always registered, enabled/disabled via settings
        from .linkedin.client import LinkedInSource
        registry.register(LinkedInSource())

    # WUZZUF
    from .wuzzuf.client import WuzzufSource
    registry.register(WuzzufSource())

    # Remote OK
    from .remoteok.client import RemoteOKSource
    registry.register(RemoteOKSource())

    # Greenhouse
    from .greenhouse.client import GreenhouseSource
    registry.register(GreenhouseSource())

    # Lever
    from .lever.client import LeverSource
    registry.register(LeverSource())

    # Adzuna
    from .adzuna.client import AdzunaSource
    registry.register(AdzunaSource())

    # Remotive (public remote jobs API, no key required)
    from .remotive.client import RemotiveSource
    registry.register(RemotiveSource())

    # Bayt Egypt (public Egyptian job search, no key required)
    from .bayt.client import BaytSource
    registry.register(BaytSource())

    logger.info("Source registry built", extra={"total": len(registry.all_sources())})
    return registry
