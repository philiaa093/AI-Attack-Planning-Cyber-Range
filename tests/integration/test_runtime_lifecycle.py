"""Offline local-target/evidence composition; no enterprise episode or server durability claim."""
import json
from io import BytesIO
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch
import uuid

from runtime.evidence.discovery_recorder import DurableEvidenceRecorder
from runtime.evidence.evidence_package import EvidenceVerifier
from runtime.lab import server as lab_server
from runtime.lab.targets import Target


class RuntimeLifecycleTests(unittest.TestCase):
    def test_clean_control_lifecycle_preserves_append_only_evidence(self):
        root = Path(tempfile.gettempdir()) / ("runtime-lifecycle-" + uuid.uuid4().hex)
        root.mkdir(mode=0o755)
        root = root.resolve()
        self.assertEqual(root.parent, Path(tempfile.gettempdir()).resolve())
        self.addCleanup(shutil.rmtree, root)
        run_id = "RUN-LIFECYCLE-" + uuid.uuid4().hex
        recorder = DurableEvidenceRecorder(
            run_id, base_dir=root / run_id, approved_root=root,
            source="UNIT_TEST", exclusive_creation=True,
        )
        target = Target("lab-clean-001")
        self.assertEqual(target.health().body, {
            "status": "ok", "target_id": "lab-clean-001", "family": None, "reset_count": 0,
        })
        first_reset = target.reset()
        self.assertEqual(first_reset.status, 200)
        self.assertEqual(first_reset.body["status"], "reset")
        self.assertEqual(first_reset.body["reset_count"], 1)
        first = recorder.persist_phase_artifact(
            "reset", first_reset.body,
            expected_state="RESET_RECORDED", observed_state="RESET_RECORDED",
        )
        before = {path: path.read_bytes() for path in recorder.directory.iterdir() if path.is_file()}
        second_reset = target.reset()
        self.assertEqual(second_reset.body["reset_count"], 2)
        second = recorder.persist_phase_artifact(
            "reset", second_reset.body, derived_from=[first["evidence_id"]],
            expected_state="RESET_RECORDED", observed_state="RESET_RECORDED",
        )
        self.assertNotEqual(first["evidence_id"], second["evidence_id"])
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.assertGreater(len(list(recorder.directory.iterdir())), len(before))
        self.assertEqual(json.loads(Path(first["payload_path"]).read_text())["reset_count"], 1)
        self.assertEqual(json.loads(Path(second["payload_path"]).read_text())["reset_count"], 2)
        result = EvidenceVerifier.verify_directory(recorder.directory)
        self.assertTrue(result.passed, result.errors)
        self.assertEqual(result.verified_records_count, 2)

    def test_http_handler_denies_malformed_action_body_without_dispatch(self):
        target = Target("lab-clean-001")
        before = target.health()
        body = b"{malformed JSON"
        request = (b"POST /action HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n"
                   + f"Content-Length: {len(body)}\r\nContent-Type: application/json\r\n\r\n".encode()
                   + body)
        response = bytearray()
        connection = Mock(spec=["makefile", "sendall"])
        connection.makefile.return_value = BytesIO(request)
        connection.sendall.side_effect = response.extend
        with patch.object(lab_server, "state", target), patch.object(lab_server, "route") as route, \
                patch("socket.socket", side_effect=AssertionError("socket creation forbidden")), \
                patch("socket.create_connection", side_effect=AssertionError("network connection forbidden")):
            lab_server.Handler(connection, ("127.0.0.1", 0), Mock())
        headers, payload = bytes(response).split(b"\r\n\r\n", 1)
        self.assertEqual(headers.split(b"\r\n", 1)[0].split()[1], b"400")
        self.assertEqual(json.loads(payload), {"status": "body_not_allowed"})
        route.assert_not_called()
        self.assertEqual(target.health(), before)


if __name__ == "__main__":
    unittest.main()
