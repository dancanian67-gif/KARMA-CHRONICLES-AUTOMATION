"""Provider protocol definitions."""

from __future__ import annotations

from typing import Protocol

from karma.providers.contracts import ProviderRequest, ProviderResult


class ProviderProtocol(Protocol):
    """Minimal contract for provider-backed asset execution.

    The provider lifecycle is provider-facing and intentionally separate from the
    application-level AssetExecutionJob lifecycle. Provider status should never be
    used as a second application-level checkpoint system.
    """

    def submit(self, request: ProviderRequest) -> ProviderResult:
        """Submit a provider request for execution."""

    def get_status(self, job_id: str, *, provider_job_id: str | None = None) -> ProviderResult:
        """Return the last known provider-backed execution status."""

    def cancel(self, job_id: str, *, provider_job_id: str | None = None) -> ProviderResult:
        """Cancel a submitted provider-backed job if supported."""
