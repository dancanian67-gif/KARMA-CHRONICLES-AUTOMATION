"""Tests for Phase 1B episode storage."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from karma.schemas.episode import EpisodeManifest, EpisodeStatus
from karma.storage import (
    EpisodeAlreadyExistsError,
    EpisodeNotFoundError,
    EpisodeStore,
    ManifestStorageError,
)
from karma.storage.episode_store import EPISODE_SUBDIRS, MANIFEST_FILENAME


@pytest.fixture
def store(tmp_path: Path) -> EpisodeStore:
    return EpisodeStore(tmp_path / "01_EPISODES")


def test_create_episode_creates_directory_structure(store: EpisodeStore):
    store.create_episode("KC_E001")

    episode_dir = store.episode_dir("KC_E001")
    assert episode_dir.is_dir()
    assert (episode_dir / MANIFEST_FILENAME).is_file()

    for subdir in EPISODE_SUBDIRS:
        assert (episode_dir / subdir).is_dir()


def test_create_episode_writes_manifest_json(store: EpisodeStore):
    manifest = store.create_episode("KC_E001")

    manifest_path = store.episode_dir("KC_E001") / MANIFEST_FILENAME
    assert manifest_path.is_file()

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["episode_id"] == "KC_E001"
    assert payload["status"] == manifest.status.value


def test_load_episode_round_trips_manifest(store: EpisodeStore):
    created = store.create_episode("KC_E002")
    loaded = store.load_episode("KC_E002")

    assert loaded.episode_id == created.episode_id
    assert loaded.status == created.status
    assert loaded.script.qa_status == created.script.qa_status


def test_save_episode_persists_manifest_changes(store: EpisodeStore):
    manifest = store.create_episode("KC_E003")
    manifest.status = EpisodeStatus.IN_PRODUCTION
    manifest.metadata.title = "The First Chronicle"

    store.save_episode(manifest)
    loaded = store.load_episode("KC_E003")

    assert loaded.status == EpisodeStatus.IN_PRODUCTION
    assert loaded.metadata.title == "The First Chronicle"


def test_save_episode_updates_updated_at_but_preserves_created_at(store: EpisodeStore):
    manifest = store.create_episode("KC_E004")
    created_at = manifest.created_at
    original_updated_at = manifest.updated_at

    manifest.status = EpisodeStatus.RESEARCHING
    store.save_episode(manifest)

    assert manifest.created_at == created_at
    assert manifest.updated_at >= original_updated_at

    loaded = store.load_episode("KC_E004")
    assert loaded.created_at == created_at
    assert loaded.updated_at >= original_updated_at


def test_create_episode_refuses_overwrite(store: EpisodeStore):
    store.create_episode("KC_E005")

    with pytest.raises(EpisodeAlreadyExistsError):
        store.create_episode("KC_E005")


def test_load_episode_missing_raises_clear_error(store: EpisodeStore):
    with pytest.raises(EpisodeNotFoundError, match="episode not found"):
        store.load_episode("KC_MISSING")


def test_malformed_manifest_raises_manifest_storage_error(store: EpisodeStore):
    store.create_episode("KC_BAD")
    manifest_path = store.episode_dir("KC_BAD") / MANIFEST_FILENAME
    manifest_path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(ManifestStorageError, match="manifest validation failed"):
        store.load_episode("KC_BAD")


def test_invalid_episode_ids_are_rejected(store: EpisodeStore):
    with pytest.raises(ValueError):
        store.create_episode("")

    with pytest.raises(ValueError):
        store.create_episode("bad id")


def test_path_traversal_episode_id_is_rejected(store: EpisodeStore):
    for bad_id in ("../escape", "../../escape", "foo/../../bar", ".."):
        with pytest.raises(ValueError):
            store.create_episode(bad_id)


def test_artifact_path_resolves_correctly(store: EpisodeStore):
    store.create_episode("KC_E006")

    path = store.artifact_path("KC_E006", "audio", "scene-01-v1.mp3", create_dir=False)

    assert path == store.episode_dir("KC_E006") / "audio" / "scene-01-v1.mp3"


def test_artifact_path_traversal_is_rejected(store: EpisodeStore):
    store.create_episode("KC_E007")

    with pytest.raises(ValueError):
        store.artifact_path("KC_E007", "audio", "../escape.mp3")

    with pytest.raises(ValueError):
        store.artifact_path("KC_E007", "audio", "../../escape.mp3")

    with pytest.raises(ValueError):
        store.artifact_path("KC_E007", "unknown", "file.mp3")


def test_two_episodes_remain_isolated(store: EpisodeStore):
    first = store.create_episode("KC_E001")
    second = store.create_episode("KC_E002")

    first.status = EpisodeStatus.IN_PRODUCTION
    first.metadata.title = "Episode One"
    store.save_episode(first)

    reloaded_second = store.load_episode("KC_E002")
    assert reloaded_second.status == EpisodeStatus.DRAFT
    assert reloaded_second.metadata.title is None

    reloaded_first = store.load_episode("KC_E001")
    assert reloaded_first.metadata.title == "Episode One"


def test_persisted_json_validates_through_episode_manifest(store: EpisodeStore):
    store.create_episode("KC_E008")
    manifest_path = store.episode_dir("KC_E008") / MANIFEST_FILENAME

    EpisodeManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))


def test_repeated_saves_do_not_corrupt_manifest(store: EpisodeStore):
    manifest = store.create_episode("KC_E009")

    for idx in range(5):
        manifest.status = EpisodeStatus.SCRIPT_DEVELOPMENT
        manifest.metadata.tags = [f"tag-{idx}"]
        store.save_episode(manifest)
        loaded = store.load_episode("KC_E009")
        assert loaded.metadata.tags == [f"tag-{idx}"]

    episode_dir = store.episode_dir("KC_E009")
    temp_files = list(episode_dir.glob(f".{MANIFEST_FILENAME}.*.tmp"))
    assert temp_files == []


def test_save_failure_is_surfaced_and_manifest_remains_valid(store: EpisodeStore):
    manifest = store.create_episode("KC_E010")
    manifest.metadata.title = "Stable Title"
    store.save_episode(manifest)

    manifest.metadata.title = "Broken Save"
    with patch("karma.storage.episode_store.os.replace", side_effect=OSError("disk full")):
        with pytest.raises(ManifestStorageError, match="failed to save manifest"):
            store.save_episode(manifest)

    loaded = store.load_episode("KC_E010")
    assert loaded.metadata.title == "Stable Title"


def test_legitimate_episode_id_formats_are_accepted(store: EpisodeStore):
    for episode_id in ("KC_E001", "KC-0042", "episode_0001"):
        store.create_episode(episode_id)
        assert store.episode_exists(episode_id)


def test_create_episode_with_existing_manifest(store: EpisodeStore):
    custom = EpisodeManifest(
        episode_id="KC_CUSTOM",
        status=EpisodeStatus.RESEARCHING,
    )
    created = store.create_episode("KC_CUSTOM", manifest=custom)

    assert created.status == EpisodeStatus.RESEARCHING
    loaded = store.load_episode("KC_CUSTOM")
    assert loaded.status == EpisodeStatus.RESEARCHING


def test_create_episode_manifest_id_mismatch_raises(store: EpisodeStore):
    custom = EpisodeManifest(episode_id="KC_A")
    with pytest.raises(ValueError, match="must match"):
        store.create_episode("KC_B", manifest=custom)


def test_save_to_missing_episode_raises(store: EpisodeStore):
    manifest = EpisodeManifest(episode_id="KC_GHOST")
    with pytest.raises(EpisodeNotFoundError):
        store.save_episode(manifest)


def test_tmp_path_episode_create_save_load_cycle(tmp_path: Path):
    store = EpisodeStore(tmp_path / "01_EPISODES")
    manifest = store.create_episode("KC_CYCLE")
    manifest.metadata.description = "checkpoint test"
    store.save_episode(manifest)

    loaded = store.load_episode("KC_CYCLE")
    assert loaded.metadata.description == "checkpoint test"


def test_malformed_manifest_schema_raises_manifest_storage_error(store: EpisodeStore):
    store.create_episode("KC_SCHEMA")
    manifest_path = store.episode_dir("KC_SCHEMA") / MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps({"episode_id": "KC_SCHEMA", "status": "not-a-real-status"}),
        encoding="utf-8",
    )

    with pytest.raises(ManifestStorageError, match="manifest validation failed"):
        store.load_episode("KC_SCHEMA")
