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
