"""Authenticated workflow against an ephemeral ShopLab server; no existing lab writes."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import os
import runpy
import threading
import time
import unittest
from unittest.mock import call, patch

from test_ecommerce_storage import load_app
from runtime.evidence.discovery_recorder import DurableEvidenceRecorder
from runtime.lab.authenticated_workflow import AuthenticatedWorkflow
from runtime.lab.workflow_policy import WorkflowPolicy, WORKFLOW_ACTIONS, AUTH_ACTION
from runtime.lab.workflow_lab import WorkflowLab
from runtime.safety.discovery_gate import CentralizedSafetyGate, ApprovalToken, BudgetTracker, TokenBucketRateLimiter, DiscoveryRequest
from dashboards.app.backend.models import StartRunRequest


class AuthenticatedWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.recorder = DurableEvidenceRecorder("RUN-WORKFLOW-TEST", self.root / "evidence", approved_root=self.root)
        self.approval = ApprovalToken("APP-TEST", "RUN-WORKFLOW-TEST", "lab-ecommerce", "*", time.time()-1, time.time()+600)
        self.gate = CentralizedSafetyGate("http://127.0.0.1:18088", recorder=self.recorder,
            action_allowlist=WORKFLOW_ACTIONS, target_allowlist={"lab-ecommerce"},
            rate_limiter=TokenBucketRateLimiter(1000, 1000), budget_tracker=BudgetTracker(max_requests=200))

    def test_post_requires_isolation_observed_form_approval_and_fixed_fields(self):
        req = DiscoveryRequest("RUN-WORKFLOW-TEST", "lab-ecommerce", AUTH_ACTION,
            "http://127.0.0.1:18088/register", method="POST", approval=self.approval,
            form={"username": "rt_123456789abc_a", "password": "ephemeral-test-password"})
        with patch("runtime.safety.discovery_gate.http.client.HTTPConnection") as transport:
            self.assertEqual(self.gate.dispatch(req).outcome, "DENIED")
            self.gate.workflow_policy = WorkflowPolicy(req.run_id, lambda: False)
            self.gate.workflow_policy.forms.add("/register")
            self.assertEqual(self.gate.dispatch(req).outcome, "DENIED")
            self.gate.workflow_policy.isolated = lambda: True
            req.form["role"] = "admin"
            self.assertEqual(self.gate.dispatch(req).outcome, "DENIED")
            del req.form["role"]
            self.approval.revoke()
            self.assertEqual(self.gate.dispatch(req).outcome, "DENIED")
            transport.assert_not_called()

    def test_request_model_requires_separate_write_opt_in(self):
        with self.assertRaises(ValueError):
            StartRunRequest(approve_authenticated_workflow=True)
        req = StartRunRequest(mode="autonomous", approve_active_verification=True,
                              approve_authenticated_workflow=True, max_requests=200)
        self.assertTrue(req.approve_authenticated_workflow)

    def test_full_workflow_on_temp_application_and_no_credentials_in_evidence(self):
        app = load_app()
        app.initialize_storage(self.root / "data")
        self.addCleanup(app.close_storage)
        app.Handler.log_message = lambda *args: None
        server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        origin = "http://127.0.0.1:" + str(server.server_port)
        self.gate.base_origin = origin
        self.gate.canonicalizer = type(self.gate.canonicalizer)(origin)
        def promote(username):
            with app.storage_transaction(write=True) as db:
                db.execute("UPDATE users SET role='admin' WHERE username=?", (username,))
        lab = SimpleNamespace(run_id="RUN-WORKFLOW-TEST", key="123456789abc", active=True, promote=promote)
        with patch("runtime.lab.authenticated_workflow.secrets.token_urlsafe", return_value="workflow-password-not-for-evidence"):
            result = AuthenticatedWorkflow(self.gate, self.recorder, self.approval, lab).execute()
        self.assertEqual(result["failed_checks"], 0, result)
        self.assertGreaterEqual(len(result["checks"]), 10)
        self.assertIsNone(self.gate.workflow_policy)
        evidence = "".join(path.read_text(encoding="utf-8") for path in (self.root / "evidence").glob("*.json"))
        self.assertNotIn("workflow-password-not-for-evidence", evidence)
        self.assertNotIn("session=", evidence)
        with app.storage_transaction() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM orders").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT status FROM orders").fetchone()[0], "shipped")

    def test_restore_verifies_original_and_retains_clone(self):
        (self.root / "runtime").mkdir()
        with patch("runtime.lab.workflow_lab.ROOT", self.root):
            lab = WorkflowLab("RUN-WORKFLOW-TEST", self.recorder)
        lab.lock.write_text("lease")
        lab.override.write_text("{}")
        lab.owned, lab.stopped, lab.active, lab.snapshot = True, True, True, "hash"
        with patch.object(lab, "volume_operation", return_value="hash"), \
             patch("runtime.lab.workflow_lab.docker", return_value="lab-ecommerce\ngateway-ecommerce") as docker:
            lab.__exit__(None, None, None)
        self.assertFalse(lab.lock.exists())
        self.assertFalse(lab.active)
        self.assertFalse(any("rm" in call.args or "--volumes" in call.args for call in docker.call_args_list))

    def test_restore_hash_mismatch_retains_recovery_lock(self):
        (self.root / "runtime").mkdir()
        with patch("runtime.lab.workflow_lab.ROOT", self.root):
            lab = WorkflowLab("RUN-WORKFLOW-TEST", self.recorder)
        lab.lock.write_text("lease")
        lab.override.write_text("{}")
        lab.owned, lab.stopped, lab.snapshot = True, True, "original"
        with patch.object(lab, "volume_operation", return_value="changed"), \
             patch("runtime.lab.workflow_lab.docker") as docker:
            with self.assertRaisesRegex(RuntimeError, "ORIGINAL_VOLUME_CHANGED"):
                lab.__exit__(None, None, None)
        self.assertTrue(lab.lock.exists())
        self.assertFalse(any("start" in call.args for call in docker.call_args_list))

    def test_snapshot_preserves_source_ownership_and_content(self):
        helper = runpy.run_path(str(Path(__file__).resolve().parents[2] / "cyber-range/runtime/workflow_volume.py"))
        source, destination = self.root / "source", self.root / "clone"
        source.mkdir()
        destination.mkdir()
        (source / "invoices").mkdir()
        (source / "shoplab.sqlite3").write_bytes(b"temporary database fixture")
        (source / "invoices" / "fixture.txt").write_bytes(b"lab fixture")
        expected_hash = helper["digest"](source)
        expected_owners = []
        for original in (source, *source.rglob("*")):
            info = original.stat()
            expected_owners.append(call(destination / original.relative_to(source), info.st_uid, info.st_gid,
                                        follow_symlinks=False))
        with patch.object(os, "chown", create=True) as chown:
            self.assertEqual(helper["snapshot"](source, destination), expected_hash)
        chown.assert_has_calls(expected_owners, any_order=True)
        self.assertEqual(chown.call_count, len(expected_owners))
        self.assertEqual(helper["digest"](source), expected_hash)
        self.assertEqual(helper["digest"](destination), expected_hash)

    def test_snapshot_ownership_failure_is_not_reported_as_success(self):
        helper = runpy.run_path(str(Path(__file__).resolve().parents[2] / "cyber-range/runtime/workflow_volume.py"))
        source, destination = self.root / "source", self.root / "clone"
        source.mkdir()
        destination.mkdir()
        (source / "shoplab.sqlite3").write_bytes(b"temporary database fixture")
        with patch.object(os, "chown", create=True, side_effect=PermissionError("ownership denied")):
            with self.assertRaises(PermissionError):
                helper["snapshot"](source, destination)
        self.assertEqual((source / "shoplab.sqlite3").read_bytes(), b"temporary database fixture")

    def test_only_snapshot_helper_gets_chown_capability(self):
        lab = WorkflowLab("RUN-WORKFLOW-TEST", self.recorder)
        lab.source, lab.helper = "source-fixture", "helper-fixture"
        for operation in ("snapshot", "verify"):
            with self.subTest(operation=operation), \
                 patch("runtime.lab.workflow_lab.docker", return_value='{"sha256":"fixture-hash"}') as docker:
                self.assertEqual(lab.volume_operation(operation), "fixture-hash")
                args = docker.call_args.args
                self.assertEqual(args[args.index("--network") + 1], "none")
                self.assertEqual(args[args.index("--cap-drop") + 1], "ALL")
                self.assertIn("--read-only", args)
                self.assertIn("no-new-privileges", args)
                self.assertIn("type=volume,source=source-fixture,target=/source,readonly", args)
                self.assertTrue(any(str(arg).endswith("target=/helper.py,readonly") for arg in args))
                self.assertEqual(args.count("--cap-add"), int(operation == "snapshot"))
                if operation == "snapshot":
                    self.assertEqual(args[args.index("--cap-add") + 1], "CHOWN")
                self.assertEqual(args[-1], operation)


if __name__ == "__main__":
    unittest.main()
