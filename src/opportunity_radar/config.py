from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).parent.parent.parent.parent  # repo root


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_env: Literal["development", "staging", "production"] = "development"
    demo_mode: bool = False
    default_timezone: str = "Africa/Cairo"
    database_url: str = "sqlite:///./data/opportunity_radar.db"

    # LLM
    llm_provider: Literal["gemini", "openai", "none"] = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    gemini_embedding_model: str = "gemini-embedding-001"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    # Matching
    enable_semantic_matching: bool = True
    matching_version: str = "1.0.0"
    skill_weight: float = 0.50
    experience_weight: float = 0.25
    title_weight: float = 0.25
    work_arrangement_weight: float = 0.00

    # CV
    cv_max_size_mb: int = 10

    # Sources
    request_timeout_seconds: int = 15
    max_pages_per_source: int = 2
    max_concurrent_source_requests: int = 3
    job_lookback_days: int = 7
    enable_linkedin_source: bool = True
    enable_wuzzuf_source: bool = True
    enable_remoteok_source: bool = True
    enable_greenhouse_source: bool = False
    enable_lever_source: bool = False
    enable_adzuna_source: bool = False
    enable_remotive_source: bool = True
    enable_bayt_source: bool = True
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    greenhouse_board_slugs: str = ""  # comma-separated
    lever_company_slugs: str = ""  # comma-separated

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v:
            return "sqlite:///./data/opportunity_radar.db"
        return v

    @property
    def cv_max_size_bytes(self) -> int:
        return self.cv_max_size_mb * 1024 * 1024

    @property
    def has_llm(self) -> bool:
        if self.llm_provider == "gemini":
            return bool(self.gemini_api_key)
        if self.llm_provider == "openai":
            return bool(self.openai_api_key)
        return False

    @property
    def greenhouse_slugs_list(self) -> list[str]:
        return [s.strip() for s in self.greenhouse_board_slugs.split(",") if s.strip()]

    @property
    def lever_slugs_list(self) -> list[str]:
        return [s.strip() for s in self.lever_company_slugs.split(",") if s.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
