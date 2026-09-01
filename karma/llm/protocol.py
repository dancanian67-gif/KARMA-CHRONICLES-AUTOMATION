"""Structured LLM client protocol."""

from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

from karma.llm.types import LLMRequest

T = TypeVar("T", bound=BaseModel)


class StructuredLLMClient(Protocol):
    """Provider-agnostic interface for typed LLM generation."""

    def generate_structured(
        self,
        request: LLMRequest,
        response_model: type[T],
    ) -> T:
        """Generate and validate structured output."""
