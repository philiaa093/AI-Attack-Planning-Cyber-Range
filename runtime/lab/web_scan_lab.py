"""Disposable instances of the existing Web labs, with an internal target network."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import time
import uuid

from runtime.lab.control_support import docker

ROOT = Path(__file__).resolve().parents[2]
TARGETS = {
    "lab-webapp-a": (18085, "custom-webapp-a"),
    "lab-webapp-b": (18086, "custom-webapp-b"),
}


class WebScanLab:
    """Never adopt, stop, reset or mount data from an existing target instance."""

    def __init__(self, run_id, recorder, target_id, origin, *, cancelled=lambda: False):
        if (not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", run_id)
                or target_id not in TARGETS or recorder.run_id != run_id):
            raise ValueError("WEB_SCAN_LAB_SCOPE_INVALID")
        self.port, folder = TARGETS[target_id]
        if origin != f"http://127.0.0.1:{self.port}":
            raise ValueError("WEB_SCAN_LAB_SCOPE_INVALID")
        self.run_id, self.recorder, self.target_id = run_id, recorder, target_id
        self.cancelled = cancelled
        self.source = ROOT / "cyber-range" / "targets" / folder / "app.py"
        self.key = "webscan-" + uuid.uuid4().hex
        self.label = "webscan.owner=" + self.key
        self.resources = []

    def record(self, phase, **details):
        self.recorder.persist_phase_artifact("scan_lab_" + phase, {
            "run_id": self.run_id, "target_id": self.target_id,
            "provider": "DISPOSABLE_DOCKER", **details,
        }, source="OPERATOR", expected_state=phase.upper(), observed_state=phase.upper())

    def check_cancelled(self):
        if self.cancelled():
            raise RuntimeError("WEB_SCAN_LAB_CANCELLED")

    def create(self, kind, *args):
        self.check_cancelled()
        identity = docker(*args).strip()
        if not re.fullmatch(r"[a-f0-9]{64}", identity):
            raise RuntimeError("WEB_SCAN_LAB_RESOURCE_INVALID")
        self.resources.append((kind, identity))
        return identity

    def inspect_container(self, identity):
        info = json.loads(docker("inspect", identity))[0]
        if info.get("Id") != identity or info.get("Config", {}).get("Labels", {}).get("webscan.owner") != self.key:
            raise RuntimeError("WEB_SCAN_LAB_OWNERSHIP_INVALID")
        return info

    def __enter__(self):
        try:
            self.check_cancelled()
            images = json.loads(docker("image", "inspect", "cyber-range-" + self.target_id + ":latest",
                                       "cyber-range-gateway:latest"))
            if len(images) != 2 or any(not re.fullmatch(r"sha256:[a-f0-9]{64}", row.get("Id", "")) for row in images):
                raise RuntimeError("WEB_SCAN_LAB_IMAGE_INVALID")
            if self.source.is_symlink() or not self.source.is_file():
                raise RuntimeError("WEB_SCAN_LAB_SOURCE_INVALID")
            self.record("intent", owner=self.key, images=[row["Id"] for row in images],
                        source_sha256=hashlib.sha256(self.source.read_bytes()).hexdigest())
            internal = self.create("network", "network", "create", "--internal", "--label", self.label, self.key + "-lab")
            ingress = self.create("network", "network", "create", "--label", self.label, self.key + "-ingress")
            common = ["create", "--pull", "never", "--label", self.label, "--read-only", "--cap-drop", "ALL",
                      "--security-opt", "no-new-privileges", "--user", "65534:65534", "--memory", "128m",
                      "--cpus", "0.5", "--pids-limit", "64", "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m"]
            target = self.create("container", *common, "--name", self.key + "-target", "--network", internal,
                                 "--network-alias", self.target_id,
                                 "--mount", f"type=bind,source={self.source},target=/app/app.py,readonly",
                                 "--env", "TARGET_ID=" + self.target_id, "--env", "PORT=8080", images[0]["Id"])
            gateway = self.create("container", *common, "--name", self.key + "-gateway", "--network", ingress,
                                  "--publish", f"127.0.0.1:{self.port}:8080",
                                  "--env", "TARGET_HOST=" + self.target_id, "--env", "TARGET_PORT=8080",
                                  "--env", "PORT=8080", images[1]["Id"])
            docker("network", "connect", internal, gateway)
            docker("start", target, gateway)
            target_info = self.inspect_container(target)
            gateway_info = self.inspect_container(gateway)
            target_networks = target_info["NetworkSettings"]["Networks"]
            gateway_networks = gateway_info["NetworkSettings"]["Networks"]
            network = json.loads(docker("network", "inspect", internal))[0]
            if (network.get("Id") != internal or network.get("Internal") is not True
                    or {row["NetworkID"] for row in target_networks.values()} != {internal}
                    or {row["NetworkID"] for row in gateway_networks.values()} != {internal, ingress}
                    or target_info["HostConfig"].get("PortBindings")
                    or gateway_info["HostConfig"].get("PortBindings") != {
                        "8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(self.port)}]}
                    or not target_info["State"]["Running"] or not gateway_info["State"]["Running"]):
                raise RuntimeError("WEB_SCAN_LAB_ISOLATION_INVALID")
            # Check process readiness locally; assessment traffic still goes through the gate.
            deadline = time.monotonic() + 10
            while True:
                self.check_cancelled()
                output = docker("exec", target, "python", "-B", "-c",
                    "import socket; s=socket.socket(); s.settimeout(0.2); "
                    "print(s.connect_ex(('127.0.0.1',8080))); s.close()")
                if output.strip() == "0":
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError("WEB_SCAN_LAB_START_TIMEOUT")
            self.record("started", target_container=target, gateway_container=gateway,
                        internal_network=internal, ingress_network=ingress)
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *exc):
        had_resources = bool(self.resources)
        while self.resources:
            kind, identity = self.resources[-1]
            if kind == "container":
                self.inspect_container(identity)
                docker("rm", "--force", identity)
            else:
                info = json.loads(docker("network", "inspect", identity))[0]
                if info.get("Id") != identity or info.get("Labels", {}).get("webscan.owner") != self.key:
                    raise RuntimeError("WEB_SCAN_LAB_OWNERSHIP_INVALID")
                docker("network", "rm", identity)
            self.resources.pop()
        if had_resources:
            self.record("restored", original_resources="UNTOUCHED", disposable_resources="REMOVED")
