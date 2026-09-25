import json
import tempfile
import unittest
from http.client import HTTPConnection
from pathlib import Path

from runtime.evidence import EvidenceLog
from runtime.server import RuntimeHTTPServer

from runtime.config import RuntimeConfig
from runtime.runner import RuntimeRunner


class RuntimeLifecycleTests(unittest.TestCase):
    def test_clean_control_lifecycle_preserves_append_only_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = RuntimeRunner(RuntimeConfig(), evidence=EvidenceLog(directory))
            self.assertEqual(runner.health()["target_id"], "lab-clean-001")
            self.assertEqual(runner.reset()["state"], "clean")
            before = (Path(directory) / "events.jsonl").read_bytes()
            runner.reset()
            after = (Path(directory) / "events.jsonl").read_bytes()
            self.assertGreater(len(after), len(before))
            self.assertTrue(runner.evidence.verify())

    def test_loopback_http_denies_malformed_action(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = RuntimeRunner(RuntimeConfig(), evidence=EvidenceLog(directory))
            server = RuntimeHTTPServer(runner, ("127.0.0.1", 0))
            try:
                connection = HTTPConnection("127.0.0.1", server.server_port)
                server.timeout = 0.1
                import threading
                thread = threading.Thread(target=server.handle_request)
                thread.start()
                connection.request("POST", "/action", json.dumps({"action": {}}), {"Content-Type": "application/json"})
                response = connection.getresponse()
                self.assertEqual(response.status, 400)
                thread.join()
            finally:
                server.server_close()


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()
