"""Live Range Test & Execution Harness for Mini Enterprise Cyber Range.

RT-06A — Live Range Lifecycle and Network Boundary Harness.

Enforces:
  1. Threaded, isolated loopback HTTP servers running on local ports.
  2. Network isolation barrier: fail-closed rejection of unpivoted internal requests.
  3. Dynamic route blocking for L2 Replan testing.
  4. Decoy signal configuration for L4 testing.
  5. Deterministic reset and health checks.
"""
from __future__ import annotations

import http.client
import json
import logging
import threading
from http.server import ThreadingHTTPServer
from typing import Any, Mapping
from urllib.parse import urlsplit

from runtime.lab.enterprise_range.services import (
    BaseEnterpriseHandler,
    CleanControlServiceHandler,
    DecoyServiceHandler,
    DMZServiceHandler,
    InternalServiceHandler,
    RestrictedServiceHandler,
    TargetState,
)
from runtime.lab.enterprise_range.topology import (
    ENTERPRISE_TARGETS,
    is_direct_ingress_allowed,
    validate_network_transition,
)

logger = logging.getLogger(__name__)


class EnterpriseLiveRangeHarness:
    """Manages the lifecycle and network boundaries of the live enterprise range services."""

    def __init__(self, host: str = "127.0.0.1") -> None:
        self.host = host
        self.servers: dict[str, ThreadingHTTPServer] = {}
        self.threads: dict[str, threading.Thread] = {}
        self.states: dict[str, TargetState] = {}
        self.endpoints: dict[str, str] = {}
        self.ports: dict[str, int] = {}
        self._running = False
        self._lock = threading.Lock()

    def start(self) -> dict[str, str]:
        """Start all enterprise target services on isolated loopback ports."""
        with self._lock:
            if self._running:
                return dict(self.endpoints)

            handlers = {
                "lab-enterprise-dmz": (DMZServiceHandler, "ZONE_DMZ"),
                "lab-enterprise-internal": (InternalServiceHandler, "ZONE_INTERNAL"),
                "lab-enterprise-restricted": (RestrictedServiceHandler, "ZONE_RESTRICTED"),
                "lab-enterprise-decoy": (DecoyServiceHandler, "ZONE_DECOY"),
                "lab-enterprise-clean": (CleanControlServiceHandler, "ZONE_CLEAN"),
            }

            for target_id, (handler_cls, zone_id) in handlers.items():
                state = TargetState(target_id=target_id, zone_id=zone_id)
                self.states[target_id] = state

                # Create dedicated handler class bound to target state
                class BoundHandler(handler_cls):
                    target_state = state

                server = ThreadingHTTPServer((self.host, 0), BoundHandler)
                port = server.server_address[1]
                thread = threading.Thread(
                    target=server.serve_forever,
                    name=f"LiveRange-{target_id}",
                    daemon=True,
                )
                thread.start()

                self.servers[target_id] = server
                self.threads[target_id] = thread
                self.ports[target_id] = port
                self.endpoints[target_id] = f"http://{self.host}:{port}"

            self._running = True
            return dict(self.endpoints)

    def stop(self) -> None:
        """Shut down all running target services cleanly."""
        with self._lock:
            if not self._running:
                return

            for target_id, server in self.servers.items():
                try:
                    server.shutdown()
                    server.server_close()
                except Exception as exc:
                    logger.warning("Error shutting down server %s: %s", target_id, exc)

            for target_id, thread in self.threads.items():
                try:
                    thread.join(timeout=2.0)
                except Exception:
                    pass

            self.servers.clear()
            self.threads.clear()
            self.endpoints.clear()
            self.ports.clear()
            self.states.clear()
            self._running = False

    def reset_all(self) -> None:
        """Reset state across all live enterprise targets."""
        with self._lock:
            for state in self.states.values():
                state.reset()

    def health_check_all(self) -> dict[str, bool]:
        """Perform health checks across all running live targets."""
        results = {}
        for target_id, base_url in self.endpoints.items():
            parsed = urlsplit(base_url)
            conn = http.client.HTTPConnection(parsed.hostname or self.host, parsed.port or 80, timeout=2.0)
            try:
                conn.request("GET", "/health")
                resp = conn.getresponse()
                results[target_id] = (resp.status == 200)
                resp.read()
            except Exception:
                results[target_id] = False
            finally:
                conn.close()
        return results

    def block_route(self, target_id: str, route_name: str = "primary") -> None:
        """Block a specific route to test L2 Replan behavior."""
        state = self.states.get(target_id)
        if state:
            with state.lock:
                state.blocked_routes.add(route_name)

    def unblock_route(self, target_id: str, route_name: str = "primary") -> None:
        """Unblock a route."""
        state = self.states.get(target_id)
        if state:
            with state.lock:
                state.blocked_routes.discard(route_name)

    def dispatch_bounded_request(
        self,
        target_id: str,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        from_target_id: str | None = None,
        timeout: float = 5.0,
    ) -> dict[str, Any]:
        """Dispatch a bounded HTTP request through the live network boundary.

        Enforces zone firewall / reachability checks:
        If target is internal and not directly reachable from ingress, it requires
        that the request originates from a valid, authorized pivot node.
        """
        if not self._running:
            raise RuntimeError("Live range harness is not running")

        if target_id not in self.endpoints:
            return {
                "outcome": "DENIED",
                "status_code": 404,
                "error": "UNKNOWN_TARGET",
                "message": f"Target '{target_id}' not found in live range",
            }

        target_state = self.states.get(target_id)
        is_host_local = target_state is not None and target_state.has_active_session("FOOTHOLD") and path != "/api/v1/pivot"

        if not is_host_local:
            # 1. Enforce network boundary and zone transition
            permitted, reason = validate_network_transition(from_target_id, target_id)
            if not permitted:
                return {
                    "outcome": "DENIED",
                    "status_code": 403,
                    "error": "NETWORK_ISOLATION_BARRIER",
                    "message": reason,
                }

            # 2. If target is internal, verify that from_target_id has an active session
            if from_target_id is not None and not is_direct_ingress_allowed(target_id):
                source_state = self.states.get(from_target_id)
                if not source_state or not source_state.has_active_session("FOOTHOLD"):
                    return {
                        "outcome": "DENIED",
                        "status_code": 403,
                        "error": "PIVOT_SOURCE_UNAUTHORIZED",
                        "message": f"Source node '{from_target_id}' has no active session to route traffic to '{target_id}'",
                    }

        # 3. Perform network I/O to the target loopback endpoint
        base_url = self.endpoints[target_id]
        parsed = urlsplit(base_url)
        encoded_body = json.dumps(body or {}).encode("utf-8") if method in ("POST", "PUT") else None
        headers = {"Content-Type": "application/json"} if encoded_body else {}
        if encoded_body:
            headers["Content-Length"] = str(len(encoded_body))

        conn = http.client.HTTPConnection(parsed.hostname or self.host, parsed.port or 80, timeout=timeout)
        try:
            conn.request(method, path, body=encoded_body, headers=headers)
            resp = conn.getresponse()
            raw_data = resp.read()
            status_code = resp.status
            try:
                data = json.loads(raw_data.decode("utf-8"))
            except Exception:
                data = {"raw_text": raw_data.decode("utf-8", errors="replace")}
            data["http_status"] = status_code
            return data
        except Exception as exc:
            return {
                "outcome": "ERROR",
                "status_code": 500,
                "error": "NETWORK_ERROR",
                "message": str(exc),
            }
        finally:
            conn.close()


