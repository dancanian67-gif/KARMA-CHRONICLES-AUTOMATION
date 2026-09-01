"""Publishing, approval, render, and metadata models."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Privacy(StrEnum):
    """YouTube privacy setting."""

    PRIVATE = "private"
    UNLISTED = "unlisted"
    PUBLIC = "public"


class Approval(BaseModel):
    """A human approval record for a pipeline stage."""

    stage: str
    approved_by: str
    approved_at: datetime
    artifact_version: int = Field(ge=1)


class PublishState(BaseModel):
    """YouTube publish state for an episode."""

    youtube_video_id: str | None = None
    uploaded_at: datetime | None = None
    privacy: Privacy | None = None
    publish_at: datetime | None = None


class MetadataState(BaseModel):
    """YouTube metadata for an episode."""

    title: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    category: str | None = None


class ThumbnailState(BaseModel):
    """Thumbnail artifact state."""

    version: int = Field(default=1, ge=1)
    path: str | None = None


class RenderState(BaseModel):
    """Final rendered video state."""

    version: int = Field(default=1, ge=1)
    path: str | None = None
    duration_s: float | None = Field(default=None, ge=0)
    completed_at: datetime | None = None
