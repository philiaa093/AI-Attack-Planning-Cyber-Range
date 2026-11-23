"""Bounded HTTP Target Services for Mini Enterprise Live Validation Range.

RT-06A — Bounded Enterprise Services.

Enforces:
  1. Bounded typed API endpoints corresponding to canonical benchmark action families.
  2. Zero arbitrary shell execution, zero arbitrary code execution.
  3. Synthetic credentials with opaque handles; raw secrets stay on target/executor.
  4. Zone-aware state transitions (DMZ -> INTERNAL -> RESTRICTED).
  5. Decoy honeypot defense signal generation.
  6. Clean baseline false-positive control target.
"""
from __future__ import annotations

import http.client
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler
from typing import Any, Mapping
from urllib.parse import parse_qs, urlsplit

logger = logging.getLogger(__name__)

# Synthetic secret store maintained strictly within the live range boundary
SYNTHETIC_LAB_SECRETS: dict[str, str] = {
    "svc_internal": "SYNTHETIC_LAB_TOKEN_INT_98472a1f",
    "vault_admin": "SYNTHETIC_LAB_KEY_VAULT_33b890cc",
}


# Relay authority is deliberately narrower than network reachability. A
# container may resolve another service, but it may only forward the exact
# bounded operations needed by the canonical live-range workflow.
_RELAY_POLICY: dict[str, dict[str, dict[str, frozenset[str]]]] = {
    "lab-enterprise-dmz": {
        "internal-service": {
            "GET": frozenset({
                "/health",
                "/api/v1/discovery",
                "/api/v1/system/recon",
            }),
            "POST": frozenset({
                "/api/v1/relay",
                "/api/v1/pivot",
                "/api/v1/auth/privesc",
                "/api/v1/credentials/harvest",
            }),
        },
    },
    "lab-enterprise-internal": {
        "restricted-service": {
            "GET": frozenset({"/health", "/api/v1/discovery"}),
            "POST": frozenset({
                "/api/v1/pivot",
                "/api/v1/vault/objective",
            }),
        },
        "decoy-service": {
            "GET": frozenset({"/health", "/api/v1/discovery"}),
            "POST": frozenset(),
        },
    },
}


def _validate_relay_request(
    source_target_id: str,
    body: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, tuple[int, str, str] | None]:
    """Canonicalize a relay request and reject anything outside fixed policy."""
    target_host = body.get("target_host")
    target_port = body.get("target_port", 8080)
    method_value = body.get("method", "GET")
    path = body.get("path", "/")
    forwarded_body = body.get("body")

    if (
        not isinstance(target_host, str)
        or not target_host
        or type(target_port) is not int
        or not isinstance(method_value, str)
        or not isinstance(path, str)
        or not path.startswith("/")
        or (forwarded_body is not None and not isinstance(forwarded_body, dict))
    ):
        return None, (
            400,
            "INVALID_RELAY_REQUEST",
            "Relay request fields are malformed",
        )

    source_policy = _RELAY_POLICY.get(source_target_id, {})
    destination_policy = source_policy.get(target_host)
    if destination_policy is None or target_port != 8080:
        return None, (
            403,
            "RELAY_DESTINATION_DENIED",
            "Relay destination is not permitted for this source zone",
        )

    method = method_value.upper()
    allowed_paths = destination_policy.get(method)
    if allowed_paths is None or path not in allowed_paths:
        return None, (
            403,
            "RELAY_ACTION_DENIED",
            "Relay method and path are not permitted for this destination",
        )

    return {
        "target_host": target_host,
        "target_port": target_port,
        "method": method,
        "path": path,
        "body": forwarded_body,
    }, None


def _open_relay_connection(host: str, port: int, timeout: float) -> http.client.HTTPConnection:
    """Single post-policy network seam used by focused no-dispatch tests."""
    return http.client.HTTPConnection(host, port, timeout=timeout)


