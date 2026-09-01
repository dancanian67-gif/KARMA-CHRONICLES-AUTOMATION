"""Tests for Phase 1C orchestration and checkpointing."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from karma.orchestration import Orchestrator, StageExecutionError, get_stage_names
from karma.orchestration.stages import (
    STAGE_REGISTRY,
    StageContext,
    StageDefinition,
    run_script,
)
from karma.schemas.episode import EpisodeStatus, StageRunStatus
from karma.storage import EpisodeStore


@pytest.fixture
def store(tmp_path: Path) -> EpisodeStore:
    return EpisodeStore(tmp_path / "01_EPISODES")


@pytest.fixture
def orchestrator(store: EpisodeStore) -> Orchestrator:
    return Orchestrator(store)


def test_new_episode_executes_all_five_stages(orchestrator: Orchestrator, store: EpisodeStore):
    manifest = store.create_episode("KC_E100")
    manifest.research_topic = "A story about karma"
    store.save_episode(manifest)
    
    result = orchestrator.run("KC_E100", create_if_missing=False)

    assert result.success is True
    assert result.stages_executed == get_stage_names()
    assert result.stages_skipped == ()

    manifest = store.load_episode("KC_E100")
    for stage_name in get_stage_names():
        assert manifest.orchestration.stages[stage_name].status == StageRunStatus.COMPLETED


def test_stage_order_is_correct(orchestrator: Orchestrator, store: EpisodeStore):
    manifest = store.create_episode("KC_E101")
    manifest.research_topic = "A story about karma"
    store.save_episode(manifest)
    result = orchestrator.run("KC_E101", create_if_missing=False)

    assert result.stages_executed == (
        "initialize",
        "research",
        "story",
        "script",
        "qa",
    )


def test_manifest_is_persisted_after_each_successful_stage(store: EpisodeStore):
    manifest = store.create_episode("KC_E102")
    manifest.research_topic = "A story about karma"
    store.save_episode(manifest)
    save_calls: list[int] = []
    original_save = store.save_episode

    def tracked_save(manifest):
        save_calls.append(len(manifest.orchestration.stages))
        return original_save(manifest)

    store.save_episode = tracked_save  # type: ignore[method-assign]
    orchestrator = Orchestrator(store)
    orchestrator.run("KC_E102", create_if_missing=False)

    assert save_calls == [1, 2, 3, 4, 5]


def test_completed_stages_are_skipped_on_second_run(orchestrator: Orchestrator, store: EpisodeStore):
    manifest = store.create_episode("KC_E103")
    manifest.research_topic = "A story about karma"
    store.save_episode(manifest)
    first = orchestrator.run("KC_E103", create_if_missing=False)
    assert first.stages_executed == get_stage_names()

    second = orchestrator.run("KC_E103", create_if_missing=False)
    assert second.success is True
    assert second.stages_executed == ()
    assert second.stages_skipped == get_stage_names()


def test_failing_stage_is_recorded_as_failed(store: EpisodeStore):
    def failing_script(_ctx: StageContext) -> dict[str, Any]:
        raise RuntimeError("script generation failed")

    registry = tuple(
        stage if stage.name != "script"
        else StageDefinition("script", failing_script)
        for stage in STAGE_REGISTRY
    )
    orchestrator = Orchestrator(store, registry=registry)
    manifest = store.create_episode("KC_E104")
    manifest.research_topic = "A story about karma"
    store.save_episode(manifest)

    with pytest.raises(StageExecutionError) as exc_info:
        orchestrator.run("KC_E104", create_if_missing=False)

    manifest = store.load_episode("KC_E104")
    script_checkpoint = manifest.orchestration.stages["script"]

    assert exc_info.value.stage_name == "script"
    assert script_checkpoint.status == StageRunStatus.FAILED
    assert script_checkpoint.error is not None
    assert "script generation failed" in script_checkpoint.error
    assert manifest.status == EpisodeStatus.FAILED


def test_later_stages_do_not_execute_after_failure(store: EpisodeStore):
    def failing_story(_ctx: StageContext) -> dict[str, Any]:
        raise ValueError("story failed")

    registry = tuple(
        stage if stage.name != "story"
        else StageDefinition("story", failing_story)
        for stage in STAGE_REGISTRY
    )
    orchestrator = Orchestrator(store, registry=registry)
    manifest = store.create_episode("KC_E105")
    manifest.research_topic = "A story about karma"
    store.save_episode(manifest)

    with pytest.raises(StageExecutionError) as exc_info:
        orchestrator.run("KC_E105", create_if_missing=False)

    manifest = store.load_episode("KC_E105")
    assert "qa" not in manifest.orchestration.stages
    assert exc_info.value.result.stages_executed == ("initialize", "research")


def test_subsequent_run_resumes_from_failed_stage(store: EpisodeStore):
    manifest = store.create_episode("KC_E106")
    manifest.research_topic = "A story about karma"
    store.save_episode(manifest)
    
    attempts = {"count": 0}

    def flaky_script(ctx: StageContext) -> dict[str, Any]:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("temporary script failure")
        return run_script(ctx)

    registry = tuple(
        stage if stage.name != "script"
        else StageDefinition("script", flaky_script)
        for stage in STAGE_REGISTRY
    )
    orchestrator = Orchestrator(store, registry=registry)

    with pytest.raises(StageExecutionError):
        orchestrator.run("KC_E106", create_if_missing=False)

    resumed = orchestrator.run("KC_E106", create_if_missing=False)
    assert resumed.success is True
    assert resumed.stages_executed == ("script", "qa")
    assert resumed.stages_skipped == ("initialize", "research", "story")


def test_previously_completed_stages_remain_completed_after_resume(store: EpisodeStore):
    manifest = store.create_episode("KC_E107")
    manifest.research_topic = "A story about karma"
    store.save_episode(manifest)
    
    attempts = {"count": 0}

    def flaky_script(ctx: StageContext) -> dict[str, Any]:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("temporary script failure")
        return run_script(ctx)

    registry = tuple(
        stage if stage.name != "script"
        else StageDefinition("script", flaky_script)
        for stage in STAGE_REGISTRY
    )
    orchestrator = Orchestrator(store, registry=registry)

    with pytest.raises(StageExecutionError):
        orchestrator.run("KC_E107", create_if_missing=False)

    manifest = store.load_episode("KC_E107")
    assert manifest.orchestration.stages["research"].status == StageRunStatus.COMPLETED
    assert manifest.orchestration.stages["story"].status == StageRunStatus.COMPLETED

    orchestrator.run("KC_E107", create_if_missing=False)
    manifest = store.load_episode("KC_E107")
    assert manifest.orchestration.stages["research"].status == StageRunStatus.COMPLETED
    assert manifest.orchestration.stages["story"].status == StageRunStatus.COMPLETED


def test_failure_information_is_persisted(store: EpisodeStore):
    manifest = store.create_episode("KC_E108")
    manifest.research_topic = "A story about karma"
    store.save_episode(manifest)
    
    def failing_research(_ctx: StageContext) -> dict[str, Any]:
        raise RuntimeError("research unavailable")

    registry = tuple(
        stage if stage.name != "research"
        else StageDefinition("research", failing_research)
        for stage in STAGE_REGISTRY
    )
    orchestrator = Orchestrator(store, registry=registry)

    with pytest.raises(StageExecutionError) as exc_info:
        orchestrator.run("KC_E108", create_if_missing=False)

    manifest = store.load_episode("KC_E108")
    checkpoint = manifest.orchestration.stages["research"]

    assert checkpoint.error == exc_info.value.result.error
    assert checkpoint.output is None
    assert checkpoint.completed_at is None


def test_orchestrator_uses_episode_store_not_direct_file_io(store: EpisodeStore):
    created_manifest = store.create_episode("KC_E109")
    created_manifest.research_topic = "A story about karma"
    store.save_episode(created_manifest)
    
    mock_store = MagicMock(spec=EpisodeStore)
    mock_store.episode_exists.return_value = True
    mock_store.load_episode.return_value = created_manifest
    mock_store.save_episode.side_effect = store.save_episode

    orchestrator = Orchestrator(mock_store)
    orchestrator.run("KC_E109", create_if_missing=False)

    assert mock_store.load_episode.called
    assert mock_store.save_episode.call_count == 5
    mock_store.create_episode.assert_not_called()


def test_successful_resumed_run_marks_all_stages_complete(store: EpisodeStore):
    manifest = store.create_episode("KC_E110")
    manifest.research_topic = "A story about karma"
    store.save_episode(manifest)
    
    attempts = {"count": 0}

    def flaky_script(ctx: StageContext) -> dict[str, Any]:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("temporary script failure")
        return run_script(ctx)

    registry = tuple(
        stage if stage.name != "script"
        else StageDefinition("script", flaky_script)
        for stage in STAGE_REGISTRY
    )
    orchestrator = Orchestrator(store, registry=registry)

    with pytest.raises(StageExecutionError):
        orchestrator.run("KC_E110", create_if_missing=False)

    result = orchestrator.run("KC_E110", create_if_missing=False)
    assert result.success is True

    manifest = store.load_episode("KC_E110")
    for stage_name in get_stage_names():
        assert manifest.orchestration.stages[stage_name].status == StageRunStatus.COMPLETED


def test_no_external_api_calls_are_made(monkeypatch: pytest.MonkeyPatch, orchestrator: Orchestrator, store: EpisodeStore):
    manifest = store.create_episode("KC_E111")
    manifest.research_topic = "A story about karma"
    store.save_episode(manifest)
    
    def forbidden_network(*_args, **_kwargs):
        raise AssertionError("network call attempted")

    monkeypatch.setattr("socket.socket", forbidden_network)
    orchestrator.run("KC_E111", create_if_missing=False)
