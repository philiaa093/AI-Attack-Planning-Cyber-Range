"""Scope/ownership regressions and opt-in scans of disposable existing Web labs."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
import uuid

from dashboards.app.backend.coverage import build_coverage
from dashboards.app.backend.event_sink import EventSink
from dashboards.app.backend.models import AgentState, StartRunRequest
from dashboards.app.backend.run_manager import RunManager
from runtime.evidence.discovery_recorder import DurableEvidenceRecorder
from runtime.lab.web_scan_lab import WebScanLab


class WebScanLabTests(unittest.TestCase):
    def setUp(self):
        self.recorder = Mock(run_id="RUN-WEB-SCAN-UNIT")

    def test_scope_mismatch_rejected_before_docker(self):
        with patch("runtime.lab.web_scan_lab.docker") as docker:
            for target, origin in (("lab-ecommerce", "http://127.0.0.1:18088"),
                                   ("lab-webapp-a", "http://127.0.0.1:18086"),
                                   ("lab-webapp-b", "http://192.168.1.1:18086")):
                with self.subTest(target=target), self.assertRaises(ValueError):
                    WebScanLab(self.recorder.run_id, self.recorder, target, origin)
        docker.assert_not_called()

    def test_cancelled_setup_has_no_side_effects(self):
        lab = WebScanLab(self.recorder.run_id, self.recorder, "lab-webapp-a", "http://127.0.0.1:18085",
                         cancelled=lambda: True)
        with patch("runtime.lab.web_scan_lab.docker") as docker, self.assertRaisesRegex(RuntimeError, "CANCELLED"):
            lab.__enter__()
        docker.assert_not_called()
        self.recorder.persist_phase_artifact.assert_not_called()

    def test_cleanup_never_removes_resource_with_changed_owner(self):
        lab = WebScanLab(self.recorder.run_id, self.recorder, "lab-webapp-a", "http://127.0.0.1:18085")
        identity = "a" * 64
        lab.resources = [("container", identity)]
        other = {"Id": identity, "Config": {"Labels": {"webscan.owner": "another-run"}}}
        with patch("runtime.lab.web_scan_lab.docker", return_value=json.dumps([other])) as docker, \
             self.assertRaisesRegex(RuntimeError, "OWNERSHIP_INVALID"):
            lab.__exit__(None, None, None)
        self.assertEqual(docker.call_count, 1)
        self.assertEqual(lab.resources, [("container", identity)])
        self.recorder.persist_phase_artifact.assert_not_called()

    def test_cleanup_failure_retains_identity_and_cannot_record_restored(self):
        lab = WebScanLab(self.recorder.run_id, self.recorder, "lab-webapp-b", "http://127.0.0.1:18086")
        identity = "b" * 64
        lab.resources = [("network", identity)]
        info = {"Id": identity, "Labels": {"webscan.owner": lab.key}}
        with patch("runtime.lab.web_scan_lab.docker", side_effect=[json.dumps([info]), RuntimeError("fixture")]), \
             self.assertRaises(RuntimeError):
            lab.__exit__(None, None, None)
        self.assertEqual(len(lab.resources), 1)
        self.recorder.persist_phase_artifact.assert_not_called()

    def test_partial_setup_removes_only_created_network(self):
        lab = WebScanLab(self.recorder.run_id, self.recorder, "lab-webapp-a", "http://127.0.0.1:18085")
        identity = "c" * 64
        images = [{"Id": "sha256:" + "d" * 64}, {"Id": "sha256:" + "e" * 64}]
        info = {"Id": identity, "Labels": {"webscan.owner": lab.key}}
        outputs = [json.dumps(images), identity, RuntimeError("fixture create failure"), json.dumps([info]), identity]
        with patch("runtime.lab.web_scan_lab.docker", side_effect=outputs) as docker, \
             self.assertRaisesRegex(RuntimeError, "fixture create failure"):
            lab.__enter__()
        self.assertEqual(docker.call_args.args, ("network", "rm", identity))
        self.assertEqual(lab.resources, [])


@unittest.skipUnless(os.environ.get("WEB_SCAN_DOCKER_TESTS") == "1", "Opt-in disposable Docker scan")
class WebScanDockerTests(unittest.TestCase):
    def test_observed_surface_reaches_real_executors_and_cleans_up(self):
        target = os.environ.get("WEB_SCAN_TEST_TARGET", "lab-webapp-a")
        port = {"lab-webapp-a": 18085, "lab-webapp-b": 18086}[target]
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_id = "RUN-WEB-SCAN-" + uuid.uuid4().hex
            run_dir = root / run_id
            run_dir.mkdir()
            recorder = DurableEvidenceRecorder(run_id, run_dir / "assessment", approved_root=root)
            manager = RunManager(output_root=root)
            manager._active_run_id = run_id
            request = StartRunRequest(mode="autonomous", planner="rule", target=target,
                target_origin=f"http://127.0.0.1:{port}", execution_scope="scan",
                approve_read_only=True, approve_active_verification=True,
                max_requests=120, max_pages=20, max_decisions=25)
            with patch("runtime.lab.control_support.new_recorder", return_value=recorder):
                manager._worker(run_id, request, run_dir, EventSink())
            report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(manager.get_snapshot()[0].state, AgentState.COMPLETED, report.get("error"))
            coverage = build_coverage(run_dir, run_id)
            self.assertEqual(coverage["integrity"], "VERIFIED")
            self.assertEqual(coverage["scan_isolation"]["restore"], "RECORDED")
            self.assertGreater(report["active_verifications_count"], 0)
            observed_urls = [row.get("value", "") for row in report.get("final_state", {}).get("observed_facts", [])
                             if row.get("fact_type") == "ENDPOINT"]
            expected_route = "/api/users/search" if target == "lab-webapp-a" else "/api/orders"
            self.assertTrue(any(expected_route in url for url in observed_urls), observed_urls)
            if target == "lab-webapp-a":
                self.assertTrue(any(row["classification"] == "VERIFIED_IN_LAB" and row["family"] == "SQL_INJECTION"
                                    for row in report["findings"]), report["findings"])
                self.assertTrue(any(row["classification"] == "VERIFIED_IN_LAB" and row["family"] == "SCRIPT_INJECTION"
                                    for row in report["findings"]), report["findings"])


if __name__ == "__main__":
    unittest.main()
