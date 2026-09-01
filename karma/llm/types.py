"""LLM request/response types."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LLMRequest(BaseModel):
    """Provider-agnostic structured generation request."""

    prompt: str
    system_instruction: str | None = None
    model: str | None = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
