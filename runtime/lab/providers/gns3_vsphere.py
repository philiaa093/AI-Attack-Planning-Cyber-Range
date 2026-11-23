"""Production-oriented GNS3 + vSphere implementation of RangeProvider."""
from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import urlsplit

from runtime.lab.enterprise_range.topology import (
    is_direct_ingress_allowed,
    validate_network_transition,
)
from runtime.lab.providers import JsonTransport, UrllibJsonTransport
from runtime.lab.providers.gns3 import GNS3ProjectClient
from runtime.lab.providers.vsphere import VSphereLifecycleClient
from runtime.lab.range_provider import (
    RangeProviderCapabilities,
    RangeProviderError,
    sanitized_provider_metadata,
)
from runtime.lab.remote_range_config import RemoteRangeConfig


_DATA_PLANE_POLICY: dict[str, frozenset[str]] = {
    "GET": frozenset({
        "/health",
        "/api/v1/discovery",
        "/api/v1/system/recon",
    }),
    "POST": frozenset({
        "/api/v1/auth/foothold",
        "/api/v1/credentials/harvest",
        "/api/v1/pivot",
        "/api/v1/auth/privesc",
        "/api/v1/vault/objective",
    }),
}


class GNS3VSphereRangeProvider:
    """Coordinate approved workloads while preserving the bounded executor contract."""

    capabilities = RangeProviderCapabilities(external_infrastructure=True)

    def __init__(
        self,
        config: RemoteRangeConfig,
        *,
        transport: JsonTransport | None = None,
        environ: Mapping[str, str] | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.config = config
        if transport is None:
            configured_urls = [config.gns3.base_url, config.vsphere.base_url]
            configured_urls.extend(target.data_url for target in config.targets.values())
            configured_urls.extend(target.control_url for target in config.targets.values())
            allowed_hosts = frozenset(
                hostname
                for url in configured_urls
                if (hostname := urlsplit(url).hostname) is not None
            )
            transport = UrllibJsonTransport(allowed_hosts=allowed_hosts)
        self.transport = transport
        self.timeout = timeout
        self.control_token = config.resolve_control_token(environ)
        self.gns3 = GNS3ProjectClient(
            config.gns3,
            transport=self.transport,
            environ=environ,
            timeout=timeout,
        )
        self.vsphere = VSphereLifecycleClient(
            config.vsphere,
            transport=self.transport,
            environ=environ,
            timeout=max(timeout, 30.0),
        )
        self.compromised_hosts: set[str] = set()
        self._running = False

    @property
    def metadata(self) -> dict[str, Any]:
        return sanitized_provider_metadata({
            "provider_kind": "GNS3_VSPHERE",
            "configuration_id": self.config.configuration_id,
            "external_infrastructure": True,
        })

    def start(self) -> dict[str, str]:
        if self._running:
            return {target_id: target.data_url for target_id, target in self.config.targets.items()}
        powered: list[str] = []
        started_nodes: list[str] = []
        try:
            for target in self.config.targets.values():
                if target.vsphere_vm_id not in powered:
                    self.vsphere.power_on(target.vsphere_vm_id)
                    powered.append(target.vsphere_vm_id)
            self.gns3.open_project()
            for target in self.config.targets.values():
                if target.gns3_node_id not in started_nodes:
                    self.gns3.start_node(target.gns3_node_id)
                    started_nodes.append(target.gns3_node_id)
        except Exception:
            for node_id in reversed(started_nodes):
                try:
                    self.gns3.stop_node(node_id)
                except Exception:
                    pass
            for vm_id in reversed(powered):
                try:
                    self.vsphere.power_off(vm_id)
                except Exception:
                    pass
            raise
        self._running = True
        return {target_id: target.data_url for target_id, target in self.config.targets.items()}

    def stop(self) -> None:
        failures: list[str] = []
        for target in reversed(tuple(self.config.targets.values())):
            try:
                self.gns3.stop_node(target.gns3_node_id)
            except Exception as exc:
                failures.append(getattr(exc, "code", "GNS3_NODE_STOP_FAILED"))
        try:
            self.gns3.close_project()
        except Exception as exc:
            failures.append(getattr(exc, "code", "GNS3_PROJECT_CLOSE_FAILED"))
        for target in reversed(tuple(self.config.targets.values())):
            try:
                self.vsphere.power_off(target.vsphere_vm_id)
            except Exception as exc:
                failures.append(getattr(exc, "code", "VSPHERE_POWER_OFF_FAILED"))
        self._running = False
        self.compromised_hosts.clear()
        if failures:
            raise RangeProviderError("REMOTE_RANGE_STOP_INCOMPLETE", ", ".join(sorted(set(failures))))

    def reset_all(self) -> None:
        self.compromised_hosts.clear()
        for target in reversed(tuple(self.config.targets.values())):
            self.vsphere.revert_current_snapshot(target.vsphere_vm_id)
        for target in self.config.targets.values():
            self.vsphere.power_on(target.vsphere_vm_id)

    def health_check_all(self) -> dict[str, bool]:
        results: dict[str, bool] = {}
        for target_id, target in self.config.targets.items():
            try:
                vm_ok = self.vsphere.power_state(target.vsphere_vm_id) == "POWERED_ON"
                node_ok = self.gns3.node_started(target.gns3_node_id)
                response = self.transport.request(
                    "GET",
                    f"{target.data_url}/health",
                    timeout=self.timeout,
                )
                results[target_id] = vm_ok and node_ok and response.status == 200
            except Exception:
                results[target_id] = False
        return results

    def block_route(self, target_id: str, route_name: str = "primary") -> None:
        self._control_request(target_id, "/control/v1/routes/block", {"route": route_name})

    def unblock_route(self, target_id: str, route_name: str = "primary") -> None:
        self._control_request(target_id, "/control/v1/routes/unblock", {"route": route_name})

    def _control_request(self, target_id: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        target = self.config.targets.get(target_id)
        if target is None:
            raise RangeProviderError("UNKNOWN_CONTROL_TARGET", "Control target is not configured")
        response = self.transport.request(
            "POST",
            f"{target.control_url}{path}",
            headers={"Authorization": f"Bearer {self.control_token}"},
            body=body,
            timeout=self.timeout,
        )
        if response.status != 200 or not isinstance(response.body, dict):
            raise RangeProviderError("REMOTE_CONTROL_REQUEST_FAILED", f"Control API returned HTTP {response.status}")
        return dict(response.body)

    def dispatch_bounded_request(
        self,
        target_id: str,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        from_target_id: str | None = None,
        timeout: float = 5.0,
    ) -> dict[str, Any]:
        target = self.config.targets.get(target_id)
        if target is None:
            return {"outcome": "DENIED", "status_code": 404, "error": "UNKNOWN_TARGET"}
        if not isinstance(method, str) or not isinstance(path, str) or not isinstance(body, (dict, type(None))):
            return {"outcome": "DENIED", "status_code": 400, "error": "INVALID_BOUNDED_REQUEST"}
        normalized_method = method.upper()
        if path not in _DATA_PLANE_POLICY.get(normalized_method, frozenset()):
            return {"outcome": "DENIED", "status_code": 403, "error": "DATA_PLANE_ACTION_DENIED"}

        is_host_local = target_id in self.compromised_hosts and path != "/api/v1/pivot"
        if not is_host_local:
            permitted, reason = validate_network_transition(from_target_id, target_id)
            if not permitted:
                return {
                    "outcome": "DENIED",
                    "status_code": 403,
                    "error": "NETWORK_ISOLATION_BARRIER",
                    "message": reason,
                }
            if from_target_id is not None and not is_direct_ingress_allowed(target_id):
                if from_target_id not in self.compromised_hosts:
                    return {
                        "outcome": "DENIED",
                        "status_code": 403,
                        "error": "PIVOT_SOURCE_UNAUTHORIZED",
                    }

        response = self.transport.request(
            normalized_method,
            f"{target.data_url}{path}",
            body=body if normalized_method == "POST" else None,
            timeout=min(max(timeout, 0.1), 30.0),
        )
        payload = dict(response.body) if isinstance(response.body, dict) else {}
        payload["http_status"] = response.status
        payload.setdefault("status_code", response.status)
        if payload.get("status") == "ok" and payload.get("outcome") == "SUCCESS" and "session" in payload:
            self.compromised_hosts.add(target_id)
        return payload
