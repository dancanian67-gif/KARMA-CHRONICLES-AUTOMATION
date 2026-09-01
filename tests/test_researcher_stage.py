"""Tests for Phase 2B.1 researcher stage."""

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
)
from karma.researcher import research
from karma.schemas.episode import EpisodeStatus, ResearchState, StageRunStatus
from karma.schemas.research import ResearchBrief, ResearchClaim, ResearchSource
from karma.schemas.story import StoryArchitecture, StoryBeat, StoryCharacter, CharacterRole, BeatType
from karma.storage import EpisodeStore


@pytest.fixture
def store(tmp_path: Path) -> EpisodeStore:
    return EpisodeStore(tmp_path / "01_EPISODES")


@pytest.fixture
def orchestrator(store: EpisodeStore) -> Orchestrator:
    return Orchestrator(store)


def _make_fake_llm_client(response: ResearchBrief) -> MagicMock:
    """Create a fake LLM client that returns a research brief."""
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


class TestResearcherFunction:
    """Tests for the research() function."""

    def test_research_valid_topic_returns_brief(self):
        """research() with valid topic and mock LLM returns ResearchBrief."""
        brief = _valid_research_brief()
        fake_llm = _make_fake_llm_client(brief)

        result = research("Test topic", fake_llm)

        assert isinstance(result, ResearchBrief)
        assert result.topic == "The debt collector who vanished"
        assert len(result.factual_claims) == 1
        assert len(result.sources) == 1

    def test_research_calls_llm_with_correct_request(self):
        """research() calls LLM with properly formatted request."""
        brief = _valid_research_brief()
        fake_llm = _make_fake_llm_client(brief)

        research("Custom topic here", fake_llm)

        # Verify LLM was called with correct signature
        fake_llm.generate_structured.assert_called_once()
        call_args = fake_llm.generate_structured.call_args
        request: LLMRequest = call_args[0][0]
        response_model = call_args[0][1]

        assert "Custom topic here" in request.prompt
        assert response_model == ResearchBrief
        assert request.temperature == 0.3

    def test_research_llm_failure_propagates(self):
        """research() propagates LLM errors without swallowing."""
        fake_llm = MagicMock()
        fake_llm.generate_structured.side_effect = ValueError("LLM unavailable")

        with pytest.raises(ValueError, match="LLM unavailable"):
            research("Test topic", fake_llm)

    def test_research_validation_failure_propagates(self):
        """research() raises when LLM returns invalid schema."""
        fake_llm = MagicMock()
        fake_llm.generate_structured.side_effect = StructuredOutputValidationError(
            "Invalid schema"
        )

        with pytest.raises(StructuredOutputValidationError):
            research("Test topic", fake_llm)


class TestResearchStage:
    """Tests for the run_research stage."""

    def test_research_stage_missing_topic_raises_without_llm_call(self, store: EpisodeStore):
        """run_research() raises ValueError if topic is missing, without LLM call."""
        store.create_episode("KC_E200")
        manifest = store.load_episode("KC_E200")
        # research_topic is None by default
        ctx = StageContext(manifest, store)

        with pytest.raises(ValueError, match="research_topic is required"):
            run_research(ctx)

    def test_research_stage_empty_topic_raises_without_llm_call(self, store: EpisodeStore):
        """run_research() raises if topic is empty string."""
        store.create_episode("KC_E201")
        manifest = store.load_episode("KC_E201")
        manifest.research_topic = ""
        ctx = StageContext(manifest, store)

        with pytest.raises(ValueError, match="research_topic is required"):
            run_research(ctx)

    def test_research_stage_sets_researching_status(self, store: EpisodeStore, monkeypatch):
        """run_research() sets status to RESEARCHING."""
        store.create_episode("KC_E202")
        manifest = store.load_episode("KC_E202")
        manifest.research_topic = "Test topic"

        # Mock the LLM and researcher
        fake_llm = _make_fake_llm_client(_valid_research_brief())
        mock_research = MagicMock(return_value=_valid_research_brief())

        monkeypatch.setattr("karma.orchestration.stages.research", mock_research)
        monkeypatch.setattr(
            "karma.orchestration.stages.GeminiStructuredClient",
            MagicMock(return_value=fake_llm),
        )
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        ctx = StageContext(manifest, store)
        run_research(ctx)

        assert manifest.status == EpisodeStatus.RESEARCHING

    def test_research_stage_persists_brief_to_manifest(
        self, store: EpisodeStore, monkeypatch
    ):
        """run_research() persists ResearchBrief in manifest.research.content."""
        store.create_episode("KC_E203")
        manifest = store.load_episode("KC_E203")
        manifest.research_topic = "Test topic"

        brief = _valid_research_brief()
        mock_research = MagicMock(return_value=brief)

        monkeypatch.setattr("karma.orchestration.stages.research", mock_research)
        monkeypatch.setattr(
            "karma.orchestration.stages.GeminiStructuredClient",
            MagicMock(return_value=_make_fake_llm_client(brief)),
        )
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        ctx = StageContext(manifest, store)
        run_research(ctx)

        # Verify content is stored
        assert manifest.research.content is not None
        assert manifest.research.content["topic"] == "The debt collector who vanished"
        assert len(manifest.research.content["factual_claims"]) == 1

    def test_research_stage_returns_valid_output(self, store: EpisodeStore, monkeypatch):
        """run_research() returns dict with topic, claims_count, sources_count."""
        store.create_episode("KC_E204")
        manifest = store.load_episode("KC_E204")
        manifest.research_topic = "Test topic"

        brief = _valid_research_brief()
        mock_research = MagicMock(return_value=brief)

        monkeypatch.setattr("karma.orchestration.stages.research", mock_research)
        monkeypatch.setattr(
            "karma.orchestration.stages.GeminiStructuredClient",
            MagicMock(return_value=_make_fake_llm_client(brief)),
        )
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        ctx = StageContext(manifest, store)
        output = run_research(ctx)

        assert output is not None
        assert "topic" in output
        assert "claims_count" in output
        assert "sources_count" in output
        assert output["topic"] == "The debt collector who vanished"
        assert output["claims_count"] == 1
        assert output["sources_count"] == 1

    def test_research_stage_no_api_key_raises(self, store: EpisodeStore, monkeypatch):
        """run_research() raises if GEMINI_API_KEY not set."""
        store.create_episode("KC_E205")
        manifest = store.load_episode("KC_E205")
        manifest.research_topic = "Test topic"

        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        ctx = StageContext(manifest, store)
        with pytest.raises(ValueError, match="GEMINI_API_KEY environment variable"):
            run_research(ctx)


