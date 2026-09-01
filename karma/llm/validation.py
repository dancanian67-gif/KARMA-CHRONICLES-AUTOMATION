"""Structured output parsing and validation."""

from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from karma.llm.errors import StructuredOutputValidationError

T = TypeVar("T", bound=BaseModel)


def parse_structured_response(text: str, response_model: type[T]) -> T:
    """Validate model text output against a Pydantic response model."""
    if not text or not text.strip():
        raise StructuredOutputValidationError(
            f"empty response for {response_model.__name__}",
        )

    try:
        return response_model.model_validate_json(text)
    except json.JSONDecodeError as exc:
        raise StructuredOutputValidationError(
            f"invalid JSON for {response_model.__name__}: {exc}",
        ) from exc
    except ValidationError as exc:
        raise StructuredOutputValidationError(
            f"schema validation failed for {response_model.__name__}: {exc}",
        ) from exc
