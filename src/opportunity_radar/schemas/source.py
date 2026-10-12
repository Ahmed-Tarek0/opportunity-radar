from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class SourceStatus(str, Enum):
    success = "success"
    partial = "partial"
    disabled = "disabled"
    not_configured = "not_configured"
    failed = "failed"
    not_implemented = "not_implemented"


class SourceRunResult(BaseModel):
    source_name: str
    status: SourceStatus
    jobs_fetched: int = 0
    duration_seconds: float = 0.0
    message: str = ""
    error_category: str | None = None
    warnings: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None
