"""Bounded vSphere lifecycle client for approved enterprise-range VMs."""
from __future__ import annotations

import base64
import time
from typing import Mapping
from urllib.parse import quote, urlsplit

from runtime.lab.providers import JsonTransport, UrllibJsonTransport, require_status
from runtime.lab.range_provider import RangeProviderError
from runtime.lab.remote_range_config import VSphereRemoteConfig, resolve_basic_credentials


class VSphereLifecycleClient:
    """Power and baseline-revert operations with fixed vSphere API paths."""

    def __init__(
        self,
        config: VSphereRemoteConfig,
        *,
        transport: JsonTransport | None = None,
        environ: Mapping[str, str] | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.config = config
        hostname = urlsplit(config.base_url).hostname
        self.transport = transport or UrllibJsonTransport(
            allowed_hosts=frozenset({hostname}) if hostname else frozenset(),
        )
        self.environ = environ
        self.timeout = timeout
        self._session_id: str | None = None

    def _session(self) -> str:
        if self._session_id is not None:
            return self._session_id
        username, password = resolve_basic_credentials(
            self.config.username_env,
            self.config.password_env,
            self.environ,
        )
        encoded = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        response = self.transport.request(
            "POST",
            f"{self.config.base_url}/api/session",
            headers={"Authorization": f"Basic {encoded}"},
            timeout=self.timeout,
        )
        require_status(response, frozenset({200, 201}), "VSPHERE_SESSION_CREATE_FAILED")
        session_id = response.body
        if isinstance(session_id, dict):
            session_id = session_id.get("value")
        if not isinstance(session_id, str) or not session_id:
            raise RangeProviderError("VSPHERE_SESSION_INVALID", "vSphere returned no session identifier")
        self._session_id = session_id
        return session_id

    def _headers(self) -> dict[str, str]:
        return {"vmware-api-session-id": self._session()}

    def power_state(self, vm_id: str) -> str:
        response = self.transport.request(
            "GET",
            f"{self.config.base_url}/api/vcenter/vm/{quote(vm_id, safe='')}/power",
            headers=self._headers(),
            timeout=self.timeout,
        )
        require_status(response, frozenset({200}), "VSPHERE_POWER_STATUS_FAILED")
        state = response.body
        if isinstance(state, dict):
            state = state.get("state") or state.get("value")
        if not isinstance(state, str):
            raise RangeProviderError("VSPHERE_POWER_STATE_INVALID", "vSphere returned an invalid power state")
        return state.upper()

    def power_on(self, vm_id: str) -> None:
        if self.power_state(vm_id) == "POWERED_ON":
            return
        response = self.transport.request(
            "POST",
            f"{self.config.base_url}/api/vcenter/vm/{quote(vm_id, safe='')}/power?action=start",
            headers=self._headers(),
            timeout=self.timeout,
        )
        require_status(response, frozenset({200, 202, 204}), "VSPHERE_POWER_ON_FAILED")

    def power_off(self, vm_id: str) -> None:
        if self.power_state(vm_id) == "POWERED_OFF":
            return
        response = self.transport.request(
            "POST",
            f"{self.config.base_url}/api/vcenter/vm/{quote(vm_id, safe='')}/power?action=stop",
            headers=self._headers(),
            timeout=self.timeout,
        )
        require_status(response, frozenset({200, 202, 204}), "VSPHERE_POWER_OFF_FAILED")

    def revert_current_snapshot(self, vm_id: str) -> None:
        release = quote(self.config.api_release, safe=".")
        response = self.transport.request(
            "POST",
            (
                f"{self.config.base_url}/sdk/vim25/{release}/VirtualMachine/"
                f"{quote(vm_id, safe='')}/RevertToCurrentSnapshot_Task"
            ),
            headers=self._headers(),
            body={"suppressPowerOn": True},
            timeout=self.timeout,
        )
        require_status(response, frozenset({200, 201, 202}), "VSPHERE_SNAPSHOT_REVERT_FAILED")
        task_id = self._task_id(response.body)
        self._wait_for_task(task_id)

    @staticmethod
    def _task_id(body: object) -> str:
        task_id = body
        if isinstance(task_id, dict):
            task_id = task_id.get("value")
        if not isinstance(task_id, str) or not task_id:
            raise RangeProviderError(
                "VSPHERE_TASK_REFERENCE_INVALID",
                "vSphere returned no task reference for the snapshot restore",
            )
        return task_id

    def _wait_for_task(self, task_id: str) -> None:
        release = quote(self.config.api_release, safe=".")
        encoded_task_id = quote(task_id, safe="")
        deadline = time.monotonic() + self.timeout
        while True:
            response = self.transport.request(
                "GET",
                f"{self.config.base_url}/sdk/vim25/{release}/Task/{encoded_task_id}/info",
                headers=self._headers(),
                timeout=min(self.timeout, 10.0),
            )
            require_status(response, frozenset({200}), "VSPHERE_TASK_STATUS_FAILED")
            info = response.body
            if isinstance(info, dict) and isinstance(info.get("value"), dict):
                info = info["value"]
            if not isinstance(info, dict) or not isinstance(info.get("state"), str):
                raise RangeProviderError(
                    "VSPHERE_TASK_STATUS_INVALID",
                    "vSphere returned an invalid task state",
                )
            state = info["state"].lower()
            if state == "success":
                return
            if state == "error":
                raise RangeProviderError(
                    "VSPHERE_SNAPSHOT_REVERT_TASK_FAILED",
                    "vSphere snapshot restore task failed",
                )
            if state not in {"queued", "running"}:
                raise RangeProviderError(
                    "VSPHERE_TASK_STATUS_INVALID",
                    "vSphere returned an unknown task state",
                )
            if time.monotonic() >= deadline:
                raise RangeProviderError(
                    "VSPHERE_TASK_TIMEOUT",
                    "vSphere snapshot restore task did not complete in time",
                )
            time.sleep(min(0.25, max(deadline - time.monotonic(), 0.0)))