class TestResearchStageOrchestration:
    """Tests for researcher in the full orchestration pipeline."""

    def test_research_stage_executes_in_pipeline(self, orchestrator: Orchestrator, monkeypatch):
        """Research stage executes as part of the orchestration."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        brief = _valid_research_brief()
        arch = _valid_story_architecture()
        mock_research = MagicMock(return_value=brief)
        mock_story_arch = MagicMock(return_value=arch)

        monkeypatch.setattr("karma.orchestration.stages.research", mock_research)
        monkeypatch.setattr("karma.orchestration.stages.story_architect", mock_story_arch)
        monkeypatch.setattr(
            "karma.orchestration.stages.GeminiStructuredClient",
            MagicMock(return_value=_make_fake_llm_client(brief)),
        )

        # Create episode with research topic
        orchestrator.store.create_episode("KC_E206")
        manifest = orchestrator.store.load_episode("KC_E206")
        manifest.research_topic = "Test episode topic"
        orchestrator.store.save_episode(manifest)

        result = orchestrator.run("KC_E206", create_if_missing=False)

        assert result.success is True
        assert "research" in result.stages_executed

    def test_completed_research_stage_skipped_on_resume(
        self, orchestrator: Orchestrator, monkeypatch
    ):
        """Completed research stage is skipped on orchestrator resume."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        brief = _valid_research_brief()
        arch = _valid_story_architecture()
        mock_research = MagicMock(return_value=brief)
        mock_story_arch = MagicMock(return_value=arch)

        monkeypatch.setattr("karma.orchestration.stages.research", mock_research)
        monkeypatch.setattr("karma.orchestration.stages.story_architect", mock_story_arch)
        monkeypatch.setattr(
            "karma.orchestration.stages.GeminiStructuredClient",
            MagicMock(return_value=_make_fake_llm_client(brief)),
        )

        orchestrator.store.create_episode("KC_E207")
        manifest = orchestrator.store.load_episode("KC_E207")
        manifest.research_topic = "Test episode topic"
        orchestrator.store.save_episode(manifest)

        # First run: all stages
        first = orchestrator.run("KC_E207", create_if_missing=False)
        assert "research" in first.stages_executed

        # Second run: skip completed stages
        second = orchestrator.run("KC_E207", create_if_missing=False)
        assert "research" not in second.stages_executed
        assert "research" in second.stages_skipped

    def test_research_stage_failure_propagates_in_orchestration(
        self, orchestrator: Orchestrator, monkeypatch
    ):
        """LLM failure in research stage propagates through orchestrator."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        mock_research = MagicMock(side_effect=ValueError("LLM unavailable"))
        mock_story_arch = MagicMock(return_value=_valid_story_architecture())

        monkeypatch.setattr("karma.orchestration.stages.research", mock_research)
        monkeypatch.setattr("karma.orchestration.stages.story_architect", mock_story_arch)
        monkeypatch.setattr(
            "karma.orchestration.stages.GeminiStructuredClient",
            MagicMock(return_value=MagicMock()),
        )

        orchestrator.store.create_episode("KC_E208")
        manifest = orchestrator.store.load_episode("KC_E208")
        manifest.research_topic = "Test episode topic"
        orchestrator.store.save_episode(manifest)

        with pytest.raises(StageExecutionError) as exc_info:
            orchestrator.run("KC_E208", create_if_missing=False)

        assert exc_info.value.stage_name == "research"
