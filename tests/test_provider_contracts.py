from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from karma.asset_execution import AssetExecutionJob
from karma.providers import (
    FakeProvider,
    ProviderArtifactMetadata,
    ProviderAssetType,
    ProviderErrorCategory,
    ProviderExecutionStatus,
    ProviderOutputSpec,
    ProviderRequest,
    ProviderResult,
    ProviderRetryInfo,
    ProviderSecurityPolicy,
    asset_requirement_to_provider_request,
)
from karma.schemas.asset_execution import AssetExecutionStatus
from karma.schemas.production import (
    AssetGenerationKind,
    AssetRequirement,
    AssetSourceKind,
    AssetStatus,
    AssetType,
)


def make_asset_requirement(*, asset_id: str = "asset_01", scene_id: str = "scene_01") -> AssetRequirement:
    return AssetRequirement(
        asset_id=asset_id,
        episode_id="ep_001",
        scene_id=scene_id,
        asset_type=AssetType.VISUAL,
        generation_kind=AssetGenerationKind.GENERATED,
        source_kind=AssetSourceKind.LLM,
        prompt_or_spec="Generate a dramatic still frame",
        version=1,
        status=AssetStatus.PENDING,
    )


def make_job(*, asset_id: str = "asset_01", scene_id: str = "scene_01") -> AssetExecutionJob:
    return AssetExecutionJob(
        job_id="ep_001:asset_01:v1",
        asset_id=asset_id,
        episode_id="ep_001",
        production_scene_id="prod_scene_01",
        scene_id=scene_id,
        asset_type=AssetType.VISUAL,
        generation_kind=AssetGenerationKind.GENERATED.value,
        source_kind=AssetSourceKind.LLM,
        requested_version=1,
        status=AssetExecutionStatus.REQUESTED,
    )


def test_provider_request_construction_from_asset_requirement_and_job():
    requirement = make_asset_requirement()
    job = make_job()

    request = asset_requirement_to_provider_request(
        requirement,
        job,
        provider_name="fake_provider",
        provider_model="fake-model",
        provider_model_version="1.2.3",
        capability=ProviderAssetType.image,
        prompt_or_input="Wide shot of a city rooftop at dusk",
        requested_output=ProviderOutputSpec(width=1024, height=1024, format="png"),
        source_context={"scene_number": 1},
        metadata={"source": "phase2e2"},
    )

    assert request.asset_id == "asset_01"
    assert request.job_id == "ep_001:asset_01:v1"
    assert request.episode_id == "ep_001"
    assert request.scene_id == "scene_01"
    assert request.production_scene_id == "prod_scene_01"
    assert request.requested_version == 1
    assert request.idempotency_key


def test_blank_canonical_identity_is_rejected():
    with pytest.raises(ValidationError, match="asset_id must be non-empty"):
        make_asset_requirement(asset_id="")

    with pytest.raises(ValueError, match="job_id must be non-empty"):
        ProviderRequest(
            provider_name="fake_provider",
            provider_model="fake-model",
            capability=ProviderAssetType.image,
            asset_id="asset_01",
            job_id="",
            episode_id="ep_001",
            production_scene_id="prod_scene_01",
            scene_id="scene_01",
            prompt_or_input="prompt",
            requested_output=ProviderOutputSpec(format="png"),
            idempotency_key="abc",
            requested_version=1,
        )


def test_idempotency_is_deterministic():
    requirement = make_asset_requirement()
    job = make_job()

    first = asset_requirement_to_provider_request(
        requirement,
        job,
        provider_name="fake_provider",
        provider_model="fake-model",
        capability=ProviderAssetType.image,
    )
    second = asset_requirement_to_provider_request(
        requirement,
        job,
        provider_name="fake_provider",
        provider_model="fake-model",
        capability=ProviderAssetType.image,
    )

    assert first.idempotency_key == second.idempotency_key
    assert first.asset_id == second.asset_id
    assert first.job_id == second.job_id


def test_provider_result_serialization_round_trip():
    result = ProviderResult(
        success=True,
        provider_name="fake_provider",
        provider_model="fake-model",
        provider_model_version="1.2.3",
        provider_job_id="prov_job_123",
        provider_request_id="prov_req_456",
        job_id="ep_001:asset_01:v1",
        asset_id="asset_01",
        episode_id="ep_001",
        capability=ProviderAssetType.image,
        status=ProviderExecutionStatus.succeeded,
        artifact=ProviderArtifactMetadata(
            uri="file:///tmp/result.png",
            mime_type="image/png",
            metadata={"provider": "fake_provider", "sanitized": True},
        ),
        retry=ProviderRetryInfo(
            safe_to_retry=False,
            retry_after_seconds=None,
            duplicate_submission=False,
            may_already_be_accepted=False,
            permanent_failure=False,
            cancelled=False,
            provider_error_code=None,
        ),
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        error=None,
    )

    payload = result.model_dump()
    restored = ProviderResult.model_validate(payload)

    assert restored.job_id == result.job_id
    assert restored.asset_id == result.asset_id
    assert restored.status == ProviderExecutionStatus.succeeded


