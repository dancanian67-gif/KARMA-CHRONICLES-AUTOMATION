"""Episode script schema compatible with Phase 1 scene identity."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class ScriptLineKind(StrEnum):
    """Kind of content within a script scene."""

    NARRATION = "narration"
    DIALOGUE = "dialogue"
    ACTION = "action"
    TRANSITION = "transition"


class ScriptLine(BaseModel):
    """A single line of narration, dialogue, action, or transition."""

    kind: ScriptLineKind
    text: str
    character: str | None = None

    @model_validator(mode="after")
    def validate_dialogue_character(self) -> ScriptLine:
        if self.kind == ScriptLineKind.DIALOGUE and not self.character:
            raise ValueError("dialogue lines must include character")
        if self.kind != ScriptLineKind.DIALOGUE and self.character is not None:
            raise ValueError("character is only valid for dialogue lines")
        return self


class ScriptScene(BaseModel):
    """A scripted scene aligned with Phase 1 ``Scene.scene_id`` / ``scene_number``."""

    scene_id: str
    scene_number: int = Field(ge=1)
    title: str | None = None
    location: str | None = None
    time_context: str | None = None
    characters_present: list[str] = Field(default_factory=list)
    lines: list[ScriptLine] = Field(default_factory=list)
    transition_out: str | None = None


class EpisodeScript(BaseModel):
    """Full episode script for narration and production."""

    title: str
    working_title: str | None = None
    script_version: int = Field(default=1, ge=1)
    logline: str | None = None
    scenes: list[ScriptScene] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_scene_numbering(self) -> EpisodeScript:
        if not self.scenes:
            return self

        numbers = [scene.scene_number for scene in self.scenes]
        if len(numbers) != len(set(numbers)):
            raise ValueError("scene_number values must be unique within the script")

        ids = [scene.scene_id for scene in self.scenes]
        if len(ids) != len(set(ids)):
            raise ValueError("scene_id values must be unique within the script")

        return self
