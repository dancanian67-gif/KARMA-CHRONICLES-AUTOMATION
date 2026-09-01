"""Tests for Phase 2B.2 story architect stage."""

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
    run_research,
    run_story,
)
from karma.story_architect import story_architect
from karma.schemas.episode import EpisodeStatus, StageRunStatus
from karma.schemas.research import ResearchBrief, ResearchClaim, ResearchSource
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


class TestStoryArchitectFunction:
    """Tests for the story_architect() function."""

    def test_story_architect_valid_research_returns_architecture(self):
        """story_architect() with valid research and mock LLM returns StoryArchitecture."""
        research_brief = _valid_research_brief()
        architecture = _valid_story_architecture()
        fake_llm = _make_fake_llm_client(architecture)

        result = story_architect(research_brief, fake_llm)

        assert isinstance(result, StoryArchitecture)
        assert result.premise == "A debt collector haunted by consequences."
        assert len(result.characters) == 3
        assert len(result.major_beats) >= 4

    def test_story_architect_calls_llm_with_correct_request(self):
        """story_architect() calls LLM with properly formatted request."""
        research_brief = _valid_research_brief()
        architecture = _valid_story_architecture()
        fake_llm = _make_fake_llm_client(architecture)

        story_architect(research_brief, fake_llm)

        # Verify LLM was called with correct signature
        fake_llm.generate_structured.assert_called_once()
        call_args = fake_llm.generate_structured.call_args
        request: LLMRequest = call_args[0][0]
        response_model = call_args[0][1]

        assert research_brief.topic in request.prompt
        assert response_model == StoryArchitecture
        assert request.temperature == 0.5

    def test_story_architect_llm_failure_propagates(self):
        """story_architect() propagates LLM errors without swallowing."""
        research_brief = _valid_research_brief()
        fake_llm = MagicMock()
        fake_llm.generate_structured.side_effect = ValueError("LLM unavailable")

        with pytest.raises(ValueError, match="LLM unavailable"):
            story_architect(research_brief, fake_llm)

    def test_story_architect_validation_failure_propagates(self):
        """story_architect() raises when LLM returns invalid schema."""
        research_brief = _valid_research_brief()
        fake_llm = MagicMock()
        fake_llm.generate_structured.side_effect = StructuredOutputValidationError(
            "Invalid schema"
        )

        with pytest.raises(StructuredOutputValidationError):
            story_architect(research_brief, fake_llm)


class TestStoryArchitectStage:
    """Tests for the run_story stage."""

    def test_story_stage_missing_research_raises_without_llm_call(
        self, store: EpisodeStore
    ):
        """run_story() raises ValueError if research is missing."""
        store.create_episode("KC_S100")
        manifest = store.load_episode("KC_S100")
        # research.content is None by default
        ctx = StageContext(manifest, store)

        with pytest.raises(ValueError, match="research stage must be completed"):
            run_story(ctx)

    def test_story_stage_invalid_research_raises_deterministically(
        self, store: EpisodeStore
    ):
        """run_story() raises ValueError if research.content is corrupted."""
        store.create_episode("KC_S101")
        manifest = store.load_episode("KC_S101")
        manifest.research.content = {"invalid": "schema"}
        ctx = StageContext(manifest, store)

        with pytest.raises(ValueError, match="research.content is corrupted"):
            run_story(ctx)

    def test_story_stage_sets_story_development_status(
        self, store: EpisodeStore, monkeypatch
    ):
        """run_story() sets status to STORY_DEVELOPMENT."""
        store.create_episode("KC_S102")
        manifest = store.load_episode("KC_S102")

        # Populate with valid research
        research_brief = _valid_research_brief()
        manifest.research.content = research_brief.model_dump()

        # Mock the story architect
        architecture = _valid_story_architecture()
        mock_architect = MagicMock(return_value=architecture)

        monkeypatch.setattr("karma.orchestration.stages.story_architect", mock_architect)
        monkeypatch.setattr(
            "karma.orchestration.stages.GeminiStructuredClient",
            MagicMock(return_value=_make_fake_llm_client(architecture)),
        )
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        ctx = StageContext(manifest, store)
        run_story(ctx)

        assert manifest.status == EpisodeStatus.STORY_DEVELOPMENT

    def test_story_stage_persists_architecture_to_manifest(
        self, store: EpisodeStore, monkeypatch
    ):
        """run_story() persists StoryArchitecture in manifest.story.content."""
        store.create_episode("KC_S103")
        manifest = store.load_episode("KC_S103")

        research_brief = _valid_research_brief()
        manifest.research.content = research_brief.model_dump()

        architecture = _valid_story_architecture()
        mock_architect = MagicMock(return_value=architecture)

        monkeypatch.setattr("karma.orchestration.stages.story_architect", mock_architect)
        monkeypatch.setattr(
            "karma.orchestration.stages.GeminiStructuredClient",
            MagicMock(return_value=_make_fake_llm_client(architecture)),
        )
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        ctx = StageContext(manifest, store)
        run_story(ctx)

        # Verify content is stored
        assert manifest.story.content is not None
        assert manifest.story.content["premise"] == "A debt collector haunted by consequences."
        assert len(manifest.story.content["characters"]) == 3

    def test_story_stage_returns_valid_output(self, store: EpisodeStore, monkeypatch):
        """run_story() returns dict with premise, character_count, beat_count."""
        store.create_episode("KC_S104")
        manifest = store.load_episode("KC_S104")

        research_brief = _valid_research_brief()
        manifest.research.content = research_brief.model_dump()

        architecture = _valid_story_architecture()
        mock_architect = MagicMock(return_value=architecture)

        monkeypatch.setattr("karma.orchestration.stages.story_architect", mock_architect)
        monkeypatch.setattr(
            "karma.orchestration.stages.GeminiStructuredClient",
            MagicMock(return_value=_make_fake_llm_client(architecture)),
        )
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        ctx = StageContext(manifest, store)
        output = run_story(ctx)

        assert output is not None
        assert "premise" in output
        assert "character_count" in output
        assert "beat_count" in output
        assert output["character_count"] == 3
        assert output["beat_count"] >= 4

    def test_story_stage_no_api_key_raises(self, store: EpisodeStore, monkeypatch):
        """run_story() raises if GEMINI_API_KEY not set."""
        store.create_episode("KC_S105")
        manifest = store.load_episode("KC_S105")

        research_brief = _valid_research_brief()
        manifest.research.content = research_brief.model_dump()

        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        ctx = StageContext(manifest, store)
        with pytest.raises(ValueError, match="GEMINI_API_KEY environment variable"):
            run_story(ctx)


