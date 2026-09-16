"""Offline tests for the Replicate real HTTP transport (mocked network only)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from karma.providers.replicate_image import ReplicateImageProvider, ReplicateTransportResponse
from karma.providers.replicate_transport import ReplicateHttpTransport
from karma.providers.runtime import LIVE_PROVIDER_AUTH_ENV
from karma.providers import (
    ProviderAssetType,
    ProviderErrorCategory,
    ProviderOutputSpec,
    ProviderRequest,
)

TEST_ONLY_FAKE_SECRET = "TEST_ONLY_FAKE_SECRET"


class FakeHttpResponse:
    def __init__(
        self,
        status_code: int,
        body: Any,
        *,
        headers: dict[str, str] | None = None,
        text: str | None = None,
        json_error: bool = False,
    ) -> None:
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}
        self.text = text if text is not None else ""
        self._json_error = json_error

    def json(self) -> Any:
        if self._json_error:
            raise ValueError("malformed json")
        return self._body


def _clear_live_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(LIVE_PROVIDER_AUTH_ENV, raising=False)
    monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)


def _authorize(monkeypatch: pytest.MonkeyPatch, *, token: str | None = TEST_ONLY_FAKE_SECRET) -> None:
    monkeypatch.setenv(LIVE_PROVIDER_AUTH_ENV, "1")
    if token is None:
        monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)
    else:
        monkeypatch.setenv("REPLICATE_API_TOKEN", token)


def _recording_http(responses: list[Any]) -> tuple[MagicMock, list[dict[str, Any]]]:
    calls: list[dict[str, Any]] = []

    def _request(method: str, url: str, *, headers: dict[str, str], json: Any, timeout: float) -> Any:
        calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "json": json,
                "timeout": timeout,
            }
        )
        item = responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    return MagicMock(side_effect=_request), calls


def _image_request(**overrides: Any) -> ProviderRequest:
    payload: dict[str, Any] = {
        "provider_name": "replicate",
        "provider_model": "configured-image-model",
        "provider_model_version": "configured-version",
        "capability": ProviderAssetType.image,
        "asset_id": "asset_01",
        "job_id": "ep_001:asset_01:v1",
        "episode_id": "ep_001",
        "production_scene_id": "prod_scene_01",
        "scene_id": "scene_01",
        "prompt_or_input": "A cinematic rooftop at dusk",
        "requested_output": ProviderOutputSpec(width=1280, height=720, format="png", seed=17),
        "idempotency_key": "ep_001:asset_01:v1:replicate:configured-image-model:image",
        "requested_version": 1,
    }
    payload.update(overrides)
    return ProviderRequest(**payload)


def test_create_prediction_uses_post_v1_predictions(monkeypatch: pytest.MonkeyPatch) -> None:
    _authorize(monkeypatch)
    http, calls = _recording_http(
        [FakeHttpResponse(201, {"id": "prediction-native-001", "status": "starting"})]
    )
    transport = ReplicateHttpTransport(http_request=http)

    response = transport.create_prediction({"version": "configured-version", "input": {"prompt": "x"}})

    assert response.status_code == 201
    assert calls[0]["method"] == "POST"
    assert calls[0]["url"] == "https://api.replicate.com/v1/predictions"
    assert calls[0]["json"]["version"] == "configured-version"


def test_get_prediction_uses_get_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _authorize(monkeypatch)
    http, calls = _recording_http(
        [FakeHttpResponse(200, {"id": "prediction-native-001", "status": "processing"})]
    )
    transport = ReplicateHttpTransport(http_request=http)

    response = transport.get_prediction("prediction-native-001")

    assert response.status_code == 200
    assert calls[0]["method"] == "GET"
    assert calls[0]["url"] == "https://api.replicate.com/v1/predictions/prediction-native-001"


def test_cancel_prediction_uses_post_cancel_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _authorize(monkeypatch)
    http, calls = _recording_http(
        [FakeHttpResponse(200, {"id": "prediction-native-001", "status": "canceled"})]
    )
    transport = ReplicateHttpTransport(http_request=http)

    response = transport.cancel_prediction("prediction-native-001")

    assert response.status_code == 200
    assert calls[0]["method"] == "POST"
    assert calls[0]["url"] == "https://api.replicate.com/v1/predictions/prediction-native-001/cancel"


def test_authorization_header_uses_runtime_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    _authorize(monkeypatch, token=TEST_ONLY_FAKE_SECRET)
    http, calls = _recording_http(
        [FakeHttpResponse(201, {"id": "prediction-native-001", "status": "starting"})]
    )
    transport = ReplicateHttpTransport(http_request=http)

    transport.create_prediction({"version": "v", "input": {}})

    assert calls[0]["headers"]["Authorization"] == f"Bearer {TEST_ONLY_FAKE_SECRET}"
    assert calls[0]["headers"]["Content-Type"] == "application/json"


def test_fake_credential_not_in_transport_response_body(monkeypatch: pytest.MonkeyPatch) -> None:
    _authorize(monkeypatch)
    http, _calls = _recording_http(
        [FakeHttpResponse(201, {"id": "prediction-native-001", "status": "starting"})]
    )
    transport = ReplicateHttpTransport(http_request=http)

    response = transport.create_prediction({"version": "v", "input": {}})

    assert TEST_ONLY_FAKE_SECRET not in str(response.body)
    assert TEST_ONLY_FAKE_SECRET not in str(response.headers)


def test_live_authorization_absent_denies_before_network(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_live_env(monkeypatch)
    monkeypatch.setenv("REPLICATE_API_TOKEN", TEST_ONLY_FAKE_SECRET)
    http, calls = _recording_http(
        [FakeHttpResponse(201, {"id": "prediction-native-001", "status": "starting"})]
    )
    transport = ReplicateHttpTransport(http_request=http)

    response = transport.create_prediction({"version": "v", "input": {}})

    assert response.status_code == 403
    assert response.body == {"error": "live_execution_unauthorized"}
    assert calls == []
    assert http.call_count == 0


def test_credential_resolution_only_after_authorization(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_live_env(monkeypatch)
    resolved: list[str] = []

    def tracking_authorize_and_resolve(provider_name: str, *, environ=None):
        resolved.append(provider_name)
        return "ok", TEST_ONLY_FAKE_SECRET

    monkeypatch.setattr(
        "karma.providers.replicate_transport.authorize_and_resolve_provider_credential",
        tracking_authorize_and_resolve,
    )
    http, calls = _recording_http([])
    transport = ReplicateHttpTransport(http_request=http)

    response = transport.request("POST", "/v1/predictions", headers={}, json_body={})

    assert response.status_code == 403
    assert resolved == []
    assert calls == []


def test_missing_credential_after_auth_fails_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    _authorize(monkeypatch, token=None)
    http, calls = _recording_http([])
    transport = ReplicateHttpTransport(http_request=http)

    response = transport.create_prediction({"version": "v", "input": {}})

    assert response.status_code == 401
    assert response.body == {"error": "missing_runtime_credential"}
    assert calls == []


def test_adapter_maps_401_to_authentication_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _authorize(monkeypatch)
    http, _calls = _recording_http([FakeHttpResponse(401, {"error": "unauthorized"})])
    adapter = ReplicateImageProvider(ReplicateHttpTransport(http_request=http))
    result = adapter.submit(_image_request())

    assert result.error is not None
    assert result.error.category == ProviderErrorCategory.authentication_error
    assert TEST_ONLY_FAKE_SECRET not in result.model_dump_json()
    assert result.asset_id == "asset_01"
    assert result.job_id == "ep_001:asset_01:v1"


def test_adapter_maps_403_to_authentication_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _authorize(monkeypatch)
    http, _calls = _recording_http([FakeHttpResponse(403, {"error": "forbidden"})])
    adapter = ReplicateImageProvider(ReplicateHttpTransport(http_request=http))
    result = adapter.submit(_image_request())

    assert result.error is not None
    assert result.error.category == ProviderErrorCategory.authentication_error


def test_adapter_maps_429_to_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    _authorize(monkeypatch)
    http, _calls = _recording_http(
        [FakeHttpResponse(429, {"error": "rate_limited"}, headers={"Retry-After": "7"})]
    )
    adapter = ReplicateImageProvider(ReplicateHttpTransport(http_request=http))
    result = adapter.submit(_image_request())

    assert result.error is not None
    assert result.error.category == ProviderErrorCategory.rate_limit
    assert result.error.retry_after_seconds == 7.0


def test_adapter_maps_5xx_to_transient_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _authorize(monkeypatch)
    http, _calls = _recording_http([FakeHttpResponse(503, {"error": "unavailable"})])
    adapter = ReplicateImageProvider(ReplicateHttpTransport(http_request=http))
    result = adapter.submit(_image_request())

    assert result.error is not None
    assert result.error.category == ProviderErrorCategory.transient_provider_failure
    assert result.retry is not None
    assert result.retry.may_already_be_accepted is True


def test_connection_failure_preserves_ambiguous_submission(monkeypatch: pytest.MonkeyPatch) -> None:
    _authorize(monkeypatch)

    class _RequestsConnectionError(ConnectionError):
        pass

    _RequestsConnectionError.__name__ = "ConnectionError"
    _RequestsConnectionError.__module__ = "requests.exceptions"

    http, _calls = _recording_http([_RequestsConnectionError("boom")])
    adapter = ReplicateImageProvider(ReplicateHttpTransport(http_request=http))
    request = _image_request()
    result = adapter.submit(request)

    assert result.error is not None
    assert result.error.category == ProviderErrorCategory.transient_provider_failure
    assert result.error.code == "ambiguous_submission_outcome"
    assert result.error.may_already_be_accepted is True
    # No blind resubmit / identity rewrite.
    assert result.job_id == request.job_id
    assert result.asset_id == request.asset_id


def test_timeout_preserves_ambiguous_submission(monkeypatch: pytest.MonkeyPatch) -> None:
    _authorize(monkeypatch)

    class _RequestsTimeout(Exception):
        pass

    _RequestsTimeout.__name__ = "Timeout"
    _RequestsTimeout.__module__ = "requests.exceptions"

    http, _calls = _recording_http([_RequestsTimeout("slow")])
    adapter = ReplicateImageProvider(ReplicateHttpTransport(http_request=http))
    request = _image_request()
    result = adapter.submit(request)

    assert result.error is not None
    assert result.error.category == ProviderErrorCategory.timeout
    assert result.error.code == "ambiguous_submission_outcome"
    assert result.error.safe_to_retry is False
    assert result.error.may_already_be_accepted is True
    assert result.job_id == request.job_id


def test_malformed_json_is_rejected_safely(monkeypatch: pytest.MonkeyPatch) -> None:
    _authorize(monkeypatch)
    http, _calls = _recording_http(
        [FakeHttpResponse(201, None, text="not-json", json_error=True)]
    )
    adapter = ReplicateImageProvider(ReplicateHttpTransport(http_request=http))
    result = adapter.submit(_image_request())

    assert result.success is False
    assert result.error is not None
    assert result.error.category == ProviderErrorCategory.malformed_provider_response
    assert TEST_ONLY_FAKE_SECRET not in result.model_dump_json()


def test_malformed_success_response_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _authorize(monkeypatch)
    http, _calls = _recording_http([FakeHttpResponse(201, {"status": "starting"})])  # missing id
    adapter = ReplicateImageProvider(ReplicateHttpTransport(http_request=http))
    result = adapter.submit(_image_request())

    assert result.error is not None
    assert result.error.code == "missing_prediction_id"
    assert result.error.may_already_be_accepted is True


def test_provider_native_id_is_metadata_only(monkeypatch: pytest.MonkeyPatch) -> None:
    _authorize(monkeypatch)
    http, _calls = _recording_http(
        [
            FakeHttpResponse(
                201,
                {
                    "id": "prediction-native-001",
                    "status": "succeeded",
                    "output": "https://example.invalid/out.png",
                    "mime_type": "image/png",
                },
            )
        ]
    )
    request = _image_request()
    result = ReplicateImageProvider(ReplicateHttpTransport(http_request=http)).submit(request)

    assert result.provider_job_id == "prediction-native-001"
    assert result.asset_id == "asset_01"
    assert result.job_id == "ep_001:asset_01:v1"
    assert result.asset_id != result.provider_job_id
    assert result.job_id != result.provider_job_id


def test_provider_request_is_not_mutated(monkeypatch: pytest.MonkeyPatch) -> None:
    _authorize(monkeypatch)
    http, _calls = _recording_http(
        [FakeHttpResponse(201, {"id": "prediction-native-001", "status": "starting"})]
    )
    request = _image_request()
    before = request.model_dump()
    ReplicateImageProvider(ReplicateHttpTransport(http_request=http)).submit(request)
    assert request.model_dump() == before
    assert "credential" not in ProviderRequest.model_fields


def test_provider_result_has_no_credential_leakage(monkeypatch: pytest.MonkeyPatch) -> None:
    _authorize(monkeypatch)
    http, calls = _recording_http(
        [FakeHttpResponse(201, {"id": "prediction-native-001", "status": "starting"})]
    )
    result = ReplicateImageProvider(ReplicateHttpTransport(http_request=http)).submit(_image_request())

    serialized = result.model_dump_json()
    assert TEST_ONLY_FAKE_SECRET not in serialized
    assert "Bearer" not in serialized
    assert TEST_ONLY_FAKE_SECRET in calls[0]["headers"]["Authorization"]


def test_no_authorization_header_logged(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _authorize(monkeypatch)
    http, _calls = _recording_http(
        [FakeHttpResponse(201, {"id": "prediction-native-001", "status": "starting"})]
    )
    ReplicateHttpTransport(http_request=http).create_prediction({"version": "v", "input": {}})
    captured = capsys.readouterr()
    assert TEST_ONLY_FAKE_SECRET not in captured.out
    assert TEST_ONLY_FAKE_SECRET not in captured.err
    assert "Authorization" not in captured.out
    assert "Bearer" not in captured.out


def test_fake_transport_remains_unaffected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Existing offline FakeTransport path must not require live auth or real HTTP."""
    _clear_live_env(monkeypatch)

    class FakeTransport:
        def __init__(self) -> None:
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
                {"method": method, "path": path, "headers": dict(headers), "json_body": json_body}
            )
            return ReplicateTransportResponse(
                201,
                {},
                {"id": "prediction-native-001", "status": "starting"},
            )

    transport = FakeTransport()
    result = ReplicateImageProvider(
        transport,
        credential_provider=lambda: TEST_ONLY_FAKE_SECRET,
    ).submit(_image_request())

    assert result.provider_job_id == "prediction-native-001"
    assert len(transport.calls) == 1
