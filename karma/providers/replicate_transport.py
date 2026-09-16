"""Real Replicate HTTP transport behind the frozen ReplicateTransport seam.

This module performs network I/O only after Phase Next.2 live authorization and
runtime credential resolution succeed. It does not persist credentials, does not
log authorization headers, and does not download provider artifacts.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from karma.providers.replicate_image import ReplicateTransportResponse
from karma.providers.runtime import (
    authorize_and_resolve_provider_credential,
    is_live_provider_authorized,
)

DEFAULT_REPLICATE_API_BASE_URL = "https://api.replicate.com"
DEFAULT_TIMEOUT_SECONDS = 30.0

HttpRequestFn = Callable[..., Any]


def _default_http_request(
    method: str,
    url: str,
    *,
    headers: Mapping[str, str],
    json: dict[str, Any] | None,
    timeout: float,
) -> Any:
    """Perform one HTTP request using the repository's existing requests dependency."""
    import requests

    return requests.request(
        method,
        url,
        headers=dict(headers),
        json=json,
        timeout=timeout,
    )


class ReplicateHttpTransport:
    """Fail-closed real HTTP transport for ReplicateImageProvider.

    Implements the existing ``ReplicateTransport`` protocol via ``request()``.
    Convenience helpers mirror the adapter's documented operations without
    introducing a second transport abstraction.
    """

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_REPLICATE_API_BASE_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        http_request: HttpRequestFn | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._http_request = http_request or _default_http_request

    def create_prediction(self, json_body: dict[str, Any]) -> ReplicateTransportResponse:
        """POST /v1/predictions"""
        return self.request("POST", "/v1/predictions", headers={}, json_body=json_body)

    def get_prediction(self, prediction_id: str) -> ReplicateTransportResponse:
        """GET /v1/predictions/{prediction_id}"""
        prediction_id = prediction_id.strip()
        return self.request(
            "GET",
            f"/v1/predictions/{prediction_id}",
            headers={},
            json_body=None,
        )

    def cancel_prediction(self, prediction_id: str) -> ReplicateTransportResponse:
        """POST /v1/predictions/{prediction_id}/cancel"""
        prediction_id = prediction_id.strip()
        return self.request(
            "POST",
            f"/v1/predictions/{prediction_id}/cancel",
            headers={},
            json_body=None,
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str],
        json_body: dict[str, Any] | None = None,
    ) -> ReplicateTransportResponse:
        """Execute one Replicate HTTP call after live authorization + credential resolve.

        Caller-supplied Authorization headers are ignored. The transport constructs
        the Bearer header only from a runtime credential resolved after explicit
        live authorization. Credentials are never logged or returned.
        """
        del headers  # never trust/log caller auth material for the real transport

        if not is_live_provider_authorized():
            return ReplicateTransportResponse(
                status_code=403,
                headers={},
                body={"error": "live_execution_unauthorized"},
            )

        status, credential = authorize_and_resolve_provider_credential("replicate")
        if status != "ok" or not credential:
            return ReplicateTransportResponse(
                status_code=401,
                headers={},
                body={"error": "missing_runtime_credential"},
            )

        url = self._join_url(path)
        request_headers = {
            "Authorization": f"Bearer {credential}",
            "Content-Type": "application/json",
        }
        # Drop local reference to the secret as soon as headers are built for the call.
        credential = None

        try:
            response = self._http_request(
                method.upper(),
                url,
                headers=request_headers,
                json=json_body,
                timeout=self._timeout_seconds,
            )
        except TimeoutError:
            raise
        except Exception as exc:
            # Map requests timeout/connection failures into the exceptions the
            # frozen adapter already handles for ambiguity / transient failure.
            name = type(exc).__name__
            module = type(exc).__module__
            message = str(exc).lower()
            if name in {"Timeout", "ReadTimeout", "ConnectTimeout"} or "timeout" in message:
                raise TimeoutError("Replicate HTTP request timed out") from exc
            if name in {"ConnectionError", "ConnectTimeoutError"} or module.startswith("requests"):
                raise ConnectionError("Replicate HTTP transport failure") from exc
            raise

        return self._to_transport_response(response)

    def _join_url(self, path: str) -> str:
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{self._base_url}{path}"

    @staticmethod
    def _to_transport_response(response: Any) -> ReplicateTransportResponse:
        status_code = int(getattr(response, "status_code", 0) or 0)
        raw_headers = getattr(response, "headers", {}) or {}
        headers = {str(key): str(value) for key, value in dict(raw_headers).items()}

        body: Any
        try:
            body = response.json()
        except Exception:
            text = getattr(response, "text", None)
            body = text if isinstance(text, str) else None

        return ReplicateTransportResponse(
            status_code=status_code,
            headers=headers,
            body=body,
        )


__all__ = [
    "DEFAULT_REPLICATE_API_BASE_URL",
    "DEFAULT_TIMEOUT_SECONDS",
    "ReplicateHttpTransport",
]
