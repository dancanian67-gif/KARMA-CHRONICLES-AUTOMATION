"""Runtime-only live authorization and credential resolution for providers.

This module is a fail-closed safety gate. It does not perform network I/O and
does not persist secrets. Credential presence alone never authorizes live
provider execution.
"""

from __future__ import annotations

import os
from typing import Mapping

# Explicit process-level opt-in. Presence of provider API tokens is not enough.
LIVE_PROVIDER_AUTH_ENV = "KARMA_LIVE_PROVIDER_AUTH"
_LIVE_AUTH_ALLOWLIST = frozenset({"1", "true", "yes"})

# Provider-scoped runtime secret names. Values are never stored here.
PROVIDER_CREDENTIAL_ENV: Mapping[str, str] = {
    "replicate": "REPLICATE_API_TOKEN",
    "luma": "LUMA_API_KEY",
}


def is_live_provider_authorized(
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Return True only for an explicit allow-listed live-authorization value."""
    env = os.environ if environ is None else environ
    raw = env.get(LIVE_PROVIDER_AUTH_ENV)
    if raw is None:
        return False
    return raw.strip().lower() in _LIVE_AUTH_ALLOWLIST


def resolve_runtime_credential(
    env_var: str,
    *,
    environ: Mapping[str, str] | None = None,
) -> str | None:
    """Read a credential at call time. Never log or retain the value.

    Callers must invoke this only after live authorization has succeeded.
    """
    env = os.environ if environ is None else environ
    value = env.get(env_var)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def resolve_provider_credential(
    provider_name: str,
    *,
    environ: Mapping[str, str] | None = None,
) -> str | None:
    """Resolve a provider-scoped runtime credential without authorizing live use."""
    env_var = PROVIDER_CREDENTIAL_ENV.get(provider_name)
    if env_var is None:
        return None
    return resolve_runtime_credential(env_var, environ=environ)


def authorize_and_resolve_provider_credential(
    provider_name: str,
    *,
    environ: Mapping[str, str] | None = None,
) -> tuple[str, str | None]:
    """Gate live credential access.

    Returns:
        ("unauthorized", None) when live execution is not explicitly authorized.
        ("missing_credential", None) when authorized but no usable secret exists.
        ("ok", credential) when authorized and a credential is available.

    The credential string is returned only to the immediate caller for transport
    authentication. It must never be copied into ProviderRequest/ProviderResult.
    """
    if not is_live_provider_authorized(environ):
        return "unauthorized", None
    credential = resolve_provider_credential(provider_name, environ=environ)
    if credential is None:
        return "missing_credential", None
    return "ok", credential


__all__ = [
    "LIVE_PROVIDER_AUTH_ENV",
    "PROVIDER_CREDENTIAL_ENV",
    "authorize_and_resolve_provider_credential",
    "is_live_provider_authorized",
    "resolve_provider_credential",
    "resolve_runtime_credential",
]
