"""Tests for Phase 2C production planning stage."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from karma.llm import LLMRequest
from karma.orchestration.stages import StageContext, run_production_plan
from karma.production_planner import production_planner
from karma.schemas.episode import EpisodeStatus, QAStatus
from karma.schemas.production import (
    AssetGenerationKind,
    AssetRequirement,
    AssetSourceKind,
    AssetStatus,
    AssetType,
    CameraAngle,
    CameraMovement,
    FramingType,
    LightingStyle,
    MoodType,
    ProductionPlan,
    ProductionScene,
    ScenePlanningStatus,
)
from karma.schemas.script import EpisodeScript, ScriptLine, ScriptLineKind, ScriptScene
from karma.storage import EpisodeStore


@pytest.fixture
def store(tmp_path: Path) -> EpisodeStore:
    return EpisodeStore(tmp_path / "01_EPISODES")


def _valid_script() -> EpisodeScript:
    return EpisodeScript(
        title="The Ledger of Rain",
        script_version=1,
        scenes=[
            ScriptScene(
                scene_id="scene_01",
                scene_number=1,
                title="The Ledger",
                location="Mara's apartment",
                characters_present=["char_mara"],
                lines=[
                    ScriptLine(
                        kind=ScriptLineKind.NARRATION,
                        text="Mara opens the ledger and remembers what was owed.",
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
            ),
        ],
    )


def _valid_plan() -> ProductionPlan:
    return ProductionPlan(
        plan_id="plan_ep_001",
        episode_id="ep_001",
        script_id="script_ep_001",
        script_version=1,
        scenes=[
            ProductionScene(
                production_scene_id="prod_scene_01",
                script_scene_id="scene_01",
                scene_number=1,
                title="The Ledger",
                narrative_purpose="Establish motive and debt burden.",
                characters=["char_mara"],
                primary_location_id="loc_apartment",
                location_name="Mara's apartment",
                visual_spec=None,
                planning_status=ScenePlanningStatus.PLANNED,
            ),
            ProductionScene(
                production_scene_id="prod_scene_02",
                script_scene_id="scene_02",
                scene_number=2,
                title="The Debt Returns",
                narrative_purpose="Introduce conflict and pressure.",
                characters=["char_mara", "char_kito"],
                primary_location_id="loc_office",
                location_name="Debt office",
                planning_status=ScenePlanningStatus.PLANNED,
            ),
        ],
        asset_requirements=[
            AssetRequirement(
                asset_id="asset_001",
                episode_id="ep_001",
                scene_id="scene_01",
                asset_type=AssetType.LOCATION,
                generation_kind=AssetGenerationKind.EXISTING,
                source_kind=AssetSourceKind.REFERENCE,
                prompt_or_spec="Apartment interior reference",
                status=AssetStatus.PENDING,
            )
        ],
        metadata={"total_scenes": 2},
    )


class TestProductionPlannerFunction:
    def test_production_planner_valid_script_returns_plan(self):
        script = _valid_script()
        planned = _valid_plan()
        fake_llm = MagicMock()
        fake_llm.generate_structured.return_value = planned

        result = production_planner(script, fake_llm)

        assert isinstance(result, ProductionPlan)
        assert result.plan_id == "plan_ep_001"
        assert len(result.scenes) == 2
        assert result.asset_requirements[0].asset_type == AssetType.LOCATION

    def test_production_planner_calls_llm_with_correct_request(self):
        script = _valid_script()
        planned = _valid_plan()
        fake_llm = MagicMock()
        fake_llm.generate_structured.return_value = planned

        production_planner(script, fake_llm)

        fake_llm.generate_structured.assert_called_once()
        request: LLMRequest = fake_llm.generate_structured.call_args[0][0]
        response_model = fake_llm.generate_structured.call_args[0][1]

        assert "The Ledger of Rain" in request.prompt
        assert response_model == ProductionPlan
        assert request.temperature == 0.5


class TestProductionPlanStage:
    def test_production_stage_requires_script_content(self, store: EpisodeStore):
        manifest = store.create_episode("ep_001")
        ctx = StageContext(manifest=manifest, store=store)

        with pytest.raises(ValueError, match="script stage must be completed before production planning"):
            run_production_plan(ctx)

    def test_production_stage_generates_and_persists_plan(self, store: EpisodeStore, monkeypatch):
        manifest = store.create_episode("ep_001")
        manifest.script.content = _valid_script().model_dump()
        manifest.script.qa_status = QAStatus.PASSED
        context = StageContext(manifest=manifest, store=store)

        fake_llm = MagicMock()
        fake_llm.generate_structured.return_value = _valid_plan()
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
        monkeypatch.setattr("karma.orchestration.stages.production_planner", lambda script, llm: fake_llm.generate_structured.return_value)
        monkeypatch.setattr("karma.orchestration.stages.GeminiStructuredClient", MagicMock(return_value=fake_llm))

        result = run_production_plan(context)

        assert result["plan_id"] == "plan_ep_001"
        assert result["scene_count"] == 2
        assert manifest.production.content is not None
        assert manifest.status == EpisodeStatus.IN_PRODUCTION
