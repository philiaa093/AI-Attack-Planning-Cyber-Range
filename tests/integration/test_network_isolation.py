import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "cyber-range" / "compose.yaml"
ALLOWED_TARGETS = {
    "lab-sqli-001",
    "lab-xss-001",
    "lab-path-001",
    "lab-clean-001",
    "lab-webapp-a",
    "lab-webapp-b",
    "lab-clean-control",
}


class NetworkIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compose = json.loads(COMPOSE.read_text(encoding="utf-8"))
        cls.services = cls.compose["services"]

    def test_all_services_use_internal_lab_network(self):
        self.assertTrue(self.compose["networks"]["lab"]["internal"])
        for service in self.services.values():
            self.assertEqual(service["networks"], ["lab"])

    def test_ports_bind_loopback_only(self):
        for service in self.services.values():
            for published in service.get("ports", []):
                self.assertRegex(published, r"^127\.0\.0\.1:\d+:\d+$")

    def test_target_ids_are_allowlisted(self):
        target_ids = {
            service["environment"]["TARGET_ID"]
            for service in self.services.values()
            if "TARGET_ID" in service.get("environment", {})
        }
        self.assertEqual(target_ids, ALLOWED_TARGETS)

    def test_rejects_unrestricted_network_configuration(self):
        self.assertNotIn("default", self.compose["networks"])
        for service in self.services.values():
            self.assertNotIn("network_mode", service)
            self.assertNotIn("host", service.get("networks", []))
            for published in service.get("ports", []):
                self.assertFalse(published.startswith(("0.0.0.0:", ":::")))


if __name__ == "__main__":
    unittest.main()
