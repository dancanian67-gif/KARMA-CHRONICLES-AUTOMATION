"""Structured LLM foundation for KARMA CHRONICLES."""

from karma.llm.errors import (
    LLMError,
    LLMGenerationError,
    StructuredOutputValidationError,
    TransientLLMError,
    is_transient_error,
)
from karma.llm.gemini import DEFAULT_GEMINI_MODELS, GeminiStructuredClient, build_model_chain
from karma.llm.protocol import StructuredLLMClient
from karma.llm.types import LLMRequest
from karma.llm.validation import parse_structured_response

__all__ = [
    "DEFAULT_GEMINI_MODELS",
    "GeminiStructuredClient",
    "LLMError",
    "LLMGenerationError",
    "LLMRequest",
    "StructuredLLMClient",
    "StructuredOutputValidationError",
    "TransientLLMError",
    "build_model_chain",
    "is_transient_error",
    "parse_structured_response",
]
