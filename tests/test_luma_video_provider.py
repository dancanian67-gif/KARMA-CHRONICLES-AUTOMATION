from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from karma.providers import (
    ProviderAssetType,
    ProviderErrorCategory,
    ProviderExecutionStatus,
    ProviderOutputSpec,
    ProviderRequest,
)
from karma.providers.luma_video import LumaVideoProvider, LumaTransportResponse


@dataclass
class FakeTransport:
    responses: list[Any]
    calls: list[dict[str, Any]] = field(default_factory=list)

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str],
        json_body: dict[str, Any] | None = None,
    ) -> LumaTransportResponse:
        self.calls.append({
            "method": method,
            "path": path,
            "headers": dict(headers),
            "json_body": json_body,
        })
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def response(status_code: int, body: Any, *, headers: dict[str, str] | None = None) -> LumaTransportResponse:
    return LumaTransportResponse(status_code=status_code, headers=headers or {}, body=body)


def generation(
    status: str,
    *,
    generation_id: str = "generation-native-001",
    output: Any = None,
    error: Any = None,
    mime_type: str | None = "video/mp4",
    **extra: Any,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": generation_id,
        "status": status,
        "output": output,
        "error": error,
        "mime_type": mime_type,
    }
    body.update(extra)
    return body


def make_request(**overrides: Any) -> ProviderRequest:
    payload: dict[str, Any] = {
        "provider_name": "luma",
        "provider_model": "dream-machine",
        "provider_model_version": "1.0",
        "capability": ProviderAssetType.video,
        "asset_id": "asset_01",
        "job_id": "ep_001:asset_01:v1",
        "episode_id": "ep_001",
        "production_scene_id": "prod_scene_01",
        "scene_id": "scene_01",
        "prompt_or_input": "A cinematic rooftop reveal at dusk",
        "requested_output": ProviderOutputSpec(
            format="mp4",
            width=1280,
            height=720,
            duration_seconds=6.0,
            aspect_ratio="16:9",
        ),
        "idempotency_key": "ep_001:asset_01:v1:luma:dream-machine:video",
        "requested_version": 1,
    }
    payload.update(overrides)
    return ProviderRequest(**payload)


def provider(transport: FakeTransport, *, token: str | None = "runtime-only-test-token") -> LumaVideoProvider:
    return LumaVideoProvider(transport, credential_provider=lambda: token)


def test_video_capability_is_accepted() -> None:
    transport = FakeTransport([response(201, generation("submitted"))])
    result = provider(transport).submit(make_request())

    assert result.success is False
    assert result.status == ProviderExecutionStatus.accepted
    assert result.provider_job_id == "generation-native-001"


def test_non_video_capability_is_rejected() -> None:
    transport = FakeTransport([])
    result = provider(transport).submit(make_request(capability=ProviderAssetType.image))

    assert result.error is not None
    assert result.error.category == ProviderErrorCategory.validation_error
    assert result.error.code == "unsupported_capability"


def test_image_to_video_request_uses_reference_image_when_provided() -> None:
    transport = FakeTransport([response(201, generation("submitted"))])
    payload = {
        "prompt_or_input": {
            "prompt": "A cityscape transitions into motion",
            "reference_image": "https://example.test/reference.png",
        }
    }
    provider(transport).submit(make_request(**payload))

    body = transport.calls[0]["json_body"]
    assert body["prompt"] == "A cityscape transitions into motion"
    assert body["reference_image"] == "https://example.test/reference.png"


def test_prompt_and_aspect_ratio_are_mapped() -> None:
    transport = FakeTransport([response(201, generation("submitted"))])
    provider(transport).submit(make_request())

    body = transport.calls[0]["json_body"]
    assert body["prompt"] == "A cinematic rooftop reveal at dusk"
    assert body["aspect_ratio"] == "16:9"
    assert body["duration"] == 6.0


def test_provider_model_version_is_preserved() -> None:
    transport = FakeTransport([response(201, generation("submitted"))])
    result = provider(transport).submit(make_request())

    assert result.provider_model == "dream-machine"
    assert result.provider_model_version == "1.0"


def test_canonical_asset_and_job_identity_are_preserved() -> None:
    transport = FakeTransport([response(201, generation("submitted"))])
    result = provider(transport).submit(make_request())

    assert result.asset_id == "asset_01"
    assert result.job_id == "ep_001:asset_01:v1"
    assert result.episode_id == "ep_001"
    assert result.provider_job_id == "generation-native-001"


def test_luma_generation_id_stays_metadata_only() -> None:
    transport = FakeTransport([response(201, generation("dreaming"))])
    result = provider(transport).submit(make_request())

    assert result.provider_job_id == "generation-native-001"
    assert result.job_id == "ep_001:asset_01:v1"


def test_dreaming_maps_to_running() -> None:
    transport = FakeTransport([response(201, generation("dreaming"))])
    result = provider(transport).submit(make_request())

    assert result.status == ProviderExecutionStatus.running
    assert result.success is False


def test_completed_state_maps_to_succeeded() -> None:
    transport = FakeTransport([response(200, generation("completed", output="https://cdn.example.test/output.mp4", mime_type="video/mp4"))])
    result = provider(transport).submit(make_request())

    assert result.status == ProviderExecutionStatus.succeeded
    assert result.artifact is not None
    assert result.artifact.uri == "https://cdn.example.test/output.mp4"
    assert result.artifact.mime_type == "video/mp4"


def test_failed_status_maps_to_failed() -> None:
    transport = FakeTransport([response(200, generation("failed", error="content_rejected"))])
    result = provider(transport).submit(make_request())

    assert result.status == ProviderExecutionStatus.failed
    assert result.error is not None
    assert result.error.category == ProviderErrorCategory.permanent_provider_failure


