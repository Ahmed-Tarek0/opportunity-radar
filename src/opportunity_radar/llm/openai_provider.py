from __future__ import annotations

from ..exceptions import LLMProviderError
from ..logging_config import get_logger
from .base import LLMProvider

logger = get_logger("llm.openai")


class OpenAIProvider(LLMProvider):
    """OpenAI LLM provider."""

    def __init__(self, api_key: str, model: str, embedding_model: str | None = None) -> None:
        self._api_key = api_key
        self._model = model
        self._embedding_model = embedding_model
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self._api_key)
            except ImportError:
                raise LLMProviderError(
                    "openai package is not installed. Run: pip install openai"
                )
        return self._client

    @property
    def provider_name(self) -> str:
        return "OpenAI"

    @property
    def model_name(self) -> str:
        return self._model

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def generate(
        self,
        user_prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> str:
        if not self.is_configured():
            raise LLMProviderError(
                "OpenAI API key is not configured. Set OPENAI_API_KEY in your .env file."
            )

        client = self._get_client()
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        try:
            response = client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            text = response.choices[0].message.content
            if not text:
                raise LLMProviderError("OpenAI returned an empty response")
            return text
        except LLMProviderError:
            raise
        except Exception as exc:
            error_str = str(exc)
            if "model" in error_str.lower() and ("not found" in error_str.lower() or "does not exist" in error_str.lower()):
                raise LLMProviderError(
                    f"OpenAI model '{self._model}' is not available. "
                    f"Check OPENAI_MODEL in your .env file. Details: {exc}"
                ) from exc
            raise LLMProviderError(f"OpenAI generation failed: {exc}") from exc

    def get_embedding(self, text: str) -> list[float]:
        if not self._embedding_model or not self.is_configured():
            return []
        client = self._get_client()
        try:
            response = client.embeddings.create(
                model=self._embedding_model,
                input=text,
            )
            return response.data[0].embedding
        except Exception as exc:
            logger.warning("OpenAI embedding failed", extra={"error": str(exc)[:100]})
            return []

    def supports_embeddings(self) -> bool:
        return bool(self._embedding_model and self._api_key)
