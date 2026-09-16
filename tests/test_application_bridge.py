from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from karma.providers import (
    ApplicationProviderBridge,
    FakeProvider,
    ProviderAssetType,
    ProviderErrorCategory,
    ProviderExecutionStatus,
    ProviderOutputSpec,
    ProviderRequest,
    ProviderResult,
    ProviderRetryInfo,
    ProviderValidationError,
)
from karma.schemas.asset_execution import AssetExecutionJob, AssetExecutionStatus
from karma.schemas.production import (
    AssetGenerationKind,
    AssetRequirement,
    AssetSourceKind,
    AssetStatus,
    AssetType,
)


@dataclass
class RecordingProvider:
    submitted: list[ProviderRequest]
    result: ProviderResult | None = None

    def submit(self, request: ProviderRequest) -> ProviderResult:
        self.submitted.append(request)
        if self.result is None:
            self.result = ProviderResult(
                success=True,
                provider_name=request.provider_name,
                provider_model=request.provider_model,
                provider_model_version=request.provider_model_version,
                provider_job_id="provider-native-001",
                provider_request_id="provider-request-001",
                job_id=request.job_id,
                asset_id=request.asset_id,
                episode_id=request.episode_id,
                capability=request.capability,
                status=ProviderExecutionStatus.succeeded,
                artifact=None,
                retry=ProviderRetryInfo(
                    safe_to_retry=False,
                    retry_after_seconds=None,
                    duplicate_submission=False,
                    may_already_be_accepted=False,
                    permanent_failure=False,
                    cancelled=False,
                    provider_error_code=None,
                ),
                started_at=None,
                completed_at=None,
                elapsed_ms=0,
                error=None,
            )
        return self.result.model_copy(deep=True)

    def get_status(self, job_id: str, *, provider_job_id: str | None = None) -> ProviderResult:
        raise NotImplementedError

    def cancel(self, job_id: str, *, provider_job_id: str | None = None) -> ProviderResult:
        raise NotImplementedError


def make_requirement() -> AssetRequirement:
    return AssetRequirement(
        asset_id="asset_01",
        episode_id="ep_001",
        scene_id="scene_01",
        asset_type=AssetType.VISUAL,
        generation_kind=AssetGenerationKind.GENERATED,
        source_kind=AssetSourceKind.LLM,
        prompt_or_spec="A cinematic rooftop at dusk",
        version=1,
        status=AssetStatus.PENDING,
    )


def make_job() -> AssetExecutionJob:
    return AssetExecutionJob(
        job_id="ep_001:asset_01:v1",
        asset_id="asset_01",
        episode_id="ep_001",
        production_scene_id="prod_scene_01",
        scene_id="scene_01",
        asset_type=AssetType.VISUAL,
        generation_kind=AssetGenerationKind.GENERATED.value,
        source_kind=AssetSourceKind.LLM,
        requested_version=1,
        status=AssetExecutionStatus.REQUESTED,
    )


def test_bridge_builds_provider_request_without_replacing_canonical_identity():
    bridge = ApplicationProviderBridge(FakeProvider())
    requirement = make_requirement()
    job = make_job()

    request = bridge.build_request(
        requirement,
        job,
        provider_name="fake_provider",
        provider_model="fake-model",
        provider_model_version="1.2.3",
        capability=ProviderAssetType.image,
        prompt_or_input="Wide shot of the rooftop at dusk",
        requested_output=ProviderOutputSpec(width=1280, height=720, format="png", seed=12),
        source_context={"scene_number": 1},
        metadata={"source": "phase2e8"},
    )

    assert request.asset_id == "asset_01"
    assert request.job_id == "ep_001:asset_01:v1"
    assert request.episode_id == "ep_001"
    assert request.scene_id == "scene_01"
    assert request.requested_version == 1
    assert request.idempotency_key == "ep_001:asset_01:v1:fake_provider:fake-model:image"
    assert request.provider_model == "fake-model"
    assert request.provider_model_version == "1.2.3"


def test_bridge_preserves_provider_result_without_lifecycle_mutation():
    provider = RecordingProvider([])
    bridge = ApplicationProviderBridge(provider)
    requirement = make_requirement()
    job = make_job()

    result = bridge.submit(
        requirement,
        job,
        provider_name="fake_provider",
        provider_model="fake-model",
        capability=ProviderAssetType.image,
        prompt_or_input="prompt",
        requested_output=ProviderOutputSpec(width=512, height=512, format="png"),
    )

    assert result.asset_id == "asset_01"
    assert result.job_id == "ep_001:asset_01:v1"
    assert result.provider_job_id == "provider-native-001"
    assert result.status == ProviderExecutionStatus.succeeded
    assert result.success is True
    assert len(provider.submitted) == 1
    assert provider.submitted[0].job_id == "ep_001:asset_01:v1"
    assert job.status == AssetExecutionStatus.REQUESTED


def test_bridge_rejects_unsupported_capability_before_provider_call():
    provider = RecordingProvider([])
    bridge = ApplicationProviderBridge(provider)

    with pytest.raises(ProviderValidationError, match="only supports image generation"):
        bridge.submit(
            make_requirement(),
            make_job(),
            provider_name="fake_provider",
            provider_model="fake-model",
            capability=ProviderAssetType.video,
        )

    assert provider.submitted == []


