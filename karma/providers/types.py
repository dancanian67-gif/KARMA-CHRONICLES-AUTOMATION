"""Provider capability enums and domain-neutral execution primitives."""

from __future__ import annotations

from enum import StrEnum


class ProviderAssetType(StrEnum):
    """Provider-supported media asset capability."""

    image = "image"
    video = "video"
    tts = "tts"
    music = "music"
    sfx = "sfx"


class ProviderExecutionStatus(StrEnum):
    """Provider-facing lifecycle states for a submitted job.

    The application-level lifecycle remains the authoritative AssetExecutionJob
    lifecycle. This provider lifecycle tracks only the external provider's view of
    the request.
    """

    submitted = "submitted"
    accepted = "accepted"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class ProviderErrorCategory(StrEnum):
    """Structured provider error taxonomy."""

    validation_error = "validation_error"
    authentication_error = "authentication_error"
    rate_limit = "rate_limit"
    transient_provider_failure = "transient_provider_failure"
    permanent_provider_failure = "permanent_provider_failure"
    timeout = "timeout"
    malformed_provider_response = "malformed_provider_response"
    provider_rejected = "provider_rejected"
    duplicate_submission = "duplicate_submission"
    cancelled = "cancelled"
