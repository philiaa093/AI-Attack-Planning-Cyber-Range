"""Bounded GNS3 controller client for an approved remote project."""
from __future__ import annotations

import base64
from typing import Mapping
from urllib.parse import quote, urlsplit

from runtime.lab.providers import JsonTransport, UrllibJsonTransport, require_status
from runtime.lab.range_provider import RangeProviderError
from runtime.lab.remote_range_config import GNS3RemoteConfig, resolve_basic_credentials


class GNS3ProjectClient:
    """Expose only project/node lifecycle operations required by RT-06P."""

    def __init__(
        self,
        config: GNS3RemoteConfig,
        *,
        transport: JsonTransport | None = None,
        environ: Mapping[str, str] | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.config = config
        hostname = urlsplit(config.base_url).hostname
        self.transport = transport or UrllibJsonTransport(
            allowed_hosts=frozenset({hostname}) if hostname else frozenset(),
        )
        self.environ = environ
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        username, password = resolve_basic_credentials(
            self.config.username_env,
            self.config.password_env,
            self.environ,
        )
        encoded = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {encoded}"}

    def _url(self, suffix: str) -> str:
        project_id = quote(self.config.project_id, safe="")
        return f"{self.config.base_url}/v2/projects/{project_id}{suffix}"

    def open_project(self) -> None:
        response = self.transport.request(
            "POST",
            self._url("/open"),
            headers=self._headers(),
            timeout=self.timeout,
        )
        require_status(response, frozenset({200, 201, 204}), "GNS3_PROJECT_OPEN_FAILED")

    def close_project(self) -> None:
        response = self.transport.request(
            "POST",
            self._url("/close"),
            headers=self._headers(),
            timeout=self.timeout,
        )
        require_status(response, frozenset({200, 201, 204}), "GNS3_PROJECT_CLOSE_FAILED")

    def start_node(self, node_id: str) -> None:
        if not node_id:
            raise RangeProviderError("GNS3_NODE_ID_INVALID", "Node ID is required")
        response = self.transport.request(
            "POST",
            self._url(f"/nodes/{quote(node_id, safe='')}/start"),
            headers=self._headers(),
            timeout=self.timeout,
        )
        require_status(response, frozenset({200, 201, 204}), "GNS3_NODE_START_FAILED")

    def stop_node(self, node_id: str) -> None:
        if not node_id:
            raise RangeProviderError("GNS3_NODE_ID_INVALID", "Node ID is required")
        response = self.transport.request(
            "POST",
            self._url(f"/nodes/{quote(node_id, safe='')}/stop"),
            headers=self._headers(),
            timeout=self.timeout,
        )
        require_status(response, frozenset({200, 201, 204}), "GNS3_NODE_STOP_FAILED")

    def node_started(self, node_id: str) -> bool:
        response = self.transport.request(
            "GET",
            self._url(f"/nodes/{quote(node_id, safe='')}"),
            headers=self._headers(),
            timeout=self.timeout,
        )
        require_status(response, frozenset({200}), "GNS3_NODE_STATUS_FAILED")
        return isinstance(response.body, dict) and response.body.get("status") == "started"
