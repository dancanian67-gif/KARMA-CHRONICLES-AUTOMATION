"""In-memory fake provider implementations for deterministic contract tests."""

from __future__ import annotations

from datetime import datetime, timezone

from karma.providers.base import ProviderProtocol
from karma.providers.contracts import (
    ProviderArtifactMetadata,
    ProviderErrorCategory,
    ProviderErrorInfo,
    ProviderRequest,
    ProviderResult,
    ProviderRetryInfo,
)
from karma.providers.types import ProviderAssetType, ProviderExecutionStatus


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FakeProvider(ProviderProtocol):
    """Deterministic in-memory provider used for unit tests only."""

    def __init__(self) -> None:
        self._jobs: dict[str, ProviderResult] = {}

    def submit(self, request: ProviderRequest) -> ProviderResult:
        if not request.asset_id.strip():
            raise ValueError("asset_id must be non-empty")
        if not request.job_id.strip():
            raise ValueError("job_id must be non-empty")

        if request.job_id in self._jobs:
            duplicate = self._jobs[request.job_id].model_copy()
            duplicate.retry = ProviderRetryInfo(
                safe_to_retry=False,
                duplicate_submission=True,
                may_already_be_accepted=True,
                permanent_failure=False,
                cancelled=False,
                provider_error_code="duplicate_submission",
            )
            duplicate.success = False
            duplicate.status = ProviderExecutionStatus.accepted
            return duplicate

        result = ProviderResult(
            success=True,
            provider_name=request.provider_name,
            provider_model=request.provider_model,
            provider_model_version=request.provider_model_version,
            provider_job_id=f"{request.job_id}:provider:{request.provider_name}",
            provider_request_id=f"{request.idempotency_key}:request",
            job_id=request.job_id,
            asset_id=request.asset_id,
            episode_id=request.episode_id,
            capability=request.capability,
            status=ProviderExecutionStatus.submitted,
            artifact=ProviderArtifactMetadata(
                uri=f"file:///tmp/{request.asset_id}.bin",
                mime_type="application/octet-stream",
                metadata={
                    "provider": request.provider_name,
                    "model": request.provider_model,
                    "idempotency_key": request.idempotency_key,
                    "capability": request.capability.value,
                    "sanitized": True,
                },
            ),
            retry=ProviderRetryInfo(
                safe_to_retry=True,
                retry_after_seconds=0,
                duplicate_submission=False,
                may_already_be_accepted=False,
                permanent_failure=False,
                cancelled=False,
                provider_error_code=None,
            ),
            started_at=_utc_now(),
            completed_at=None,
            elapsed_ms=0,
            error=None,
        )
        self._jobs[result.job_id] = result
        return result

    def get_status(self, job_id: str, *, provider_job_id: str | None = None) -> ProviderResult:
        if job_id not in self._jobs:
            raise ValueError(f"unknown job_id: {job_id}")

        result = self._jobs[job_id].model_copy()
        result.status = ProviderExecutionStatus.accepted
        result.completed_at = _utc_now()
        result.elapsed_ms = 5
        self._jobs[job_id] = result
        return result

    def cancel(self, job_id: str, *, provider_job_id: str | None = None) -> ProviderResult:
        if job_id not in self._jobs:
            raise ValueError(f"unknown job_id: {job_id}")

        result = self._jobs[job_id].model_copy()
        result.status = ProviderExecutionStatus.cancelled
        result.completed_at = _utc_now()
        result.success = False
        result.error = ProviderErrorInfo(
            code="cancelled",
            category=ProviderErrorCategory.cancelled,
            message="provider execution cancelled",
            retryable=False,
            safe_to_retry=False,
            retry_after_seconds=None,
            duplicate_submission=False,
            may_already_be_accepted=False,
            provider_error_code="cancelled",
            provider_detail={"cancelled": True},
        )
        self._jobs[job_id] = result
        return result


__all__ = ["FakeProvider"]
