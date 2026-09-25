import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

_spec = importlib.util.spec_from_file_location("runtime_executor", Path(__file__).resolve().parents[2] / "runtime" / "executor.py")
_module = importlib.util.module_from_spec(_spec)
import sys
sys.modules["runtime_executor"] = _module
_spec.loader.exec_module(_module)
Executor = _module.Executor
validate_base_url = _module.validate_base_url


class ExecutorTests(unittest.TestCase):
    def test_internal_validation_rejects_loopback_ip_and_external_hosts(self):
        for url in (
            "http://127.0.0.1:8080",
            "http://localhost:8080",
            "https://lab-sqli-001:8080",
            "http://example.test:8080",
            "http://lab-sqli-001:8081",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_base_url(url)

    def test_internal_validation_accepts_only_allowlisted_service_dns(self):
        self.assertEqual(validate_base_url("http://lab-sqli-001:8080"), ("lab-sqli-001", 8080))
        with self.assertRaises(ValueError):
            validate_base_url("http://lab-sqli-001:8080/path")
        with self.assertRaises(ValueError):
            validate_base_url("http://user:pass@lab-sqli-001:8080")

    def test_default_endpoints_use_all_four_service_dns_names(self):
        executor = Executor()
        self.assertEqual(set(executor.endpoints), {
            "lab-sqli-001", "lab-xss-001", "lab-path-001", "lab-clean-001",
        })
        self.assertEqual(set(executor.endpoints.values()), {
            "http://lab-sqli-001:8080", "http://lab-xss-001:8080",
            "http://lab-path-001:8080", "http://lab-clean-001:8080",
        })

    @patch("runtime_executor.HTTPConnection")
    def test_health_reset_action_flow(self, connection_type):
        connection = connection_type.return_value
        responses = []
        for body in (
            b'{"status":"ok","target_id":"lab-sqli-001"}',
            b'{"status":"reset","target_id":"lab-sqli-001","reset_count":1}',
            b'{"status":"detected","target_id":"lab-sqli-001","vulnerable":true}',
        ):
            response = unittest.mock.Mock(status=200)
            response.read.return_value = body
            responses.append(response)
        connection.getresponse.side_effect = responses
        executor = Executor({"lab-sqli-001": "http://lab-sqli-001:8080"})
        self.assertEqual(executor.health("lab-sqli-001")["status"], "ok")
        self.assertEqual(executor.reset("lab-sqli-001")["reset_count"], 1)
        self.assertTrue(executor.action("lab-sqli-001", "ACTION-WEB-001")["vulnerable"])
        self.assertEqual(connection.request.call_args_list[0].args, ("GET", "/health"))
        self.assertEqual(connection.request.call_args_list[1].args, ("POST", "/reset"))
        self.assertEqual(connection.request.call_args_list[2].args, ("POST", "/action?action=ACTION-WEB-001"))

    def test_unknown_action_is_rejected_before_request(self):
        executor = Executor({"lab-clean-001": "http://lab-clean-001:8080"})
        with self.assertRaises(ValueError):
            executor.action("lab-clean-001", "ACTION-UNKNOWN-999")


if __name__ == "__main__":
    unittest.main()