class TestStoryArchitectStageOrchestration:
    """Tests for story architect in the full orchestration pipeline."""

    def test_story_stage_executes_after_research_in_pipeline(
        self, orchestrator: Orchestrator, monkeypatch
    ):
        """Story stage executes after research in the orchestration."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        research_brief = _valid_research_brief()
        architecture = _valid_story_architecture()

        mock_research_fn = MagicMock(return_value=research_brief)
        mock_architect_fn = MagicMock(return_value=architecture)

        monkeypatch.setattr("karma.orchestration.stages.research", mock_research_fn)
        monkeypatch.setattr(
            "karma.orchestration.stages.story_architect", mock_architect_fn
        )
        monkeypatch.setattr(
            "karma.orchestration.stages.GeminiStructuredClient",
            MagicMock(return_value=_make_fake_llm_client(None)),
        )

        # Create episode with research topic
        orchestrator.store.create_episode("KC_S106")
        manifest = orchestrator.store.load_episode("KC_S106")
        manifest.research_topic = "Test episode topic"
        orchestrator.store.save_episode(manifest)

        result = orchestrator.run("KC_S106", create_if_missing=False)

        assert result.success is True
        assert "research" in result.stages_executed
        assert "story" in result.stages_executed

    def test_full_research_to_story_pipeline(self, orchestrator: Orchestrator, monkeypatch):
        """Full orchestration: initialize → research → story."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        research_brief = _valid_research_brief()
        architecture = _valid_story_architecture()

        mock_research_fn = MagicMock(return_value=research_brief)
        mock_architect_fn = MagicMock(return_value=architecture)

        monkeypatch.setattr("karma.orchestration.stages.research", mock_research_fn)
        monkeypatch.setattr(
            "karma.orchestration.stages.story_architect", mock_architect_fn
        )
        monkeypatch.setattr(
            "karma.orchestration.stages.GeminiStructuredClient",
            MagicMock(return_value=_make_fake_llm_client(None)),
        )

        orchestrator.store.create_episode("KC_S107")
        manifest = orchestrator.store.load_episode("KC_S107")
        manifest.research_topic = "Karma and debt collection"
        orchestrator.store.save_episode(manifest)

        result = orchestrator.run("KC_S107", create_if_missing=False)

        # Verify pipeline executed
        assert result.success is True
        assert result.stages_executed == ("initialize", "research", "story", "script", "qa")

        # Verify final manifest has story content
        final_manifest = orchestrator.store.load_episode("KC_S107")
        assert final_manifest.research.content is not None
        assert final_manifest.story.content is not None

    def test_completed_story_stage_skipped_on_resume(
        self, orchestrator: Orchestrator, monkeypatch
    ):
        """Completed story stage is skipped on orchestrator resume."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        research_brief = _valid_research_brief()
        architecture = _valid_story_architecture()

        mock_research_fn = MagicMock(return_value=research_brief)
        mock_architect_fn = MagicMock(return_value=architecture)

        monkeypatch.setattr("karma.orchestration.stages.research", mock_research_fn)
        monkeypatch.setattr(
            "karma.orchestration.stages.story_architect", mock_architect_fn
        )
        monkeypatch.setattr(
            "karma.orchestration.stages.GeminiStructuredClient",
            MagicMock(return_value=_make_fake_llm_client(None)),
        )

        orchestrator.store.create_episode("KC_S108")
        manifest = orchestrator.store.load_episode("KC_S108")
        manifest.research_topic = "Test topic"
        orchestrator.store.save_episode(manifest)

        # First run: execute all stages
        first = orchestrator.run("KC_S108", create_if_missing=False)
        assert "story" in first.stages_executed

        # Second run: skip completed stages
        second = orchestrator.run("KC_S108", create_if_missing=False)
        assert "story" not in second.stages_executed
        assert "story" in second.stages_skipped

    def test_story_stage_failure_propagates_in_orchestration(
        self, orchestrator: Orchestrator, monkeypatch
    ):
        """LLM failure in story stage propagates through orchestrator."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        research_brief = _valid_research_brief()

        mock_research_fn = MagicMock(return_value=research_brief)
        mock_architect_fn = MagicMock(side_effect=ValueError("Story generation failed"))

        monkeypatch.setattr("karma.orchestration.stages.research", mock_research_fn)
        monkeypatch.setattr(
            "karma.orchestration.stages.story_architect", mock_architect_fn
        )
        monkeypatch.setattr(
            "karma.orchestration.stages.GeminiStructuredClient",
            MagicMock(return_value=MagicMock()),
        )

        orchestrator.store.create_episode("KC_S109")
        manifest = orchestrator.store.load_episode("KC_S109")
        manifest.research_topic = "Test topic"
        orchestrator.store.save_episode(manifest)

        with pytest.raises(StageExecutionError) as exc_info:
            orchestrator.run("KC_S109", create_if_missing=False)

        assert exc_info.value.stage_name == "story"
