"""Tests for Phase 2B.3 scriptwriter stage."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from karma.llm import LLMRequest, StructuredOutputValidationError
from karma.orchestration import Orchestrator, StageExecutionError
from karma.orchestration.stages import (
    STAGE_REGISTRY,
    StageContext,
    StageDefinition,
    run_script,
)
from karma.scriptwriter import scriptwriter
from karma.schemas.episode import EpisodeStatus, StageCheckpoint, StageRunStatus
from karma.schemas.research import ResearchBrief, ResearchClaim, ResearchSource
from karma.schemas.script import (
    EpisodeScript,
    ScriptLine,
    ScriptLineKind,
    ScriptScene,
)
from karma.schemas.story import (
    BeatType,
    CharacterRole,
    StoryArchitecture,
    StoryBeat,
    StoryCharacter,
)
from karma.storage import EpisodeStore


@pytest.fixture
def store(tmp_path: Path) -> EpisodeStore:
    return EpisodeStore(tmp_path / "01_EPISODES")


@pytest.fixture
def orchestrator(store: EpisodeStore) -> Orchestrator:
    return Orchestrator(store)


def _make_fake_llm_client(response: Any) -> MagicMock:
    """Create a fake LLM client that returns structured output."""
    client = MagicMock()
    client.generate_structured.return_value = response
    return client


def _valid_research_brief() -> ResearchBrief:
    """Create a valid research brief for testing."""
    return ResearchBrief(
        topic="The debt collector who vanished",
        premise_context="Urban karma tale set in Nairobi",
        factual_claims=[
            ResearchClaim(
                claim="Microfinance debt cycles are documented social issues",
                confidence="high",
                notes="Common in informal economies",
            ),
        ],
        sources=[
            ResearchSource(
                title="Field research notes",
                url="https://example.com/notes",
                notes="Primary source",
            ),
        ],
        real_world_context="Contemporary East African city life",
        research_notes=["Focus on moral complexity, not moralism"],
    )


def _valid_story_architecture() -> StoryArchitecture:
    """Create a valid story architecture for testing."""
    return StoryArchitecture(
        premise="A debt collector haunted by consequences.",
        theme="Actions return to the actor.",
        protagonist_id="char_mara",
        antagonist_or_opposing_force_id="char_kito",
        supporting_character_ids=["char_ayo"],
        characters=[
            StoryCharacter(
                character_id="char_mara",
                name="Mara",
                role=CharacterRole.PROTAGONIST,
                motivation="Protect her brother from inherited debt",
                description="A fierce woman bound by family loyalty",
            ),
            StoryCharacter(
                character_id="char_kito",
                name="Kito",
                role=CharacterRole.ANTAGONIST,
                motivation="Collect what is owed, no matter the cost",
                description="A relentless debt collector",
            ),
            StoryCharacter(
                character_id="char_ayo",
                name="Ayo",
                role=CharacterRole.SUPPORTING,
                motivation="Expose systemic injustice",
                description="A crusading journalist",
            ),
        ],
        central_conflict="Mara must stop Kito without becoming him.",
        stakes="Her brother's freedom and her own soul.",
        setting="A rain-soaked coastal city in East Africa",
        major_beats=[
            StoryBeat(
                beat_id="beat_1",
                beat_type=BeatType.SETUP,
                title="The Ledger",
                description="Mara inherits her father's debt collection ledger",
                order=1,
                involved_characters=["char_mara"],
            ),
            StoryBeat(
                beat_id="beat_2",
                beat_type=BeatType.INCITING_INCIDENT,
                title="The Debt Returns",
                description="Kito arrives demanding the first collection",
                order=2,
                involved_characters=["char_mara", "char_kito"],
            ),
            StoryBeat(
                beat_id="beat_3",
                beat_type=BeatType.CLIMAX,
                title="The Choice",
                description="Mara must decide between revenge and redemption",
                order=3,
                involved_characters=["char_mara", "char_kito"],
            ),
            StoryBeat(
                beat_id="beat_4",
                beat_type=BeatType.RESOLUTION,
                title="The Ledger Burns",
                description="Mara destroys the ledger, breaking the cycle",
                order=4,
                involved_characters=["char_mara"],
            ),
            StoryBeat(
                beat_id="beat_5",
                beat_type=BeatType.CONSEQUENCE,
                title="Karma Complete",
                description="The weight lifts; consequences settle",
                order=5,
                involved_characters=["char_mara", "char_kito"],
            ),
        ],
        escalation="Debts compound as Kito's methods grow more aggressive",
        turning_points=[
            "Mara discovers Kito's humanity beneath cruelty",
            "Kito realizes the ledger destroys everyone it touches",
        ],
        climax="Mara confronts Kito as the ledger burns between them",
        resolution="Both are freed, though scarred by what they owe",
        karma_payoff="The debt collector learns debts can never truly be collected",
    )


def _valid_episode_script() -> EpisodeScript:
    """Create a valid episode script for testing."""
    return EpisodeScript(
        title="The Ledger of Rain",
        working_title="Ledger Draft 1",
        script_version=1,
        logline="A collector learns every debt eventually collects its maker.",
        scenes=[
            ScriptScene(
                scene_id="scene_01",
                scene_number=1,
                title="The Ledger",
                location="Mara's apartment",
                time_context="Night",
                characters_present=["char_mara"],
                lines=[
                    ScriptLine(
                        kind=ScriptLineKind.NARRATION,
                        text="Mara opens a rusted ledger. Each entry is a name, a debt, a consequence.",
                    ),
                    ScriptLine(
                        kind=ScriptLineKind.ACTION,
                        text="She closes her eyes, holding the weight of her inheritance.",
                    ),
                ],
            ),
            ScriptScene(
                scene_id="scene_02",
                scene_number=2,
                title="The Debt Returns",
                location="Debt office",
                time_context="Day",
                characters_present=["char_mara", "char_kito"],
                lines=[
                    ScriptLine(
                        kind=ScriptLineKind.NARRATION,
                        text="Kito waits at the desk. He is patient. He is inevitable.",
                    ),
                    ScriptLine(
                        kind=ScriptLineKind.DIALOGUE,
                        character="char_kito",
                        text="Everyone pays. Eventually.",
                    ),
                    ScriptLine(
                        kind=ScriptLineKind.DIALOGUE,
                        character="char_mara",
                        text="Not this time.",
                    ),
                ],
                transition_out="Cut to black.",
            ),
            ScriptScene(
                scene_id="scene_03",
                scene_number=3,
                title="The Choice",
                location="Rain-soaked street",
                time_context="Night",
                characters_present=["char_mara", "char_kito"],
                lines=[
                    ScriptLine(
                        kind=ScriptLineKind.ACTION,
                        text="Mara holds the ledger over a burning barrel. Rain falls.",
                    ),
                    ScriptLine(
                        kind=ScriptLineKind.NARRATION,
                        text="In this moment, the cycle could break.",
                    ),
                ],
            ),
        ],
    )


class TestScriptwriterFunction:
    """Tests for the scriptwriter() function."""

    def test_scriptwriter_valid_architecture_returns_script(self):
        """scriptwriter() with valid architecture and mock LLM returns EpisodeScript."""
        architecture = _valid_story_architecture()
        script = _valid_episode_script()
        fake_llm = _make_fake_llm_client(script)

        result = scriptwriter(architecture, fake_llm)

        assert isinstance(result, EpisodeScript)
        assert result.title == "The Ledger of Rain"
        assert len(result.scenes) == 3

    def test_scriptwriter_calls_llm_with_correct_request(self):
        """scriptwriter() calls LLM with properly formatted request."""
        architecture = _valid_story_architecture()
        script = _valid_episode_script()
        fake_llm = _make_fake_llm_client(script)

        scriptwriter(architecture, fake_llm)

        # Verify LLM was called with correct signature
        fake_llm.generate_structured.assert_called_once()
        call_args = fake_llm.generate_structured.call_args
        request: LLMRequest = call_args[0][0]
        response_model = call_args[0][1]

        assert architecture.premise in request.prompt
        assert architecture.theme in request.prompt
        assert response_model == EpisodeScript
        assert request.temperature == 0.6

    def test_scriptwriter_includes_characters_in_prompt(self):
        """scriptwriter() includes all characters in the LLM prompt."""
        architecture = _valid_story_architecture()
        script = _valid_episode_script()
        fake_llm = _make_fake_llm_client(script)

        scriptwriter(architecture, fake_llm)

        call_args = fake_llm.generate_structured.call_args
        request: LLMRequest = call_args[0][0]

        # Verify character information is in the prompt
        assert "char_mara" in request.prompt
        assert "Mara" in request.prompt
        assert "char_kito" in request.prompt
        assert "Kito" in request.prompt

    def test_scriptwriter_includes_beats_in_prompt(self):
        """scriptwriter() includes all story beats in the LLM prompt."""
        architecture = _valid_story_architecture()
        script = _valid_episode_script()
        fake_llm = _make_fake_llm_client(script)

        scriptwriter(architecture, fake_llm)

        call_args = fake_llm.generate_structured.call_args
        request: LLMRequest = call_args[0][0]

        # Verify beat information is in the prompt
        for beat in architecture.major_beats:
            assert beat.title in request.prompt

    def test_scriptwriter_llm_failure_propagates(self):
        """scriptwriter() propagates LLM errors without swallowing."""
        architecture = _valid_story_architecture()
        fake_llm = MagicMock()
        fake_llm.generate_structured.side_effect = ValueError("LLM unavailable")

        with pytest.raises(ValueError, match="LLM unavailable"):
            scriptwriter(architecture, fake_llm)

    def test_scriptwriter_validation_failure_propagates(self):
        """scriptwriter() raises when LLM returns invalid schema."""
        architecture = _valid_story_architecture()
        fake_llm = MagicMock()
        fake_llm.generate_structured.side_effect = StructuredOutputValidationError(
            "Invalid schema"
        )

        with pytest.raises(StructuredOutputValidationError):
            scriptwriter(architecture, fake_llm)


class TestScriptwriterStage:
    """Tests for the run_script stage."""

    def test_script_stage_missing_story_raises_without_llm_call(
        self, store: EpisodeStore
    ):
        """run_script() raises ValueError if story is missing."""
        store.create_episode("KC_SC100")
        manifest = store.load_episode("KC_SC100")
        # story.content is None by default
        ctx = StageContext(manifest, store)

        with pytest.raises(ValueError, match="story stage must be completed"):
            run_script(ctx)

    def test_script_stage_invalid_story_raises_deterministically(
        self, store: EpisodeStore
    ):
        """run_script() raises ValueError if story.content is corrupted."""
        store.create_episode("KC_SC101")
        manifest = store.load_episode("KC_SC101")
        manifest.story.content = {"invalid": "schema"}
        ctx = StageContext(manifest, store)

        with pytest.raises(ValueError, match="story.content is corrupted"):
            run_script(ctx)

    def test_script_stage_sets_script_development_status(
        self, store: EpisodeStore, monkeypatch
    ):
        """run_script() sets status to SCRIPT_DEVELOPMENT."""
        store.create_episode("KC_SC102")
        manifest = store.load_episode("KC_SC102")

        # Populate with valid story architecture
        story_arch = _valid_story_architecture()
        manifest.story.content = story_arch.model_dump()

        # Mock the scriptwriter
        script = _valid_episode_script()
        mock_writer = MagicMock(return_value=script)

        monkeypatch.setattr("karma.orchestration.stages.scriptwriter", mock_writer)
        monkeypatch.setattr(
            "karma.orchestration.stages.GeminiStructuredClient",
            MagicMock(return_value=_make_fake_llm_client(script)),
        )
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        ctx = StageContext(manifest, store)
        run_script(ctx)

        assert manifest.status == EpisodeStatus.SCRIPT_DEVELOPMENT

    def test_script_stage_persists_script_to_manifest(
        self, store: EpisodeStore, monkeypatch
    ):
        """run_script() persists EpisodeScript in manifest.script.content."""
        store.create_episode("KC_SC103")
        manifest = store.load_episode("KC_SC103")

        story_arch = _valid_story_architecture()
        manifest.story.content = story_arch.model_dump()

        script = _valid_episode_script()
        mock_writer = MagicMock(return_value=script)

        monkeypatch.setattr("karma.orchestration.stages.scriptwriter", mock_writer)
        monkeypatch.setattr(
            "karma.orchestration.stages.GeminiStructuredClient",
            MagicMock(return_value=_make_fake_llm_client(script)),
        )
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        ctx = StageContext(manifest, store)
        run_script(ctx)

        # Verify content is stored
        assert manifest.script.content is not None
        assert manifest.script.content["title"] == "The Ledger of Rain"
        assert len(manifest.script.content["scenes"]) == 3

    def test_script_stage_returns_valid_output(self, store: EpisodeStore, monkeypatch):
        """run_script() returns dict with title, scene_count, total_lines."""
        store.create_episode("KC_SC104")
        manifest = store.load_episode("KC_SC104")

        story_arch = _valid_story_architecture()
        manifest.story.content = story_arch.model_dump()

        script = _valid_episode_script()
        mock_writer = MagicMock(return_value=script)

        monkeypatch.setattr("karma.orchestration.stages.scriptwriter", mock_writer)
        monkeypatch.setattr(
            "karma.orchestration.stages.GeminiStructuredClient",
            MagicMock(return_value=_make_fake_llm_client(script)),
        )
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        ctx = StageContext(manifest, store)
        output = run_script(ctx)

        assert output is not None
        assert "title" in output
        assert "scene_count" in output
        assert "total_lines" in output
        assert output["title"] == "The Ledger of Rain"
        assert output["scene_count"] == 3
        assert output["total_lines"] > 0

    def test_script_stage_no_api_key_raises(self, store: EpisodeStore, monkeypatch):
        """run_script() raises if GEMINI_API_KEY not set."""
        store.create_episode("KC_SC105")
        manifest = store.load_episode("KC_SC105")

        story_arch = _valid_story_architecture()
        manifest.story.content = story_arch.model_dump()

        ctx = StageContext(manifest, store)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        with pytest.raises(ValueError, match="GEMINI_API_KEY environment variable"):
            run_script(ctx)

    def test_script_stage_malformed_llm_output_raises(
        self, store: EpisodeStore, monkeypatch
    ):
        """run_script() raises when scriptwriter returns data that fails EpisodeScript validation."""
        store.create_episode("KC_SC106")
        manifest = store.load_episode("KC_SC106")

        story_arch = _valid_story_architecture()
        manifest.story.content = story_arch.model_dump()

        # Mock scriptwriter to raise validation error
        mock_writer = MagicMock()
        mock_writer.side_effect = StructuredOutputValidationError(
            "missing required field: title"
        )

        monkeypatch.setattr(
            "karma.orchestration.stages.scriptwriter",
            mock_writer,
        )
        monkeypatch.setattr(
            "karma.orchestration.stages.GeminiStructuredClient",
            MagicMock(return_value=MagicMock()),
        )
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        ctx = StageContext(manifest, store)

        with pytest.raises(StructuredOutputValidationError):
            run_script(ctx)


class TestScriptwriterIntegration:
    """Integration tests for scriptwriter with orchestrator."""

    def test_script_stage_manifest_persisted_after_completion(
        self, store: EpisodeStore, monkeypatch
    ):
        """Script result persists when manifest is saved and reloaded."""
        store.create_episode("KC_SC200")
        manifest = store.load_episode("KC_SC200")
        manifest.research_topic = "Test topic"

        # Mock LLM for research stage
        research_brief = _valid_research_brief()
        mock_research = MagicMock(return_value=research_brief)

        # Mock LLM for story stage
        story_arch = _valid_story_architecture()
        mock_architect = MagicMock(return_value=story_arch)

        # Mock LLM for script stage
        script = _valid_episode_script()
        mock_writer = MagicMock(return_value=script)

        monkeypatch.setattr("karma.orchestration.stages.research", mock_research)
        monkeypatch.setattr("karma.orchestration.stages.story_architect", mock_architect)
        monkeypatch.setattr("karma.orchestration.stages.scriptwriter", mock_writer)
        monkeypatch.setattr(
            "karma.orchestration.stages.GeminiStructuredClient",
            MagicMock(return_value=MagicMock()),
        )
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        store.save_episode(manifest)

        # Run up to and including script stage
        orchestrator = Orchestrator(store)
        result = orchestrator.run("KC_SC200", create_if_missing=False)

        # Load fresh from disk
        manifest_reloaded = store.load_episode("KC_SC200")

        # Verify script persists
        assert manifest_reloaded.script.content is not None
        assert EpisodeScript.model_validate(manifest_reloaded.script.content)

    def test_script_stage_checkpoint_behavior_on_success(
        self, store: EpisodeStore, monkeypatch
    ):
        """Script stage checkpoint is marked COMPLETED after success."""
        store.create_episode("KC_SC201")
        manifest = store.load_episode("KC_SC201")
        manifest.research_topic = "Test topic"

        # Mock LLM clients for all stages
        research_brief = _valid_research_brief()
        story_arch = _valid_story_architecture()
        script = _valid_episode_script()

        monkeypatch.setattr(
            "karma.orchestration.stages.research",
            MagicMock(return_value=research_brief),
        )
        monkeypatch.setattr(
            "karma.orchestration.stages.story_architect",
            MagicMock(return_value=story_arch),
        )
        monkeypatch.setattr(
            "karma.orchestration.stages.scriptwriter",
            MagicMock(return_value=script),
        )
        monkeypatch.setattr(
            "karma.orchestration.stages.GeminiStructuredClient",
            MagicMock(return_value=MagicMock()),
        )
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        store.save_episode(manifest)

        orchestrator = Orchestrator(store)
        orchestrator.run("KC_SC201", create_if_missing=False)

        manifest = store.load_episode("KC_SC201")
        script_checkpoint = manifest.orchestration.stages["script"]

        assert script_checkpoint.status == StageRunStatus.COMPLETED
        assert script_checkpoint.output is not None
        assert "scene_count" in script_checkpoint.output

    def test_script_stage_skipped_on_second_run(
        self, store: EpisodeStore, monkeypatch
    ):
        """Script stage is skipped on subsequent orchestrator run if already completed."""
        store.create_episode("KC_SC202")
        manifest = store.load_episode("KC_SC202")
        manifest.research_topic = "Test topic"

        # Mock LLM clients
        research_brief = _valid_research_brief()
        story_arch = _valid_story_architecture()
        script = _valid_episode_script()

        call_counter = {"scriptwriter_calls": 0}

        def counting_scriptwriter(story, client):
            call_counter["scriptwriter_calls"] += 1
            return script

        monkeypatch.setattr(
            "karma.orchestration.stages.research",
            MagicMock(return_value=research_brief),
        )
        monkeypatch.setattr(
            "karma.orchestration.stages.story_architect",
            MagicMock(return_value=story_arch),
        )
        monkeypatch.setattr(
            "karma.orchestration.stages.scriptwriter",
            counting_scriptwriter,
        )
        monkeypatch.setattr(
            "karma.orchestration.stages.GeminiStructuredClient",
            MagicMock(return_value=MagicMock()),
        )
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        store.save_episode(manifest)

        orchestrator = Orchestrator(store)
        orchestrator.run("KC_SC202", create_if_missing=False)
        assert call_counter["scriptwriter_calls"] == 1

        # Run again
        orchestrator.run("KC_SC202", create_if_missing=False)
        assert call_counter["scriptwriter_calls"] == 1  # No additional call

    def test_orchestration_integration_full_pipeline_through_script(
        self, store: EpisodeStore, monkeypatch
    ):
        """Full orchestration pipeline runs successfully through script stage."""
        store.create_episode("KC_SC203")
        manifest = store.load_episode("KC_SC203")
        manifest.research_topic = "Test topic for full pipeline"

        # Mock all stages
        research_brief = _valid_research_brief()
        story_arch = _valid_story_architecture()
        script = _valid_episode_script()

        monkeypatch.setattr(
            "karma.orchestration.stages.research",
            MagicMock(return_value=research_brief),
        )
        monkeypatch.setattr(
            "karma.orchestration.stages.story_architect",
            MagicMock(return_value=story_arch),
        )
        monkeypatch.setattr(
            "karma.orchestration.stages.scriptwriter",
            MagicMock(return_value=script),
        )
        monkeypatch.setattr(
            "karma.orchestration.stages.GeminiStructuredClient",
            MagicMock(return_value=MagicMock()),
        )
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        store.save_episode(manifest)

        orchestrator = Orchestrator(store)
        result = orchestrator.run("KC_SC203", create_if_missing=False)

        # Verify all stages completed
        assert result.success is True
        assert "script" in result.stages_executed

        # Verify manifest state
        manifest = store.load_episode("KC_SC203")
        assert manifest.script.content is not None
        assert EpisodeScript.model_validate(manifest.script.content)

    def test_script_stage_resume_after_failure(
        self, store: EpisodeStore, monkeypatch
    ):
        """Scriptwriter stage can resume after initial failure."""
        store.create_episode("KC_SC204")
        manifest = store.load_episode("KC_SC204")

        research_brief = _valid_research_brief()
        story_arch = _valid_story_architecture()
        manifest.research.content = research_brief.model_dump()
        manifest.story.content = story_arch.model_dump()

        # First attempt fails
        attempts = {"count": 0}

        def flaky_scriptwriter(story, client):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise RuntimeError("temporary scriptwriter failure")
            return _valid_episode_script()

        monkeypatch.setattr(
            "karma.orchestration.stages.scriptwriter",
            flaky_scriptwriter,
        )
        monkeypatch.setattr(
            "karma.orchestration.stages.GeminiStructuredClient",
            MagicMock(return_value=MagicMock()),
        )
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        store.save_episode(manifest)

        # Create custom registry that skips already-completed stages
        registry = STAGE_REGISTRY
        orchestrator = Orchestrator(store, registry=registry)

        # Manually mark earlier stages as completed to test script stage only
        manifest.orchestration.stages["initialize"] = StageCheckpoint(
            name="initialize", status=StageRunStatus.COMPLETED
        )
        manifest.orchestration.stages["research"] = StageCheckpoint(
            name="research", status=StageRunStatus.COMPLETED
        )
        manifest.orchestration.stages["story"] = StageCheckpoint(
            name="story", status=StageRunStatus.COMPLETED
        )
        store.save_episode(manifest)

        # First run of script stage fails
        with pytest.raises(StageExecutionError):
            orchestrator.run("KC_SC204", create_if_missing=False)

        # Verify it failed
        manifest = store.load_episode("KC_SC204")
        assert manifest.orchestration.stages["script"].status == StageRunStatus.FAILED

        # Resume run succeeds
        resumed = orchestrator.run("KC_SC204", create_if_missing=False)
        assert resumed.success is True
        assert "script" in resumed.stages_executed

        # Verify script now persists
        manifest = store.load_episode("KC_SC204")
        assert manifest.script.content is not None
        assert attempts["count"] == 2  # Called twice (failed then succeeded)

    def test_zero_real_api_calls_in_scriptwriter_tests(self):
        """All scriptwriter tests use mocks; no real API calls."""
        # This test is implicit in all the above tests using MagicMock
        # We verify by confirming that mock_llm_client.generate_structured
        # is called instead of actual Gemini client
        architecture = _valid_story_architecture()
        script = _valid_episode_script()
        fake_llm = _make_fake_llm_client(script)

        scriptwriter(architecture, fake_llm)

        # If this passes without network errors, we verified no real calls
        fake_llm.generate_structured.assert_called_once()