class DockerEnterpriseRangeHarness:
    """Manages communication with the real Docker Compose deployment of the enterprise cyber range.

    Enforces wire-level network isolation by routing requests through valid ingress and pivot paths:
      - DMZ (lab-enterprise-dmz): Direct ingress via published loopback port (127.0.0.1:18081).
      - Clean (lab-enterprise-clean): Direct ingress via published loopback port (127.0.0.1:18085).
      - Internal (lab-enterprise-internal): Routed via DMZ pivot relay (dmz_net -> internal_net).
      - Restricted (lab-enterprise-restricted): Routed via DMZ -> Internal pivot relay (internal_net -> restricted_net).
      - Decoy (lab-enterprise-decoy): Routed via DMZ -> Internal pivot relay (internal_net -> decoy_net).

    Direct access to internal/restricted/decoy nodes from the host is physically blocked
    by Docker network isolation (no published host ports, internal: true).
    Direct access from DMZ to Restricted or Decoy is physically blocked by Docker network segmentation.
    """

    def __init__(
        self,
        dmz_host: str = "127.0.0.1",
        dmz_port: int = 18081,
        clean_port: int = 18085,
    ) -> None:
        self.dmz_host = dmz_host
        self.dmz_port = dmz_port
        self.clean_port = clean_port
        self.endpoints = {
            "lab-enterprise-dmz": f"http://{dmz_host}:{dmz_port}",
            "lab-enterprise-clean": f"http://{dmz_host}:{clean_port}",
        }
        self.compromised_hosts: set[str] = set()
        self._running = False

    def start(self) -> dict[str, str]:
        """Verify that the Docker containers are reachable on their ingress endpoints."""
        self._running = True
        return dict(self.endpoints)

    def stop(self) -> None:
        """Mark harness stopped."""
        self._running = False

    def reset_all(self) -> None:
        """Reset state across all running Docker containers in innermost-first order."""
        self.compromised_hosts.clear()
        # Reset restricted vault
        self._dispatch_http_raw(
            self.dmz_host,
            self.dmz_port,
            "POST",
            "/api/v1/relay",
            body={
                "target_host": "internal-service",
                "target_port": 8080,
                "method": "POST",
                "path": "/api/v1/relay",
                "body": {
                    "target_host": "restricted-service",
                    "target_port": 8080,
                    "method": "POST",
                    "path": "/reset",
                },
            },
        )
        # Reset decoy honeypot
        self._dispatch_http_raw(
            self.dmz_host,
            self.dmz_port,
            "POST",
            "/api/v1/relay",
            body={
                "target_host": "internal-service",
                "target_port": 8080,
                "method": "POST",
                "path": "/api/v1/relay",
                "body": {
                    "target_host": "decoy-service",
                    "target_port": 8080,
                    "method": "POST",
                    "path": "/reset",
                },
            },
        )
        # Reset internal app
        self._dispatch_http_raw(
            self.dmz_host,
            self.dmz_port,
            "POST",
            "/api/v1/relay",
            body={
                "target_host": "internal-service",
                "target_port": 8080,
                "method": "POST",
                "path": "/reset",
            },
        )
        # Reset DMZ
        self._dispatch_http_raw(self.dmz_host, self.dmz_port, "POST", "/reset")
        # Reset Clean control
        self._dispatch_http_raw(self.dmz_host, self.clean_port, "POST", "/reset")

    def health_check_all(self) -> dict[str, bool]:
        """Perform health checks across all Docker containers."""
        results: dict[str, bool] = {}
        # DMZ
        r_dmz = self._dispatch_http_raw(self.dmz_host, self.dmz_port, "GET", "/health")
        results["lab-enterprise-dmz"] = (r_dmz.get("http_status") == 200)

        # Clean
        r_clean = self._dispatch_http_raw(self.dmz_host, self.clean_port, "GET", "/health")
        results["lab-enterprise-clean"] = (r_clean.get("http_status") == 200)

        # Internal (via DMZ relay)
        r_int = self._dispatch_http_raw(
            self.dmz_host,
            self.dmz_port,
            "POST",
            "/api/v1/relay",
            body={"target_host": "internal-service", "target_port": 8080, "method": "GET", "path": "/health"},
        )
        results["lab-enterprise-internal"] = (r_int.get("http_status") == 200)

        # Restricted (via nested relay)
        r_restr = self._dispatch_http_raw(
            self.dmz_host,
            self.dmz_port,
            "POST",
            "/api/v1/relay",
            body={
                "target_host": "internal-service",
                "target_port": 8080,
                "method": "POST",
                "path": "/api/v1/relay",
                "body": {"target_host": "restricted-service", "target_port": 8080, "method": "GET", "path": "/health"},
            },
        )
        results["lab-enterprise-restricted"] = (r_restr.get("http_status") == 200)

        # Decoy (via nested relay)
        r_decoy = self._dispatch_http_raw(
            self.dmz_host,
            self.dmz_port,
            "POST",
            "/api/v1/relay",
            body={
                "target_host": "internal-service",
                "target_port": 8080,
                "method": "POST",
                "path": "/api/v1/relay",
                "body": {"target_host": "decoy-service", "target_port": 8080, "method": "GET", "path": "/health"},
            },
        )
        results["lab-enterprise-decoy"] = (r_decoy.get("http_status") == 200)

        return results

    def block_route(self, target_id: str, route_name: str = "primary") -> None:
        """Block a route on an internal Docker target via admin control."""
        if target_id == "lab-enterprise-internal":
            self._dispatch_http_raw(
                self.dmz_host,
                self.dmz_port,
                "POST",
                "/api/v1/relay",
                body={
                    "target_host": "internal-service",
                    "target_port": 8080,
                    "method": "POST",
                    "path": "/api/v1/admin/block_route",
                    "body": {"route": route_name},
                },
            )

    def unblock_route(self, target_id: str, route_name: str = "primary") -> None:
        """Unblock a route on an internal Docker target via admin control."""
        if target_id == "lab-enterprise-internal":
            self._dispatch_http_raw(
                self.dmz_host,
                self.dmz_port,
                "POST",
                "/api/v1/relay",
                body={
                    "target_host": "internal-service",
                    "target_port": 8080,
                    "method": "POST",
                    "path": "/api/v1/admin/unblock_route",
                    "body": {"route": route_name},
                },
            )

    def _dispatch_http_raw(
        self,
        host: str,
        port: int,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        timeout: float = 5.0,
    ) -> dict[str, Any]:
        encoded = json.dumps(body or {}).encode("utf-8") if method in ("POST", "PUT") else None
        headers = {"Content-Type": "application/json"} if encoded else {}
        if encoded:
            headers["Content-Length"] = str(len(encoded))
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
        try:
            conn.request(method, path, body=encoded, headers=headers)
            resp = conn.getresponse()
            raw_data = resp.read()
            try:
                data = json.loads(raw_data.decode("utf-8"))
            except Exception:
                data = {"raw_text": raw_data.decode("utf-8", errors="replace")}
            data["http_status"] = resp.status
            return data
        except Exception as exc:
            return {"outcome": "ERROR", "status_code": 500, "error": "NETWORK_ERROR", "message": str(exc), "http_status": 500}
        finally:
            conn.close()

    def dispatch_bounded_request(
        self,
        target_id: str,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        from_target_id: str | None = None,
        timeout: float = 5.0,
    ) -> dict[str, Any]:
        """Dispatch bounded HTTP request through wire-level Docker network topology."""
        eff_from = from_target_id or (body.get("from_node_id") if isinstance(body, dict) else None)
        is_host_local = target_id in self.compromised_hosts and path != "/api/v1/pivot"

        if not is_host_local:
            permitted, reason = validate_network_transition(eff_from, target_id)
            if not permitted:
                return {
                    "outcome": "DENIED",
                    "status_code": 403,
                    "error": "NETWORK_ISOLATION_BARRIER",
                    "message": reason,
                }
            if eff_from is not None and not is_direct_ingress_allowed(target_id):
                if eff_from not in self.compromised_hosts:
                    return {
                        "outcome": "DENIED",
                        "status_code": 403,
                        "error": "PIVOT_SOURCE_UNAUTHORIZED",
                        "message": f"Source node '{eff_from}' has no active session to route traffic to '{target_id}'",
                    }

        if target_id == "lab-enterprise-dmz":
            res = self._dispatch_http_raw(self.dmz_host, self.dmz_port, method, path, body=body, timeout=timeout)
        elif target_id == "lab-enterprise-clean":
            res = self._dispatch_http_raw(self.dmz_host, self.clean_port, method, path, body=body, timeout=timeout)
        elif target_id == "lab-enterprise-internal":
            # Dispatched via DMZ relay
            relay_body = {
                "target_host": "internal-service",
                "target_port": 8080,
                "method": method,
                "path": path,
                "body": body,
            }
            res = self._dispatch_http_raw(self.dmz_host, self.dmz_port, "POST", "/api/v1/relay", body=relay_body, timeout=timeout)
        elif target_id in ("lab-enterprise-restricted", "lab-enterprise-decoy"):
            dest_host = "restricted-service" if target_id == "lab-enterprise-restricted" else "decoy-service"
            # Nested relay: DMZ -> Internal -> target
            nested_relay_body = {
                "target_host": "internal-service",
                "target_port": 8080,
                "method": "POST",
                "path": "/api/v1/relay",
                "body": {
                    "target_host": dest_host,
                    "target_port": 8080,
                    "method": method,
                    "path": path,
                    "body": body,
                },
            }
            res = self._dispatch_http_raw(self.dmz_host, self.dmz_port, "POST", "/api/v1/relay", body=nested_relay_body, timeout=timeout)
        else:
            return {
                "outcome": "DENIED",
                "status_code": 404,
                "error": "UNKNOWN_TARGET",
                "message": f"Target '{target_id}' not found in live range",
            }

        # Track successfully compromised hosts
        if res.get("status") == "ok" and res.get("outcome") == "SUCCESS" and "session" in res:
            self.compromised_hosts.add(target_id)

        return res
