"""Tests for Phase 2B.4 script QA stage."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from karma.llm import LLMRequest
from karma.orchestration import Orchestrator, StageExecutionError
from karma.orchestration.stages import StageContext, run_qa
from karma.qa import script_qa
from karma.schemas.episode import EpisodeStatus, StageRunStatus
from karma.schemas.qa import (
    QAIssue,
    QACategory,
    QASeverity,
    QAVerdict,
    ScriptQAResult,
)
from karma.schemas.research import ResearchBrief, ResearchClaim, ResearchSource
from karma.schemas.script import EpisodeScript, ScriptLine, ScriptLineKind, ScriptScene
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


def _valid_research_brief() -> ResearchBrief:
    return ResearchBrief(
        topic="The debt collector who vanished",
        premise_context="Urban karma tale set in Nairobi",
        factual_claims=[
            ResearchClaim(
                claim="Debt cycles shape choices",
                confidence="high",
                notes="Thematic grounding",
            )
        ],
        sources=[
            ResearchSource(
                title="Field research notes",
                url="https://example.com/notes",
                notes="Primary source",
            )
        ],
        real_world_context="Contemporary city life",
        research_notes=["Use moral complexity over melodrama"],
    )


def _valid_story_architecture() -> StoryArchitecture:
    return StoryArchitecture(
        premise="A debt collector haunted by the life he built.",
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
                description="Mara inherits her father's debt ledger",
                order=1,
                involved_characters=["char_mara"],
            ),
            StoryBeat(
                beat_id="beat_2",
                beat_type=BeatType.INCITING_INCIDENT,
                title="The Debt Returns",
                description="Kito returns demanding payment",
                order=2,
                involved_characters=["char_mara", "char_kito"],
            ),
            StoryBeat(
                beat_id="beat_3",
                beat_type=BeatType.CLIMAX,
                title="The Choice",
                description="Mara chooses whether to let the ledger burn",
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
        escalation="Debts compound as Kito's methods become more aggressive.",
        turning_points=[
            "Mara learns Kito is part of the same debt system.",
            "The ledger itself becomes a weapon of moral choice.",
        ],
        climax="Mara confronts Kito beneath a broken sign while the ledger burns.",
        resolution="Both are freed, though scarred by what they owe.",
        karma_payoff="The debt collector learns that every act of collection leaves a debt behind.",
    )


def _valid_script() -> EpisodeScript:
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
                        text="Mara opens a rusted ledger. Each entry is a life and a debt.",
                    ),
                    ScriptLine(
                        kind=ScriptLineKind.DIALOGUE,
                        character="char_mara",
                        text="This ledger was never mine to keep.",
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
        ],
    )


def _valid_qa_result() -> ScriptQAResult:
    return ScriptQAResult(
        verdict=QAVerdict.PASS,
        summary="The script remains coherent, character-driven, and thematically aligned.",
        issues=[],
    )


class TestScriptQA:
    def test_script_qa_valid_result_generation(self):
        fake_llm = MagicMock()
        fake_llm.generate_structured.return_value = _valid_qa_result()

        result = script_qa(_valid_script(), fake_llm)

        assert isinstance(result, ScriptQAResult)
        assert result.verdict == QAVerdict.PASS
        assert result.summary

    def test_script_qa_uses_correct_request(self):
        fake_llm = MagicMock()
        fake_llm.generate_structured.return_value = _valid_qa_result()

        script_qa(_valid_script(), fake_llm)

        request = fake_llm.generate_structured.call_args.args[0]
        assert isinstance(request, LLMRequest)
        assert "evaluate" in request.prompt.lower()
        assert "evaluator" in request.system_instruction.lower()
        assert request.temperature == 0.3

    def test_script_qa_passes_script_to_llm(self):
        fake_llm = MagicMock()
        fake_llm.generate_structured.return_value = _valid_qa_result()

        script_qa(_valid_script(), fake_llm)

        prompt = fake_llm.generate_structured.call_args.args[0].prompt
        assert "The Ledger of Rain" in prompt
        assert "scene_01" in prompt

    def test_script_qa_llm_error_propagates(self):
        fake_llm = MagicMock()
        fake_llm.generate_structured.side_effect = RuntimeError("QA service failed")

        with pytest.raises(RuntimeError, match="QA service failed"):
            script_qa(_valid_script(), fake_llm)


class TestScriptQATask:
    def test_run_qa_missing_script_content_raises_without_llm(self, store: EpisodeStore, monkeypatch):
        store.create_episode("KC_QA_01")
        manifest = store.load_episode("KC_QA_01")
        fake_llm = MagicMock()
        monkeypatch.setattr("karma.orchestration.stages.GeminiStructuredClient", MagicMock(return_value=fake_llm))
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        ctx = StageContext(manifest, store)

        with pytest.raises(ValueError, match="script stage must be completed before QA"):
            run_qa(ctx)

        fake_llm.generate_structured.assert_not_called()

    def test_run_qa_invalid_script_content_raises_deterministically(self, store: EpisodeStore, monkeypatch):
        store.create_episode("KC_QA_02")
        manifest = store.load_episode("KC_QA_02")
        manifest.script.content = {"not_a_script": True}
        fake_llm = MagicMock()
        monkeypatch.setattr("karma.orchestration.stages.GeminiStructuredClient", MagicMock(return_value=fake_llm))
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        ctx = StageContext(manifest, store)

        with pytest.raises(ValueError, match="script.content is corrupted or invalid"):
            run_qa(ctx)

        fake_llm.generate_structured.assert_not_called()

    def test_run_qa_missing_api_key_raises(self, store: EpisodeStore, monkeypatch):
        store.create_episode("KC_QA_03")
        manifest = store.load_episode("KC_QA_03")
        manifest.script.content = _valid_script().model_dump()
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        ctx = StageContext(manifest, store)

        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            run_qa(ctx)

    def test_run_qa_persists_qa_status(self, store: EpisodeStore, monkeypatch):
        store.create_episode("KC_QA_04")
        manifest = store.load_episode("KC_QA_04")
        manifest.script.content = _valid_script().model_dump()
        fake_llm = MagicMock()
        fake_llm.generate_structured.return_value = _valid_qa_result()
        monkeypatch.setattr("karma.orchestration.stages.GeminiStructuredClient", MagicMock(return_value=fake_llm))
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        ctx = StageContext(manifest, store)
        result = run_qa(ctx)

        assert result["verdict"] == QAVerdict.PASS.value
        assert manifest.script.qa_status.value == "passed"
        assert manifest.status == EpisodeStatus.IN_REVIEW

    def test_run_qa_checkpoint_completion(self, orchestrator: Orchestrator, monkeypatch):
        manifest = orchestrator.store.create_episode("KC_QA_05")
        manifest.research_topic = "A debt collector learns the cost of his choices"
        manifest.research.content = _valid_research_brief().model_dump()
        manifest.story.content = _valid_story_architecture().model_dump()
        manifest.script.content = _valid_script().model_dump()
        orchestrator.store.save_episode(manifest)

        fake_llm = MagicMock()
        fake_llm.generate_structured.return_value = _valid_qa_result()
        monkeypatch.setattr("karma.orchestration.stages.GeminiStructuredClient", MagicMock(return_value=fake_llm))
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        result = orchestrator.run("KC_QA_05")

        assert result.success is True
        assert "qa" in result.stages_executed
        assert result.manifest.orchestration.stages["qa"].status == StageRunStatus.COMPLETED

    def test_run_qa_failed_checkpoint_behavior(self, orchestrator: Orchestrator, monkeypatch):
        manifest = orchestrator.store.create_episode("KC_QA_06")
        manifest.research_topic = "A debt collector learns the cost of his choices"
        manifest.research.content = _valid_research_brief().model_dump()
        manifest.story.content = _valid_story_architecture().model_dump()
        manifest.script.content = _valid_script().model_dump()
        orchestrator.store.save_episode(manifest)

        monkeypatch.setattr(
            "karma.orchestration.stages.script_qa",
            MagicMock(side_effect=RuntimeError("QA failed")),
        )
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        with pytest.raises(StageExecutionError):
            orchestrator.run("KC_QA_06")

        persisted = orchestrator.store.load_episode("KC_QA_06")
        assert persisted.orchestration.stages["qa"].status == StageRunStatus.FAILED
        assert persisted.status == EpisodeStatus.FAILED

    def test_orchestrator_resume_idempotent_after_qa(self, orchestrator: Orchestrator, monkeypatch):
        manifest = orchestrator.store.create_episode("KC_QA_07")
        manifest.research_topic = "A debt collector learns the cost of his choices"
        manifest.research.content = _valid_research_brief().model_dump()
        manifest.story.content = _valid_story_architecture().model_dump()
        manifest.script.content = _valid_script().model_dump()
        orchestrator.store.save_episode(manifest)

        fake_llm = MagicMock()
        fake_llm.generate_structured.return_value = _valid_qa_result()
        monkeypatch.setattr("karma.orchestration.stages.GeminiStructuredClient", MagicMock(return_value=fake_llm))
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        first = orchestrator.run("KC_QA_07")
        second = orchestrator.run("KC_QA_07")

        assert first.success is True
        assert "qa" in second.stages_skipped
        persisted = orchestrator.store.load_episode("KC_QA_07")
        assert persisted.orchestration.stages["qa"].status == StageRunStatus.COMPLETED

    def test_zero_real_api_calls_in_qa_tests(self, monkeypatch):
        fake_llm = MagicMock()
        fake_llm.generate_structured.return_value = _valid_qa_result()

        script_qa(_valid_script(), fake_llm)

        assert fake_llm.generate_structured.call_count == 1
