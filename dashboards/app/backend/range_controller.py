"""Cyber Range Controller wrapping isolated Docker Compose lifecycle with ownership tracking."""
from __future__ import annotations

from datetime import datetime, timezone
import http.client
from pathlib import Path
import sys
import threading
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.lab import control_support as lab
from dashboards.app.backend.models import RangeState, RangeStatus


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class RangeController:
    """Thread-safe controller for ShopLab services, reusing shared lab orchestration."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._owned: Dict[str, str] = {}
        self.target_id: str = lab.TARGET
        self.origin: str = lab.ORIGIN

    @property
    def owned_services(self) -> Dict[str, str]:
        with self._lock:
            return dict(self._owned)

    def probe_http_health(self) -> Dict[str, Any]:
        """Perform loopback HTTP health check on Gateway."""
        try:
            conn = http.client.HTTPConnection("127.0.0.1", 18088, timeout=3.0)
            conn.request("GET", "/health")
            res = conn.getresponse()
            status = res.status
            body = res.read(1024).decode("utf-8", errors="replace")
            conn.close()
            return {
                "accessible": True,
                "status_code": status,
                "healthy": (status == 200),
                "body": body,
            }
        except Exception as exc:
            return {
                "accessible": False,
                "status_code": 0,
                "healthy": False,
                "error": type(exc).__name__,
            }

    def get_status(self) -> RangeStatus:
        """Query real container status and gateway health without faking state."""
        checked_at = _utc_now_iso()
        with self._lock:
            try:
                snapshot = lab.service_snapshot()
            except lab.DemoBlocked as exc:
                return RangeStatus(
                    status=RangeState.UNAVAILABLE,
                    target_id=self.target_id,
                    origin=self.origin,
                    services={},
                    message=f"DEMO_BLOCKED: {exc}",
                    checked_at_utc=checked_at,
                )
            except Exception as exc:
                return RangeStatus(
                    status=RangeState.UNAVAILABLE,
                    target_id=self.target_id,
                    origin=self.origin,
                    services={},
                    message=f"UNAVAILABLE: {type(exc).__name__}",
                    checked_at_utc=checked_at,
                )

            # Analyze service rows
            services_info: Dict[str, Any] = {}
            all_running = True
            any_running = False

            for svc in lab.SERVICES:
                row = snapshot.get(svc)
                if row:
                    running = row.get("State", {}).get("Running", False)
                    status_str = row.get("State", {}).get("Status", "unknown")
                    services_info[svc] = {
                        "id": row.get("Id", "")[:12],
                        "running": running,
                        "status": status_str,
                    }
                    if running:
                        any_running = True
                    else:
                        all_running = False
                else:
                    services_info[svc] = {"running": False, "status": "stopped"}
                    all_running = False

            if not any_running:
                return RangeStatus(
                    status=RangeState.STOPPED,
                    target_id=self.target_id,
                    origin=self.origin,
                    services=services_info,
                    message="All lab services stopped",
                    checked_at_utc=checked_at,
                )

            # If services are reported running, verify runtime isolation and probe HTTP health
            try:
                lab.inspect_runtime(snapshot)
            except lab.DemoBlocked as exc:
                return RangeStatus(
                    status=RangeState.UNHEALTHY,
                    target_id=self.target_id,
                    origin=self.origin,
                    services=services_info,
                    message=f"ISOLATION_VIOLATION: {exc}",
                    checked_at_utc=checked_at,
                )

            probe = self.probe_http_health()
            if probe.get("healthy"):
                return RangeStatus(
                    status=RangeState.HEALTHY,
                    target_id=self.target_id,
                    origin=self.origin,
                    services=services_info,
                    message="Services running and HTTP health endpoint 200 OK",
                    checked_at_utc=checked_at,
                )
            else:
                return RangeStatus(
                    status=RangeState.UNHEALTHY,
                    target_id=self.target_id,
                    origin=self.origin,
                    services=services_info,
                    message=f"HTTP probe unready: status_code={probe.get('status_code')}",
                    checked_at_utc=checked_at,
                )

    def start(self) -> RangeStatus:
        """Start project services (lab-ecommerce and gateway-ecommerce) with ownership tracking."""
        with self._lock:
            try:
                lab.start_services(self._owned)
            except lab.DemoBlocked as exc:
                return RangeStatus(
                    status=RangeState.UNAVAILABLE,
                    target_id=self.target_id,
                    origin=self.origin,
                    services={},
                    message=f"START_FAILED: {exc}",
                    checked_at_utc=_utc_now_iso(),
                )
            except Exception as exc:
                return RangeStatus(
                    status=RangeState.UNAVAILABLE,
                    target_id=self.target_id,
                    origin=self.origin,
                    services={},
                    message=f"START_ERROR: {type(exc).__name__}",
                    checked_at_utc=_utc_now_iso(),
                )

        return self.get_status()

    def stop_owned(self) -> RangeStatus:
        """Stop only services owned by this process/controller, preserving volumes."""
        with self._lock:
            if not self._owned:
                return RangeStatus(
                    status=RangeState.STOPPED,
                    target_id=self.target_id,
                    origin=self.origin,
                    services={},
                    message="No owned services to stop",
                    checked_at_utc=_utc_now_iso(),
                )

            try:
                res = lab.stop_owned(self._owned)
                self._owned.clear()
            except lab.DemoBlocked as exc:
                return RangeStatus(
                    status=RangeState.UNKNOWN,
                    target_id=self.target_id,
                    origin=self.origin,
                    services={},
                    message=f"STOP_FAILED: {exc}",
                    checked_at_utc=_utc_now_iso(),
                )
            except Exception as exc:
                return RangeStatus(
                    status=RangeState.UNKNOWN,
                    target_id=self.target_id,
                    origin=self.origin,
                    services={},
                    message=f"STOP_ERROR: {type(exc).__name__}",
                    checked_at_utc=_utc_now_iso(),
                )

        return self.get_status()
