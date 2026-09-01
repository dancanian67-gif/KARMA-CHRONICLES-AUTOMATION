"""Asset execution models for Phase 2D."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from karma.schemas.production import AssetProvenance, AssetSourceKind, AssetType


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AssetExecutionStatus(StrEnum):
    """Provider-agnostic lifecycle for an execution job."""

    REQUESTED = "requested"
    GENERATING = "generating"
    GENERATED = "generated"
    VALIDATED = "validated"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    AVAILABLE = "available"
    FAILED = "failed"


class AssetExecutionJob(BaseModel):
    """Execution job for a planned asset requirement."""

    job_id: str
    asset_id: str
    episode_id: str
    production_scene_id: str
    scene_id: str
    continuity_ref_id: str | None = None
    asset_type: AssetType
    generation_kind: str | None = None
    source_kind: AssetSourceKind | None = None
    requested_version: int = Field(default=1, ge=1)
    status: AssetExecutionStatus = AssetExecutionStatus.REQUESTED
    provider_name: str | None = None
    provider_job_id: str | None = None
    provider_asset_id: str | None = None
    output_path_or_uri: str | None = None
    provenance: AssetProvenance = Field(default_factory=AssetProvenance)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    error_message: str | None = None

    @model_validator(mode="after")
    def validate_job(self) -> AssetExecutionJob:
        if not self.job_id.strip():
            raise ValueError("job_id must be non-empty")
        if not self.asset_id.strip():
            raise ValueError("asset_id must be non-empty")
        if not self.episode_id.strip():
            raise ValueError("episode_id must be non-empty")
        if not self.production_scene_id.strip():
            raise ValueError("production_scene_id must be non-empty")
        if not self.scene_id.strip():
            raise ValueError("scene_id must be non-empty")
        if self.output_path_or_uri is not None and not self.output_path_or_uri.strip():
            raise ValueError("output_path_or_uri cannot be blank")
        if self.requested_version < 1:
            raise ValueError("requested_version must be >= 1")
        return self

    def transition_to(self, next_status: AssetExecutionStatus) -> None:
        """Move this job through the supported lifecycle."""
        valid_next = {
            AssetExecutionStatus.REQUESTED: {
                AssetExecutionStatus.GENERATING,
                AssetExecutionStatus.REJECTED,
                AssetExecutionStatus.FAILED,
            },
            AssetExecutionStatus.GENERATING: {
                AssetExecutionStatus.GENERATED,
                AssetExecutionStatus.FAILED,
                AssetExecutionStatus.REJECTED,
            },
            AssetExecutionStatus.GENERATED: {
                AssetExecutionStatus.VALIDATED,
                AssetExecutionStatus.REJECTED,
                AssetExecutionStatus.FAILED,
            },
            AssetExecutionStatus.VALIDATED: {
                AssetExecutionStatus.ACCEPTED,
                AssetExecutionStatus.REJECTED,
                AssetExecutionStatus.FAILED,
            },
            AssetExecutionStatus.ACCEPTED: {
                AssetExecutionStatus.AVAILABLE,
                AssetExecutionStatus.REJECTED,
                AssetExecutionStatus.FAILED,
            },
            AssetExecutionStatus.REJECTED: {
                AssetExecutionStatus.REQUESTED,
                AssetExecutionStatus.FAILED,
            },
            AssetExecutionStatus.AVAILABLE: set(),
            AssetExecutionStatus.FAILED: set(),
        }

        if next_status not in valid_next.get(self.status, set()):
            raise ValueError(
                f"invalid transition: {self.status.value} -> {next_status.value}"
            )

        self.status = next_status
        self.updated_at = _utc_now()