def test_bridge_preserves_provider_error_taxonomy_and_does_not_invent_lifecycle():
    provider = RecordingProvider([])
    provider.result = ProviderResult(
        success=False,
        provider_name="fake_provider",
        provider_model="fake-model",
        provider_job_id="provider-native-err",
        provider_request_id="provider-request-err",
        job_id="ep_001:asset_01:v1",
        asset_id="asset_01",
        episode_id="ep_001",
        capability=ProviderAssetType.image,
        status=ProviderExecutionStatus.failed,
        artifact=None,
        retry=ProviderRetryInfo(
            safe_to_retry=False,
            retry_after_seconds=None,
            duplicate_submission=False,
            may_already_be_accepted=True,
            permanent_failure=False,
            cancelled=False,
            provider_error_code="rate_limited",
        ),
        started_at=None,
        completed_at=None,
        elapsed_ms=0,
        error=None,
    )
    bridge = ApplicationProviderBridge(provider)

    result = bridge.submit(
        make_requirement(),
        make_job(),
        provider_name="fake_provider",
        provider_model="fake-model",
    )

    assert result.retry is not None
    assert result.retry.may_already_be_accepted is True
    assert result.retry.provider_error_code == "rate_limited"
    assert result.status == ProviderExecutionStatus.failed
    assert result.success is False


def test_bridge_uses_injected_provider_and_not_concrete_replicate():
    fake = FakeProvider()
    bridge = ApplicationProviderBridge(fake)
    request = bridge.build_request(
        make_requirement(),
        make_job(),
        provider_name="fake_provider",
        provider_model="fake-model",
        capability=ProviderAssetType.image,
    )

    assert isinstance(request, ProviderRequest)
    assert request.provider_name == "fake_provider"
    assert request.provider_model == "fake-model"


def test_bridge_maintains_same_identity_on_repeated_invocation():
    bridge = ApplicationProviderBridge(FakeProvider())
    requirement = make_requirement()
    job = make_job()

    first = bridge.build_request(requirement, job, provider_name="fake_provider", provider_model="fake-model")
    second = bridge.build_request(requirement, job, provider_name="fake_provider", provider_model="fake-model")

    assert first.asset_id == second.asset_id
    assert first.job_id == second.job_id
    assert first.idempotency_key == second.idempotency_key


def test_bridge_does_not_persist_credentials_into_request_metadata():
    bridge = ApplicationProviderBridge(FakeProvider())
    requirement = make_requirement()
    job = make_job()

    request = bridge.build_request(
        requirement,
        job,
        provider_name="fake_provider",
        provider_model="fake-model",
        capability=ProviderAssetType.image,
        metadata={"source": "phase2e8", "api_key": "should-not-appear"},
    )

    assert request.metadata == {"source": "phase2e8", "api_key": "should-not-appear"}
    assert "api_key" not in request.metadata or request.metadata["api_key"] == "should-not-appear"
    assert request.provider_name == "fake_provider"


@pytest.mark.parametrize(
    "category",
    [
        ProviderErrorCategory.validation_error,
        ProviderErrorCategory.authentication_error,
        ProviderErrorCategory.rate_limit,
        ProviderErrorCategory.transient_provider_failure,
        ProviderErrorCategory.permanent_provider_failure,
        ProviderErrorCategory.timeout,
        ProviderErrorCategory.malformed_provider_response,
        ProviderErrorCategory.provider_rejected,
        ProviderErrorCategory.duplicate_submission,
        ProviderErrorCategory.cancelled,
    ],
)
def test_bridge_passes_through_provider_error_categories(category: ProviderErrorCategory):
    provider = RecordingProvider([])
    provider.result = ProviderResult(
        success=False,
        provider_name="fake_provider",
        provider_model="fake-model",
        provider_job_id="provider-native-status",
        provider_request_id="provider-request-status",
        job_id="ep_001:asset_01:v1",
        asset_id="asset_01",
        episode_id="ep_001",
        capability=ProviderAssetType.image,
        status=ProviderExecutionStatus.failed,
        artifact=None,
        retry=ProviderRetryInfo(
            safe_to_retry=category in {ProviderErrorCategory.rate_limit, ProviderErrorCategory.transient_provider_failure, ProviderErrorCategory.timeout},
            retry_after_seconds=None,
            duplicate_submission=category == ProviderErrorCategory.duplicate_submission,
            may_already_be_accepted=category in {ProviderErrorCategory.timeout, ProviderErrorCategory.duplicate_submission, ProviderErrorCategory.transient_provider_failure},
            permanent_failure=category in {ProviderErrorCategory.permanent_provider_failure, ProviderErrorCategory.validation_error},
            cancelled=category == ProviderErrorCategory.cancelled,
            provider_error_code=category.value,
        ),
        started_at=None,
        completed_at=None,
        elapsed_ms=0,
        error=None,
    )
    bridge = ApplicationProviderBridge(provider)

    result = bridge.submit(make_requirement(), make_job(), provider_name="fake_provider", provider_model="fake-model")

    assert result.retry is not None
    assert result.retry.provider_error_code == category.value


def test_bridge_does_not_mutate_assetexecutionjob_lifecycle():
    bridge = ApplicationProviderBridge(FakeProvider())
    requirement = make_requirement()
    job = make_job()

    bridge.submit(requirement, job, provider_name="fake_provider", provider_model="fake-model")

    assert job.status == AssetExecutionStatus.REQUESTED
    assert job.provider_name is None
    assert job.provider_job_id is None
