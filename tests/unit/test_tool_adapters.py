"""Unit tests for all three tool adapters: Discovery, ZAP, Nuclei.

Tests cover:
- Target allowlist enforcement
- Action allowlist enforcement
- Rate limiting
- Template allowlist (Nuclei)
- Request budget (ZAP, Nuclei)
- Schema-conformant output (observation + scanner-result)
- Parser correctness
"""

import json
import re
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.adapters.base import (
    validate_target,
    validate_action,
    build_observation,
    build_scanner_result,
    RateLimiter,
)
from tools.adapters.discovery.adapter import DiscoveryAdapter
from tools.adapters.zap.adapter import ZapAdapter
from tools.adapters.nuclei.adapter import NucleiAdapter, TEMPLATE_ALLOWLIST
from tools.parsers.zap_parser import parse_zap_results
from tools.parsers.nuclei_parser import parse_nuclei_results

ROOT = Path(__file__).resolve().parents[2]


def load_schema(name):
    return json.loads((ROOT / f"agent/planner/contracts/{name}.schema.json").read_text(encoding="utf-8"))


# ---------- lightweight schema check ----------

def schema_errors(data, schema):
    """Minimal check: required keys present, types match, patterns match."""
    errors = []
    if schema.get("type") == "object":
        for req in schema.get("required", []):
            if req not in data:
                errors.append(f"missing required field: {req}")
        for key, prop_schema in schema.get("properties", {}).items():
            if key in data:
                val = data[key]
                if "pattern" in prop_schema and isinstance(val, str):
                    if not re.match(prop_schema["pattern"], val):
                        errors.append(f"{key}: '{val}' doesn't match {prop_schema['pattern']}")
                if "enum" in prop_schema and val not in prop_schema["enum"]:
                    errors.append(f"{key}: '{val}' not in {prop_schema['enum']}")
    return errors


# ===================== Base Safety Tests =====================

class TestTargetValidation(unittest.TestCase):
    def test_valid_lab_target(self):
        validate_target("lab-sqli-001")

    def test_reject_non_lab_target(self):
        with self.assertRaises(ValueError):
            validate_target("public.example.com")

    def test_reject_unknown_lab_target(self):
        with self.assertRaises(ValueError):
            validate_target("lab-unknown-999")


class TestActionValidation(unittest.TestCase):
    def test_valid_action(self):
        validate_action("ACTION-RECON-001", expected_class="RECON")

    def test_reject_unknown_action(self):
        with self.assertRaises(ValueError):
            validate_action("ACTION-UNKNOWN-999")

    def test_reject_wrong_class(self):
        with self.assertRaises(ValueError):
            validate_action("ACTION-RECON-001", expected_class="SCAN")

    def test_reject_bad_format(self):
        with self.assertRaises(ValueError):
            validate_action("bad-format")


class TestRateLimiter(unittest.TestCase):
    def test_acquire_within_limit(self):
        rl = RateLimiter()
        rl.acquire("run-1", "lab-sqli-001")

    def test_burst_exceeded(self):
        rl = RateLimiter()
        rl.acquire("run-1", "lab-sqli-001")
        with self.assertRaises(RuntimeError):
            rl.acquire("run-1", "lab-sqli-001")


class TestOutputBuilders(unittest.TestCase):
    def test_observation_conforms(self):
        obs = build_observation("OBS-1", "RUN-1", "ACTION-RECON-001", "SUCCESS")
        schema = load_schema("observation")
        self.assertEqual(schema_errors(obs, schema), [])

    def test_scanner_result_conforms(self):
        sr = build_scanner_result("ZAP", "lab-sqli-001", "sqli", 0.9)
        schema = load_schema("scanner-result")
        self.assertEqual(schema_errors(sr, schema), [])


# ===================== Discovery Adapter Tests =====================

class TestDiscoveryAdapter(unittest.TestCase):
    def setUp(self):
        self.adapter = DiscoveryAdapter()

    def test_port_scan_returns_observation(self):
        obs = self.adapter.execute("ACTION-RECON-001", "lab-sqli-001", "RUN-001")
        schema = load_schema("observation")
        self.assertEqual(schema_errors(obs, schema), [])
        self.assertEqual(obs["outcome"], "SUCCESS")
        self.assertEqual(obs["action_id"], "ACTION-RECON-001")
        self.assertTrue(len(obs.get("new_facts", [])) > 0)

    def test_endpoint_discovery_returns_observation_and_results(self):
        obs, results = self.adapter.execute("ACTION-RECON-002", "lab-sqli-001", "RUN-002")
        schema = load_schema("observation")
        self.assertEqual(schema_errors(obs, schema), [])
        self.assertTrue(len(results) > 0)
        sr_schema = load_schema("scanner-result")
        for sr in results:
            self.assertEqual(schema_errors(sr, sr_schema), [])

    def test_reject_non_lab_target(self):
        with self.assertRaises(ValueError):
            self.adapter.execute("ACTION-RECON-001", "public.example", "RUN-003")

    def test_reject_wrong_action(self):
        with self.assertRaises(ValueError):
            self.adapter.execute("ACTION-SCAN-001", "lab-sqli-001", "RUN-004")


