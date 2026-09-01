"""Story architecture schema for KARMA CHRONICLES episodes."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class CharacterRole(StrEnum):
    """Narrative role of a character in the story."""

    PROTAGONIST = "protagonist"
    ANTAGONIST = "antagonist"
    SUPPORTING = "supporting"
    OPPOSING_FORCE = "opposing_force"


class BeatType(StrEnum):
    """Type of major story beat."""

    SETUP = "setup"
    INCITING_INCIDENT = "inciting_incident"
    ESCALATION = "escalation"
    TURNING_POINT = "turning_point"
    CLIMAX = "climax"
    RESOLUTION = "resolution"
    CONSEQUENCE = "consequence"


class StoryCharacter(BaseModel):
    """A character in the story architecture."""

    character_id: str
    name: str
    role: CharacterRole
    motivation: str
    description: str | None = None
    relationships: list[str] = Field(default_factory=list)


class StoryBeat(BaseModel):
    """A major beat in the episode blueprint."""

    beat_id: str
    beat_type: BeatType
    title: str
    description: str
    order: int = Field(ge=1)
    involved_characters: list[str] = Field(default_factory=list)


class StoryArchitecture(BaseModel):
    """Blueprint for a KARMA CHRONICLES narrative episode."""

    premise: str
    theme: str
    protagonist_id: str
    antagonist_or_opposing_force_id: str
    supporting_character_ids: list[str] = Field(default_factory=list)
    characters: list[StoryCharacter] = Field(default_factory=list)
    central_conflict: str
    stakes: str
    setting: str
    major_beats: list[StoryBeat] = Field(default_factory=list)
    escalation: str
    turning_points: list[str] = Field(default_factory=list)
    climax: str
    resolution: str
    karma_payoff: str

    @model_validator(mode="after")
    def validate_character_references(self) -> StoryArchitecture:
        known_ids = {character.character_id for character in self.characters}
        required_ids = {
            self.protagonist_id,
            self.antagonist_or_opposing_force_id,
            *self.supporting_character_ids,
        }
        missing = required_ids - known_ids
        if missing:
            missing_list = ", ".join(sorted(missing))
            raise ValueError(
                f"characters list is missing referenced character_id(s): {missing_list}",
            )
        return self
