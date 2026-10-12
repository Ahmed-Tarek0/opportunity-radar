#!/usr/bin/env python
"""CLI diagnostic script that checks connectivity, configuration, and health of all job sources."""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add src to python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from opportunity_radar.logging_config import setup_logging
from opportunity_radar.sources.registry import build_registry
from opportunity_radar.schemas.source import SourceStatus


def format_status(status: SourceStatus) -> str:
    """Format status with terminal color codes."""
    if status == SourceStatus.success:
        return "\033[92mSUCCESS\033[0m"
    elif status == SourceStatus.partial:
        return "\033[93mPARTIAL\033[0m"
    elif status == SourceStatus.not_configured:
        return "\033[94mNOT CONFIGURED\033[0m"
    elif status == SourceStatus.disabled:
        return "\033[90mDISABLED\033[0m"
    elif status == SourceStatus.failed:
        return "\033[91mFAILED\033[0m"
    return status.value.upper()


def run_diagnostics() -> None:
    """Run health checks and dry-run query fetches on all configured sources."""
    setup_logging()
    registry = build_registry()
    sources = registry.all_sources()

    print("\n" + "=" * 90)
    print(" 📡 OPPORTUNITY RADAR — SOURCE HEALTH & DIAGNOSTIC CHECK")
    print("=" * 90)
    print(f"{'Source ID':<14} | {'Display Name':<24} | {'Status':<16} | {'Jobs':<6} | {'Message / Reason'}")
    print("-" * 90)

    test_queries = ["python"]
    summary_counts: dict[str, int] = {
        "success": 0,
        "partial": 0,
        "not_configured": 0,
        "disabled": 0,
        "failed": 0,
    }

    for source in sources:
        name = source.source_name
        display = source.display_name[:24]

        if not source.is_enabled():
            status = SourceStatus.disabled
            msg = "Disabled in settings (.env)"
            count = 0
        elif not source.is_configured():
            status = SourceStatus.not_configured
            msg = "Missing required credentials or slug parameters"
            count = 0
        else:
            # Perform a test dry-run query
            start_t = time.monotonic()
            try:
                jobs, run_result = source.fetch_jobs(
                    queries=test_queries,
                    max_results=5,
                )
                status = run_result.status
                count = len(jobs)
                dur = time.monotonic() - start_t
                msg = run_result.message or f"Fetched {count} jobs in {dur:.2f}s"
            except Exception as exc:
                status = SourceStatus.failed
                count = 0
                msg = f"Exception: {exc}"

        summary_counts[status.value] = summary_counts.get(status.value, 0) + 1
        status_styled = format_status(status)
        clean_msg = (msg[:38] + "...") if len(msg) > 40 else msg
        print(f"{name:<14} | {display:<24} | {status_styled:<25} | {count:<6} | {clean_msg}")

    print("-" * 90)
    print(
        f"Summary: "
        f"Ready={summary_counts['success']} | "
        f"Not Configured={summary_counts['not_configured']} | "
        f"Disabled={summary_counts['disabled']} | "
        f"Partial={summary_counts['partial']} | "
        f"Failed={summary_counts['failed']} | "
        f"Total Sources={len(sources)}"
    )
    print("=" * 90 + "\n")


if __name__ == "__main__":
    run_diagnostics()
