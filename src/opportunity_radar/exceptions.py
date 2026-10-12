from __future__ import annotations


class OpportunityRadarError(Exception):
    """Base exception for all application errors."""


class ConfigurationError(OpportunityRadarError):
    """Raised when required configuration is missing or invalid."""


class CVParsingError(OpportunityRadarError):
    """Raised when CV file cannot be parsed."""


class CVValidationError(CVParsingError):
    """Raised for file size/type/content validation failures."""


class LLMProviderError(OpportunityRadarError):
    """Raised when LLM provider call fails."""


class LLMValidationError(LLMProviderError):
    """Raised when LLM output fails Pydantic validation."""


class SourceError(OpportunityRadarError):
    """Raised when a job source fails."""
    def __init__(self, source_name: str, message: str, category: str = "unknown") -> None:
        self.source_name = source_name
        self.category = category
        super().__init__(f"[{source_name}] {message}")


class SourceTimeoutError(SourceError):
    """Raised when a source request times out."""


class SourceParseError(SourceError):
    """Raised when source HTML/JSON cannot be parsed."""


class DatabaseError(OpportunityRadarError):
    """Raised when database operations fail."""


class DuplicateError(DatabaseError):
    """Raised when a unique constraint is violated."""


class MatchingError(OpportunityRadarError):
    """Raised when matching computation fails."""


class EmbeddingError(OpportunityRadarError):
    """Raised when embedding computation fails."""
