"""Gemini structured-output adapter for the karma LLM foundation."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel

from karma.llm.errors import (
    LLMGenerationError,
    TransientLLMError,
    is_transient_error,
)
from karma.llm.types import LLMRequest
from karma.llm.validation import parse_structured_response

T = TypeVar("T", bound=BaseModel)

DEFAULT_GEMINI_MODELS: tuple[str, ...] = (
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemma-4-31b-it",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemma-3-27b-it",
    "gemini-1.5-flash-001",
    "gemini-1.5-pro-001",
)


def build_model_chain(
    models: tuple[str, ...] | list[str],
    starting_model: str | None = None,
) -> list[str]:
    """Rotate the model chain so ``starting_model`` is first when known."""
    chain = list(models)
    preferred = (starting_model or "").strip()
    if preferred and preferred in chain:
        index = chain.index(preferred)
        return chain[index:] + chain[:index]
    return chain


class GeminiStructuredClient:
    """Gemini adapter that returns Pydantic-validated structured output."""

    def __init__(
        self,
        api_key: str,
        *,
        models: tuple[str, ...] | list[str] | None = None,
        starting_model: str | None = None,
        max_attempts_per_model: int = 3,
        client: Any | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("api_key must be provided")

        self._api_key = api_key
        self._models = tuple(models or DEFAULT_GEMINI_MODELS)
        self._starting_model = starting_model
        self._max_attempts_per_model = max_attempts_per_model
        self._client = client
        self._sleeper = sleeper

    def generate_structured(
        self,
        request: LLMRequest,
        response_model: type[T],
    ) -> T:
        """Generate structured output with model fallback and validation."""
        chain = build_model_chain(
            self._models,
            request.model or self._starting_model,
        )
        last_error: Exception | None = None

        for model_name in chain:
            for attempt in range(self._max_attempts_per_model):
                try:
                    raw_text = self._generate_raw_text(request, model_name, response_model)
                    return parse_structured_response(raw_text, response_model)
                except Exception as exc:
                    last_error = exc
                    if not is_transient_error(exc):
                        raise

                    if attempt < self._max_attempts_per_model - 1:
                        self._sleeper(15 * (attempt + 1))
                        continue
                    break

        raise LLMGenerationError(
            "all configured Gemini models failed to produce structured output",
        ) from last_error

    def _generate_raw_text(
        self,
        request: LLMRequest,
        model_name: str,
        response_model: type[BaseModel],
    ) -> str:
        client = self._client or self._build_client()
        config = self._build_generation_config(request, response_model)
        response = client.models.generate_content(
            model=model_name,
            contents=request.prompt,
            config=config,
        )
        text = getattr(response, "text", None)
        if text is None:
            raise TransientLLMError("model returned empty text response")
        return text.strip()

    def _build_client(self) -> Any:
        from google import genai

        return genai.Client(api_key=self._api_key)

    def _build_generation_config(
        self,
        request: LLMRequest,
        response_model: type[BaseModel],
    ) -> Any:
        from google.genai import types

        config_kwargs: dict[str, Any] = {
            "temperature": request.temperature,
            "response_mime_type": "application/json",
            "response_schema": response_model.model_json_schema(),
        }
        if request.system_instruction:
            config_kwargs["system_instruction"] = request.system_instruction
        return types.GenerateContentConfig(**config_kwargs)
