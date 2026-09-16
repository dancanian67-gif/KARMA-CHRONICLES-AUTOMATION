from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from karma.providers import ProviderAssetType, ProviderExecutionStatus
from karma.providers.contracts import ProviderOutputSpec, ProviderRequest
from karma.providers.replicate_image import (
    ReplicateImageProvider,
    ReplicateTransportResponse,
)
from karma.providers.types import ProviderErrorCategory


@dataclass
class FakeTransport:
    responses: list[Any]

    def __post_init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str],
        json_body: dict[str, Any] | None = None,
    ) -> ReplicateTransportResponse:
        self.calls.append(
            {
                "method": method,
                "path": path,
                "headers": dict(headers),
                "json_body": json_body,
            }
        )
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def response(status_code: int, body: Any, *, headers: dict[str, str] | None = None) -> ReplicateTransportResponse:
    return ReplicateTransportResponse(status_code, headers or {}, body)


def prediction(
    status: str,
    *,
    prediction_id: str = "prediction-native-001",
    output: Any = "https://cdn.example.test/generated-image.png",
    error: Any = None,
    **extra: Any,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": prediction_id,
        "status": status,
        "output": output,
        "error": error,
        "mime_type": "image/png",
    }
    body.update(extra)
    return body


def make_request() -> ProviderRequest:
    return ProviderRequest(
        provider_name="replicate",
        provider_model="configured-image-model",
        provider_model_version="configured-version",
        capability=ProviderAssetType.image,
        asset_id="asset_01",
        job_id="ep_001:asset_01:v1",
        episode_id="ep_001",
        production_scene_id="prod_scene_01",
        scene_id="scene_01",
        prompt_or_input="A cinematic 16:9 rooftop at dusk",
        requested_output=ProviderOutputSpec(width=1280, height=720, format="png", seed=17),
        idempotency_key="ep_001:asset_01:v1:replicate:configured-image-model:image",
        requested_version=1,
    )


def provider(transport: FakeTransport, *, token: str | None = "runtime-only-test-token") -> ReplicateImageProvider:
    return ReplicateImageProvider(transport, credential_provider=lambda: token)


def test_successful_submission_normalizes_native_prediction_id():
    transport = FakeTransport([response(201, prediction("succeeded"))])
    result = provider(transport).submit(make_request())

    assert result.success is True
    assert result.status == ProviderExecutionStatus.succeeded
    assert result.provider_job_id == "prediction-native-001"
    assert result.asset_id == "asset_01"
    assert result.job_id == "ep_001:asset_01:v1"


def test_accepted_pending_response_maps_starting_to_accepted():
    transport = FakeTransport([response(201, prediction("starting"))])
    result = provider(transport).submit(make_request())

    assert result.status == ProviderExecutionStatus.accepted
    assert result.success is False
    assert result.provider_job_id == "prediction-native-001"


def test_status_polling_maps_processing_to_running():
    transport = FakeTransport([
        response(201, prediction("starting")),
        response(200, prediction("processing")),
    ])
    adapter = provider(transport)
    submitted = adapter.submit(make_request())
    result = adapter.get_status(submitted.job_id, provider_job_id=submitted.provider_job_id)

    assert result.status == ProviderExecutionStatus.running
    assert result.job_id == submitted.job_id
    assert transport.calls[1]["path"] == "/v1/predictions/prediction-native-001"


def test_successful_completion_normalizes_artifact():
    transport = FakeTransport([
        response(201, prediction("starting")),
        response(
            200,
            prediction(
                "succeeded",
                width=1280,
                height=720,
                sha256="abc123",
                size_bytes=2048,
                mime_type="image/png",
            ),
        ),
    ])
    adapter = provider(transport)
    submitted = adapter.submit(make_request())
    result = adapter.get_status(submitted.job_id, provider_job_id=submitted.provider_job_id)

    assert result.status == ProviderExecutionStatus.succeeded
    assert result.artifact is not None
    assert result.artifact.uri == "https://cdn.example.test/generated-image.png"
    assert result.artifact.mime_type == "image/png"
    assert result.artifact.width == 1280
    assert result.artifact.height == 720
    assert result.artifact.sha256 == "abc123"
    assert result.artifact.metadata["temporary_url"] is True


def test_failed_prediction_maps_to_permanent_provider_failure():
    transport = FakeTransport([response(200, prediction("failed", error="content_rejected"))])
    result = provider(transport).submit(make_request())

    assert result.status == ProviderExecutionStatus.failed
    assert result.error is not None
    assert result.error.category == ProviderErrorCategory.permanent_provider_failure
    assert result.error.provider_error_code == "content_rejected"