def test_error_taxonomy_and_retry_metadata():
    categories = [
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
    ]

    assert [item.value for item in categories] == [
        "validation_error",
        "authentication_error",
        "rate_limit",
        "transient_provider_failure",
        "permanent_provider_failure",
        "timeout",
        "malformed_provider_response",
        "provider_rejected",
        "duplicate_submission",
        "cancelled",
    ]

    retry = ProviderRetryInfo(
        safe_to_retry=True,
        retry_after_seconds=5.0,
        duplicate_submission=False,
        may_already_be_accepted=True,
        permanent_failure=False,
        cancelled=False,
        provider_error_code="timeout",
    )
    assert retry.safe_to_retry is True
    assert retry.retry_after_seconds == 5.0


def test_fake_provider_submit_and_status():
    provider = FakeProvider()
    request = ProviderRequest(
        provider_name="fake_provider",
        provider_model="fake-model",
        capability=ProviderAssetType.image,
        asset_id="asset_01",
        job_id="ep_001:asset_01:v1",
        episode_id="ep_001",
        production_scene_id="prod_scene_01",
        scene_id="scene_01",
        prompt_or_input="Generate a mock image",
        requested_output=ProviderOutputSpec(format="png", width=256, height=256),
        idempotency_key="fixed-key",
        requested_version=1,
    )

    submitted = provider.submit(request)
    assert submitted.status == ProviderExecutionStatus.submitted
    assert submitted.asset_id == "asset_01"
    assert submitted.job_id == "ep_001:asset_01:v1"

    running = provider.get_status(submitted.job_id, provider_job_id=submitted.provider_job_id)
    assert running.status == ProviderExecutionStatus.accepted


def test_fake_provider_cancel_and_duplicate_submission():
    provider = FakeProvider()
    request = ProviderRequest(
        provider_name="fake_provider",
        provider_model="fake-model",
        capability=ProviderAssetType.tts,
        asset_id="asset_02",
        job_id="ep_001:asset_02:v1",
        episode_id="ep_001",
        production_scene_id="prod_scene_01",
        scene_id="scene_01",
        prompt_or_input="Hello world",
        requested_output=ProviderOutputSpec(format="wav"),
        idempotency_key="fixed-key-2",
        requested_version=1,
    )

    first = provider.submit(request)
    cancelled = provider.cancel(first.job_id, provider_job_id=first.provider_job_id)
    assert cancelled.status == ProviderExecutionStatus.cancelled

    duplicate = provider.submit(request)
    assert duplicate.retry is not None
    assert duplicate.retry.duplicate_submission is True
    assert duplicate.job_id == first.job_id


def test_provider_security_policy():
    policy = ProviderSecurityPolicy()
    assert policy.credentials_in_request is False
    assert policy.credentials_in_result is False
    assert policy.credentials_in_artifact_metadata is False
    assert policy.secrets_must_not_be_logged is True


def test_provider_contract_is_independent_of_gemini():
    requirement = make_asset_requirement()
    job = make_job()
    request = asset_requirement_to_provider_request(
        requirement,
        job,
        provider_name="omniroute_fallback",
        provider_model="auto",
        capability=ProviderAssetType.music,
    )

    assert request.provider_name == "omniroute_fallback"
    assert request.prompt_or_input is not None
    assert "model_config" not in request.model_dump()
    assert "provider_routing" not in request.model_dump()


def test_provider_contract_is_independent_of_orchestrator():
    requirement = make_asset_requirement()
    job = make_job()
    request = asset_requirement_to_provider_request(
        requirement,
        job,
        provider_name="provider_x",
        provider_model="fake-model",
        capability=ProviderAssetType.sfx,
    )

    assert request.episode_id == "ep_001"
    assert request.asset_id == "asset_01"
    assert request.job_id == "ep_001:asset_01:v1"


def test_duplicate_and_synthetic_identity_protection():
    requirement = make_asset_requirement(asset_id="asset_01")
    job = make_job(asset_id="asset_01")

    request = asset_requirement_to_provider_request(
        requirement,
        job,
        provider_name="fake_provider",
        provider_model="fake-model",
        capability=ProviderAssetType.image,
    )

    assert request.asset_id == "asset_01"
    assert request.job_id == "ep_001:asset_01:v1"

    duplicate_requirement = make_asset_requirement(asset_id="asset_01")
    duplicate_job = make_job(asset_id="asset_01")

    second = asset_requirement_to_provider_request(
        duplicate_requirement,
        duplicate_job,
        provider_name="fake_provider",
        provider_model="fake-model",
        capability=ProviderAssetType.image,
    )

    assert second.asset_id == "asset_01"
    assert second.job_id == duplicate_job.job_id
    assert second.idempotency_key == request.idempotency_key


def test_provider_native_id_cannot_replace_canonical_identity():
    request = ProviderRequest(
        provider_name="fake_provider",
        provider_model="fake-model",
        capability=ProviderAssetType.image,
        asset_id="asset_42",
        job_id="ep_001:asset_42:v1",
        episode_id="ep_001",
        production_scene_id="prod_scene_01",
        scene_id="scene_01",
        prompt_or_input="prompt",
        requested_output=ProviderOutputSpec(format="png"),
        idempotency_key="ep_001:asset_42:v1:fake_provider:fake-model:image",
        requested_version=1,
        metadata={"provider_job_id": "provider-native-123", "provider_asset_id": "native-asset-456"},
    )

    assert request.asset_id == "asset_42"
    assert request.job_id == "ep_001:asset_42:v1"
    assert request.metadata["provider_job_id"] == "provider-native-123"
    assert request.metadata["provider_asset_id"] == "native-asset-456"
