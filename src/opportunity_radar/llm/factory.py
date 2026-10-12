from __future__ import annotations

from ..config import Settings, get_settings
from ..logging_config import get_logger
from .base import LLMProvider

logger = get_logger("llm.factory")


def create_llm_provider(settings: Settings | None = None) -> LLMProvider | None:
    """Create an LLM provider instance based on configuration.

    Returns None if no LLM is configured or available.
    Never raises — the app must start without an LLM.
    """
    if settings is None:
        settings = get_settings()

    provider_name = settings.llm_provider.lower()

    if provider_name == "none":
        logger.info("LLM provider set to 'none'")
        return None

    if provider_name == "gemini":
        if not settings.gemini_api_key:
            logger.info("Gemini API key not configured; LLM features disabled")
            return None
        from .gemini_provider import GeminiProvider
        provider = GeminiProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            embedding_model=settings.gemini_embedding_model,
        )
        logger.info(
            "Gemini provider created",
            extra={"model": settings.gemini_model},
        )
        return provider

    if provider_name == "openai":
        if not settings.openai_api_key:
            logger.info("OpenAI API key not configured; LLM features disabled")
            return None
        from .openai_provider import OpenAIProvider
        provider = OpenAIProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            embedding_model=settings.openai_embedding_model,
        )
        logger.info(
            "OpenAI provider created",
            extra={"model": settings.openai_model},
        )
        return provider

    logger.warning("Unknown LLM provider", extra={"provider": provider_name})
    return None
