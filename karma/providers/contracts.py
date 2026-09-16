"""Schema contracts for external asset providers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from karma.providers.types import ProviderAssetType, ProviderErrorCategory, ProviderExecutionStatus
from karma.schemas.asset_execution import AssetExecutionJob
from karma.schemas.production import AssetRequirement


class ProviderOutputSpec(BaseModel):
    """Requested output characteristics for a provider request."""

    format: str | None = None
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    duration_seconds: float | None = Field(default=None, gt=0)
    bitrate: int | None = Field(default=None, gt=0)
    sample_rate: int | None = Field(default=None, gt=0)
    channels: int | None = Field(default=None, gt=0)
    voice: str | None = None
    quality: str | None = None
    seed: int | None = None
    aspect_ratio: str | None = None
    output_uri: str | None = None

    @model_validator(mode="after")
    def validate_output_spec(self) -> "ProviderOutputSpec":
        if self.output_uri is not None and not self.output_uri.strip():
            raise ValueError("output_uri cannot be blank")
        return self


class ProviderArtifactMetadata(BaseModel):
    """Artifact metadata returned by a provider."""

    uri: str | None = None
    local_path: str | None = None
    mime_type: str | None = None
    sha256: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)
    duration_seconds: float | None = Field(default=None, gt=0)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderRetryInfo(BaseModel):
    """Retry semantics for provider-facing requests.

    This is a normalized contract, not execution logic. A future adapter decides
    whether it can safely retry based on the provider response and the policy.
    """

    safe_to_retry: bool = False
    retry_after_seconds: float | None = Field(default=None, ge=0)
    duplicate_submission: bool = False
    may_already_be_accepted: bool = False
    permanent_failure: bool = False
    cancelled: bool = False
    provider_error_code: str | None = None


class ProviderErrorInfo(BaseModel):
    """Structured provider-side failure information."""

    code: str
    category: ProviderErrorCategory
    message: str
    retryable: bool = False
    safe_to_retry: bool = False
    retry_after_seconds: float | None = Field(default=None, ge=0)
    duplicate_submission: bool = False
    may_already_be_accepted: bool = False
    provider_error_code: str | None = None
    provider_detail: dict[str, Any] = Field(default_factory=dict)


class ProviderSecurityPolicy(BaseModel):
    """Explicit credential-handling rules for future real provider adapters.

    These are contract rules only; the actual credential source remains runtime
    configuration, environment variables, or a secure external injection layer.
    """

    credentials_from_runtime_only: bool = True
    credentials_in_request: bool = False
    credentials_in_result: bool = False
    credentials_in_artifact_metadata: bool = False
    credentials_in_generic_metadata: bool = False
    credentials_in_errors: bool = False
    secrets_must_not_be_logged: bool = True
    provider_secrets_must_not_be_persisted: bool = True


class ProviderRequest(BaseModel):
    """Canonical request payload for a provider-backed asset execution.

    Credentials and secrets are never part of this request contract. Real provider
    adapters must resolve credentials from runtime configuration or secure
    injection, not from the request payload.
    """

    provider_name: str
    provider_model: str
    provider_model_version: str | None = None
    capability: ProviderAssetType
    asset_id: str
    job_id: str
    episode_id: str
    production_scene_id: str
    scene_id: str
    prompt_or_input: str | dict[str, Any] | None = None
    requested_output: ProviderOutputSpec = Field(default_factory=ProviderOutputSpec)
    idempotency_key: str
    requested_version: int = Field(default=1, ge=1)
    source_context: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_request(self) -> "ProviderRequest":
        if not self.provider_name.strip():
            raise ValueError("provider_name must be non-empty")
        if not self.provider_model.strip():
            raise ValueError("provider_model must be non-empty")
        if not self.asset_id.strip():
            raise ValueError("asset_id must be non-empty")
        if not self.job_id.strip():
            raise ValueError("job_id must be non-empty")
        if not self.episode_id.strip():
            raise ValueError("episode_id must be non-empty")
        if not self.production_scene_id.strip():
            raise ValueError("production_scene_id must be non-empty")
        if not self.scene_id.strip():
            raise ValueError("scene_id must be non-empty")
        if not self.idempotency_key.strip():
            raise ValueError("idempotency_key must be non-empty")
        if self.requested_version < 1:
            raise ValueError("requested_version must be >= 1")
        return self


class ProviderResult(BaseModel):
    """Provider-neutral result metadata for a request submission.

    Provider-native response payloads are treated as internal adapter detail. They
    may be inspected at runtime but should not be persisted as application state
    unless sanitized and explicitly approved by a future adapter contract.
    """

    success: bool
    provider_name: str
    provider_model: str
    provider_model_version: str | None = None
    provider_job_id: str | None = None
    provider_request_id: str | None = None
    job_id: str
    asset_id: str
    episode_id: str
    capability: ProviderAssetType
    status: ProviderExecutionStatus
    artifact: ProviderArtifactMetadata | None = None
    retry: ProviderRetryInfo | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    elapsed_ms: int | None = Field(default=None, ge=0)
    error: ProviderErrorInfo | None = None
    internal_raw_response: dict[str, Any] | None = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def validate_result(self) -> "ProviderResult":
        if not self.provider_name.strip():
            raise ValueError("provider_name must be non-empty")
        if not self.provider_model.strip():
            raise ValueError("provider_model must be non-empty")
        if not self.job_id.strip():
            raise ValueError("job_id must be non-empty")
        if not self.asset_id.strip():
            raise ValueError("asset_id must be non-empty")
        if not self.episode_id.strip():
            raise ValueError("episode_id must be non-empty")
        return self


def asset_requirement_to_provider_request(
    asset_requirement: AssetRequirement,
    execution_job: AssetExecutionJob,
    *,
    provider_name: str,
    provider_model: str,
    provider_model_version: str | None = None,
    capability: ProviderAssetType,
    prompt_or_input: str | dict[str, Any] | None = None,
    requested_output: ProviderOutputSpec | None = None,
    source_context: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> ProviderRequest:
    """Map frozen Phase 2D asset metadata to a provider request without replacing canonical IDs."""
    if not asset_requirement.asset_id.strip():
        raise ValueError("asset_id must be non-empty")
    if not execution_job.job_id.strip():
        raise ValueError("job_id must be non-empty")
    if asset_requirement.asset_id != execution_job.asset_id:
        raise ValueError("asset_id mismatch between AssetRequirement and AssetExecutionJob")
    if asset_requirement.episode_id != execution_job.episode_id:
        raise ValueError("episode_id mismatch between AssetRequirement and AssetExecutionJob")
    if asset_requirement.scene_id != execution_job.scene_id:
        raise ValueError("scene_id mismatch between AssetRequirement and AssetExecutionJob")

    idempotency_key = (
        f"{execution_job.episode_id}:{execution_job.asset_id}:"
        f"v{execution_job.requested_version}:{provider_name}:{provider_model}:{capability.value}"
    )

    return ProviderRequest(
        provider_name=provider_name,
        provider_model=provider_model,
        provider_model_version=provider_model_version,
        capability=capability,
        asset_id=asset_requirement.asset_id,
        job_id=execution_job.job_id,
        episode_id=execution_job.episode_id,
        production_scene_id=execution_job.production_scene_id,
        scene_id=execution_job.scene_id,
        prompt_or_input=prompt_or_input or asset_requirement.prompt_or_spec,
        requested_output=requested_output or ProviderOutputSpec(),
        idempotency_key=idempotency_key,
        requested_version=execution_job.requested_version,
        source_context=source_context,
        metadata=metadata or {},
    )
