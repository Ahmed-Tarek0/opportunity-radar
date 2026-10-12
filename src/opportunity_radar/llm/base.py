from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider name."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Model identifier being used."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if the provider has valid credentials."""

    @abstractmethod
    def generate(
        self,
        user_prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> str:
        """Generate a text response.

        Args:
            user_prompt: The user message.
            system_prompt: Optional system instruction.
            temperature: Generation temperature (0.0 = deterministic).
            max_tokens: Maximum response tokens.

        Returns:
            Generated text response.

        Raises:
            LLMProviderError: If generation fails.
        """

    def get_embedding(self, text: str) -> list[float]:
        """Get a text embedding vector. Returns empty list if not supported."""
        return []

    def supports_embeddings(self) -> bool:
        """Return True if this provider supports embeddings."""
        return False
