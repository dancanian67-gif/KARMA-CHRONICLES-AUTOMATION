"""Audio models for scene-level and master audio tracks."""

from pydantic import BaseModel, Field

from karma.schemas.scene import VersionHistoryEntry


class SceneAudio(BaseModel):
    """Audio artifacts for a single scene."""

    scene_id: str
    path: str | None = None
    duration_s: float | None = Field(default=None, ge=0)
    captions_path: str | None = None
    version: int = Field(default=1, ge=1)


class AudioMaster(BaseModel):
    """Final mastered audio for the episode."""

    version: int = Field(default=1, ge=1)
    path: str | None = None
    duration_s: float | None = Field(default=None, ge=0)
    loudness_lufs: float | None = None
    history: list[VersionHistoryEntry] = Field(default_factory=list)
