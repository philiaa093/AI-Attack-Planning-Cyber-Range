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
          1. Foothold requirement: Node must have active session to permit outbound relaying
             (except for lab lifecycle /reset).
          2. Physical/wire-level network boundary: Connection is made from inside the container's
             network namespace using standard HTTPConnection to the onward container hostname.
          3. Fail-closed error mapping: If onward host is unroutable (e.g. DMZ attempting direct
             connection to RESTRICTED across unjoined networks), socket failure is mapped to 403
             NETWORK_ISOLATION_BARRIER.
        """
        body = self._read_body_json()
        target_host = body.get("target_host")
        target_port = int(body.get("target_port", 8080))
        fwd_method = body.get("method", "GET").upper()
        fwd_path = body.get("path", "/")
        fwd_body = body.get("body")

        if not target_host or not fwd_path.startswith("/"):
            self._send_json(400, {
                "outcome": "DENIED",
                "status_code": 400,
                "error": "INVALID_RELAY_REQUEST",
                "message": "target_host and valid path starting with / are required",
            })
            return

        # Verification of active session (foothold) on this pivot host for operational actions
        is_admin_lifecycle = (
            fwd_path in ("/health", "/reset", "/api/v1/admin/block_route", "/api/v1/admin/unblock_route")
            or (fwd_path == "/api/v1/relay" and isinstance(fwd_body, dict) and fwd_body.get("path") in ("/health", "/reset", "/api/v1/admin/block_route", "/api/v1/admin/unblock_route"))
        )
        if not is_admin_lifecycle and not self.target_state.has_active_session("FOOTHOLD"):
            self._send_json(403, {
                "outcome": "DENIED",
                "status_code": 403,
                "error": "PIVOT_SOURCE_UNAUTHORIZED",
                "message": f"Source node '{self.target_state.target_id}' has no active session to route traffic",
            })
            return

        import http.client
        try:
            conn = http.client.HTTPConnection(target_host, target_port, timeout=3.0)
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
            conn.close()
        except Exception as exc:
            self._send_json(403, {
                "outcome": "DENIED",
                "status_code": 403,
                "error": "NETWORK_ISOLATION_BARRIER",
                "message": f"Network route to '{target_host}:{target_port}' is unreachable from '{self.target_state.target_id}': {exc}",
            })


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
        if path == "/reset":
            self.target_state.reset()
            self._send_json(200, {"status": "ok", "reset_count": self.target_state.reset_count})
            return

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
        if path == "/reset":
            self.target_state.reset()
            self._send_json(200, {"status": "ok", "reset_count": self.target_state.reset_count})
            return

        if path == "/api/v1/relay":
            self._handle_relay()
            return

        if path == "/api/v1/admin/block_route":
            body = self._read_body_json()
            route = body.get("route", "primary")
            with self.target_state.lock:
                self.target_state.blocked_routes.add(route)
            self._send_json(200, {"status": "ok", "blocked_routes": list(self.target_state.blocked_routes)})
            return

        if path == "/api/v1/admin/unblock_route":
            body = self._read_body_json()
            route = body.get("route", "primary")
            with self.target_state.lock:
                self.target_state.blocked_routes.discard(route)
            self._send_json(200, {"status": "ok", "blocked_routes": list(self.target_state.blocked_routes)})
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
        if path == "/reset":
            self.target_state.reset()
            self._send_json(200, {"status": "ok", "reset_count": self.target_state.reset_count})
            return

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
        path = urlsplit(self.path).path
        if path == "/reset":
            self.target_state.reset()
            self._send_json(200, {"status": "ok", "reset_count": self.target_state.reset_count})
            return

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
        path = urlsplit(self.path).path
        if path == "/reset":
            self.target_state.reset()
            self._send_json(200, {"status": "ok", "reset_count": self.target_state.reset_count})
            return

        # All attack actions cleanly fail without granting sessions or credentials
        self._send_json(200, {
            "status": "ok",
            "outcome": "FAILURE",
            "target_id": self.target_state.target_id,
            "message": "Input rejected by secure validation filter",
        })
