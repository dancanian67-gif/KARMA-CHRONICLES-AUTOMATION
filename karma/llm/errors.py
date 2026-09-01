"""LLM client errors."""

from __future__ import annotations


class LLMError(Exception):
    """Base error for LLM operations."""


class TransientLLMError(LLMError):
    """Raised when an LLM failure is likely temporary."""


class StructuredOutputValidationError(LLMError):
    """Raised when model output cannot be validated against the expected schema."""


class LLMGenerationError(LLMError):
    """Raised when all models/retries are exhausted."""


def is_transient_error(exc: BaseException) -> bool:
    """Return True when the error suggests retrying or switching models."""
    message = str(exc)
    transient_markers = (
        "429",
        "RESOURCE_EXHAUSTED",
        "quota",
        "rate limit",
        "503",
        "UNAVAILABLE",
        "overloaded",
        "high demand",
        "500",
        "INTERNAL",
        "404",
        "NOT_FOUND",
        "not found",
    )
    return any(marker in message for marker in transient_markers)
