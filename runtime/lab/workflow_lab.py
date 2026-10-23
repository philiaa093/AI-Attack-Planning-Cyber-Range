"""Switch a stopped lab to an isolated volume clone, then restore original services."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from runtime.lab.external_scanners import load_config, image_identity

ROOT = Path(__file__).resolve().parents[2]
SERVICES = ["lab-ecommerce", "gateway-ecommerce"]


def docker(*args):
    result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise RuntimeError("WORKFLOW_DOCKER_OPERATION_FAILED")
    return result.stdout.strip()


class WorkflowLab:
    def __init__(self, run_id, recorder):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", run_id):
            raise ValueError("WORKFLOW_RUN_INVALID")
        self.run_id, self.recorder = run_id, recorder
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

    def record(self, phase, **details):
        self.recorder.persist_phase_artifact("workflow_" + phase, {
            "run_id": self.run_id, "source": "ISOLATED_WORKFLOW_COORDINATOR",
            "expected_state": phase.upper(), "observed_state": phase.upper(), **details})

    def volume_operation(self, operation):
        mounts = ["--mount", f"type=volume,source={self.source},target=/source,readonly",
                  "--mount", f"type=bind,source={ROOT / 'cyber-range/runtime/workflow_volume.py'},target=/helper.py,readonly"]
        if operation == "snapshot":
            mounts += ["--mount", f"type=volume,source={self.volume},target=/clone"]
        return json.loads(docker("run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", *mounts, self.helper, "python", "-B", "/helper.py", operation))["sha256"]

    def __enter__(self):
        fd = os.open(self.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        self.owned = True
        with os.fdopen(fd, "w") as stream:
            json.dump({"run_id": self.run_id, "project": self.project, "volume": self.volume}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        try:
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
        docker(*self.clone, "exec", "-T", "lab-ecommerce", "python", "-B", "/workflow_volume.py", "promote", username)
        self.record("admin_provisioned", role="admin", account_alias="c")

    def __exit__(self, *exc):
        self.active = False
        if not self.owned:
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