def test_cancelled_prediction_maps_to_cancelled():
    transport = FakeTransport([
        response(201, prediction("starting")),
        response(200, prediction("canceled")),
    ])
    adapter = provider(transport)
    submitted = adapter.submit(make_request())
    result = adapter.cancel(submitted.job_id, provider_job_id=submitted.provider_job_id)

    assert result.status == ProviderExecutionStatus.cancelled
    assert result.error is not None
    assert result.error.category == ProviderErrorCategory.cancelled
    assert transport.calls[1]["path"].endswith("/cancel")


def test_aborted_prediction_maps_to_timeout():
    transport = FakeTransport([response(200, prediction("aborted"))])
    result = provider(transport).submit(make_request())

    assert result.status == ProviderExecutionStatus.failed
    assert result.error is not None
    assert result.error.category == ProviderErrorCategory.timeout
    assert result.error.code == "prediction_aborted"


def test_malformed_provider_response_is_rejected():
    transport = FakeTransport([response(201, {"id": "prediction-native-001"})])
    result = provider(transport).submit(make_request())

    assert result.error is not None
    assert result.error.category == ProviderErrorCategory.malformed_provider_response
    assert result.error.code == "missing_prediction_status"


def test_missing_prediction_id_marks_submission_ambiguous_and_blocks_resubmission():
    transport = FakeTransport([
        response(201, {"status": "starting", "mime_type": "image/png"}),
    ])
    adapter = provider(transport)
    request = make_request()

    first = adapter.submit(request)
    second = adapter.submit(request)

    assert first.error is not None
    assert first.error.category == ProviderErrorCategory.malformed_provider_response
    assert first.error.may_already_be_accepted is True
    assert second.error is not None
    assert second.error.category == ProviderErrorCategory.duplicate_submission
    assert second.error.may_already_be_accepted is True
    assert len(transport.calls) == 1


def test_authentication_failure_is_normalized_without_exception():
    transport = FakeTransport([])
    result = provider(transport, token=None).submit(make_request())

    assert result.error is not None
    assert result.error.category == ProviderErrorCategory.authentication_error
    assert transport.calls == []


def test_rate_limit_exposes_bounded_retry_guidance():
    transport = FakeTransport([response(429, {"error": "rate_limited"}, headers={"Retry-After": "7"})])
    result = provider(transport).submit(make_request())

    assert result.error is not None
    assert result.error.category == ProviderErrorCategory.rate_limit
    assert result.error.retryable is True
    assert result.error.safe_to_retry is True
    assert result.error.retry_after_seconds == 7


def test_transient_submit_failure_is_ambiguous_and_not_safe_to_retry():
    transport = FakeTransport([response(503, {"error": "temporary"})])
    result = provider(transport).submit(make_request())

    assert result.error is not None
    assert result.error.category == ProviderErrorCategory.transient_provider_failure
    assert result.error.may_already_be_accepted is True
    assert result.error.safe_to_retry is False


def test_permanent_http_failure_is_not_retryable():
    transport = FakeTransport([response(400, {"error": "invalid_input"})])
    result = provider(transport).submit(make_request())

    assert result.error is not None
    assert result.error.category == ProviderErrorCategory.validation_error
    assert result.error.retryable is False
    assert result.error.safe_to_retry is False


def test_ambiguous_timeout_blocks_second_submission():
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
    assert second.error.may_already_be_accepted is True
    assert len(transport.calls) == 1


def test_idempotency_key_is_preserved_without_claiming_provider_idempotency():
    transport = FakeTransport([response(201, prediction("starting"))])
    request = make_request()
    adapter = provider(transport)
    adapter.submit(request)

    assert request.idempotency_key == "ep_001:asset_01:v1:replicate:configured-image-model:image"
    assert "Idempotency-Key" not in transport.calls[0]["headers"]


def test_canonical_asset_id_is_preserved():
    transport = FakeTransport([response(201, prediction("starting"))])
    result = provider(transport).submit(make_request())

    assert result.asset_id == "asset_01"


def test_canonical_job_id_is_preserved():
    transport = FakeTransport([response(201, prediction("starting"))])
    result = provider(transport).submit(make_request())

    assert result.job_id == "ep_001:asset_01:v1"


def test_provider_native_prediction_id_does_not_replace_canonical_ids():
    transport = FakeTransport([response(201, prediction("starting", prediction_id="native-different-id"))])
    result = provider(transport).submit(make_request())

    assert result.provider_job_id == "native-different-id"
    assert result.asset_id == "asset_01"
    assert result.job_id == "ep_001:asset_01:v1"


