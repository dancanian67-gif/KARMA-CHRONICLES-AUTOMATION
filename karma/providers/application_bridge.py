"""Application-boundary bridge between canonical asset execution and provider adapters."""

from __future__ import annotations

from typing import Any

from karma.providers.base import ProviderProtocol
from karma.providers.contracts import (
    ProviderOutputSpec,
    ProviderRequest,
    ProviderResult,
    asset_requirement_to_provider_request,
)
from karma.providers.errors import ProviderValidationError
from karma.providers.types import ProviderAssetType
from karma.schemas.asset_execution import AssetExecutionJob
from karma.schemas.production import AssetRequirement


class ApplicationProviderBridge:
    """Translate canonical application requests into provider-facing requests.

    This bridge intentionally does not own the application lifecycle or a second
    checkpoint system. It validates the canonical inputs, builds a ProviderRequest,
    delegates to an injected ProviderProtocol, and returns the provider result.
    """

    def __init__(self, provider: ProviderProtocol) -> None:
        self._provider = provider

    @property
    def provider(self) -> ProviderProtocol:
        return self._provider

    def build_request(
        self,
        asset_requirement: AssetRequirement,
        execution_job: AssetExecutionJob,
        *,
        provider_name: str,
        provider_model: str,
        provider_model_version: str | None = None,
        capability: ProviderAssetType = ProviderAssetType.image,
        prompt_or_input: str | dict[str, Any] | None = None,
        requested_output: ProviderOutputSpec | None = None,
        source_context: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProviderRequest:
        """Create a provider request from the canonical application pair."""
        self._validate_asset_job_pair(asset_requirement, execution_job)

        if capability != ProviderAssetType.image:
            raise ProviderValidationError(
                "Phase 2E.8 only supports image generation through the provider boundary."
            )

        return asset_requirement_to_provider_request(
            asset_requirement,
            execution_job,
            provider_name=provider_name,
            provider_model=provider_model,
            provider_model_version=provider_model_version,
            capability=capability,
            prompt_or_input=prompt_or_input,
            requested_output=requested_output,
            source_context=source_context,
            metadata=metadata,
        )

    def submit(
        self,
        asset_requirement: AssetRequirement,
        execution_job: AssetExecutionJob,
        *,
        provider_name: str,
        provider_model: str,
        provider_model_version: str | None = None,
        capability: ProviderAssetType = ProviderAssetType.image,
        prompt_or_input: str | dict[str, Any] | None = None,
        requested_output: ProviderOutputSpec | None = None,
        source_context: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProviderResult:
        """Validate canonical identity and delegate to the injected provider."""
        request = self.build_request(
            asset_requirement,
            execution_job,
            provider_name=provider_name,
            provider_model=provider_model,
            provider_model_version=provider_model_version,
            capability=capability,
            prompt_or_input=prompt_or_input,
            requested_output=requested_output,
            source_context=source_context,
            metadata=metadata,
        )
        return self._provider.submit(request)

    def get_status(self, job_id: str, *, provider_job_id: str | None = None) -> ProviderResult:
        return self._provider.get_status(job_id, provider_job_id=provider_job_id)

    def cancel(self, job_id: str, *, provider_job_id: str | None = None) -> ProviderResult:
        return self._provider.cancel(job_id, provider_job_id=provider_job_id)

    @staticmethod
    def _validate_asset_job_pair(
        asset_requirement: AssetRequirement,
        execution_job: AssetExecutionJob,
    ) -> None:
        if asset_requirement.asset_id != execution_job.asset_id:
            raise ProviderValidationError("asset_id mismatch between AssetRequirement and AssetExecutionJob")
        if asset_requirement.episode_id != execution_job.episode_id:
            raise ProviderValidationError("episode_id mismatch between AssetRequirement and AssetExecutionJob")
        if asset_requirement.scene_id != execution_job.scene_id:
            raise ProviderValidationError("scene_id mismatch between AssetRequirement and AssetExecutionJob")
        if asset_requirement.version != execution_job.requested_version:
            raise ProviderValidationError("requested_version mismatch between AssetRequirement and AssetExecutionJob")
        if not asset_requirement.asset_id.strip():
            raise ProviderValidationError("asset_id must be non-empty")
        if not execution_job.job_id.strip():
            raise ProviderValidationError("job_id must be non-empty")


__all__ = ["ApplicationProviderBridge"]
