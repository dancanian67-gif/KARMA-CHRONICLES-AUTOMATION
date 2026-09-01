"""Tests for Phase 1A episode manifest schemas."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from karma.schemas.episode import EpisodeManifest, QAStatus, ScriptState
from karma.schemas.publishing import Privacy, PublishState
from karma.schemas.scene import Scene, VersionHistoryEntry


def test_minimal_episode_manifest_creation():
    manifest = EpisodeManifest(episode_id="KC_E001")
    assert manifest.episode_id == "KC_E001"
    assert manifest.status.value == "draft"


def test_episode_manifest_json_round_trip():
    manifest = EpisodeManifest(episode_id="KC_E002")
    payload = manifest.model_dump(mode="json")
    restored = EpisodeManifest.model_validate(payload)
    assert restored.episode_id == manifest.episode_id
    assert restored.status == manifest.status
    assert restored.script.qa_status == QAStatus.PENDING


def test_scene_rejects_invalid_scene_number():
    with pytest.raises(ValidationError):
        Scene(
            scene_id="s1",
            scene_number=0,
            script_version=1,
        )


def test_scene_rejects_negative_duration():
    with pytest.raises(ValidationError):
        Scene(
            scene_id="s1",
            scene_number=1,
            script_version=1,
            narration_duration_s=-0.1,
        )


def test_version_fields_cannot_be_below_one():
    with pytest.raises(ValidationError):
        ScriptState(version=0)

    with pytest.raises(ValidationError):
        VersionHistoryEntry(
            version=0,
            timestamp=datetime.now(timezone.utc),
        )


def test_qa_status_accepts_only_defined_values():
    assert ScriptState(qa_status=QAStatus.PASSED).qa_status == QAStatus.PASSED

    with pytest.raises(ValidationError):
        ScriptState.model_validate({"version": 1, "qa_status": "unknown"})


def test_publish_privacy_accepts_only_defined_values():
    assert PublishState(privacy=Privacy.PUBLIC).privacy == Privacy.PUBLIC

    with pytest.raises(ValidationError):
        PublishState.model_validate({"privacy": "restricted"})


def test_new_episode_has_empty_pending_artifacts():
    manifest = EpisodeManifest(episode_id="KC_E003")

    assert manifest.scenes == []
    assert manifest.approvals == []
    assert manifest.analytics_ref is None
    assert manifest.story.content is None
    assert manifest.script.content is None
    assert manifest.script.qa_status == QAStatus.PENDING
    assert manifest.audio_master.path is None
    assert manifest.render.path is None
    assert manifest.thumbnail.path is None
    assert manifest.metadata.title is None
    assert manifest.publish.youtube_video_id is None
    assert manifest.publish.privacy is None
    assert manifest.orchestration.stages == {}


def test_new_manifests_have_independent_mutable_defaults():
    a = EpisodeManifest(episode_id="KC_A")
    b = EpisodeManifest(episode_id="KC_B")

    a.scenes.append(
        Scene(scene_id="s1", scene_number=1, script_version=1),
    )
    a.metadata.tags.append("karma")
    a.story.history.append(
        VersionHistoryEntry(
            version=1,
            timestamp=datetime.now(timezone.utc),
        ),
    )

    assert b.scenes == []
    assert b.metadata.tags == []
    assert b.story.history == []
