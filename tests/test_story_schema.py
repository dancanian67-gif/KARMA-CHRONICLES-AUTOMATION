"""Tests for story architecture schema."""

import pytest
from pydantic import ValidationError

from karma.schemas.story import (
    BeatType,
    CharacterRole,
    StoryArchitecture,
    StoryBeat,
    StoryCharacter,
)


def _sample_characters() -> list[StoryCharacter]:
    return [
        StoryCharacter(
            character_id="char_mara",
            name="Mara",
            role=CharacterRole.PROTAGONIST,
            motivation="Protect her younger brother from inherited debt.",
        ),
        StoryCharacter(
            character_id="char_kito",
            name="Kito",
            role=CharacterRole.ANTAGONIST,
            motivation="Collect what he is owed, no matter the cost.",
        ),
        StoryCharacter(
            character_id="char_ayo",
            name="Ayo",
            role=CharacterRole.SUPPORTING,
            motivation="Expose the ledger that binds the neighborhood.",
        ),
    ]


def test_valid_story_architecture():
    architecture = StoryArchitecture(
        premise="A debt collector is haunted by the consequences of every loan he enforces.",
        theme="Actions return to the actor.",
        protagonist_id="char_mara",
        antagonist_or_opposing_force_id="char_kito",
        supporting_character_ids=["char_ayo"],
        characters=_sample_characters(),
        central_conflict="Mara must stop Kito without becoming him.",
        stakes="Her brother's freedom and her own soul.",
        setting="A rain-soaked coastal city",
        major_beats=[
            StoryBeat(
                beat_id="beat_01",
                beat_type=BeatType.SETUP,
                title="The ledger opens",
                description="Mara inherits her mother's unpaid debts.",
                order=1,
            ),
        ],
        escalation="Each collection reveals a deeper chain of harm.",
        turning_points=["Mara discovers she once benefited from Kito's cruelty."],
        climax="She chooses mercy over collection.",
        resolution="The ledger is burned in public view.",
        karma_payoff="Kito is left holding debts he cannot collect from himself.",
    )

    assert architecture.theme == "Actions return to the actor."


def test_character_validation_requires_referenced_ids():
    with pytest.raises(ValidationError, match="missing referenced character_id"):
        StoryArchitecture(
            premise="Test",
            theme="Karma",
            protagonist_id="char_missing",
            antagonist_or_opposing_force_id="char_kito",
            supporting_character_ids=[],
            characters=_sample_characters()[1:],
            central_conflict="Conflict",
            stakes="Stakes",
            setting="Setting",
            escalation="Escalation",
            turning_points=[],
            climax="Climax",
            resolution="Resolution",
            karma_payoff="Payoff",
        )


def test_story_beat_validation():
    with pytest.raises(ValidationError):
        StoryBeat(
            beat_id="bad",
            beat_type=BeatType.CLIMAX,
            title="Invalid order",
            description="Order must be >= 1",
            order=0,
        )


def test_story_serialization_round_trip():
    architecture = StoryArchitecture(
        premise="Test premise",
        theme="Test theme",
        protagonist_id="char_mara",
        antagonist_or_opposing_force_id="char_kito",
        supporting_character_ids=["char_ayo"],
        characters=_sample_characters(),
        central_conflict="Conflict",
        stakes="Stakes",
        setting="Setting",
        major_beats=[
            StoryBeat(
                beat_id="beat_01",
                beat_type=BeatType.SETUP,
                title="Setup",
                description="Setup beat",
                order=1,
            ),
        ],
        escalation="Escalation",
        turning_points=["Turn"],
        climax="Climax",
        resolution="Resolution",
        karma_payoff="Payoff",
    )
    restored = StoryArchitecture.model_validate_json(architecture.model_dump_json())
    assert restored == architecture
