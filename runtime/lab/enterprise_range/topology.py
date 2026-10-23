"""Explicit Network Topology and Isolation Specification for Mini Enterprise Live Range.

RT-06A — Enterprise Range Network Isolation.

Enforces:
  1. Strict Zone Segmentation:
     - Zone A (DMZ): Externally reachable edge service (e.g. lab-enterprise-dmz).
     - Zone B (INTERNAL): Application & identity service reachable only via lateral pivot.
     - Zone C (RESTRICTED): Mission objective / crown jewel reachable only from Zone B.
     - Zone D (DECOY): Isolated decoy honeypot service.
     - Zone Clean (CONTROL): Bounded clean baseline target for false-positive validation.
  2. Fail-Closed Network Isolation:
     - No arbitrary internet outbound.
     - No host-network mode.
     - No cross-zone traffic except explicitly authorized observed routes.
     - No Docker socket or Compose topology exposure to Planner.
  3. Abstracted Identity Terminology:
     - Uses 'Enterprise-like Identity Service' or 'Abstracted Identity and Credential Service'.
     - Zero real credential dumping / zero Active Directory claims.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class NetworkZone:
    zone_id: str
    name: str
    cidr: str
    is_internal_only: bool
    allowed_ingress_from: tuple[str, ...]
    description: str


@dataclass(frozen=True)
class TargetServiceDescriptor:
    target_id: str
    zone_id: str
    hostname: str
    port: int
    service_name: str
    is_external_ingress: bool
    requires_pivot_from: str | None = None
    description: str = ""


# Canonical Enterprise Range Network Zones
ZONES: dict[str, NetworkZone] = {
    "ZONE_DMZ": NetworkZone(
        zone_id="ZONE_DMZ",
        name="DMZ Network (Edge Ingress)",
        cidr="172.28.10.0/24",
        is_internal_only=False,
        allowed_ingress_from=("INGRESS_GATEWAY", "HOST_LOOPBACK"),
        description="Publicly exposed perimeter zone with bounded reverse proxy / web edge.",
    ),
    "ZONE_INTERNAL": NetworkZone(
        zone_id="ZONE_INTERNAL",
        name="Internal Corporate Network",
        cidr="172.28.20.0/24",
        is_internal_only=True,
        allowed_ingress_from=("ZONE_DMZ",),
        description="Isolated internal network hosting corporate apps and identity services.",
    ),
    "ZONE_RESTRICTED": NetworkZone(
        zone_id="ZONE_RESTRICTED",
        name="Restricted Crown-Jewel Vault Network",
        cidr="172.28.30.0/24",
        is_internal_only=True,
        allowed_ingress_from=("ZONE_INTERNAL",),
        description="Highly secure enclave holding mission objectives and sensitive vaults.",
    ),
    "ZONE_DECOY": NetworkZone(
        zone_id="ZONE_DECOY",
        name="Decoy / Honeypot Enclave",
        cidr="172.28.40.0/24",
        is_internal_only=True,
        allowed_ingress_from=("ZONE_INTERNAL",),
        description="Isolated trap zone emitting defensive signals upon unauthorized probing.",
    ),
}

# Canonical Target Service Descriptors
ENTERPRISE_TARGETS: dict[str, TargetServiceDescriptor] = {
    "lab-enterprise-dmz": TargetServiceDescriptor(
        target_id="lab-enterprise-dmz",
        zone_id="ZONE_DMZ",
        hostname="dmz-web.enterprise.local",
        port=8080,
        service_name="http-edge-portal",
        is_external_ingress=True,
        requires_pivot_from=None,
        description="DMZ Web Portal exposing bounded initial authentication surface.",
    ),
    "lab-enterprise-internal": TargetServiceDescriptor(
        target_id="lab-enterprise-internal",
        zone_id="ZONE_INTERNAL",
        hostname="internal-app.enterprise.local",
        port=8080,
        service_name="http-internal-app",
        is_external_ingress=False,
        requires_pivot_from="lab-enterprise-dmz",
        description="Enterprise-like Identity and Application Service reachable via pivot.",
    ),
    "lab-enterprise-restricted": TargetServiceDescriptor(
        target_id="lab-enterprise-restricted",
        zone_id="ZONE_RESTRICTED",
        hostname="restricted-vault.enterprise.local",
        port=8080,
        service_name="http-crown-jewel-vault",
        is_external_ingress=False,
        requires_pivot_from="lab-enterprise-internal",
        description="Restricted vault containing the synthetic mission objective record.",
    ),
    "lab-enterprise-decoy": TargetServiceDescriptor(
        target_id="lab-enterprise-decoy",
        zone_id="ZONE_DECOY",
        hostname="decoy-srv.enterprise.local",
        port=8080,
        service_name="http-decoy-honeypot",
        is_external_ingress=False,
        requires_pivot_from="lab-enterprise-internal",
        description="Decoy honeypot service triggering defensive lockout signals.",
    ),
    "lab-enterprise-clean": TargetServiceDescriptor(
        target_id="lab-enterprise-clean",
        zone_id="ZONE_DMZ",
        hostname="clean-edge.enterprise.local",
        port=8080,
        service_name="http-clean-baseline",
        is_external_ingress=True,
        requires_pivot_from=None,
        description="Clean baseline edge service containing zero exploitable vulnerabilities.",
    ),
}


def get_target_allowlist() -> frozenset[str]:
    """Authoritative target allowlist for the Enterprise Live Range."""
    return frozenset(ENTERPRISE_TARGETS.keys())


def is_direct_ingress_allowed(target_id: str) -> bool:
    """Check if target can be reached directly from external ingress boundary."""
    descriptor = ENTERPRISE_TARGETS.get(target_id)
    if not descriptor:
        return False
    return descriptor.is_external_ingress


def validate_network_transition(from_target_id: str | None, to_target_id: str) -> tuple[bool, str]:
    """Validate cross-zone reachability boundary (fail-closed)."""
    to_desc = ENTERPRISE_TARGETS.get(to_target_id)
    if not to_desc:
        return False, f"UNKNOWN_DESTINATION_TARGET: '{to_target_id}'"

    if to_desc.is_external_ingress:
        return True, "DIRECT_INGRESS_ALLOWED"

    if from_target_id is None:
        return False, f"ZONE_ISOLATION_VIOLATION: '{to_target_id}' is internal and requires an observed pivot source"

    from_desc = ENTERPRISE_TARGETS.get(from_target_id)
    if not from_desc:
        return False, f"UNKNOWN_SOURCE_TARGET: '{from_target_id}'"

    if to_desc.requires_pivot_from != from_target_id:
        return False, (
            f"NETWORK_BARRIER_FAIL_CLOSED: route from '{from_target_id}' ({from_desc.zone_id}) "
            f"to '{to_target_id}' ({to_desc.zone_id}) is blocked by network firewall policy"
        )

    return True, "ZONE_TRANSITION_PERMITTED"
