"""Provider abstraction contracts for future asset execution backends."""

from .application_bridge import ApplicationProviderBridge
from .base import ProviderProtocol
from .contracts import (
    ProviderArtifactMetadata,
    ProviderErrorInfo,
    ProviderOutputSpec,
    ProviderRequest,
    ProviderResult,
    ProviderRetryInfo,
    ProviderSecurityPolicy,
    asset_requirement_to_provider_request,
)
from .errors import ProviderContractError, ProviderValidationError
from .fakes import FakeProvider
from .luma_video import LumaTransport, LumaTransportResponse, LumaVideoProvider
from .replicate_image import (
    ReplicateImageProvider,
    ReplicateTransport,
    ReplicateTransportResponse,
)
from .replicate_transport import ReplicateHttpTransport
from .runtime import (
    LIVE_PROVIDER_AUTH_ENV,
    authorize_and_resolve_provider_credential,
    is_live_provider_authorized,
    resolve_provider_credential,
    resolve_runtime_credential,
)
from .types import ProviderAssetType, ProviderErrorCategory, ProviderExecutionStatus

__all__ = [
    "ApplicationProviderBridge",
    "FakeProvider",
    "LIVE_PROVIDER_AUTH_ENV",
    "LumaTransport",
    "LumaTransportResponse",
    "LumaVideoProvider",
    "ProviderArtifactMetadata",
    "ProviderAssetType",
    "ProviderContractError",
    "ProviderErrorCategory",
    "ProviderErrorInfo",
    "ProviderExecutionStatus",
    "ProviderOutputSpec",
    "ProviderProtocol",
    "ProviderRequest",
    "ProviderResult",
    "ProviderRetryInfo",
    "ProviderSecurityPolicy",
    "ProviderValidationError",
    "ReplicateHttpTransport",
    "ReplicateImageProvider",
    "ReplicateTransport",
    "ReplicateTransportResponse",
    "asset_requirement_to_provider_request",
    "authorize_and_resolve_provider_credential",
    "is_live_provider_authorized",
    "resolve_provider_credential",
    "resolve_runtime_credential",
]
