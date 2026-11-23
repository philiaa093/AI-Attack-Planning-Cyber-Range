"""Provider-neutral live-range lifecycle and bounded dispatch contract."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, runtime_checkable


class RangeProviderError(RuntimeError):
    """Stable fail-closed error raised by range infrastructure providers."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class RangeProviderCapabilities:
    """Explicit provider capabilities; absence must be treated as unsupported."""

    lifecycle: bool = True
    restore: bool = True
    route_control: bool = True
    bounded_dispatch: bool = True
    external_infrastructure: bool = False


@runtime_checkable
class RangeProvider(Protocol):
    """Shared contract used by Docker, loopback, GNS3 and vSphere ranges."""

    capabilities: RangeProviderCapabilities

    def start(self) -> dict[str, str]: ...

    def stop(self) -> None: ...

    def reset_all(self) -> None: ...

    def health_check_all(self) -> dict[str, bool]: ...

    def block_route(self, target_id: str, route_name: str = "primary") -> None: ...

    def unblock_route(self, target_id: str, route_name: str = "primary") -> None: ...

    def dispatch_bounded_request(
        self,
        target_id: str,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        from_target_id: str | None = None,
        timeout: float = 5.0,
    ) -> dict[str, Any]: ...


def validate_provider_contract(provider: object) -> None:
    """Reject incomplete provider implementations before an episode starts."""
    required = (
        "start",
        "stop",
        "reset_all",
        "health_check_all",
        "block_route",
        "unblock_route",
        "dispatch_bounded_request",
    )
    missing = [name for name in required if not callable(getattr(provider, name, None))]
    if missing:
        raise RangeProviderError(
            "RANGE_PROVIDER_CONTRACT_INVALID",
            "Missing provider operations: " + ", ".join(sorted(missing)),
        )
    capabilities = getattr(provider, "capabilities", None)
    if not isinstance(capabilities, RangeProviderCapabilities):
        raise RangeProviderError(
            "RANGE_PROVIDER_CAPABILITIES_MISSING",
            "Provider must declare RangeProviderCapabilities",
        )


def sanitized_provider_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Return bounded non-secret provider metadata for evidence/provenance."""
    allowed = {"provider_kind", "configuration_id", "external_infrastructure"}
    return {key: metadata[key] for key in sorted(allowed) if key in metadata}