class TargetState:
    """Isolated, thread-safe state container for a live enterprise target service."""

    def __init__(self, target_id: str, zone_id: str) -> None:
        self.target_id = target_id
        self.zone_id = zone_id
        self.reset_count = 0
        self.sessions: dict[str, dict[str, Any]] = {}
        self.discovered_credentials: set[str] = set()
        self.blocked_routes: set[str] = set()
        self.lock = threading.Lock()

    def reset(self) -> None:
        with self.lock:
            self.reset_count += 1
            self.sessions.clear()
            self.discovered_credentials.clear()
            self.blocked_routes.clear()

    def add_session(self, session_id: str, access_level: str, from_node: str | None = None) -> dict[str, Any]:
        with self.lock:
            sess = {
                "session_id": session_id,
                "target_id": self.target_id,
                "access_level": access_level,
                "state": "ACTIVE",
                "from_node": from_node,
            }
            self.sessions[session_id] = sess
            return dict(sess)

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self.lock:
            sess = self.sessions.get(session_id)
            return dict(sess) if sess else None

    def has_active_session(self, min_access: str = "NONE") -> bool:
        hierarchy = {"NONE": 0, "FOOTHOLD": 1, "USER": 2, "PRIVILEGED": 3, "SYSTEM": 4}
        req_level = hierarchy.get(min_access.upper(), 0)
        with self.lock:
            for s in self.sessions.values():
                if s.get("state") == "ACTIVE":
                    curr_level = hierarchy.get(s.get("access_level", "NONE").upper(), 0)
                    if curr_level >= req_level:
                        return True
            return False

    def get_active_session(self) -> dict[str, Any] | None:
        with self.lock:
            for s in self.sessions.values():
                if s.get("state") == "ACTIVE":
                    return dict(s)
            return None


