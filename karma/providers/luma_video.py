"""Luma Dream Machine video-generation adapter behind the frozen provider contract."""

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
class LumaTransportResponse:
    """Sanitized transport result supplied by an injected HTTP boundary."""

    status_code: int
    headers: dict[str, str]
    body: Any


class LumaTransport(Protocol):
    """HTTP boundary used by the adapter and replaced by tests."""

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str],
        json_body: dict[str, Any] | None = None,
    ) -> LumaTransportResponse:
        """Execute one HTTP request without exposing transport details to the adapter."""


def _runtime_credential() -> str | None:
    """Read the credential at call time so it is never captured at import time."""
    from karma.providers.runtime import resolve_provider_credential

    return resolve_provider_credential("luma")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class LumaVideoProvider(ProviderProtocol):
    """Contract-only Luma video adapter with no built-in network client.

    Default construction enforces the live-authorization gate before resolving
    runtime credentials or invoking transport. Injected credential providers are
    treated as the offline/test path unless enforce_live_authorization=True.
    """

    def __init__(
        self,
        transport: LumaTransport,
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
        """Submit a Luma video generation request without uncontrolled retry."""
        if request.capability != ProviderAssetType.video:
            return self._error_result(
                request,
                category=ProviderErrorCategory.validation_error,
                code="unsupported_capability",
                message="LumaVideoProvider accepts video requests only.",
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
                message="A prior Luma submission outcome is unknown; status reconciliation is required before resubmission.",
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
                "/video/generations",
                headers=self._auth_headers(token),
                json_body=body,
            )
        except TimeoutError:
            self._ambiguous_keys.add(request.idempotency_key)
            return self._error_result(
                request,
                category=ProviderErrorCategory.timeout,
                code="ambiguous_submission_outcome",
                message="Luma submission timed out and may have been accepted.",
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
                message="Luma submission could not be confirmed and may have been accepted.",
                retryable=False,
                safe_to_retry=False,
                may_already_be_accepted=True,
            )

        if response.status_code < 200 or response.status_code >= 300:
            return self._http_error_result(request, response, submission=True)

        generation_id = self._string_value(response.body, "id")
        if generation_id is None:
            self._ambiguous_keys.add(request.idempotency_key)
            return self._error_result(
                request,
                category=ProviderErrorCategory.malformed_provider_response,
                code="missing_generation_id",
                message="Luma submission response did not include a generation ID and may have been accepted.",
                retryable=False,
                safe_to_retry=False,
                may_already_be_accepted=True,
            )

        self._provider_jobs[request.idempotency_key] = generation_id
        self._requests_by_job[request.job_id] = request
        return self._normalize_generation(request, response.body, generation_id=generation_id)

    def get_status(self, job_id: str, *, provider_job_id: str | None = None) -> ProviderResult:
        """Poll one provider-native generation ID."""
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
                message="A Luma generation ID is required for status polling.",
                retryable=False,
                safe_to_retry=False,
            )
        if self._provider_jobs.get(request.idempotency_key) != provider_job_id:
            return self._error_result(
                request,
                category=ProviderErrorCategory.validation_error,
                code="provider_job_id_mismatch",
                message="The Luma generation ID is not bound to this canonical job.",
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
                f"/video/generations/{provider_job_id}",
                headers=self._auth_headers(token),
            )
        except TimeoutError:
            return self._error_result(
                request,
                category=ProviderErrorCategory.timeout,
                code="status_timeout",
                message="Luma status polling timed out.",
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
                message="Luma status polling encountered a temporary transport failure.",
                retryable=True,
                safe_to_retry=True,
                may_already_be_accepted=True,
                provider_job_id=provider_job_id,
            )

        if response.status_code < 200 or response.status_code >= 300:
            return self._http_error_result(request, response, provider_job_id=provider_job_id)
        return self._normalize_generation(request, response.body, generation_id=provider_job_id)

    def cancel(self, job_id: str, *, provider_job_id: str | None = None) -> ProviderResult:
        """Cancel one provider-native generation when the provider contract safely supports it."""
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
                message="A Luma generation ID is required for cancellation.",
                retryable=False,
                safe_to_retry=False,
            )
        if self._provider_jobs.get(request.idempotency_key) != provider_job_id:
            return self._error_result(
                request,
                category=ProviderErrorCategory.validation_error,
                code="provider_job_id_mismatch",
                message="The Luma generation ID is not bound to this canonical job.",
                retryable=False,
                safe_to_retry=False,
                provider_job_id=provider_job_id,
            )

        token, auth_error = self._credential_or_error(request, provider_job_id=provider_job_id)
        if auth_error is not None:
            return auth_error

        try:
            response = self._transport.request(
                "DELETE",
                f"/video/generations/{provider_job_id}",
                headers=self._auth_headers(token),
            )
        except TimeoutError:
            return self._error_result(
                request,
                category=ProviderErrorCategory.timeout,
                code="cancel_timeout",
                message="Luma cancellation could not be confirmed.",
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
                message="Luma cancellation encountered a temporary transport failure.",
                retryable=False,
                safe_to_retry=False,
                may_already_be_accepted=True,
                provider_job_id=provider_job_id,
            )

        status_value = self._string_value(response.body, "status")
        if status_value is not None and status_value.lower() in {"cancelled", "canceled"}:
            return self._error_result(
                request,
                category=ProviderErrorCategory.cancelled,
                code="generation_cancelled",
                message="Luma generation was cancelled.",
                retryable=False,
                safe_to_retry=False,
                provider_job_id=provider_job_id,
            )

        return self._error_result(
            request,
            category=ProviderErrorCategory.cancelled,
            code="unsupported_cancellation_semantics",
            message="Luma cancellation semantics are not documented for this adapter and cannot be treated as a successful cancellation.",
            retryable=False,
            safe_to_retry=False,
            provider_job_id=provider_job_id,
        )

    def _request_body(self, request: ProviderRequest) -> dict[str, Any]:
        if isinstance(request.prompt_or_input, dict):
            payload = dict(request.prompt_or_input)
            prompt = payload.get("prompt")
            if not isinstance(prompt, str) or not prompt.strip():
                prompt = request.prompt_or_input.get("input") if isinstance(request.prompt_or_input, dict) else None
                if isinstance(prompt, str):
                    payload["prompt"] = prompt
        else:
            payload = {"prompt": request.prompt_or_input or ""}

        output = request.requested_output
        if output.aspect_ratio is not None:
            payload["aspect_ratio"] = output.aspect_ratio
        if output.duration_seconds is not None:
            payload["duration"] = output.duration_seconds
        if output.width is not None:
            payload["width"] = output.width
        if output.height is not None:
            payload["height"] = output.height
        if output.format is not None:
            payload["format"] = output.format
        if output.seed is not None:
            payload["seed"] = output.seed
        if output.quality is not None:
            payload["quality"] = output.quality
        if output.output_uri is not None:
            payload["reference_image"] = output.output_uri

        if isinstance(request.prompt_or_input, dict):
            for field in ("reference_image", "keyframe", "image"):
                if field in request.prompt_or_input and field not in payload:
                    payload[field] = request.prompt_or_input[field]

        payload["model"] = request.provider_model
        if request.provider_model_version:
            payload["model_version"] = request.provider_model_version
        if request.asset_id:
            payload["asset_id"] = request.asset_id
        if request.job_id:
            payload["job_id"] = request.job_id
        if request.idempotency_key:
            payload["idempotency_key"] = request.idempotency_key
        return payload

    def _normalize_generation(
        self,
        request: ProviderRequest,
        body: Any,
        *,
        generation_id: str,
    ) -> ProviderResult:
        if not isinstance(body, dict):
            return self._error_result(
                request,
                category=ProviderErrorCategory.malformed_provider_response,
                code="generation_body_not_object",
                message="Luma generation response was not an object.",
                retryable=False,
                safe_to_retry=False,
                provider_job_id=generation_id,
            )

        status = self._string_value(body, "status")
        if status is None:
            return self._error_result(
                request,
                category=ProviderErrorCategory.malformed_provider_response,
                code="missing_generation_status",
                message="Luma generation response did not include a status.",
                retryable=False,
                safe_to_retry=False,
                provider_job_id=generation_id,
            )

        normalized_status = self._normalize_status(status)
        if normalized_status is None:
            return self._error_result(
                request,
                category=ProviderErrorCategory.malformed_provider_response,
                code="unknown_generation_status",
                message="Luma returned an unknown generation status.",
                retryable=False,
                safe_to_retry=False,
                provider_job_id=generation_id,
            )

        if normalized_status == ProviderExecutionStatus.succeeded:
            artifact = self._artifact_from_output(body)
            if artifact is None:
                return self._error_result(
                    request,
                    category=ProviderErrorCategory.malformed_provider_response,
                    code="missing_video_output",
                    message="Luma reported success without a valid video output URI.",
                    retryable=False,
                    safe_to_retry=False,
                    provider_job_id=generation_id,
                )
            return self._result(
                request,
                success=True,
                status=normalized_status,
                provider_job_id=generation_id,
                provider_request_id=self._string_value(body, "id"),
                artifact=artifact,
            )

        if normalized_status == ProviderExecutionStatus.failed:
            category = ProviderErrorCategory.permanent_provider_failure
            if status.lower() in {"aborted", "timed_out"}:
                category = ProviderErrorCategory.timeout
            provider_error_code = self._safe_error_code(body.get("error"))
            message = "Luma generation did not complete successfully."
            return self._error_result(
                request,
                category=category,
                code="generation_failed" if category != ProviderErrorCategory.timeout else "generation_timeout",
                message=message,
                retryable=category == ProviderErrorCategory.timeout,
                safe_to_retry=False,
                provider_job_id=generation_id,
                provider_error_code=provider_error_code,
            )

        if normalized_status == ProviderExecutionStatus.cancelled:
            return self._error_result(
                request,
                category=ProviderErrorCategory.cancelled,
                code="generation_cancelled",
                message="Luma generation was cancelled.",
                retryable=False,
                safe_to_retry=False,
                provider_job_id=generation_id,
            )

        return self._result(
            request,
            success=False,
            status=normalized_status,
            provider_job_id=generation_id,
            provider_request_id=self._string_value(body, "id"),
            retry=ProviderRetryInfo(
                safe_to_retry=False,
                may_already_be_accepted=True,
                permanent_failure=False,
                cancelled=False,
            ),
        )

    def _artifact_from_output(self, body: dict[str, Any]) -> ProviderArtifactMetadata | None:
        output = body.get("output")
        uri: str | None = None
        if isinstance(output, str):
            uri = output
        elif isinstance(output, dict):
            candidate = output.get("url") or output.get("uri")
            if isinstance(candidate, str):
                uri = candidate
        elif isinstance(output, list):
            if output and isinstance(output[0], str):
                uri = output[0]

        if uri is None or urlparse(uri).scheme not in {"http", "https"}:
            return None

        mime_type = self._string_value(body, "mime_type")
        if mime_type is None or not mime_type.lower().startswith("video/") or "*" in mime_type:
            return None

        width = self._safe_positive_int(body.get("width"))
        height = self._safe_positive_int(body.get("height"))
        duration = self._safe_positive_float(body.get("duration"))

        metadata: dict[str, Any] = {
            "provider": "luma",
            "temporary_url": True,
            "url_durability": "unknown",
        }
        return ProviderArtifactMetadata(
            uri=uri,
            mime_type=mime_type,
            sha256=self._safe_string(body.get("sha256")),
            size_bytes=self._safe_nonnegative_int(body.get("size_bytes")),
            duration_seconds=duration,
            width=width,
            height=height,
            metadata=metadata,
        )

    def _http_error_result(
        self,
        request: ProviderRequest,
        response: LumaTransportResponse,
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
            message = "Luma authentication failed."
        elif status_code == 429:
            category = ProviderErrorCategory.rate_limit
            retryable = True
            safe_to_retry = True
            code = "rate_limited"
            message = "Luma rate limit was reached."
        elif status_code in {408, 504}:
            category = ProviderErrorCategory.timeout
            retryable = True
            safe_to_retry = not submission
            code = "submission_timeout" if submission else "provider_timeout"
            message = "Luma did not respond before the request deadline."
        elif 500 <= status_code < 600:
            category = ProviderErrorCategory.transient_provider_failure
            retryable = True
            safe_to_retry = not submission
            code = "provider_5xx"
            message = "Luma returned a temporary server failure."
        elif 400 <= status_code < 500:
            category = ProviderErrorCategory.validation_error
            retryable = False
            safe_to_retry = False
            code = "provider_request_rejected"
            message = "Luma rejected the video request."
        else:
            category = ProviderErrorCategory.malformed_provider_response
            retryable = False
            safe_to_retry = False
            code = "unexpected_http_status"
            message = "Luma returned an unexpected HTTP status."

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
                message="Luma authentication is not configured at runtime.",
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
            completed_at=_utc_now() if status in {ProviderExecutionStatus.succeeded, ProviderExecutionStatus.failed, ProviderExecutionStatus.cancelled} else None,
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
            provider_name="luma",
            provider_model="unknown",
            provider_job_id=provider_job_id,
            provider_request_id=provider_job_id,
            job_id=job_id,
            asset_id="unknown",
            episode_id="unknown",
            capability=ProviderAssetType.video,
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
    def _normalize_status(status: str) -> ProviderExecutionStatus | None:
        status_key = status.strip().lower()
        mapping = {
            "submitted": ProviderExecutionStatus.accepted,
            "queued": ProviderExecutionStatus.accepted,
            "pending": ProviderExecutionStatus.accepted,
            "dreaming": ProviderExecutionStatus.running,
            "starting": ProviderExecutionStatus.running,
            "processing": ProviderExecutionStatus.running,
            "running": ProviderExecutionStatus.running,
            "completed": ProviderExecutionStatus.succeeded,
            "succeeded": ProviderExecutionStatus.succeeded,
            "failed": ProviderExecutionStatus.failed,
            "error": ProviderExecutionStatus.failed,
            "cancelled": ProviderExecutionStatus.cancelled,
            "canceled": ProviderExecutionStatus.cancelled,
            "aborted": ProviderExecutionStatus.failed,
            "timed_out": ProviderExecutionStatus.failed,
        }
        return mapping.get(status_key)

    @staticmethod
    def _auth_headers(token: str) -> dict[str, str]:
        return {"Authorization": "Bearer [redacted]", "Content-Type": "application/json"}

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
    def _safe_positive_float(value: Any) -> float | None:
        return value if isinstance(value, (int, float)) and value > 0 else None

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
    "LumaTransport",
    "LumaTransportResponse",
    "LumaVideoProvider",
]
