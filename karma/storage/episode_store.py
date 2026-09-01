"""Filesystem-backed episode manifest storage with atomic checkpointing."""

from __future__ import annotations

import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from karma.schemas.episode import EpisodeManifest

MANIFEST_FILENAME = "manifest.json"

EPISODE_SUBDIRS: tuple[str, ...] = (
    "research",
    "story",
    "script",
    "scenes",
    "audio",
    "visuals",
    "render",
    "thumbnail",
    "metadata",
)

# Letters, digits, underscore, hyphen, dot — covers KC_E001, KC-0042, episode_0001.
_EPISODE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class EpisodeNotFoundError(FileNotFoundError):
    """Raised when an episode directory or manifest is missing."""


class EpisodeAlreadyExistsError(FileExistsError):
    """Raised when attempting to create an episode that already exists."""


class ManifestStorageError(RuntimeError):
    """Raised when a manifest cannot be read, validated, or written safely."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _validate_episode_id(episode_id: str) -> str:
    """Validate an episode ID for safe use as a directory name."""
    if not episode_id or episode_id.strip() != episode_id:
        raise ValueError("episode_id must be a non-empty string without leading or trailing whitespace")

    if episode_id in {".", ".."}:
        raise ValueError(f"invalid episode_id: {episode_id!r}")

    if "/" in episode_id or "\\" in episode_id or ".." in episode_id:
        raise ValueError(f"invalid episode_id: {episode_id!r}")

    if not _EPISODE_ID_PATTERN.fullmatch(episode_id):
        raise ValueError(f"invalid episode_id: {episode_id!r}")

    return episode_id


def _validate_artifact_filename(filename: str) -> str:
    """Validate an artifact filename for safe use inside an episode subdirectory."""
    if not filename or filename.strip() != filename:
        raise ValueError("artifact filename must be a non-empty string without leading or trailing whitespace")

    if filename in {".", ".."}:
        raise ValueError(f"invalid artifact filename: {filename!r}")

    if "/" in filename or "\\" in filename or ".." in filename:
        raise ValueError(f"invalid artifact filename: {filename!r}")

    return filename


def _assert_within_root(root: Path, target: Path) -> None:
    """Ensure ``target`` resolves inside ``root``."""
    root_resolved = root.resolve()
    target_resolved = target.resolve()
    if target_resolved != root_resolved and root_resolved not in target_resolved.parents:
        raise ValueError(f"path escapes episode root: {target}")


class EpisodeStore:
    """Filesystem implementation of per-episode manifest storage.

    Each episode lives under ``<episode_root>/<episode_id>/`` with a
    ``manifest.json`` checkpoint and standard artifact subdirectories.

    ``save_episode`` updates ``manifest.updated_at`` to the current UTC time
    before persisting. ``created_at`` is never modified by the store.
    """

    def __init__(self, episode_root: Path | str) -> None:
        self._root = Path(episode_root)

    @property
    def episode_root(self) -> Path:
        return self._root

    def episode_dir(self, episode_id: str) -> Path:
        """Return the directory path for an episode."""
        episode_id = _validate_episode_id(episode_id)
        path = self._root / episode_id
        _assert_within_root(self._root, path)
        return path

    def episode_exists(self, episode_id: str) -> bool:
        """Return True if the episode directory exists."""
        episode_id = _validate_episode_id(episode_id)
        return self.episode_dir(episode_id).is_dir()

    def create_episode(
        self,
        episode_id: str,
        manifest: EpisodeManifest | None = None,
    ) -> EpisodeManifest:
        """Create a new episode directory tree and persist its manifest."""
        episode_id = _validate_episode_id(episode_id)

        if self.episode_exists(episode_id):
            raise EpisodeAlreadyExistsError(
                f"episode already exists: {episode_id}",
            )

        if manifest is None:
            episode_manifest = EpisodeManifest(episode_id=episode_id)
        else:
            if manifest.episode_id != episode_id:
                raise ValueError(
                    "manifest.episode_id must match the episode_id argument",
                )
            episode_manifest = manifest

        episode_path = self.episode_dir(episode_id)
        try:
            episode_path.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise EpisodeAlreadyExistsError(
                f"episode already exists: {episode_id}",
            ) from exc

        for subdir in EPISODE_SUBDIRS:
            (episode_path / subdir).mkdir(exist_ok=True)

        self.save_episode(episode_manifest)
        return episode_manifest

    def load_episode(self, episode_id: str) -> EpisodeManifest:
        """Load and validate an episode manifest from disk."""
        episode_id = _validate_episode_id(episode_id)
        manifest_path = self.episode_dir(episode_id) / MANIFEST_FILENAME

        if not manifest_path.is_file():
            raise EpisodeNotFoundError(
                f"episode not found: {episode_id}",
            )

        try:
            payload = manifest_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ManifestStorageError(
                f"failed to read manifest for episode {episode_id}: {manifest_path}",
            ) from exc

        try:
            return EpisodeManifest.model_validate_json(payload)
        except ValidationError as exc:
            raise ManifestStorageError(
                f"manifest validation failed for episode {episode_id}: {manifest_path}",
            ) from exc

    def save_episode(self, manifest: EpisodeManifest) -> None:
        """Atomically persist an episode manifest.

        Updates ``manifest.updated_at`` to the current UTC time before writing.
        """
        episode_id = _validate_episode_id(manifest.episode_id)
        episode_path = self.episode_dir(episode_id)

        if not episode_path.is_dir():
            raise EpisodeNotFoundError(
                f"episode not found: {episode_id}",
            )

        manifest.updated_at = _utc_now()
        manifest_path = episode_path / MANIFEST_FILENAME
        json_payload = manifest.model_dump_json(indent=2)

        try:
            _atomic_write_text(manifest_path, json_payload)
        except OSError as exc:
            raise ManifestStorageError(
                f"failed to save manifest for episode {episode_id}: {manifest_path}",
            ) from exc

    def artifact_path(
        self,
        episode_id: str,
        subdir: str,
        filename: str,
        *,
        create_dir: bool = True,
    ) -> Path:
        """Resolve a safe path for an artifact inside an episode subdirectory."""
        episode_id = _validate_episode_id(episode_id)
        filename = _validate_artifact_filename(filename)

        if subdir not in EPISODE_SUBDIRS:
            raise ValueError(f"unknown episode subdirectory: {subdir!r}")

        artifact_dir = self.episode_dir(episode_id) / subdir
        artifact_file = artifact_dir / filename
        _assert_within_root(self.episode_dir(episode_id), artifact_file)

        if create_dir:
            artifact_dir.mkdir(parents=True, exist_ok=True)

        return artifact_file


def _atomic_write_text(path: Path, content: str) -> None:
    """Write ``content`` to ``path`` atomically via a same-directory temp file."""
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(
        suffix=".tmp",
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    tmp_path = Path(tmp_name)

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