def test_unknown_status_is_rejected() -> None:
    transport = FakeTransport([response(200, generation("mystery-state"))])
    result = provider(transport).submit(make_request())

    assert result.error is not None
    assert result.error.category == ProviderErrorCategory.malformed_provider_response
    assert result.error.code == "unknown_generation_status"


def test_missing_generation_id_is_ambiguous() -> None:
    transport = FakeTransport([response(201, {"status": "submitted", "mime_type": "video/mp4"})])
    adapter = provider(transport)
    request = make_request()

    first = adapter.submit(request)
    second = adapter.submit(request)

    assert first.error is not None
    assert first.error.category == ProviderErrorCategory.malformed_provider_response
    assert second.error is not None
    assert second.error.category == ProviderErrorCategory.duplicate_submission


def test_timeout_makes_submission_ambiguous() -> None:
    transport = FakeTransport([TimeoutError()])
    adapter = provider(transport)
    request = make_request()

    first = adapter.submit(request)
    second = adapter.submit(request)

    assert first.error is not None
    assert first.error.category == ProviderErrorCategory.timeout
    assert first.error.may_already_be_accepted is True
    assert second.error is not None
    assert second.error.category == ProviderErrorCategory.duplicate_submission


def test_provider_job_id_mismatch_is_rejected() -> None:
    transport = FakeTransport([response(201, generation("submitted"))])
    adapter = provider(transport)
    submitted = adapter.submit(make_request())

    result = adapter.get_status(submitted.job_id, provider_job_id="different-id")

    assert result.error is not None
    assert result.error.code == "provider_job_id_mismatch"
    assert result.error.category == ProviderErrorCategory.validation_error


def test_cancel_is_not_falsely_reported_as_success() -> None:
    transport = FakeTransport([
        response(201, generation("submitted")),
        response(200, {"status": "failed", "error": "unsupported_cancellation"}),
    ])
    adapter = provider(transport)
    submitted = adapter.submit(make_request())

    result = adapter.cancel(submitted.job_id, provider_job_id=submitted.provider_job_id)

    assert result.status == ProviderExecutionStatus.cancelled
    assert result.error is not None
    assert result.error.category == ProviderErrorCategory.cancelled
    assert result.error.code == "unsupported_cancellation_semantics"
    assert result.success is False


def test_valid_video_artifact_uri_is_normalized() -> None:
    transport = FakeTransport([response(200, generation("completed", output="https://cdn.example.test/video.mp4", mime_type="video/mp4"))])
    result = provider(transport).submit(make_request())

    assert result.artifact is not None
    assert result.artifact.uri == "https://cdn.example.test/video.mp4"
    assert result.artifact.mime_type == "video/mp4"


def test_non_video_mime_type_is_rejected() -> None:
    transport = FakeTransport([response(200, generation("completed", output="https://cdn.example.test/video.mp4", mime_type="image/png"))])
    result = provider(transport).submit(make_request())

    assert result.error is not None
    assert result.error.category == ProviderErrorCategory.malformed_provider_response


def test_malformed_uri_is_rejected() -> None:
    transport = FakeTransport([response(200, generation("completed", output="file:///tmp/video.mp4", mime_type="video/mp4"))])
    result = provider(transport).submit(make_request())

    assert result.error is not None
    assert result.error.category == ProviderErrorCategory.malformed_provider_response


def test_output_metadata_is_normalized() -> None:
    transport = FakeTransport([
        response(
            200,
            generation(
                "completed",
                output="https://cdn.example.test/video.mp4",
                mime_type="video/mp4",
                width=1280,
                height=720,
                duration=6.0,
            ),
        )
    ])
    result = provider(transport).submit(make_request())

    assert result.artifact is not None
    assert result.artifact.width == 1280
    assert result.artifact.height == 720
    assert result.artifact.duration_seconds == 6.0


def test_runtime_secret_is_not_leaked() -> None:
    secret = "runtime-only-test-token"
    transport = FakeTransport([response(201, generation("submitted"))])
    result = provider(transport, token=secret).submit(make_request())

    payload = result.model_dump_json()
    assert secret not in payload
    assert secret not in str(transport.calls)


def test_provider_transport_uses_injected_fake_only() -> None:
    transport = FakeTransport([response(201, generation("submitted"))])
    result = provider(transport).submit(make_request())

    assert result.provider_name == "luma"
    assert len(transport.calls) == 1
    assert transport.calls[0]["method"] == "POST"


def test_rate_limit_maps_to_contract_category() -> None:
    transport = FakeTransport([response(429, {"error": "rate_limited"}, headers={"Retry-After": "7"})])
    result = provider(transport).submit(make_request())

    assert result.error is not None
    assert result.error.category == ProviderErrorCategory.rate_limit
    assert result.error.retryable is True
    assert result.error.retry_after_seconds == 7


def test_status_transport_failure_is_retryable() -> None:
    transport = FakeTransport([
        response(201, generation("submitted")),
        ConnectionError(),
    ])
    adapter = provider(transport)
    submitted = adapter.submit(make_request())
    result = adapter.get_status(submitted.job_id, provider_job_id=submitted.provider_job_id)

    assert result.error is not None
    assert result.error.category == ProviderErrorCategory.transient_provider_failure
    assert result.error.retryable is True


def test_permanent_failure_is_not_retryable() -> None:
    transport = FakeTransport([response(400, {"error": "invalid"})])
    result = provider(transport).submit(make_request())

    assert result.error is not None
    assert result.error.category == ProviderErrorCategory.validation_error
    assert result.error.retryable is False
