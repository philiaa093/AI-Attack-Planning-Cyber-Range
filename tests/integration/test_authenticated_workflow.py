"""Authenticated workflow against an ephemeral ShopLab server; no existing lab writes."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import threading
import time
import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
