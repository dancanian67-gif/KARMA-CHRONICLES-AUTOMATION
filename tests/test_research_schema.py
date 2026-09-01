"""Tests for research schema."""

import pytest
from pydantic import ValidationError

from karma.schemas.research import (
    ConfidenceLevel,
    ResearchBrief,
    ResearchClaim,
    ResearchSource,
)


def test_valid_research_object():
    brief = ResearchBrief(
        topic="The debt collector who vanished",
        premise_context="Urban karma tale set in Nairobi.",
        factual_claims=[
            ResearchClaim(
                claim="Microfinance debt cycles are a documented social issue.",
                confidence=ConfidenceLevel.HIGH,
            ),
        ],
        sources=[ResearchSource(title="Field notes", url="https://example.com/notes")],
        real_world_context="Contemporary East African city life.",
        research_notes=["Focus on moral ambiguity, not documentary tone."],
    )

    assert brief.topic.startswith("The debt")
    assert brief.factual_claims[0].confidence == ConfidenceLevel.HIGH


def test_invalid_required_fields():
    with pytest.raises(ValidationError):
        ResearchBrief(topic="Only topic")


def test_research_serialization_round_trip():
    brief = ResearchBrief(
        topic="Borrowed time",
        premise_context="A lender discovers every loan he makes returns as karma.",
    )
    restored = ResearchBrief.model_validate_json(brief.model_dump_json())
    assert restored == brief
