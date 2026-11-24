"""Switch a stopped lab to an isolated volume clone, then restore original services."""
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request

from runtime.lab.external_scanners import load_config, image_identity

ROOT = Path(__file__).resolve().parents[2]
SERVICES = ["lab-ecommerce", "gateway-ecommerce"]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GNS3WorkflowControl:
    """Fixed-path management client; never exposed to planners or the data-plane gate."""

    def __init__(self, target_origin: str):
        target = urllib.parse.urlsplit(target_origin)
        default_url = f"{target.scheme}://{target.hostname}:8081"
        self.base_url = os.environ.get("SHOPLAB_GNS3_CONTROL_URL", default_url).rstrip("/")
        self.token = os.environ.get("SHOPLAB_GNS3_CONTROL_TOKEN", "")
        parsed = urllib.parse.urlsplit(self.base_url)
        try:
            address = ipaddress.ip_address(parsed.hostname or "")
        except ValueError as exc:
            raise RuntimeError("WORKFLOW_GNS3_CONTROL_INVALID") from exc
        if (parsed.scheme not in ("http", "https") or not (address.is_private or address.is_loopback)
                or parsed.hostname != target.hostname or parsed.username or parsed.password
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment
                or parsed.port in (None, target.port or 80)):
            raise RuntimeError("WORKFLOW_GNS3_CONTROL_INVALID")
        if not 32 <= len(self.token) <= 256 or any(ord(c) < 33 or ord(c) > 126 for c in self.token):
            raise RuntimeError("WORKFLOW_GNS3_CONTROL_AUTH_UNAVAILABLE")
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())

    def _call(self, path: str, payload: dict | None, expected: set[str]) -> dict:
        if path not in {
            "/control/v1/health", "/control/v1/workflow/snapshot",
            "/control/v1/workflow/promote", "/control/v1/workflow/restore",
        }:
            raise RuntimeError("WORKFLOW_GNS3_CONTROL_INVALID")
        data = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
        request = urllib.request.Request(self.base_url + path, data=data,
            method="GET" if payload is None else "POST",
            headers={"Authorization": "Bearer " + self.token,
                     **({"Content-Type": "application/json"} if data is not None else {})})
        try:
            with self.opener.open(request, timeout=10) as response:
                if response.status != 200:
                    raise RuntimeError("WORKFLOW_GNS3_CONTROL_FAILED")
                raw = response.read(4097)
        except (OSError, urllib.error.HTTPError, urllib.error.URLError) as exc:
            raise RuntimeError("WORKFLOW_GNS3_CONTROL_FAILED") from exc
        if len(raw) > 4096:
            raise RuntimeError("WORKFLOW_GNS3_CONTROL_FAILED")
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("WORKFLOW_GNS3_CONTROL_FAILED") from exc
        if type(value) is not dict or set(value) != expected:
            raise RuntimeError("WORKFLOW_GNS3_CONTROL_FAILED")
        return value

    def health(self) -> None:
        value = self._call("/control/v1/health", None, {"status", "service"})
        if value != {"status": "ok", "service": "workflow-control"}:
            raise RuntimeError("WORKFLOW_GNS3_CONTROL_FAILED")

    def snapshot(self, run_id: str) -> str:
        value = self._call("/control/v1/workflow/snapshot", {"run_id": run_id}, {"status", "sha256"})
        if value.get("status") != "snapshotted" or not re.fullmatch(r"[a-f0-9]{64}", value.get("sha256", "")):
            raise RuntimeError("WORKFLOW_GNS3_CONTROL_FAILED")
        return value["sha256"]

    def promote(self, run_id: str, username: str) -> None:
        value = self._call("/control/v1/workflow/promote", {"run_id": run_id, "username": username}, {"status"})
        if value != {"status": "promoted"}:
            raise RuntimeError("WORKFLOW_GNS3_CONTROL_FAILED")

    def restore(self, run_id: str) -> str:
        value = self._call("/control/v1/workflow/restore", {"run_id": run_id}, {"status", "sha256"})
        if value.get("status") != "restored" or not re.fullmatch(r"[a-f0-9]{64}", value.get("sha256", "")):
            raise RuntimeError("WORKFLOW_GNS3_CONTROL_FAILED")
        return value["sha256"]


