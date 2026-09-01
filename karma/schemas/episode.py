"""Episode manifest — top-level domain model."""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from karma.schemas.audio import AudioMaster
from karma.schemas.publishing import (
    Approval,
    MetadataState,
    PublishState,
    RenderState,
    ThumbnailState,
)
from karma.schemas.scene import Scene, VersionHistoryEntry


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EpisodeStatus(StrEnum):
    """Lifecycle state for an episode."""

    DRAFT = "draft"
    RESEARCHING = "researching"
    STORY_DEVELOPMENT = "story_development"
    SCRIPT_DEVELOPMENT = "script_development"
    IN_PRODUCTION = "in_production"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED = "failed"
    ARCHIVED = "archived"


class QAStatus(StrEnum):
    """Script quality-assurance status."""

    PENDING = "pending"
    FAILED = "failed"
    PASSED = "passed"
    HUMAN_OVERRIDE = "human_override"


class StoryState(BaseModel):
    """Versioned story architecture state.

    ``content`` is intentionally flexible so future Story Architect output
    can evolve without schema churn.
    """

    version: int = Field(default=1, ge=1)
    history: list[VersionHistoryEntry] = Field(default_factory=list)
    content: dict[str, Any] | None = None


class ScriptState(BaseModel):
    """Versioned script state with QA tracking."""

    version: int = Field(default=1, ge=1)
    history: list[VersionHistoryEntry] = Field(default_factory=list)
    content: dict[str, Any] | None = None
    qa_status: QAStatus = QAStatus.PENDING


class ProductionState(BaseModel):
    """Versioned production planning state."""

    version: int = Field(default=1, ge=1)
    history: list[VersionHistoryEntry] = Field(default_factory=list)
    content: dict[str, Any] | None = None


class ResearchState(BaseModel):
    """Versioned research state.

    ``content`` holds the serialized ResearchBrief as a dict.
    """

    version: int = Field(default=1, ge=1)
    history: list[VersionHistoryEntry] = Field(default_factory=list)
    content: dict[str, Any] | None = None


class StageRunStatus(StrEnum):
    """Checkpoint status for a single orchestration stage."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class StageCheckpoint(BaseModel):
    """Persisted checkpoint for one pipeline stage."""

    name: str
    status: StageRunStatus = StageRunStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    output: dict[str, Any] | None = None


class OrchestrationState(BaseModel):
    """Orchestration checkpoint state stored on the episode manifest."""

    stages: dict[str, StageCheckpoint] = Field(default_factory=dict)


class EpisodeManifest(BaseModel):
    """Single source of truth for an episode's state and artifacts."""

    episode_id: str
    status: EpisodeStatus = EpisodeStatus.DRAFT
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    research_topic: str | None = None
    research: ResearchState = Field(default_factory=ResearchState)
    story: StoryState = Field(default_factory=StoryState)
    script: ScriptState = Field(default_factory=ScriptState)
    production: ProductionState = Field(default_factory=ProductionState)
    scenes: list[Scene] = Field(default_factory=list)
    audio_master: AudioMaster = Field(default_factory=AudioMaster)
    render: RenderState = Field(default_factory=RenderState)
    thumbnail: ThumbnailState = Field(default_factory=ThumbnailState)
    metadata: MetadataState = Field(default_factory=MetadataState)
    approvals: list[Approval] = Field(default_factory=list)
    publish: PublishState = Field(default_factory=PublishState)
    analytics_ref: str | None = None
    orchestration: OrchestrationState = Field(default_factory=OrchestrationState)
