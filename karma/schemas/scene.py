"""Scene models for episode manifests."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class VersionHistoryEntry(BaseModel):
    """A single historical record for a versioned artifact."""

    version: int = Field(ge=1)
    timestamp: datetime
    artifact_path: str | None = None
    reason: str | None = None


class SceneStatus(StrEnum):
    """Lifecycle state for an individual scene."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    READY = "ready"
    FAILED = "failed"


class Scene(BaseModel):
    """A single scene within an episode, with its own version history."""

    scene_id: str
    scene_number: int = Field(ge=1)
    script_version: int = Field(ge=1)
    version: int = Field(default=1, ge=1)
    history: list[VersionHistoryEntry] = Field(default_factory=list)
    status: SceneStatus = SceneStatus.PENDING
    characters: list[str] = Field(default_factory=list)
    location: str | None = None
    objects: list[str] = Field(default_factory=list)
    narration_audio: str | None = None
    narration_duration_s: float | None = Field(default=None, ge=0)
    captions: str | None = None
    visual_asset: str | None = None
    visual_provider: str | None = None
    visual_model: str | None = None
    visual_seed: int | None = None
    render_included_version: int | None = Field(default=None, ge=1)
