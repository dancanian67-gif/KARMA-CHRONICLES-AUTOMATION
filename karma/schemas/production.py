"""Production-planning schemas for Phase 2C."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PlanningStatus(StrEnum):
    """Lifecycle state for an episode production plan."""

    DRAFT = "draft"
    PLANNED = "planned"
    READY = "ready"
    BLOCKED = "blocked"
    ARCHIVED = "archived"


class ScenePlanningStatus(StrEnum):
    """Production planning status for a scene."""

    DRAFT = "draft"
    PLANNED = "planned"
    READY = "ready"
    BLOCKED = "blocked"


class FramingType(StrEnum):
    """Camera framing choices for a planned shot."""

    WIDE = "wide"
    MEDIUM = "medium"
    CLOSEUP = "closeup"
    ECU = "ecu"
    OVERHEAD = "overhead"
    TRACKING = "tracking"


class CameraAngle(StrEnum):
    """Camera angle choices."""

    EYE_LEVEL = "eye_level"
    LOW_ANGLE = "low_angle"
    HIGH_ANGLE = "high_angle"
    DUTCH = "dutch"
    AERIAL = "aerial"


class CameraMovement(StrEnum):
    """Shot movement mode."""

    STATIC = "static"
    PAN = "pan"
    TILT = "tilt"
    DOLLY = "dolly"
    TRACK = "track"
    CRANE = "crane"
    HANDHELD = "handheld"
    ZOOM = "zoom"


class LightingStyle(StrEnum):
    """Lighting style for planned visuals."""

    NATURAL = "natural"
    SOFT = "soft"
    HARSH = "harsh"
    LOW_KEY = "low_key"
    HIGH_KEY = "high_key"
    GOLDEN_HOUR = "golden_hour"
    MOODY = "moody"


class MoodType(StrEnum):
    """Emotional tone for planned visuals."""

    CALM = "calm"
    TENSE = "tense"
    OMINOUS = "ominous"
    INTIMATE = "intimate"
    BITTERSWEET = "bittersweet"
    EUPHORIC = "euphoric"
    MELANCHOLIC = "melancholic"


class AssetType(StrEnum):
    """Asset class used in production planning."""

    CHARACTER = "character"
    LOCATION = "location"
    OBJECT = "object"
    VISUAL = "visual"
    AUDIO = "audio"
    MUSIC = "music"
    SFX = "sfx"
    NARRATION = "narration"


class AssetGenerationKind(StrEnum):
    """How the asset is expected to be produced."""

    GENERATED = "generated"
    REFERENCE = "reference"
    LIBRARY = "library"
    EXISTING = "existing"
    HYBRID = "hybrid"


class AssetSourceKind(StrEnum):
    """Origin of the asset reference."""

    LLM = "llm"
    MANUAL = "manual"
    REUSED = "reused"
    ARCHIVE = "archive"
    REFERENCE = "reference"
    EXISTING_REFERENCE = "existing_reference"
    USER_UPLOAD = "user_upload"


class AssetStatus(StrEnum):
    """Lifecycle status for required production assets."""

    PENDING = "pending"
    PLANNED = "planned"
    GENERATED = "generated"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"
    DEPRECATED = "deprecated"


class ContinuityReference(BaseModel):
    """Reference to a reusable continuity item across scenes."""

    continuity_id: str
    object_type: str
    object_id: str
    version: int = Field(default=1, ge=1)
    aspect: str
    source_scene_id: str
    notes: str | None = None

    @model_validator(mode="after")
    def validate_required_values(self) -> ContinuityReference:
        if not self.object_type.strip():
            raise ValueError("object_type must be non-empty")
        if not self.object_id.strip():
            raise ValueError("object_id must be non-empty")
        if not self.aspect.strip():
            raise ValueError("aspect must be non-empty")
        if not self.source_scene_id.strip():
            raise ValueError("source_scene_id must be non-empty")
        return self


class CharacterAppearanceRequirement(BaseModel):
    """Visual appearance requirement for a character in a scene."""

    character_id: str
    description: str
    reference_asset_id: str | None = None

    @model_validator(mode="after")
    def validate_character(self) -> CharacterAppearanceRequirement:
        if not self.character_id.strip():
            raise ValueError("character_id must be non-empty")
        if not self.description.strip():
            raise ValueError("description must be non-empty")
        return self


class VisualSpecification(BaseModel):
    """Production planning for the visual look of a scene."""

    visual_id: str
    production_scene_id: str
    shot_description: str
    framing: FramingType
    camera_angle: CameraAngle
    camera_movement: CameraMovement
    composition: str | None = None
    character_appearance_requirements: list[CharacterAppearanceRequirement] = Field(default_factory=list)
    environment_requirements: list[str] = Field(default_factory=list)
    lighting: LightingStyle | None = None
    mood: MoodType | None = None
    image_generation_prompt: str | None = None
    negative_prompt: str | None = None
    continuity_reference_assets: list[str] = Field(default_factory=list)
    required_asset_count: int = Field(default=1, ge=1)
    version: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_visual(self) -> VisualSpecification:
        if not self.visual_id.strip():
            raise ValueError("visual_id must be non-empty")
        if not self.production_scene_id.strip():
            raise ValueError("production_scene_id must be non-empty")
        if not self.shot_description.strip():
            raise ValueError("shot_description must be non-empty")
        if self.image_generation_prompt is not None and not self.image_generation_prompt.strip():
            raise ValueError("image_generation_prompt cannot be empty")
        if self.required_asset_count < 1:
            raise ValueError("required_asset_count must be >= 1")
        return self


class NarrationSpec(BaseModel):
    """Narration requirements for a scene."""

    narrator: str | None = None
    style: str | None = None
    tone: str | None = None
    duration_s: float | None = Field(default=None, gt=0)
    text_source: str | None = None


class DialogueTrackSpec(BaseModel):
    """Planned dialogue track for a speaking character."""

    speaker_id: str
    speaker_name: str
    voice_profile: str | None = None
    style: str | None = None
    emotion: str | None = None
    lines: list[str] = Field(default_factory=list)
    timing_start_s: float | None = None
    timing_end_s: float | None = None

    @model_validator(mode="after")
    def validate_dialogue_track(self) -> DialogueTrackSpec:
        if not self.speaker_id.strip():
            raise ValueError("speaker_id must be non-empty")
        if not self.speaker_name.strip():
            raise ValueError("speaker_name must be non-empty")
        if self.timing_start_s is not None and self.timing_end_s is not None:
            if self.timing_end_s <= self.timing_start_s:
                raise ValueError("timing_end_s must be greater than timing_start_s")
        return self


class SFXSpec(BaseModel):
    """Sound effect requirement for a production scene."""

    sfx_id: str
    description: str
    start_s: float | None = None
    duration_s: float | None = Field(default=None, gt=0)
    intensity: str | None = None
    source: str | None = None

    @model_validator(mode="after")
    def validate_sfx(self) -> SFXSpec:
        if not self.sfx_id.strip():
            raise ValueError("sfx_id must be non-empty")
        if not self.description.strip():
            raise ValueError("description must be non-empty")
        return self


class MusicSpec(BaseModel):
    """Music cue requirement for a scene."""

    mood: str
    style: str | None = None
    duration_s: float | None = Field(default=None, gt=0)
    start_s: float | None = None
    intensity: str | None = None

    @model_validator(mode="after")
    def validate_music(self) -> MusicSpec:
        if not self.mood.strip():
            raise ValueError("mood must be non-empty")
        return self


class MasteringSpec(BaseModel):
    """Mastering and loudness metadata for audio output."""

    loudness_target_lufs: float | None = None
    normalization_mode: str | None = None
    ducking: bool = False


class AudioSpecification(BaseModel):
    """Production audio plan for a scene."""

    audio_id: str
    production_scene_id: str
    narration: NarrationSpec | None = None
    dialogue_tracks: list[DialogueTrackSpec] = Field(default_factory=list)
    sfx: list[SFXSpec] = Field(default_factory=list)
    ambience: str | None = None
    music: MusicSpec | None = None
    total_duration_s: float | None = Field(default=None, gt=0)
    mastering: MasteringSpec | None = None
    version: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_audio(self) -> AudioSpecification:
        if not self.audio_id.strip():
            raise ValueError("audio_id must be non-empty")
        if not self.production_scene_id.strip():
            raise ValueError("production_scene_id must be non-empty")
        return self


class AssetProvenance(BaseModel):
    """Traceability metadata for a production asset."""

    model: str | None = None
    prompt_hash: str | None = None
    base_asset_id: str | None = None
    source_reference: str | None = None
    notes: str | None = None


class AssetRequirement(BaseModel):
    """Deterministic requirement for a generated or referenced asset."""

    asset_id: str
    episode_id: str
    scene_id: str
    asset_type: AssetType
    generation_kind: AssetGenerationKind
    source_kind: AssetSourceKind
    prompt_or_spec: str | None = None
    reference_asset_id: str | None = None
    continuity_ref_id: str | None = None
    version: int = Field(default=1, ge=1)
    status: AssetStatus = AssetStatus.PENDING
    path_or_uri: str | None = None
    provenance: AssetProvenance = Field(default_factory=AssetProvenance)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def validate_asset(self) -> AssetRequirement:
        if not self.asset_id.strip():
            raise ValueError("asset_id must be non-empty")
        if not self.episode_id.strip():
            raise ValueError("episode_id must be non-empty")
        if not self.scene_id.strip():
            raise ValueError("scene_id must be non-empty")
        if self.path_or_uri is not None and not self.path_or_uri.strip():
            raise ValueError("path_or_uri cannot be blank")
        return self


class ProductionScene(BaseModel):
    """One production-planning record per source script scene."""

    production_scene_id: str
    script_scene_id: str
    scene_number: int = Field(ge=1)
    title: str | None = None
    narrative_purpose: str
    duration_s: float | None = Field(default=None, gt=0)
    characters: list[str] = Field(default_factory=list)
    primary_location_id: str | None = None
    location_name: str | None = None
    time_of_day: str | None = None
    emotional_state: str | None = None
    continuity_requirements: list[ContinuityReference] = Field(default_factory=list)
    visual_spec: VisualSpecification | None = None
    audio_spec: AudioSpecification | None = None
    asset_requirements: list[str] = Field(default_factory=list)
    planning_status: ScenePlanningStatus = ScenePlanningStatus.DRAFT
    notes: str | None = None
    version: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_scene(self) -> ProductionScene:
        if not self.production_scene_id.strip():
            raise ValueError("production_scene_id must be non-empty")
        if not self.script_scene_id.strip():
            raise ValueError("script_scene_id must be non-empty")
        if not self.narrative_purpose.strip():
            raise ValueError("narrative_purpose must be non-empty")
        return self


class ProductionPlan(BaseModel):
    """Authoritative production planning blueprint for an episode."""

    plan_id: str
    episode_id: str
    script_id: str
    script_version: int = Field(ge=1)
    schema_version: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    status: PlanningStatus = PlanningStatus.DRAFT
    scenes: list[ProductionScene] = Field(default_factory=list)
    continuity_index: list[ContinuityReference] = Field(default_factory=list)
    asset_requirements: list[AssetRequirement] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    version_history: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_plan(self) -> ProductionPlan:
        if not self.plan_id.strip():
            raise ValueError("plan_id must be non-empty")
        if not self.episode_id.strip():
            raise ValueError("episode_id must be non-empty")
        if not self.script_id.strip():
            raise ValueError("script_id must be non-empty")
        if not self.scenes:
            raise ValueError("ProductionPlan must contain at least one scene")

        scene_ids = [scene.production_scene_id for scene in self.scenes]
        if len(scene_ids) != len(set(scene_ids)):
            raise ValueError("production_scene_id values must be unique")

        scene_numbers = [scene.scene_number for scene in self.scenes]
        if len(scene_numbers) != len(set(scene_numbers)):
            raise ValueError("scene_number values must be unique")

        continuity_ids = [ref.continuity_id for ref in self.continuity_index]
        if len(continuity_ids) != len(set(continuity_ids)):
            raise ValueError("continuity_id values must be unique")

        asset_ids = [asset.asset_id for asset in self.asset_requirements]
        if len(asset_ids) != len(set(asset_ids)):
            raise ValueError("asset_id values must be unique")

        return self
