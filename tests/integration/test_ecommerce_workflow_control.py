import hashlib
import json
import os
import sqlite3
import threading
from tempfile import TemporaryDirectory
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from test_ecommerce_storage import load_app
from runtime.lab.workflow_lab import GNS3WorkflowControl


class ShopLabWorkflowControlTests(unittest.TestCase):
    def setUp(self):
        self.app = load_app()
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.app.close_storage)
        self.app.initialize_storage(self.temp.name)
        self.run_id = "RUN-DASH-" + "a" * 32
        self.username = "rt_" + hashlib.sha256(self.run_id.encode()).hexdigest()[:12] + "_c"
        with self.app.storage_transaction(write=True) as db:
            cursor = db.execute(
                "INSERT INTO users(username,email,password_hash,cart_key) VALUES (?,?,?,?)",
                (self.username, "workflow@lab.invalid", "fixture", "b" * 64),
            )
            self.user_id = cursor.lastrowid
            db.execute(
                "INSERT INTO sessions(token_digest,user_id,cart_key,issued_at,expires_at,csrf_secret) "
                "VALUES (?,?,?,?,?,?)",
                ("c" * 64, self.user_id, "b" * 64, 1, 9999999999, "d" * 64),
            )

    def scalar(self, sql, params=()):
        with self.app.storage_transaction() as db:
            return db.execute(sql, params).fetchone()[0]

    def test_snapshot_promote_and_restore_round_trip(self):
        changed = self.app.UPLOAD_DIR / "changed.txt"
        missing = self.app.UPLOAD_DIR / "missing.txt"
        changed.write_bytes(b"original\r\n")
        missing.write_bytes(b"\x00original")
        digest = self.app._workflow_snapshot_create(self.run_id)
        self.assertRegex(digest, r"^[a-f0-9]{64}$")

        self.app._workflow_promote(self.run_id, self.username)
        self.assertEqual(self.scalar("SELECT role FROM users WHERE id=?", (self.user_id,)), "admin")
        self.assertEqual(self.scalar("SELECT count(*) FROM sessions WHERE user_id=?", (self.user_id,)), 0)

        with self.app.storage_transaction(write=True) as db:
            db.execute(
                "INSERT INTO users(username,email,password_hash,cart_key) VALUES (?,?,?,?)",
                ("temporary", "temporary@lab.invalid", "fixture", "e" * 64),
            )
        generated = self.app.UPLOAD_DIR / "workflow-generated.txt"
        generated.write_text("temporary", encoding="utf-8")
        changed.write_text("modified", encoding="utf-8")
        missing.unlink()

        self.assertEqual(self.app._workflow_snapshot_restore(self.run_id), digest)
        self.assertEqual(self.scalar("SELECT role FROM users WHERE id=?", (self.user_id,)), "user")
        self.assertEqual(self.scalar("SELECT count(*) FROM sessions WHERE user_id=?", (self.user_id,)), 1)
        self.assertEqual(self.scalar("SELECT count(*) FROM users WHERE username='temporary'"), 0)
        self.assertFalse(generated.exists())
        self.assertEqual(changed.read_bytes(), b"original\r\n")
        self.assertEqual(missing.read_bytes(), b"\x00original")

    def test_corrupt_invoice_backup_refuses_restore_before_changes(self):
        invoice = self.app.UPLOAD_DIR / "original.txt"
        invoice.write_bytes(b"baseline")
        digest = self.app._workflow_snapshot_create(self.run_id)
        backup = self.app._workflow_snapshot["path"].parent / "invoices" / invoice.name
        backup.write_bytes(b"damaged")
        invoice.write_bytes(b"changed")
        with self.assertRaisesRegex(RuntimeError, "invoice snapshot integrity"):
            self.app._workflow_snapshot_restore(self.run_id)
        self.assertEqual(invoice.read_bytes(), b"changed")
        with self.assertRaises(self.app.StorageError):
            self.scalar("SELECT 1")
        backup.write_bytes(b"baseline")
        self.assertEqual(self.app._workflow_snapshot_restore(self.run_id), digest)
        self.assertEqual(invoice.read_bytes(), b"baseline")

    def test_valid_but_different_restored_database_stays_closed_and_retryable(self):
        digest = self.app._workflow_snapshot_create(self.run_id)
        snapshot = self.app._workflow_snapshot["path"]
        preflight = self.app._preflight_db
        def change_sequence(path, **kwargs):
            with sqlite3.connect(path) as db:
                db.execute("UPDATE sqlite_sequence SET seq = seq + 1 WHERE name = 'users'")
            db.close()
            preflight(path, **kwargs)

        with patch.object(self.app, "_preflight_db", side_effect=change_sequence):
            with self.assertRaisesRegex(RuntimeError, "differs from workflow snapshot"):
                self.app._workflow_snapshot_restore(self.run_id)
        self.assertTrue(snapshot.exists())
        with self.assertRaises(self.app.StorageError):
            self.scalar("SELECT 1")
        self.assertEqual(self.app._workflow_snapshot_restore(self.run_id), digest)
        self.assertFalse(snapshot.exists())
        self.assertEqual(self.scalar("SELECT seq FROM sqlite_sequence WHERE name='users'"), self.user_id)

    def test_wrong_run_and_wrong_account_fail_closed(self):
        self.app._workflow_snapshot_create(self.run_id)
        with self.assertRaisesRegex((ValueError, RuntimeError), "workflow"):
            self.app._workflow_promote("RUN-DASH-" + "b" * 32, self.username)
        with self.assertRaisesRegex((ValueError, RuntimeError), "workflow"):
            self.app._workflow_promote(self.run_id, "not-the-run-account")
        self.app._workflow_snapshot_restore(self.run_id)

    def test_control_http_requires_bearer_and_fixed_routes(self):
        token = "control-fixture-" + "x" * 32
        server = self.app.ThreadingHTTPServer(("127.0.0.1", 0), self.app.WorkflowControlHandler)
        server.control_token = token
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = "http://127.0.0.1:" + str(server.server_port)

        with self.assertRaises(urllib.error.HTTPError) as denied:
            urllib.request.urlopen(base + "/control/v1/health", timeout=2)
        self.assertEqual(denied.exception.code, 401)
        denied.exception.close()

        request = urllib.request.Request(base + "/control/v1/health",
                                         headers={"Authorization": "Bearer " + token})
        with urllib.request.urlopen(request, timeout=2) as response:
            self.assertEqual(json.load(response), {"status": "ok", "service": "workflow-control"})

        unknown = urllib.request.Request(base + "/control/v1/unknown", data=b"{}", method="POST",
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as missing:
            urllib.request.urlopen(unknown, timeout=2)
        self.assertEqual(missing.exception.code, 404)
        missing.exception.close()

    def test_gns3_client_completes_real_control_round_trip(self):
        token = "control-fixture-" + "y" * 32
        server = self.app.ThreadingHTTPServer(("127.0.0.1", 0), self.app.WorkflowControlHandler)
        server.control_token = token
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        env = {
            "SHOPLAB_GNS3_CONTROL_URL": "http://127.0.0.1:" + str(server.server_port),
            "SHOPLAB_GNS3_CONTROL_TOKEN": token,
        }
        with patch.dict(os.environ, env, clear=False):
            control = GNS3WorkflowControl("http://127.0.0.1:8080")
            control.health()
            digest = control.snapshot(self.run_id)
            control.promote(self.run_id, self.username)
            self.assertEqual(self.scalar("SELECT role FROM users WHERE id=?", (self.user_id,)), "admin")
            self.assertEqual(control.restore(self.run_id), digest)
            self.assertEqual(self.scalar("SELECT role FROM users WHERE id=?", (self.user_id,)), "user")


if __name__ == "__main__":
    unittest.main()
