"""Research schema for narrative episode development."""

from enum import StrEnum

from pydantic import BaseModel, Field


class ConfidenceLevel(StrEnum):
    """Confidence in a research claim or finding."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class ResearchSource(BaseModel):
    """A reference consulted during research."""

    title: str
    url: str | None = None
    notes: str | None = None


class ResearchClaim(BaseModel):
    """A factual claim relevant to the proposed narrative."""

    claim: str
    confidence: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    notes: str | None = None


class ResearchBrief(BaseModel):
    """Structured research findings for a proposed KARMA CHRONICLES episode."""

    topic: str
    premise_context: str
    factual_claims: list[ResearchClaim] = Field(default_factory=list)
    sources: list[ResearchSource] = Field(default_factory=list)
    real_world_context: str | None = None
    research_notes: list[str] = Field(default_factory=list)
