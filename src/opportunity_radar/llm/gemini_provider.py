from __future__ import annotations

from ..exceptions import LLMProviderError
from ..logging_config import get_logger
from .base import LLMProvider

logger = get_logger("llm.gemini")


class GeminiProvider(LLMProvider):
    """Gemini LLM provider using the google-genai SDK."""

    def __init__(self, api_key: str, model: str, embedding_model: str | None = None) -> None:
        self._api_key = api_key
        self._model = model
        self._embedding_model = embedding_model
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from google import genai
                self._client = genai.Client(api_key=self._api_key)
            except ImportError:
                raise LLMProviderError(
                    "google-genai package is not installed. "
                    "Run: pip install google-genai"
                )
        return self._client

    @property
    def provider_name(self) -> str:
        return "Gemini (Google AI)"

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
                "Gemini API key is not configured. "
                "Set GEMINI_API_KEY in your .env file."
            )

        client = self._get_client()

        contents = user_prompt

        try:
            from google.genai import types
            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=temperature,
                max_output_tokens=max_tokens,
            )
            response = client.models.generate_content(
                model=self._model,
                contents=contents,
                config=config,
            )
            text = response.text
            if not text:
                raise LLMProviderError("Gemini returned an empty response")
            return text
        except LLMProviderError:
            raise
        except Exception as exc:
            error_str = str(exc)
            if "API_KEY_INVALID" in error_str or "API key" in error_str:
                raise LLMProviderError(
                    f"Invalid Gemini API key. Please check GEMINI_API_KEY. Details: {exc}"
                ) from exc
            if "model" in error_str.lower() and "not found" in error_str.lower():
                raise LLMProviderError(
                    f"Gemini model '{self._model}' is not available. "
                    f"Check GEMINI_MODEL in your .env file. Details: {exc}"
                ) from exc
            if "quota" in error_str.lower() or "rate" in error_str.lower():
                raise LLMProviderError(
                    f"Gemini quota/rate limit exceeded. Details: {exc}"
                ) from exc
            raise LLMProviderError(f"Gemini generation failed: {exc}") from exc

    def get_embedding(self, text: str) -> list[float]:
        if not self._embedding_model:
            return []
        if not self.is_configured():
            return []

        client = self._get_client()
        try:
            response = client.models.embed_content(
                model=self._embedding_model,
                contents=text,
            )
            return response.embeddings[0].values
        except Exception as exc:
            logger.warning("Gemini embedding failed", extra={"error": str(exc)[:100]})
            return []

    def supports_embeddings(self) -> bool:
        return bool(self._embedding_model and self._api_key)
