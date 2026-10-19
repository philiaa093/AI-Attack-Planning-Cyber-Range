"""Offline checks for shared lab controls; Docker and transport remain mocked."""
import ast
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from runtime.evidence.discovery_recorder import EvidenceFailure
from runtime.lab import control_support as lab


class ControlSupportTests(unittest.TestCase):
    def test_backend_import_boundary(self):
        for relative in ("dashboards/app/backend/run_manager.py", "dashboards/app/backend/range_controller.py"):
            source = (lab.ROOT / relative).read_text(encoding="utf-8")
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, ast.Import):
                    self.assertFalse(any(alias.name.startswith("scripts") for alias in node.names), relative)
                elif isinstance(node, ast.ImportFrom):
                    self.assertFalse((node.module or "").startswith("scripts"), relative)

    def test_fresh_import_has_no_path_process_or_network_side_effects(self):
        check = '''
import http.client
import importlib
import os
import socket
import subprocess
import sys
from unittest.mock import patch
before_path, before_sys_path = os.environ.get("PATH"), list(sys.path)
with patch.object(subprocess, "run", side_effect=AssertionError("process on import")), \\
     patch.object(subprocess, "Popen", side_effect=AssertionError("process on import")), \\
     patch.object(socket, "create_connection", side_effect=AssertionError("network on import")), \\
     patch.object(http.client, "HTTPConnection", side_effect=AssertionError("HTTP on import")), \\
     patch.object(http.client, "HTTPSConnection", side_effect=AssertionError("HTTPS on import")):
    importlib.import_module("runtime.lab.control_support")
assert os.environ.get("PATH") == before_path
assert sys.path == before_sys_path
'''
        result = subprocess.run([sys.executable, "-B", "-c", check], cwd=lab.ROOT,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_docker_resolves_path_only_when_called_and_keeps_bounded_argv(self):
        with patch.object(lab, "_ensure_docker_on_path") as resolve, \
             patch.object(lab.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="local")) as run:
            self.assertEqual(lab.docker("version"), "local")
        resolve.assert_called_once_with()
        run.assert_called_once_with(["docker", "version"], capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=60)

    def test_docker_errors_do_not_leak_configuration(self):
        for result in (SimpleNamespace(returncode=1, stderr="private configuration"),
                       OSError("private configuration"), subprocess.TimeoutExpired("docker", 60)):
            kwargs = {"side_effect": result} if isinstance(result, Exception) else {"return_value": result}
            with self.subTest(result=type(result).__name__), \
                 patch.object(lab, "_ensure_docker_on_path"), patch.object(lab.subprocess, "run", **kwargs), \
                 self.assertRaises(lab.DemoBlocked) as caught:
                lab.docker("version")
            self.assertNotIn("private configuration", str(caught.exception))

    def test_start_rejects_changed_container_identity(self):
        prior = {"Id": "original", "State": {"Running": False}}
        after = {"Id": "replacement", "State": {"Running": True}}
        owned = {}
        with patch.object(lab, "service_snapshot", side_effect=[{lab.TARGET: prior}, {lab.TARGET: after}]), \
             patch.object(lab, "compose") as compose, \
             self.assertRaisesRegex(lab.DemoBlocked, "SERVICE_IDENTITY_CHANGED"):
            lab.start_services(owned)
        compose.assert_called_once_with("start", lab.TARGET)
        self.assertEqual(owned, {})

    def test_stop_empty_ownership_has_no_docker_calls(self):
        with patch.object(lab, "docker", side_effect=AssertionError("no owned service")), \
             patch.object(lab, "service_snapshot", side_effect=AssertionError("no owned service")):
            self.assertEqual(lab.stop_owned({}), "NOT_RUN_NO_OWNED_SERVICES")

    def test_stop_requires_observed_stopped_state(self):
        row = {"Id": "owned", "State": {"Running": True}}
        with patch.object(lab, "service_snapshot", return_value={lab.TARGET: row}), \
             patch.object(lab, "docker", side_effect=["", json.dumps([row])]) as docker, \
             self.assertRaisesRegex(lab.DemoBlocked, "SERVICE_STOP_UNVERIFIED"):
            lab.stop_owned({lab.TARGET: "owned"})
        self.assertEqual(docker.call_args_list[0].args, ("stop", "--time", "10", "owned"))

    def test_deny_records_in_order_with_zero_transport_and_no_console_output(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(lab, "OUTPUT", Path(directory)):
            recorder = lab.new_recorder(Path(directory) / "run", "RUN-SUPPORT-DENY")
            gate = lab.make_gate(recorder)
            output = io.StringIO()
            with contextlib.redirect_stdout(output), \
                 patch("runtime.safety.discovery_gate.http.client.HTTPConnection", side_effect=AssertionError("no HTTP")):
                result = lab.deny_case(gate, recorder)
            self.assertEqual(result["decision"], "DENIED")
            self.assertEqual(result["network_dispatch_delta"], 0)
            self.assertEqual(output.getvalue(), "")
            self.assertTrue(lab.verify(recorder)["passed"])
            # The verifier checks the authoritative intent/decision/result ordering.
            self.assertTrue(recorder.artifacts)

    def test_evidence_failure_stops_before_denied_dispatch(self):
        gate, recorder = Mock(), Mock()
        gate.effective_targets = {lab.TARGET}
        gate.action_allowlist = {lab.ACTION}
        gate.kill_switch.is_active.return_value = False
        gate.budget_tracker.can_request.return_value = True
        recorder.persist_phase_artifact.side_effect = EvidenceFailure("fixture write failure")
        with self.assertRaises(EvidenceFailure):
            lab.deny_case(gate, recorder)
        gate.dispatch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