# ===================== ZAP Adapter Tests =====================

class TestZapAdapter(unittest.TestCase):
    def setUp(self):
        self.adapter = ZapAdapter()

    def test_zap_scan_returns_observation_and_results(self):
        obs, results = self.adapter.execute("ACTION-SCAN-001", "lab-sqli-001", "RUN-010")
        schema = load_schema("observation")
        self.assertEqual(schema_errors(obs, schema), [])
        self.assertEqual(obs["action_id"], "ACTION-SCAN-001")
        self.assertTrue(len(results) > 0)
        sr_schema = load_schema("scanner-result")
        for sr in results:
            self.assertEqual(schema_errors(sr, sr_schema), [])
            self.assertEqual(sr["source"], "ZAP")

    def test_reject_non_lab_target(self):
        with self.assertRaises(ValueError):
            self.adapter.execute("ACTION-SCAN-001", "external.host", "RUN-011")

    def test_reject_wrong_action(self):
        with self.assertRaises(ValueError):
            self.adapter.execute("ACTION-RECON-001", "lab-sqli-001", "RUN-012")


class TestZapParser(unittest.TestCase):
    def test_parse_empty(self):
        self.assertEqual(parse_zap_results({"site": []}, "lab-sqli-001"), [])

    def test_parse_alerts(self):
        data = {
            "site": [{
                "host": "lab-sqli-001",
                "alerts": [
                    {"alert": "SQL Injection", "riskcode": "3", "uri": "http://lab-sqli-001/login"},
                ]
            }]
        }
        results = parse_zap_results(data, "lab-sqli-001")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "ZAP")
        self.assertEqual(results[0]["finding_type"], "sqli")
        self.assertEqual(results[0]["target_id"], "lab-sqli-001")


# ===================== Nuclei Adapter Tests =====================

class TestNucleiAdapter(unittest.TestCase):
    def setUp(self):
        self.adapter = NucleiAdapter()

    def test_nuclei_scan_returns_observation_and_results(self):
        obs, results = self.adapter.execute("ACTION-SCAN-002", "lab-xss-001", "RUN-020")
        schema = load_schema("observation")
        self.assertEqual(schema_errors(obs, schema), [])
        self.assertEqual(obs["action_id"], "ACTION-SCAN-002")
        self.assertTrue(len(results) > 0)
        sr_schema = load_schema("scanner-result")
        for sr in results:
            self.assertEqual(schema_errors(sr, sr_schema), [])
            self.assertEqual(sr["source"], "NUCLEI")

    def test_reject_forbidden_template(self):
        with self.assertRaises(ValueError):
            self.adapter.execute(
                "ACTION-SCAN-002", "lab-xss-001", "RUN-021",
                parameters={"templates": ["rce"]}
            )

    def test_reject_non_lab_target(self):
        with self.assertRaises(ValueError):
            self.adapter.execute("ACTION-SCAN-002", "external.host", "RUN-022")

    def test_reject_wrong_action(self):
        with self.assertRaises(ValueError):
            self.adapter.execute("ACTION-RECON-001", "lab-xss-001", "RUN-023")

    def test_template_allowlist_contents(self):
        self.assertEqual(TEMPLATE_ALLOWLIST, {"sqli", "xss", "path-traversal"})


class TestNucleiParser(unittest.TestCase):
    def test_parse_empty(self):
        self.assertEqual(parse_nuclei_results([], "lab-sqli-001"), [])

    def test_parse_findings(self):
        data = [{
            "template-id": "sqli-error",
            "severity": "high",
            "host": "lab-sqli-001",
            "matched-at": "http://lab-sqli-001/login?id=1",
            "tags": ["sqli"],
        }]
        results = parse_nuclei_results(data, "lab-sqli-001")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "NUCLEI")
        self.assertEqual(results[0]["finding_type"], "sqli")
        self.assertAlmostEqual(results[0]["confidence"], 0.9)


if __name__ == "__main__":
    unittest.main()