class BaseEnterpriseHandler(BaseHTTPRequestHandler):
    """Base HTTP handler providing bounded JSON request/response handling."""

    server_version = "MiniEnterpriseLiveRange/1.0"
    target_state: TargetState

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress noisy stdout during automated tests
        pass

    def _send_json(self, status: int, data: Mapping[str, Any]) -> None:
        encoded = json.dumps(dict(data), sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _read_body_json(self) -> dict[str, Any]:
        length_header = self.headers.get("Content-Length", "0")
        try:
            length = int(length_header)
        except ValueError:
            length = 0
        if length <= 0 or length > 65536:
            return {}
        try:
            raw = self.rfile.read(length)
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def _handle_relay(self) -> None:
        """Relay bounded request through this pivot host to an onward target.

        Enforces:
          1. Fixed source/destination/port/method/path policy before DNS or network I/O.
          2. Foothold requirement: Node must have active session to permit outbound relaying
             (except for bounded lab lifecycle operations).
          3. Physical/wire-level network boundary: Connection is made from inside the container's
             network namespace using standard HTTPConnection to the onward container hostname.
          4. Fail-closed error mapping: If an approved onward host is unroutable, socket failure
             is mapped to 403 NETWORK_ISOLATION_BARRIER.
        """
        body = self._read_body_json()
        relay_request, rejection = _validate_relay_request(self.target_state.target_id, body)
        if rejection is not None:
            status, error, message = rejection
            self._send_json(status, {
                "outcome": "DENIED",
                "status_code": status,
                "error": error,
                "message": message,
            })
            return

        if relay_request is None:
            self._send_json(400, {
                "outcome": "DENIED",
                "status_code": 400,
                "error": "INVALID_RELAY_REQUEST",
                "message": "Relay request could not be canonicalized",
            })
            return
        target_host = relay_request["target_host"]
        target_port = relay_request["target_port"]
        fwd_method = relay_request["method"]
        fwd_path = relay_request["path"]
        fwd_body = relay_request["body"]

        # Verification of active session (foothold) on this pivot host for operational actions
        is_admin_lifecycle = (
            fwd_path == "/health"
            or (
                fwd_path == "/api/v1/relay"
                and isinstance(fwd_body, dict)
                and fwd_body.get("path") == "/health"
            )
        )
        if not is_admin_lifecycle and not self.target_state.has_active_session("FOOTHOLD"):
            self._send_json(403, {
                "outcome": "DENIED",
                "status_code": 403,
                "error": "PIVOT_SOURCE_UNAUTHORIZED",
                "message": f"Source node '{self.target_state.target_id}' has no active session to route traffic",
            })
            return

        conn: http.client.HTTPConnection | None = None
        try:
            conn = _open_relay_connection(target_host, target_port, timeout=3.0)
            encoded = json.dumps(fwd_body or {}).encode("utf-8") if fwd_method in ("POST", "PUT") else None
            headers = {"Content-Type": "application/json"} if encoded else {}
            if encoded:
                headers["Content-Length"] = str(len(encoded))
            conn.request(fwd_method, fwd_path, body=encoded, headers=headers)
            resp = conn.getresponse()
            raw_data = resp.read()
            try:
                data = json.loads(raw_data.decode("utf-8"))
            except Exception:
                data = {"raw_text": raw_data.decode("utf-8", errors="replace")}
            data["http_status"] = resp.status
            self._send_json(resp.status, data)
        except Exception:
            self._send_json(403, {
                "outcome": "DENIED",
                "status_code": 403,
                "error": "NETWORK_ISOLATION_BARRIER",
                "message": "Approved relay destination is unreachable from the source zone",
            })
        finally:
            if conn is not None:
                conn.close()


class DMZServiceHandler(BaseEnterpriseHandler):
    """Zone A — DMZ Edge Web Portal / Ingress Service."""

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/health":
            self._send_json(200, {
                "status": "ok",
                "target_id": self.target_state.target_id,
                "zone": "ZONE_DMZ",
                "reset_count": self.target_state.reset_count,
            })
            return

        if path in ("/", "/api/v1/discovery"):
            self._send_json(200, {
                "status": "ok",
                "target_id": self.target_state.target_id,
                "services": [
                    {
                        "host": self.target_state.target_id,
                        "port": 8080,
                        "service": "http-edge-portal",
                        "endpoint": "/api/v1/auth/foothold",
                        "confidence": 1.0,
                    }
                ],
            })
            return

        if path == "/api/v1/system/recon":
            if not self.target_state.has_active_session("FOOTHOLD"):
                self._send_json(403, {"error": "SESSION_REQUIRED", "message": "Host recon requires active session"})
                return

            # Expose internal reachability observed from DMZ
            self._send_json(200, {
                "status": "ok",
                "target_id": self.target_state.target_id,
                "reachable_hosts": [
                    {
                        "from_host": self.target_state.target_id,
                        "to_host": "lab-enterprise-internal",
                        "protocol": "tcp",
                        "port": 8080,
                        "confidence": 1.0,
                    }
                ],
            })
            return

        self._send_json(404, {"error": "NOT_FOUND"})

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/v1/relay":
            self._handle_relay()
            return

        if path == "/api/v1/auth/foothold":
            # Bounded challenge / initial foothold (matches canonical ACTION-FOOTHOLD-001 potential_access_level=USER)
            sess = self.target_state.add_session(
                session_id=f"SESS-LIVE-DMZ-{self.target_state.reset_count:02d}",
                access_level="USER",
            )
            self._send_json(200, {
                "status": "ok",
                "outcome": "SUCCESS",
                "target_id": self.target_state.target_id,
                "access_level": "USER",
                "session": sess,
            })
            return

        if path == "/api/v1/credentials/harvest":
            if not self.target_state.has_active_session("FOOTHOLD"):
                self._send_json(403, {"error": "SESSION_REQUIRED", "message": "Credential discovery requires active session"})
                return

            # Synthetic credential for Zone B (Internal)
            self._send_json(200, {
                "status": "ok",
                "outcome": "SUCCESS",
                "target_id": self.target_state.target_id,
                "credentials": [
                    {
                        "principal": "svc_internal",
                        "credential_kind": "BEARER_TOKEN",
                        "observed_scope": "lab-enterprise-internal",
                        "validity_state": "VALID",
                        "secret_token": SYNTHETIC_LAB_SECRETS["svc_internal"],
                    }
                ],
            })
            return

        self._send_json(404, {"error": "NOT_FOUND"})


class InternalServiceHandler(BaseEnterpriseHandler):
    """Zone B — Internal Corporate Application & Identity Service."""

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/health":
            self._send_json(200, {
                "status": "ok",
                "target_id": self.target_state.target_id,
                "zone": "ZONE_INTERNAL",
                "reset_count": self.target_state.reset_count,
            })
            return

        if path in ("/", "/api/v1/discovery"):
            self._send_json(200, {
                "status": "ok",
                "target_id": self.target_state.target_id,
                "services": [
                    {
                        "host": self.target_state.target_id,
                        "port": 8080,
                        "service": "http-internal-app",
                        "endpoint": "/api/v1/pivot",
                        "confidence": 1.0,
                    }
                ],
            })
            return

        if path == "/api/v1/system/recon":
            if not self.target_state.has_active_session("USER"):
                self._send_json(403, {"error": "SESSION_REQUIRED", "message": "Host recon requires active session"})
                return

            # Expose reachability to Restricted Vault and Decoy
            self._send_json(200, {
                "status": "ok",
                "target_id": self.target_state.target_id,
                "reachable_hosts": [
                    {
                        "from_host": self.target_state.target_id,
                        "to_host": "lab-enterprise-restricted",
                        "protocol": "tcp",
                        "port": 8080,
                        "confidence": 1.0,
                    },
                    {
                        "from_host": self.target_state.target_id,
                        "to_host": "lab-enterprise-decoy",
                        "protocol": "tcp",
                        "port": 8080,
                        "confidence": 0.85,
                    },
                ],
            })
            return

        self._send_json(404, {"error": "NOT_FOUND"})

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/v1/relay":
            self._handle_relay()
            return

        if path == "/api/v1/pivot":
            body = self._read_body_json()
            from_node = body.get("from_node_id")
            route_name = body.get("route", "primary")

            # Check if this route is blocked (for L2 replan testing)
            if route_name in self.target_state.blocked_routes or "primary" in self.target_state.blocked_routes:
                self._send_json(403, {
                    "outcome": "DENIED",
                    "signal_type": "WAF_REJECTION",
                    "status_code": 403,
                    "observable_event": "Pivot blocked by internal segmentation rule",
                    "error": "ROUTE_BLOCKED",
                })
                return

            # Must originate from DMZ
            if from_node != "lab-enterprise-dmz":
                self._send_json(403, {
                    "outcome": "DENIED",
                    "error": "ZONE_VIOLATION",
                    "message": "Pivot must originate from authorized DMZ node",
                })
                return

            sess = self.target_state.add_session(
                session_id=f"SESS-LIVE-INT-{self.target_state.reset_count:02d}",
                access_level="USER",
                from_node=from_node,
            )
            self._send_json(200, {
                "status": "ok",
                "outcome": "SUCCESS",
                "target_id": self.target_state.target_id,
                "access_level": "USER",
                "session": sess,
            })
            return

        if path == "/api/v1/auth/privesc":
            if not self.target_state.has_active_session("USER"):
                self._send_json(403, {"error": "SESSION_REQUIRED", "message": "Privilege escalation requires active user session"})
                return

            if self.target_state.has_active_session("PRIVILEGED"):
                self._send_json(400, {
                    "status": "error",
                    "outcome": "FAILURE",
                    "error": "ALREADY_PRIVILEGED",
                    "message": "Host already has active privileged session",
                })
                return

            sess = self.target_state.add_session(
                session_id=f"SESS-LIVE-INT-PRIV-{self.target_state.reset_count:02d}",
                access_level="PRIVILEGED",
            )
            self._send_json(200, {
                "status": "ok",
                "outcome": "SUCCESS",
                "target_id": self.target_state.target_id,
                "access_level": "PRIVILEGED",
                "session": sess,
            })
            return

        if path == "/api/v1/credentials/harvest":
            if not self.target_state.has_active_session("USER"):
                self._send_json(403, {"error": "SESSION_REQUIRED", "message": "Credential discovery requires active session"})
                return

            self._send_json(200, {
                "status": "ok",
                "outcome": "SUCCESS",
                "target_id": self.target_state.target_id,
                "credentials": [
                    {
                        "principal": "vault_admin",
                        "credential_kind": "API_KEY_HANDLE",
                        "observed_scope": "lab-enterprise-restricted",
                        "validity_state": "VALID",
                        "secret_token": SYNTHETIC_LAB_SECRETS["vault_admin"],
                    }
                ],
            })
            return

        self._send_json(404, {"error": "NOT_FOUND"})


class RestrictedServiceHandler(BaseEnterpriseHandler):
    """Zone C — Restricted Crown-Jewel Vault Service."""

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/health":
            self._send_json(200, {
                "status": "ok",
                "target_id": self.target_state.target_id,
                "zone": "ZONE_RESTRICTED",
                "reset_count": self.target_state.reset_count,
            })
            return

        if path in ("/", "/api/v1/discovery"):
            self._send_json(200, {
                "status": "ok",
                "target_id": self.target_state.target_id,
                "services": [
                    {
                        "host": self.target_state.target_id,
                        "port": 8080,
                        "service": "http-crown-jewel-vault",
                        "endpoint": "/api/v1/vault/objective",
                        "confidence": 1.0,
                    }
                ],
            })
            return

        self._send_json(404, {"error": "NOT_FOUND"})

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/v1/pivot":
            body = self._read_body_json()
            from_node = body.get("from_node_id")

            # Must originate from Internal zone
            if from_node != "lab-enterprise-internal":
                self._send_json(403, {
                    "outcome": "DENIED",
                    "error": "ZONE_VIOLATION",
                    "message": "Pivot to restricted vault must originate from authorized internal node",
                })
                return

            sess = self.target_state.add_session(
                session_id=f"SESS-LIVE-RESTRICTED-{self.target_state.reset_count:02d}",
                access_level="USER",
                from_node=from_node,
            )
            self._send_json(200, {
                "status": "ok",
                "outcome": "SUCCESS",
                "target_id": self.target_state.target_id,
                "access_level": "USER",
                "session": sess,
            })
            return

        if path == "/api/v1/vault/objective":
            if not self.target_state.has_active_session("USER"):
                self._send_json(403, {"error": "SESSION_REQUIRED", "message": "Objective access requires active session"})
                return

            self._send_json(200, {
                "status": "ok",
                "outcome": "SUCCESS",
                "target_id": self.target_state.target_id,
                "objective": {
                    "objective_id": "OBJ-ENTERPRISE-MISSION",
                    "status": "ACHIEVED",
                    "milestone": "FLAG_RETRIEVED",
                    "evidence_ref": "EVID-VAULT-ACCESS-OK",
                },
            })
            return

        self._send_json(404, {"error": "NOT_FOUND"})


class DecoyServiceHandler(BaseEnterpriseHandler):
    """Zone D — Decoy Honeypot Service."""

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/health":
            self._send_json(200, {
                "status": "ok",
                "target_id": self.target_state.target_id,
                "zone": "ZONE_DECOY",
                "reset_count": self.target_state.reset_count,
            })
            return

        # Any probe triggers observable defensive signal
        self._send_json(403, {
            "status": "DENIED",
            "signal_type": "AUTH_LOCKOUT",
            "status_code": 403,
            "observable_event": "Security alert: unauthorized probe detected on decoy honeypot",
        })

    def do_POST(self) -> None:
        # Any action on decoy is rejected and alerted
        self._send_json(403, {
            "outcome": "DENIED",
            "signal_type": "AUTH_LOCKOUT",
            "status_code": 403,
            "observable_event": "Account lockout triggered on decoy branch",
        })


class CleanControlServiceHandler(BaseEnterpriseHandler):
    """Clean Baseline Control Service — Contains zero exploitable vulnerabilities."""

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/health":
            self._send_json(200, {
                "status": "ok",
                "target_id": self.target_state.target_id,
                "zone": "ZONE_CLEAN",
                "reset_count": self.target_state.reset_count,
            })
            return

        if path in ("/", "/api/v1/discovery"):
            self._send_json(200, {
                "status": "ok",
                "target_id": self.target_state.target_id,
                "services": [
                    {
                        "host": self.target_state.target_id,
                        "port": 8080,
                        "service": "http-clean-baseline",
                        "endpoint": "/api/v1/info",
                        "confidence": 1.0,
                    }
                ],
            })
            return

        # Secure: No sensitive endpoints, no reachability leaks
        self._send_json(200, {
            "status": "ok",
            "target_id": self.target_state.target_id,
            "message": "Secure baseline service running normally",
        })

    def do_POST(self) -> None:
        # All attack actions cleanly fail without granting sessions or credentials
        self._send_json(200, {
            "status": "ok",
            "outcome": "FAILURE",
            "target_id": self.target_state.target_id,
            "message": "Input rejected by secure validation filter",
        })
