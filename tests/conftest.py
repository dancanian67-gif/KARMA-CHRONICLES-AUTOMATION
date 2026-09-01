"""Pytest configuration and shared fixtures for all tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from karma.schemas.qa import QAVerdict, ScriptQAResult
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


def _valid_research_brief() -> ResearchBrief:
    """Create a valid research brief for testing."""
    return ResearchBrief(
        topic="Test research topic",
        premise_context="Test context",
        factual_claims=[
            ResearchClaim(
                claim="Test claim",
                confidence="high",
                notes="Test notes",
            ),
        ],
        sources=[
            ResearchSource(
                title="Test source",
                url="https://example.com",
                notes="Test source notes",
            ),
        ],
        real_world_context="Test real-world context",
        research_notes=["Test note"],
    )


def _valid_story_architecture() -> StoryArchitecture:
    """Create a valid story architecture for testing."""
    return StoryArchitecture(
        premise="Test premise",
        theme="Test theme",
        protagonist_id="char_1",
        antagonist_or_opposing_force_id="char_2",
        supporting_character_ids=[],
        characters=[
            StoryCharacter(
                character_id="char_1",
                name="Protagonist",
                role=CharacterRole.PROTAGONIST,
                motivation="Test motivation",
                description="Test description",
            ),
            StoryCharacter(
                character_id="char_2",
                name="Antagonist",
                role=CharacterRole.ANTAGONIST,
                motivation="Test motivation",
                description="Test description",
            ),
        ],
        central_conflict="Test conflict",
        stakes="Test stakes",
        setting="Test setting",
        major_beats=[
            StoryBeat(
                beat_id="beat_1",
                beat_type=BeatType.SETUP,
                title="Test beat",
                description="Test beat description",
                order=1,
                involved_characters=["char_1"],
            ),
        ],
        escalation="Test escalation",
        turning_points=["Test turning point"],
        climax="Test climax",
        resolution="Test resolution",
        karma_payoff="Test karma payoff",
    )


def _valid_episode_script() -> EpisodeScript:
    """Create a valid episode script for testing."""
    return EpisodeScript(
        title="Test Script",
        script_version=1,
        scenes=[
            ScriptScene(
                scene_id="scene_01",
                scene_number=1,
                title="Test Scene",
                location="Test location",
                characters_present=["char_1"],
                lines=[
                    ScriptLine(
                        kind=ScriptLineKind.NARRATION,
                        text="Test narration.",
                    ),
                    ScriptLine(
                        kind=ScriptLineKind.DIALOGUE,
                        character="char_1",
                        text="Test dialogue.",
                    ),
                ],
            ),
        ],
    )


def _valid_qa_result() -> ScriptQAResult:
    """Create a valid QA result for testing."""
    return ScriptQAResult(
        verdict=QAVerdict.PASS,
        summary="The script is structurally sound and meets the required standards.",
        issues=[],
    )


@pytest.fixture
def mock_llm_client():
    """Fixture providing a mocked LLM client."""
    client = MagicMock()
    return client


@pytest.fixture(autouse=True)
def mock_orchestrator_llm_stages(monkeypatch):
    """Fixture that mocks LLM-based stages for orchestrator tests."""
    # Set required environment variable
    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

    # Mock the research, story_architect, scriptwriter, and QA functions
    research_brief = _valid_research_brief()
    story_arch = _valid_story_architecture()
    script = _valid_episode_script()
    qa_result = _valid_qa_result()

    mock_research = MagicMock(return_value=research_brief)
    mock_story_architect = MagicMock(return_value=story_arch)
    mock_scriptwriter = MagicMock(return_value=script)
    mock_script_qa = MagicMock(return_value=qa_result)

    monkeypatch.setattr("karma.orchestration.stages.research", mock_research)
    monkeypatch.setattr(
        "karma.orchestration.stages.story_architect", mock_story_architect
    )
    monkeypatch.setattr("karma.orchestration.stages.scriptwriter", mock_scriptwriter)
    monkeypatch.setattr("karma.orchestration.stages.script_qa", mock_script_qa)

    # Mock the GeminiStructuredClient
    mock_client = MagicMock()
    mock_client.generate_structured.return_value = qa_result

    mock_llm_class = MagicMock(return_value=mock_client)
    monkeypatch.setattr(
        "karma.orchestration.stages.GeminiStructuredClient", mock_llm_class
    )

    yield {
        "research": mock_research,
        "story_architect": mock_story_architect,
        "scriptwriter": mock_scriptwriter,
        "script_qa": mock_script_qa,
        "llm_client": mock_client,
    }
