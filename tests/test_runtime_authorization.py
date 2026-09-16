"""Focused offline tests for the live-authorization + runtime credential boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from karma.providers import (
    FakeProvider,
    ProviderAssetType,
    ProviderErrorCategory,
    ProviderOutputSpec,
    ProviderRequest,
)
from karma.providers.luma_video import LumaTransportResponse, LumaVideoProvider
from karma.providers.replicate_image import ReplicateImageProvider, ReplicateTransportResponse
from karma.providers.runtime import (
    LIVE_PROVIDER_AUTH_ENV,
    authorize_and_resolve_provider_credential,
    is_live_provider_authorized,
    resolve_provider_credential,
    resolve_runtime_credential,
)

TEST_ONLY_FAKE_SECRET = "TEST_ONLY_FAKE_SECRET"


@dataclass
class RecordingTransport:
    """Fake transport that records calls and never performs network I/O."""

    responses: list[Any] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str],
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        self.calls.append(
            {
                "method": method,
                "path": path,
                "headers": dict(headers),
                "json_body": json_body,
            }
        )
        if not self.responses:
            raise AssertionError("unexpected transport call")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


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


def _video_request(**overrides: Any) -> ProviderRequest:
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


def _clear_live_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(LIVE_PROVIDER_AUTH_ENV, raising=False)
    monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)
    monkeypatch.delenv("LUMA_API_KEY", raising=False)


def test_default_offline_mode_is_unauthorized(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_live_env(monkeypatch)
    assert is_live_provider_authorized() is False


def test_explicit_live_authorization_enables_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_live_env(monkeypatch)
    monkeypatch.setenv(LIVE_PROVIDER_AUTH_ENV, "1")
    assert is_live_provider_authorized() is True
    monkeypatch.setenv(LIVE_PROVIDER_AUTH_ENV, "true")
    assert is_live_provider_authorized() is True
    monkeypatch.setenv(LIVE_PROVIDER_AUTH_ENV, "YES")
    assert is_live_provider_authorized() is True


@pytest.mark.parametrize("value", ["0", "false", "no", "on", "enabled", "authorize", "TRUE!"])
def test_invalid_authorization_values_remain_unauthorized(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    _clear_live_env(monkeypatch)
    monkeypatch.setenv(LIVE_PROVIDER_AUTH_ENV, value)
    assert is_live_provider_authorized() is False


def test_credential_presence_alone_does_not_authorize(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_live_env(monkeypatch)
    monkeypatch.setenv("REPLICATE_API_TOKEN", TEST_ONLY_FAKE_SECRET)
    monkeypatch.setenv("LUMA_API_KEY", TEST_ONLY_FAKE_SECRET)
    assert is_live_provider_authorized() is False
    status, credential = authorize_and_resolve_provider_credential("replicate")
    assert status == "unauthorized"
    assert credential is None


def test_credentials_resolved_only_after_authorization(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_live_env(monkeypatch)
    monkeypatch.setenv("REPLICATE_API_TOKEN", TEST_ONLY_FAKE_SECRET)

    calls: list[str] = []

    def spy_credential() -> str | None:
        calls.append("resolved")
        return TEST_ONLY_FAKE_SECRET

    transport = RecordingTransport()
    adapter = ReplicateImageProvider(
        transport,
        credential_provider=spy_credential,
        enforce_live_authorization=True,
    )
    result = adapter.submit(_image_request())

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "live_execution_unauthorized"
    assert result.error.category == ProviderErrorCategory.authentication_error
    assert calls == []
    assert transport.calls == []


def test_missing_credentials_do_not_break_offline_fake_provider() -> None:
    provider = FakeProvider()
    request = _image_request(provider_name="fake", provider_model="offline")
    result = provider.submit(request)
    assert result.success is True
    assert result.asset_id == "asset_01"
    assert result.job_id == "ep_001:asset_01:v1"


def test_authorized_live_mode_missing_credentials_fail_controlled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_live_env(monkeypatch)
    monkeypatch.setenv(LIVE_PROVIDER_AUTH_ENV, "1")

    transport = RecordingTransport()
    adapter = ReplicateImageProvider(transport)
    result = adapter.submit(_image_request())

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "missing_runtime_credential"
    assert result.error.category == ProviderErrorCategory.authentication_error
    assert transport.calls == []
    assert TEST_ONLY_FAKE_SECRET not in (result.error.message or "")


def test_credentials_never_in_provider_request_or_result(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_live_env(monkeypatch)
    monkeypatch.setenv(LIVE_PROVIDER_AUTH_ENV, "1")
    monkeypatch.setenv("REPLICATE_API_TOKEN", TEST_ONLY_FAKE_SECRET)

    transport = RecordingTransport(
        responses=[
            ReplicateTransportResponse(
                201,
                {},
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
    result = ReplicateImageProvider(transport).submit(request)

    assert TEST_ONLY_FAKE_SECRET not in request.model_dump_json()
    assert TEST_ONLY_FAKE_SECRET not in result.model_dump_json()
    if result.artifact is not None:
        assert TEST_ONLY_FAKE_SECRET not in str(result.artifact.metadata)
    if result.error is not None:
        assert TEST_ONLY_FAKE_SECRET not in result.error.message
        assert TEST_ONLY_FAKE_SECRET not in str(result.error.provider_detail)


def test_credentials_not_in_exception_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_live_env(monkeypatch)
    monkeypatch.setenv(LIVE_PROVIDER_AUTH_ENV, "1")
    monkeypatch.setenv("LUMA_API_KEY", TEST_ONLY_FAKE_SECRET)

    status, credential = authorize_and_resolve_provider_credential("luma")
    assert status == "ok"
    assert credential == TEST_ONLY_FAKE_SECRET

    transport = RecordingTransport()
    adapter = LumaVideoProvider(transport)
    # Force a controlled auth denial path and ensure secrets never surface.
    monkeypatch.delenv(LIVE_PROVIDER_AUTH_ENV, raising=False)
    result = adapter.submit(_video_request())
    assert result.error is not None
    assert TEST_ONLY_FAKE_SECRET not in result.error.message
    assert TEST_ONLY_FAKE_SECRET not in str(result.model_dump())


def test_fake_transport_usable_without_live_authorization(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_live_env(monkeypatch)
    transport = RecordingTransport(
        responses=[
            ReplicateTransportResponse(
                201,
                {},
                {"id": "prediction-native-001", "status": "starting"},
            )
        ]
    )
    adapter = ReplicateImageProvider(
        transport,
        credential_provider=lambda: TEST_ONLY_FAKE_SECRET,
    )
    result = adapter.submit(_image_request())
    assert result.provider_job_id == "prediction-native-001"
    assert result.asset_id == "asset_01"
    assert result.job_id == "ep_001:asset_01:v1"
    assert len(transport.calls) == 1


def test_default_adapter_cannot_bypass_authorization_with_env_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_live_env(monkeypatch)
    monkeypatch.setenv("REPLICATE_API_TOKEN", TEST_ONLY_FAKE_SECRET)
    monkeypatch.setenv("LUMA_API_KEY", TEST_ONLY_FAKE_SECRET)

    replicate_transport = RecordingTransport()
    luma_transport = RecordingTransport()

    replicate_result = ReplicateImageProvider(replicate_transport).submit(_image_request())
    luma_result = LumaVideoProvider(luma_transport).submit(_video_request())

    assert replicate_result.error is not None
    assert replicate_result.error.code == "live_execution_unauthorized"
    assert luma_result.error is not None
    assert luma_result.error.code == "live_execution_unauthorized"
    assert replicate_transport.calls == []
    assert luma_transport.calls == []


def test_authorized_path_resolves_runtime_credential_before_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_live_env(monkeypatch)
    monkeypatch.setenv(LIVE_PROVIDER_AUTH_ENV, "true")
    monkeypatch.setenv("REPLICATE_API_TOKEN", TEST_ONLY_FAKE_SECRET)

    transport = RecordingTransport(
        responses=[
            ReplicateTransportResponse(
                201,
                {},
                {"id": "prediction-native-001", "status": "starting"},
            )
        ]
    )
    result = ReplicateImageProvider(transport).submit(_image_request())
    assert result.error is None
    assert result.provider_job_id == "prediction-native-001"
    assert len(transport.calls) == 1
    # Credential may be used in transport headers but must not enter canonical objects.
    assert TEST_ONLY_FAKE_SECRET not in result.model_dump_json()


def test_authorization_is_runtime_scoped_not_canonical_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_live_env(monkeypatch)
    request = _image_request(asset_id="asset_99", job_id="ep_001:asset_99:v3", requested_version=3)
    assert "credential" not in ProviderRequest.model_fields
    assert request.asset_id == "asset_99"
    assert request.job_id == "ep_001:asset_99:v3"
    assert request.requested_version == 3

    transport = RecordingTransport()
    result = ReplicateImageProvider(transport).submit(request)
    assert result.asset_id == "asset_99"
    assert result.job_id == "ep_001:asset_99:v3"
    assert result.error is not None
    assert result.error.code == "live_execution_unauthorized"


def test_luma_and_replicate_remain_provider_protocol_compatible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_live_env(monkeypatch)
    replicate = ReplicateImageProvider(
        RecordingTransport(),
        credential_provider=lambda: TEST_ONLY_FAKE_SECRET,
    )
    luma = LumaVideoProvider(
        RecordingTransport(),
        credential_provider=lambda: TEST_ONLY_FAKE_SECRET,
    )
    assert callable(replicate.submit)
    assert callable(replicate.get_status)
    assert callable(replicate.cancel)
    assert callable(luma.submit)
    assert callable(luma.get_status)
    assert callable(luma.cancel)


def test_resolve_runtime_credential_is_call_time_only(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_live_env(monkeypatch)
    assert resolve_runtime_credential("REPLICATE_API_TOKEN") is None
    monkeypatch.setenv("REPLICATE_API_TOKEN", TEST_ONLY_FAKE_SECRET)
    assert resolve_provider_credential("replicate") == TEST_ONLY_FAKE_SECRET
    monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)
    assert resolve_provider_credential("replicate") is None


def test_unauthorized_live_transport_cannot_execute(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_live_env(monkeypatch)
    monkeypatch.setenv(LIVE_PROVIDER_AUTH_ENV, "maybe")
    transport = RecordingTransport(
        responses=[
            ReplicateTransportResponse(201, {}, {"id": "x", "status": "starting"}),
        ]
    )
    result = ReplicateImageProvider(transport).submit(_image_request())
    assert result.error is not None
    assert result.error.code == "live_execution_unauthorized"
    assert transport.calls == []
