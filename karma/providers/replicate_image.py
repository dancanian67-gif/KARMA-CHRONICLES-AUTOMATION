"""Replicate image-generation adapter behind the frozen provider contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Protocol
from urllib.parse import urlparse

from karma.providers.base import ProviderProtocol
from karma.providers.contracts import (
    ProviderArtifactMetadata,
    ProviderErrorInfo,
    ProviderRequest,
    ProviderResult,
    ProviderRetryInfo,
)
from karma.providers.types import ProviderAssetType, ProviderErrorCategory, ProviderExecutionStatus

CredentialProvider = Callable[[], str | None]


@dataclass(frozen=True)
class ReplicateTransportResponse:
    """Sanitized transport result supplied by an injected HTTP boundary."""

    status_code: int
    headers: dict[str, str]
    body: Any


class ReplicateTransport(Protocol):
    """HTTP boundary used by the adapter and replaced by tests."""

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str],
        json_body: dict[str, Any] | None = None,
    ) -> ReplicateTransportResponse:
        """Execute one HTTP request without exposing transport details to the adapter."""


def _runtime_credential() -> str | None:
    """Read the credential at call time so it is never captured at import time."""
    from karma.providers.runtime import resolve_provider_credential

    return resolve_provider_credential("replicate")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ReplicateImageProvider(ProviderProtocol):
    """Contract-only Replicate image adapter with no built-in network client.

    The adapter does not choose a Replicate model. The request supplies the model
    and optional version. Provider-native prediction IDs are correlation metadata;
    Karma canonical IDs remain the source of identity.

    Default construction enforces the live-authorization gate before resolving
    runtime credentials or invoking transport. Injected credential providers are
    treated as the offline/test path unless enforce_live_authorization=True.
    """

    def __init__(
        self,
        transport: ReplicateTransport,
        *,
        credential_provider: CredentialProvider | None = None,
        enforce_live_authorization: bool | None = None,
    ) -> None:
        self._transport = transport
        if credential_provider is None:
            self._credential_provider: CredentialProvider = _runtime_credential
            self._enforce_live_authorization = (
                True if enforce_live_authorization is None else enforce_live_authorization
            )
        else:
            self._credential_provider = credential_provider
            self._enforce_live_authorization = (
                False if enforce_live_authorization is None else enforce_live_authorization
            )
        self._provider_jobs: dict[str, str] = {}
        self._requests_by_job: dict[str, ProviderRequest] = {}
        self._ambiguous_keys: set[str] = set()

    def submit(self, request: ProviderRequest) -> ProviderResult:
        """Submit one image prediction without uncontrolled retry."""
        if request.capability != ProviderAssetType.image:
            return self._error_result(
                request,
                category=ProviderErrorCategory.validation_error,
                code="unsupported_capability",
                message="ReplicateImageProvider accepts image requests only.",
                retryable=False,
                safe_to_retry=False,
            )

        if request.idempotency_key in self._provider_jobs:
            return self.get_status(
                request.job_id,
                provider_job_id=self._provider_jobs[request.idempotency_key],
            )

        if request.idempotency_key in self._ambiguous_keys:
            return self._error_result(
                request,
                category=ProviderErrorCategory.duplicate_submission,
                code="ambiguous_submission_outcome",
                message="The prior submission outcome is unknown; status reconciliation is required before resubmission.",
                retryable=False,
                safe_to_retry=False,
                may_already_be_accepted=True,
            )

        token, auth_error = self._credential_or_error(request)
        if auth_error is not None:
            return auth_error

        body = self._request_body(request)
        try:
            response = self._transport.request(
                "POST",
                "/v1/predictions",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json_body=body,
            )
        except TimeoutError:
            self._ambiguous_keys.add(request.idempotency_key)
            return self._error_result(
                request,
                category=ProviderErrorCategory.timeout,
                code="ambiguous_submission_outcome",
                message="Replicate submission timed out and may have been accepted.",
                retryable=False,
                safe_to_retry=False,
                may_already_be_accepted=True,
            )
        except (ConnectionError, OSError):
            self._ambiguous_keys.add(request.idempotency_key)
            return self._error_result(
                request,
                category=ProviderErrorCategory.transient_provider_failure,
                code="ambiguous_submission_outcome",
                message="Replicate submission could not be confirmed and may have been accepted.",
                retryable=False,
                safe_to_retry=False,
                may_already_be_accepted=True,
            )

        if response.status_code < 200 or response.status_code >= 300:
            return self._http_error_result(request, response, submission=True)

        prediction_id = self._string_value(response.body, "id")
        if prediction_id is None:
            self._ambiguous_keys.add(request.idempotency_key)
            return self._error_result(
                request,
                category=ProviderErrorCategory.malformed_provider_response,
                code="missing_prediction_id",
                message="Replicate submission response did not contain a prediction ID and may have been accepted.",
                retryable=False,
                safe_to_retry=False,
                may_already_be_accepted=True,
            )

        self._provider_jobs[request.idempotency_key] = prediction_id
        self._requests_by_job[request.job_id] = request
        return self._normalize_prediction(request, response.body, prediction_id=prediction_id)

    def get_status(self, job_id: str, *, provider_job_id: str | None = None) -> ProviderResult:
        """Poll one provider-native prediction ID."""
        request = self._request_for_job(job_id)
        if request is None:
            return self._orphan_result(
                job_id,
                provider_job_id,
                category=ProviderErrorCategory.validation_error,
                code="missing_request_context",
                message="No request context is available for this canonical job.",
            )
        if not provider_job_id or not provider_job_id.strip():
            return self._error_result(
                request,
                category=ProviderErrorCategory.validation_error,
                code="missing_provider_job_id",
                message="A Replicate prediction ID is required for status polling.",
                retryable=False,
                safe_to_retry=False,
            )
        if self._provider_jobs.get(request.idempotency_key) != provider_job_id:
            return self._error_result(
                request,
                category=ProviderErrorCategory.validation_error,
                code="provider_job_id_mismatch",
                message="The Replicate prediction ID is not bound to this canonical job.",
                retryable=False,
                safe_to_retry=False,
                provider_job_id=provider_job_id,
            )

        token, auth_error = self._credential_or_error(request, provider_job_id=provider_job_id)
        if auth_error is not None:
            return auth_error

        try:
            response = self._transport.request(
                "GET",
                f"/v1/predictions/{provider_job_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
        except TimeoutError:
            return self._error_result(
                request,
                category=ProviderErrorCategory.timeout,
                code="status_timeout",
                message="Replicate status polling timed out.",
                retryable=True,
                safe_to_retry=True,
                may_already_be_accepted=True,
                provider_job_id=provider_job_id,
            )
        except (ConnectionError, OSError):
            return self._error_result(
                request,
                category=ProviderErrorCategory.transient_provider_failure,
                code="status_transport_failure",
                message="Replicate status polling encountered a temporary transport failure.",
                retryable=True,
                safe_to_retry=True,
                may_already_be_accepted=True,
                provider_job_id=provider_job_id,
            )

        if response.status_code < 200 or response.status_code >= 300:
            return self._http_error_result(request, response, provider_job_id=provider_job_id)
        return self._normalize_prediction(request, response.body, prediction_id=provider_job_id)

    def cancel(self, job_id: str, *, provider_job_id: str | None = None) -> ProviderResult:
        """Cancel one provider-native prediction without changing canonical identity."""
        request = self._request_for_job(job_id)
        if request is None:
            return self._orphan_result(
                job_id,
                provider_job_id,
                category=ProviderErrorCategory.validation_error,
                code="missing_request_context",
                message="No request context is available for this canonical job.",
            )
        if not provider_job_id or not provider_job_id.strip():
            return self._error_result(
                request,
                category=ProviderErrorCategory.validation_error,
                code="missing_provider_job_id",
                message="A Replicate prediction ID is required for cancellation.",
                retryable=False,
                safe_to_retry=False,
            )
        if self._provider_jobs.get(request.idempotency_key) != provider_job_id:
            return self._error_result(
                request,
                category=ProviderErrorCategory.validation_error,
                code="provider_job_id_mismatch",
                message="The Replicate prediction ID is not bound to this canonical job.",
                retryable=False,
                safe_to_retry=False,
                provider_job_id=provider_job_id,
            )

        token, auth_error = self._credential_or_error(request, provider_job_id=provider_job_id)
        if auth_error is not None:
            return auth_error

        try:
            response = self._transport.request(
                "POST",
                f"/v1/predictions/{provider_job_id}/cancel",
                headers={"Authorization": f"Bearer {token}"},
            )
        except TimeoutError:
            return self._error_result(
                request,
                category=ProviderErrorCategory.timeout,
                code="cancel_timeout",
                message="Replicate cancellation could not be confirmed.",
                retryable=False,
                safe_to_retry=False,
                may_already_be_accepted=True,
                provider_job_id=provider_job_id,
            )
        except (ConnectionError, OSError):
            return self._error_result(
                request,
                category=ProviderErrorCategory.transient_provider_failure,
                code="cancel_transport_failure",
                message="Replicate cancellation encountered a temporary transport failure.",
                retryable=False,
                safe_to_retry=False,
                may_already_be_accepted=True,
                provider_job_id=provider_job_id,
            )

        if response.status_code < 200 or response.status_code >= 300:
            return self._http_error_result(request, response, provider_job_id=provider_job_id)
        return self._normalize_prediction(request, response.body, prediction_id=provider_job_id)

    def _request_body(self, request: ProviderRequest) -> dict[str, Any]:
        if isinstance(request.prompt_or_input, dict):
            input_payload = dict(request.prompt_or_input)
        else:
            input_payload: dict[str, Any] = {"prompt": request.prompt_or_input or ""}

        output = request.requested_output
        common_output = {
            "width": output.width,
            "height": output.height,
            "aspect_ratio": output.aspect_ratio,
            "seed": output.seed,
            "output_format": output.format,
        }
        for key, value in common_output.items():
            if value is not None and key not in input_payload:
                input_payload[key] = value

        body: dict[str, Any] = {"input": input_payload}
        if request.provider_model_version:
            body["version"] = request.provider_model_version
        else:
            body["model"] = request.provider_model
        return body

    def _normalize_prediction(
        self,
        request: ProviderRequest,
        body: Any,
        *,
        prediction_id: str,
    ) -> ProviderResult:
        if not isinstance(body, dict):
            return self._error_result(
                request,
                category=ProviderErrorCategory.malformed_provider_response,
                code="prediction_body_not_object",
                message="Replicate prediction response was not an object.",
                retryable=False,
                safe_to_retry=False,
                provider_job_id=prediction_id,
            )

        status = self._string_value(body, "status")
        if status is None:
            return self._error_result(
                request,
                category=ProviderErrorCategory.malformed_provider_response,
                code="missing_prediction_status",
                message="Replicate prediction response did not contain a status.",
                retryable=False,
                safe_to_retry=False,
                provider_job_id=prediction_id,
            )

        status_map = {
            "starting": ProviderExecutionStatus.accepted,
            "processing": ProviderExecutionStatus.running,
            "succeeded": ProviderExecutionStatus.succeeded,
            "failed": ProviderExecutionStatus.failed,
            "canceled": ProviderExecutionStatus.cancelled,
            "cancelled": ProviderExecutionStatus.cancelled,
            "aborted": ProviderExecutionStatus.failed,
        }
        normalized_status = status_map.get(status.lower())
        if normalized_status is None:
            return self._error_result(
                request,
                category=ProviderErrorCategory.malformed_provider_response,
                code="unknown_prediction_status",
                message="Replicate returned an unknown prediction status.",
                retryable=False,
                safe_to_retry=False,
                provider_job_id=prediction_id,
            )

        if normalized_status == ProviderExecutionStatus.succeeded:
            artifact = self._artifact_from_output(body.get("output"), body)
            if artifact is None:
                return self._error_result(
                    request,
                    category=ProviderErrorCategory.malformed_provider_response,
                    code="missing_image_output",
                    message="Replicate reported success without a valid image output URI.",
                    retryable=False,
                    safe_to_retry=False,
                    provider_job_id=prediction_id,
                )
            return self._result(
                request,
                success=True,
                status=normalized_status,
                provider_job_id=prediction_id,
                provider_request_id=self._string_value(body, "id"),
                artifact=artifact,
            )

        if normalized_status == ProviderExecutionStatus.failed:
            category = (
                ProviderErrorCategory.timeout
                if status.lower() == "aborted"
                else ProviderErrorCategory.permanent_provider_failure
            )
            return self._error_result(
                request,
                category=category,
                code="prediction_aborted" if status.lower() == "aborted" else "prediction_failed",
                message="Replicate prediction did not complete successfully.",
                retryable=category == ProviderErrorCategory.timeout,
                safe_to_retry=False,
                may_already_be_accepted=False,
                provider_job_id=prediction_id,
                provider_error_code=self._safe_error_code(body.get("error")),
            )

        if normalized_status == ProviderExecutionStatus.cancelled:
            return self._error_result(
                request,
                category=ProviderErrorCategory.cancelled,
                code="prediction_cancelled",
                message="Replicate prediction was cancelled.",
                retryable=False,
                safe_to_retry=False,
                provider_job_id=prediction_id,
            )

        return self._result(
            request,
            success=False,
            status=normalized_status,
            provider_job_id=prediction_id,
            provider_request_id=self._string_value(body, "id"),
            retry=ProviderRetryInfo(
                safe_to_retry=False,
                may_already_be_accepted=True,
                permanent_failure=False,
                cancelled=False,
            ),
        )

    def _artifact_from_output(self, output: Any, body: dict[str, Any]) -> ProviderArtifactMetadata | None:
        uri: str | None = None
        output_count = 1
        if isinstance(output, str):
            uri = output
        elif isinstance(output, list):
            output_count = len(output)
            if output and isinstance(output[0], str):
                uri = output[0]
        elif isinstance(output, dict):
            possible_uri = output.get("url") or output.get("uri")
            if isinstance(possible_uri, str):
                uri = possible_uri

        if uri is None or urlparse(uri).scheme not in {"http", "https"}:
            return None

        explicit_mime = body.get("mime_type")
        if (
            not isinstance(explicit_mime, str)
            or not explicit_mime.strip().lower().startswith("image/")
            or "*" in explicit_mime
        ):
            return None
        mime_type = explicit_mime.strip()
        metadata: dict[str, Any] = {
            "provider": "replicate",
            "prediction_status": "succeeded",
            "temporary_url": True,
            "url_durability": "unknown",
            "output_count": output_count,
        }
        return ProviderArtifactMetadata(
            uri=uri,
            mime_type=mime_type,
            sha256=self._safe_string(body.get("sha256")),
            size_bytes=self._safe_nonnegative_int(body.get("size_bytes")),
            width=self._safe_positive_int(body.get("width")),
            height=self._safe_positive_int(body.get("height")),
            metadata=metadata,
        )

    def _http_error_result(
        self,
        request: ProviderRequest,
        response: ReplicateTransportResponse,
        *,
        submission: bool = False,
        provider_job_id: str | None = None,
    ) -> ProviderResult:
        status_code = response.status_code
        retry_after = self._retry_after(response.headers)
        provider_code = self._safe_error_code(response.body.get("error") if isinstance(response.body, dict) else None)
        if status_code in {401, 403}:
            category = ProviderErrorCategory.authentication_error
            retryable = False
            safe_to_retry = False
            code = "authentication_failure"
            message = "Replicate authentication failed."
        elif status_code == 429:
            category = ProviderErrorCategory.rate_limit
            retryable = True
            safe_to_retry = True
            code = "rate_limited"
            message = "Replicate rate limit was reached."
        elif status_code in {408, 504}:
            category = ProviderErrorCategory.timeout
            retryable = True
            safe_to_retry = not submission
            code = "submission_timeout" if submission else "provider_timeout"
            message = "Replicate did not respond before the request deadline."
        elif 500 <= status_code < 600:
            category = ProviderErrorCategory.transient_provider_failure
            retryable = True
            safe_to_retry = not submission
            code = "provider_5xx"
            message = "Replicate returned a temporary server failure."
        elif 400 <= status_code < 500:
            category = ProviderErrorCategory.validation_error
            retryable = False
            safe_to_retry = False
            code = "provider_request_rejected"
            message = "Replicate rejected the image request."
        else:
            category = ProviderErrorCategory.malformed_provider_response
            retryable = False
            safe_to_retry = False
            code = "unexpected_http_status"
            message = "Replicate returned an unexpected HTTP status."

        may_be_accepted = submission and category in {
            ProviderErrorCategory.timeout,
            ProviderErrorCategory.transient_provider_failure,
        }
        if may_be_accepted:
            self._ambiguous_keys.add(request.idempotency_key)

        return self._error_result(
            request,
            category=category,
            code=code,
            message=message,
            retryable=retryable,
            safe_to_retry=safe_to_retry,
            retry_after_seconds=retry_after,
            may_already_be_accepted=may_be_accepted,
            provider_job_id=provider_job_id,
            provider_error_code=provider_code,
        )

    def _request_for_job(self, job_id: str) -> ProviderRequest | None:
        return self._requests_by_job.get(job_id)

    def _credential_or_error(
        self,
        request: ProviderRequest,
        *,
        provider_job_id: str | None = None,
    ) -> tuple[str | None, ProviderResult | None]:
        """Enforce live authorization before resolving a runtime credential."""
        if self._enforce_live_authorization:
            from karma.providers.runtime import is_live_provider_authorized

            if not is_live_provider_authorized():
                return None, self._error_result(
                    request,
                    category=ProviderErrorCategory.authentication_error,
                    code="live_execution_unauthorized",
                    message="Live provider execution is not authorized.",
                    retryable=False,
                    safe_to_retry=False,
                    provider_job_id=provider_job_id,
                )

        token = self._credential_provider()
        if not token:
            return None, self._error_result(
                request,
                category=ProviderErrorCategory.authentication_error,
                code="missing_runtime_credential",
                message="Replicate authentication is not configured at runtime.",
                retryable=False,
                safe_to_retry=False,
                provider_job_id=provider_job_id,
            )
        return token, None

    def _result(
        self,
        request: ProviderRequest,
        *,
        success: bool,
        status: ProviderExecutionStatus,
        provider_job_id: str | None = None,
        provider_request_id: str | None = None,
        artifact: ProviderArtifactMetadata | None = None,
        retry: ProviderRetryInfo | None = None,
    ) -> ProviderResult:
        return ProviderResult(
            success=success,
            provider_name=request.provider_name,
            provider_model=request.provider_model,
            provider_model_version=request.provider_model_version,
            provider_job_id=provider_job_id,
            provider_request_id=provider_request_id,
            job_id=request.job_id,
            asset_id=request.asset_id,
            episode_id=request.episode_id,
            capability=request.capability,
            status=status,
            artifact=artifact,
            retry=retry,
            started_at=_utc_now(),
            completed_at=_utc_now() if status in {
                ProviderExecutionStatus.succeeded,
                ProviderExecutionStatus.failed,
                ProviderExecutionStatus.cancelled,
            } else None,
            elapsed_ms=None,
            error=None,
        )

    def _error_result(
        self,
        request: ProviderRequest,
        *,
        category: ProviderErrorCategory,
        code: str,
        message: str,
        retryable: bool,
        safe_to_retry: bool,
        retry_after_seconds: float | None = None,
        may_already_be_accepted: bool = False,
        provider_job_id: str | None = None,
        provider_error_code: str | None = None,
    ) -> ProviderResult:
        return ProviderResult(
            success=False,
            provider_name=request.provider_name,
            provider_model=request.provider_model,
            provider_model_version=request.provider_model_version,
            provider_job_id=provider_job_id,
            provider_request_id=provider_job_id,
            job_id=request.job_id,
            asset_id=request.asset_id,
            episode_id=request.episode_id,
            capability=request.capability,
            status=ProviderExecutionStatus.failed if category != ProviderErrorCategory.cancelled else ProviderExecutionStatus.cancelled,
            retry=ProviderRetryInfo(
                safe_to_retry=safe_to_retry,
                retry_after_seconds=retry_after_seconds,
                duplicate_submission=category == ProviderErrorCategory.duplicate_submission,
                may_already_be_accepted=may_already_be_accepted,
                permanent_failure=category in {
                    ProviderErrorCategory.validation_error,
                    ProviderErrorCategory.authentication_error,
                    ProviderErrorCategory.permanent_provider_failure,
                    ProviderErrorCategory.malformed_provider_response,
                    ProviderErrorCategory.provider_rejected,
                },
                cancelled=category == ProviderErrorCategory.cancelled,
                provider_error_code=provider_error_code,
            ),
            started_at=_utc_now(),
            completed_at=_utc_now(),
            elapsed_ms=None,
            error=ProviderErrorInfo(
                code=code,
                category=category,
                message=message,
                retryable=retryable,
                safe_to_retry=safe_to_retry,
                retry_after_seconds=retry_after_seconds,
                duplicate_submission=category == ProviderErrorCategory.duplicate_submission,
                may_already_be_accepted=may_already_be_accepted,
                provider_error_code=provider_error_code,
                provider_detail={},
            ),
        )

    def _orphan_result(
        self,
        job_id: str,
        provider_job_id: str | None,
        *,
        category: ProviderErrorCategory,
        code: str,
        message: str,
    ) -> ProviderResult:
        return ProviderResult(
            success=False,
            provider_name="replicate",
            provider_model="unknown",
            provider_job_id=provider_job_id,
            provider_request_id=provider_job_id,
            job_id=job_id,
            asset_id="unknown",
            episode_id="unknown",
            capability=ProviderAssetType.image,
            status=ProviderExecutionStatus.failed,
            retry=ProviderRetryInfo(safe_to_retry=False, permanent_failure=True),
            started_at=_utc_now(),
            completed_at=_utc_now(),
            error=ProviderErrorInfo(
                code=code,
                category=category,
                message=message,
                retryable=False,
                safe_to_retry=False,
                provider_detail={},
            ),
        )

    @staticmethod
    def _string_value(body: Any, key: str) -> str | None:
        if isinstance(body, dict) and isinstance(body.get(key), str) and body[key].strip():
            return body[key]
        return None

    @staticmethod
    def _safe_string(value: Any) -> str | None:
        return value if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _safe_error_code(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        candidate = value.strip()
        if candidate and len(candidate) <= 128 and all(char.isalnum() or char in "._-" for char in candidate):
            return candidate
        return None

    @staticmethod
    def _safe_positive_int(value: Any) -> int | None:
        return value if isinstance(value, int) and value > 0 else None

    @staticmethod
    def _safe_nonnegative_int(value: Any) -> int | None:
        return value if isinstance(value, int) and value >= 0 else None

    @staticmethod
    def _retry_after(headers: dict[str, str]) -> float | None:
        raw_value = next((value for key, value in headers.items() if key.lower() == "retry-after"), None)
        if raw_value is None:
            return None
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            return None
        return value if value >= 0 else None


__all__ = [
    "ReplicateImageProvider",
    "ReplicateTransport",
    "ReplicateTransportResponse",
]
