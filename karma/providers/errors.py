"""Provider contract exceptions."""

from __future__ import annotations


class ProviderContractError(RuntimeError):
    """Base exception for provider contract failures."""


class ProviderValidationError(ValueError, ProviderContractError):
    """Raised for invalid provider requests or invalid provider state."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
