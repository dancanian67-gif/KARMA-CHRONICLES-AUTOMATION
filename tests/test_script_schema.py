"""Tests for episode script schema."""

import pytest
from pydantic import ValidationError

from karma.schemas.script import (
    EpisodeScript,
    ScriptLine,
    ScriptLineKind,
    ScriptScene,
)


def test_valid_multi_scene_script():
    script = EpisodeScript(
        title="The Ledger of Rain",
        working_title="Ledger Draft 1",
        script_version=1,
        logline="A collector learns every debt eventually collects its maker.",
        scenes=[
            ScriptScene(
                scene_id="scene_01",
                scene_number=1,
                title="Opening Rain",
                location="City market",
                time_context="Night",
                characters_present=["Mara"],
                lines=[
                    ScriptLine(
                        kind=ScriptLineKind.NARRATION,
                        text="Rain does not wash debts away. It only makes them harder to see.",
                    ),
                    ScriptLine(
                        kind=ScriptLineKind.ACTION,
                        text="Mara closes a rusted ledger beneath her coat.",
                    ),
                ],
            ),
            ScriptScene(
                scene_id="scene_02",
                scene_number=2,
                location="Debt office",
                characters_present=["Mara", "Kito"],
                lines=[
                    ScriptLine(
                        kind=ScriptLineKind.DIALOGUE,
                        character="Kito",
                        text="Everyone pays. Eventually.",
                    ),
                ],
                transition_out="Cut to black.",
            ),
        ],
    )

    assert len(script.scenes) == 2
    assert script.scenes[1].lines[0].kind == ScriptLineKind.DIALOGUE


def test_narration_dialogue_distinction():
    with pytest.raises(ValidationError, match="dialogue lines must include character"):
        ScriptLine(kind=ScriptLineKind.DIALOGUE, text="Who are you?")

    with pytest.raises(ValidationError, match="character is only valid for dialogue"):
        ScriptLine(
            kind=ScriptLineKind.NARRATION,
            text="Narration only.",
            character="Mara",
        )


def test_scene_numbering_and_identity_constraints():
    with pytest.raises(ValidationError, match="scene_number values must be unique"):
        EpisodeScript(
            title="Duplicate numbers",
            scenes=[
                ScriptScene(scene_id="scene_a", scene_number=1),
                ScriptScene(scene_id="scene_b", scene_number=1),
            ],
        )

    with pytest.raises(ValidationError, match="scene_id values must be unique"):
        EpisodeScript(
            title="Duplicate ids",
            scenes=[
                ScriptScene(scene_id="scene_a", scene_number=1),
                ScriptScene(scene_id="scene_a", scene_number=2),
            ],
        )


def test_script_serialization_round_trip():
    script = EpisodeScript(
        title="Round Trip",
        scenes=[ScriptScene(scene_id="scene_01", scene_number=1)],
    )
    restored = EpisodeScript.model_validate_json(script.model_dump_json())
    assert restored == script
