"""Asset reference models for provenance and consistency tracking."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AssetType(StrEnum):
    """Category of a resolved visual or library asset."""

    CHARACTER = "character"
    LOCATION = "location"
    OBJECT = "object"
    VISUAL = "visual"


class AssetReference(BaseModel):
    """A resolved asset with provenance metadata."""

    asset_id: str
    asset_type: AssetType
    version: int = Field(ge=1)
    path: str | None = None
    provider: str | None = None
    model: str | None = None
    prompt: str | None = None
    reference_metadata: dict[str, Any] = Field(default_factory=dict)