def docker(*args):
    result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise RuntimeError("WORKFLOW_DOCKER_OPERATION_FAILED")
    return result.stdout.strip()


class WorkflowLab:
    def __init__(self, run_id, recorder, is_gns3: bool = False, target_origin: str | None = None):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", run_id):
            raise ValueError("WORKFLOW_RUN_INVALID")
        self.run_id, self.recorder = run_id, recorder
        self.is_gns3 = is_gns3 or (target_origin is not None and "10.0.0.2" in target_origin)
        self.target_origin = target_origin
        self.key = hashlib.sha256(run_id.encode()).hexdigest()[:12]
        self.project = "workflow" + self.key
        self.volume = self.project + "-data"
        self.lock = ROOT / "runtime" / ".workflow-lock.json"
        self.override = ROOT / "runtime" / (".workflow-" + self.key + ".json")
        self.compose = ["compose", "-f", str(ROOT / "cyber-range/compose.yaml")]
        self.clone = [*self.compose, "-p", self.project, "-f", str(self.override)]
        self.active = False
        self.stopped = False
        self.owned = False
        self.snapshot = None
        self.control = None

    def record(self, phase, **details):
        self.recorder.persist_phase_artifact("workflow_" + phase, {
            "run_id": self.run_id, "source": "ISOLATED_WORKFLOW_COORDINATOR",
            "expected_state": phase.upper(), "observed_state": phase.upper(), **details})

    def volume_operation(self, operation):
        capabilities = ["--cap-add", "CHOWN"] if operation == "snapshot" else []
        mounts = ["--mount", f"type=volume,source={self.source},target=/source,readonly",
                  "--mount", f"type=bind,source={ROOT / 'cyber-range/runtime/workflow_volume.py'},target=/helper.py,readonly"]
        if operation == "snapshot":
            mounts += ["--mount", f"type=volume,source={self.volume},target=/clone"]
        return json.loads(docker("run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
            *capabilities, "--security-opt", "no-new-privileges", *mounts, self.helper, "python", "-B", "/helper.py", operation))["sha256"]

    def __enter__(self):
        fd = os.open(self.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        self.owned = True
        with os.fdopen(fd, "w") as stream:
            json.dump({"run_id": self.run_id, "project": self.project, "volume": self.volume, "is_gns3": self.is_gns3}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            if self.is_gns3:
                self.record("snapshot_intent", target="gns3", origin=self.target_origin or "http://10.0.0.2:8080")
                self.control = GNS3WorkflowControl(self.target_origin or "http://10.0.0.2:8080")
                self.control.health()
                self.snapshot = self.control.snapshot(self.run_id)
                self.record("snapshot", sha256=self.snapshot, target="gns3", origin=self.target_origin or "http://10.0.0.2:8080")
                self.active = True
                self.record("control_ready", provider="GNS3", target="gns3")
                return self
            self.helper = image_identity(load_config()["bridge_image"])["id"]
            images = {}
            for service in SERVICES:
                identity = docker(*self.compose, "ps", "-q", service)
                if not re.fullmatch(r"[a-f0-9]{12,64}", identity):
                    raise RuntimeError("WORKFLOW_ORIGINAL_SERVICE_NOT_RUNNING")
                info = json.loads(docker("inspect", identity))[0]
                images[service] = info["Image"]
                if service == "lab-ecommerce":
                    mounts = [m for m in info["Mounts"] if m["Destination"] == "/app/data" and m["Type"] == "volume"]
                    if len(mounts) != 1:
                        raise RuntimeError("WORKFLOW_ORIGINAL_VOLUME_INVALID")
                    self.source = mounts[0]["Name"]
            if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]+", self.source) or self.source == self.volume:
                raise RuntimeError("WORKFLOW_VOLUME_INVALID")
            # Exclusive names: never adopt another run's existing clone.
            if self.volume in docker("volume", "ls", "--format", "{{.Name}}").splitlines():
                raise RuntimeError("WORKFLOW_CLONE_ALREADY_EXISTS")
            self.record("snapshot_intent", original_volume=self.source, clone_volume=self.volume)
            self.stopped = True
            docker(*self.compose, "stop", *reversed(SERVICES))
            docker("volume", "create", "--label", "workflow.run=" + self.run_id, self.volume)
            self.snapshot = self.volume_operation("snapshot")
            self.record("snapshot", sha256=self.snapshot, original_volume=self.source, clone_volume=self.volume)
            config = {"services": {service: {"image": image} for service, image in images.items()},
                      "volumes": {"ecommerce-data": {"name": self.volume, "external": True}}}
            config["services"]["lab-ecommerce"]["volumes"] = [
                {"type": "bind", "source": str(ROOT / "cyber-range/runtime/workflow_volume.py"),
                 "target": "/workflow_volume.py", "read_only": True}]
            with self.override.open("x", encoding="utf-8") as stream:
                json.dump(config, stream)
            docker(*self.clone, "up", "-d", "--no-deps", "--no-build", "--pull", "never", *SERVICES)
            clone_id = docker(*self.clone, "ps", "-q", "lab-ecommerce")
            clone_info = json.loads(docker("inspect", clone_id))[0]
            data_mounts = [m for m in clone_info["Mounts"] if m["Destination"] == "/app/data"]
            if len(data_mounts) != 1 or data_mounts[0].get("Name") != self.volume:
                raise RuntimeError("WORKFLOW_CLONE_MOUNT_MISMATCH")
            for network in clone_info["NetworkSettings"]["Networks"]:
                if not json.loads(docker("network", "inspect", network))[0].get("Internal"):
                    raise RuntimeError("WORKFLOW_CLONE_NETWORK_NOT_INTERNAL")
            self.active = True
            self.record("clone_started", project=self.project, clone_volume=self.volume)
            return self
        except Exception:
            self.__exit__(None, None, None)
            raise

    def promote(self, username):
        if not self.active or username != "rt_" + self.key + "_c":
            raise RuntimeError("WORKFLOW_ADMIN_SCOPE_INVALID")
        if self.is_gns3:
            if self.control is None:
                raise RuntimeError("WORKFLOW_GNS3_CONTROL_UNAVAILABLE")
            self.control.promote(self.run_id, username)
            self.record("admin_provisioned", role="admin", account_alias="c", provider="GNS3")
            return
        docker(*self.clone, "exec", "-T", "lab-ecommerce", "python", "-B", "/workflow_volume.py", "promote", username)
        self.record("admin_provisioned", role="admin", account_alias="c")

    def __exit__(self, *exc):
        self.active = False
        if not self.owned:
            return
        if self.is_gns3:
            if self.snapshot is None:
                if self.override.exists():
                    self.override.unlink()
                self.lock.unlink()
                self.owned = False
                return
            if self.control is None:
                raise RuntimeError("WORKFLOW_GNS3_RESTORE_UNAVAILABLE")
            restored = self.control.restore(self.run_id)
            if restored != self.snapshot:
                raise RuntimeError("WORKFLOW_GNS3_RESTORE_MISMATCH")
            self.record("restored", sha256=restored, target="gns3")
            if self.override.exists():
                self.override.unlink()
            self.lock.unlink()
            self.owned = False
            return
        # Failures retain the lock/override and cloned data for recovery; never delete a volume.
        if self.stopped:
            if self.override.exists():
                docker(*self.clone, "down", "--timeout", "10")
            if self.snapshot is not None and self.volume_operation("verify") != self.snapshot:
                raise RuntimeError("WORKFLOW_ORIGINAL_VOLUME_CHANGED")
            docker(*self.compose, "start", *SERVICES)
            ids = docker(*self.compose, "ps", "--status", "running", "--services").splitlines()
            if not set(SERVICES) <= set(ids):
                raise RuntimeError("WORKFLOW_RESTORE_SERVICES_FAILED")
            self.record("restored", sha256=self.snapshot, clone_volume_retained=self.volume)
        if self.override.exists():
            self.override.unlink()
        self.lock.unlink()
        self.owned = False
