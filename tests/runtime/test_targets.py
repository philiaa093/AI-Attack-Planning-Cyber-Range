import http.client
import importlib.util
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[2]
TARGETS = {
    "a": ROOT / "cyber-range" / "targets" / "custom-webapp-a" / "app.py",
    "b": ROOT / "cyber-range" / "targets" / "custom-webapp-b" / "app.py",
    "clean": ROOT / "cyber-range" / "targets" / "clean-control" / "app.py",
}


def load_target(name: str):
    spec = importlib.util.spec_from_file_location(f"target_{name}_{id(name)}", TARGETS[name])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RunningTarget:
    def __init__(self, name: str):
        self.module = load_target(name)
        self.server = self.module.ThreadingHTTPServer(("127.0.0.1", 0), self.module.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def request(self, method: str, path: str, body=None, headers=None):
        encoded = None if body is None else body.encode("utf-8")
        request_headers = {} if headers is None else dict(headers)
        if encoded is not None:
            request_headers["Content-Length"] = str(len(encoded))
        connection = http.client.HTTPConnection(*self.server.server_address)
        connection.request(method, path, body=encoded, headers=request_headers)
        response = connection.getresponse()
        result = response.status, response.read().decode("utf-8")
        connection.close()
        return result

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


class TargetTests(unittest.TestCase):
    def setUp(self):
        self.targets = []

    def tearDown(self):
        for target in self.targets:
            target.close()

    def start(self, name):
        target = RunningTarget(name)
        self.targets.append(target)
        return target

    @staticmethod
    def json_response(response):
        status, body = response
        return status, json.loads(body)

    def test_health_reset_and_ground_truth(self):
        expected = {
            "a": ("SCN-012", "lab-webapp-a", True),
            "b": ("SCN-013", "lab-webapp-b", True),
            "clean": ("SCN-014", "lab-clean-control", False),
        }
        for name, (scenario, target_id, vulnerable) in expected.items():
            with self.subTest(target=name):
                target = self.start(name)
                status, health = self.json_response(target.request("GET", "/health"))
                self.assertEqual(status, 200)
                self.assertEqual(health, {"reset_count": 0, "status": "ok", "target_id": target_id})
                status, reset = self.json_response(target.request("POST", "/reset"))
                self.assertEqual(status, 200)
                self.assertEqual(reset["reset_count"], 1)
                self.assertEqual(self.json_response(target.request("GET", "/health"))[1]["reset_count"], 1)

                truth = json.loads((TARGETS[name].parent / "ground-truth.json").read_text())
                self.assertEqual(truth["scenario_id"], scenario)
                self.assertEqual(
                    {(record["vulnerability_family"], record["is_vulnerable"]) for record in truth["truth_records"]},
                    {("SQLI", vulnerable), ("XSS", vulnerable), ("PATH_TRAVERSAL", vulnerable)},
                )

    def test_target_a_real_vulnerabilities(self):
        target = self.start("a")
        injection = urlencode({"q": "' OR 1=1 --"})
        status, body = self.json_response(target.request("GET", f"/api/users/search?{injection}"))
        self.assertEqual(status, 200)
        self.assertEqual(len(body["results"]), 3)

        marker = "<script>alert(1)</script>"
        status, body = target.request("GET", f"/search?{urlencode({'q': marker})}")
        self.assertEqual(status, 200)
        self.assertIn(marker, body)

        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / "data"
            data_dir.mkdir()
            (Path(directory) / "secret.txt").write_text("outside-data")
            target.module.DATA_DIR = str(data_dir)
            status, body = target.request("GET", f"/files?{urlencode({'name': '../secret.txt'})}")
            self.assertEqual(status, 200)
            self.assertEqual(body, "outside-data")

    def test_target_b_real_distinct_vulnerabilities(self):
        target = self.start("b")
        status, body = self.json_response(target.request("GET", f"/api/orders?{urlencode({'customer_id': '1 OR 1=1'})}"))
        self.assertEqual(status, 200)
        self.assertEqual(len(body["orders"]), 3)

        marker = "<img src=x onerror=alert(1)>"
        payload = json.dumps({"author": "tester", "body": marker})
        self.assertEqual(self.json_response(target.request("POST", "/api/comments", payload, {"Content-Type": "application/json"}))[0], 201)
        status, body = target.request("GET", "/api/comments")
        self.assertEqual(status, 200)
        self.assertIn(marker, body)

        with tempfile.TemporaryDirectory() as directory:
            uploads_dir = Path(directory) / "uploads"
            uploads_dir.mkdir()
            (Path(directory) / "secret.txt").write_text("outside-uploads")
            target.module.UPLOADS_DIR = str(uploads_dir)
            status, body = target.request("GET", f"/api/download?{urlencode({'file': '../secret.txt'})}")
            self.assertEqual(status, 200)
            self.assertEqual(body, "outside-uploads")

    def test_clean_control_negative_behavior(self):
        target = self.start("clean")
        status, body = self.json_response(target.request("GET", f"/api/items/search?{urlencode({'q': "' OR 1=1 --"})}"))
        self.assertEqual(status, 200)
        self.assertEqual(body["results"], [])

        marker = "<script>alert(1)</script>"
        status, body = target.request("GET", f"/search?{urlencode({'q': marker})}")
        self.assertEqual(status, 200)
        self.assertNotIn(marker, body)
        self.assertIn("&lt;script&gt;", body)

        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / "data"
            data_dir.mkdir()
            (Path(directory) / "secret.txt").write_text("outside-data")
            target.module.DATA_DIR = data_dir
            status, body = self.json_response(target.request("GET", f"/files?{urlencode({'name': '../secret.txt'})}"))
            self.assertEqual(status, 403)
            self.assertEqual(body["error"], "forbidden")


if __name__ == "__main__":
    unittest.main()