def test_runtime_secret_is_not_in_request_result_or_metadata():
    secret = "runtime-only-test-token"
    transport = FakeTransport([response(201, prediction("succeeded"))])
    request = make_request()
    result = provider(transport, token=secret).submit(request)

    serialized_request = request.model_dump_json()
    serialized_result = result.model_dump_json()
    assert secret not in serialized_request
    assert secret not in serialized_result
    assert secret not in result.model_dump().get("artifact", {}).get("metadata", {})
    assert secret not in transport.calls[0]["json_body"]


def test_artifact_output_must_be_a_valid_http_image_uri():
    transport = FakeTransport([response(200, prediction("succeeded", output="file:///tmp/local.png"))])
    adapter = provider(transport)
    submitted = adapter.submit(make_request())

    assert submitted.error is not None
    assert submitted.error.category == ProviderErrorCategory.malformed_provider_response
    assert submitted.error.code == "missing_image_output"


def test_request_body_uses_supplied_model_configuration_without_selection_logic():
    transport = FakeTransport([response(201, prediction("starting"))])
    provider(transport).submit(make_request())

    body = transport.calls[0]["json_body"]
    assert body["version"] == "configured-version"
    assert "model" not in body
    assert body["input"]["width"] == 1280
    assert body["input"]["height"] == 720
    assert body["input"]["seed"] == 17


def test_equivalent_requests_are_deterministic():
    first_transport = FakeTransport([response(201, prediction("starting"))])
    second_transport = FakeTransport([response(201, prediction("starting"))])
    first_request = make_request()
    second_request = make_request()

    provider(first_transport).submit(first_request)
    provider(second_transport).submit(second_request)

    assert first_request.idempotency_key == second_request.idempotency_key
    assert first_transport.calls[0]["json_body"] == second_transport.calls[0]["json_body"]


def test_status_polling_transport_failure_is_retryable():
    transport = FakeTransport([
        response(201, prediction("starting")),
        ConnectionError(),
    ])
    adapter = provider(transport)
    submitted = adapter.submit(make_request())
    result = adapter.get_status(submitted.job_id, provider_job_id=submitted.provider_job_id)

    assert result.error is not None
    assert result.error.category == ProviderErrorCategory.transient_provider_failure
    assert result.error.retryable is True
    assert result.error.safe_to_retry is True


def test_status_rejects_provider_id_not_bound_to_canonical_job():
    transport = FakeTransport([response(201, prediction("starting"))])
    adapter = provider(transport)
    submitted = adapter.submit(make_request())

    result = adapter.get_status(submitted.job_id, provider_job_id="different-provider-id")

    assert result.error is not None
    assert result.error.code == "provider_job_id_mismatch"
    assert result.error.category == ProviderErrorCategory.validation_error
    assert len(transport.calls) == 1


def test_cancel_rejects_provider_id_not_bound_to_canonical_job():
    transport = FakeTransport([response(201, prediction("starting"))])
    adapter = provider(transport)
    submitted = adapter.submit(make_request())

    result = adapter.cancel(submitted.job_id, provider_job_id="different-provider-id")

    assert result.error is not None
    assert result.error.code == "provider_job_id_mismatch"
    assert result.error.category == ProviderErrorCategory.validation_error
    assert len(transport.calls) == 1


@pytest.mark.parametrize("mime_type", [None, "text/plain", "application/octet-stream", "image/*"])
def test_successful_artifact_requires_explicit_concrete_image_mime_type(mime_type: str | None):
    body = prediction("succeeded")
    body["mime_type"] = mime_type
    transport = FakeTransport([response(200, body)])

    result = provider(transport).submit(make_request())

    assert result.error is not None
    assert result.error.category == ProviderErrorCategory.malformed_provider_response
    assert result.error.code == "missing_image_output"


@pytest.mark.parametrize("status", ["starting", "processing", "succeeded", "failed", "canceled", "aborted"])
def test_all_documented_replicate_statuses_are_normalized(status: str):
    output = "https://cdn.example.test/generated-image.png" if status == "succeeded" else None
    transport = FakeTransport([response(201, prediction(status, output=output))])
    result = provider(transport).submit(make_request())

    assert result.status in {
        ProviderExecutionStatus.accepted,
        ProviderExecutionStatus.running,
        ProviderExecutionStatus.succeeded,
        ProviderExecutionStatus.failed,
        ProviderExecutionStatus.cancelled,
    }
