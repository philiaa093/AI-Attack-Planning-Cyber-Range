"""Unit tests for TASK-018: Observation normalizer + feature extractors.

Covers:
- Scanner-result → canonical facts conversion
- Confidence clamping/standardization
- Deduplication (keep highest confidence)
- All fact types: SERVICE, ENDPOINT, PARAMETER, CANDIDATE_FINDING, CONFIRMED_FINDING
- Feature extraction utils
- No ground-truth tokens present
"""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent.perception.normalizers.observation_normalizer import (
    ObservationNormalizer,
    _clamp_confidence,
    _make_fact_id,
    _CANONICAL_FINDING_TYPES,
)
from agent.perception.feature_extractors.extractors import (
    extract_services,
    extract_endpoints,
    extract_parameters,
    extract_findings,
    group_by_subject,
    group_by_type,
)


# ===================== Confidence Clamping =====================

class TestClampConfidence(unittest.TestCase):
    def test_normal_range(self):
        self.assertEqual(_clamp_confidence(0.5), 0.5)

    def test_above_one(self):
        self.assertEqual(_clamp_confidence(1.5), 1.0)

    def test_below_zero(self):
        self.assertEqual(_clamp_confidence(-0.3), 0.0)

    def test_non_numeric(self):
        self.assertEqual(_clamp_confidence("high"), 0.5)

    def test_none(self):
        self.assertEqual(_clamp_confidence(None), 0.5)

    def test_integer(self):
        self.assertEqual(_clamp_confidence(1), 1.0)


# ===================== Fact ID Generation =====================

class TestMakeFactId(unittest.TestCase):
    def test_deterministic(self):
        a = _make_fact_id("SERVICE", "lab-sqli-001", "http/80")
        b = _make_fact_id("SERVICE", "lab-sqli-001", "http/80")
        self.assertEqual(a, b)

    def test_different_inputs(self):
        a = _make_fact_id("SERVICE", "lab-sqli-001", "http/80")
        b = _make_fact_id("SERVICE", "lab-sqli-001", "https/443")
        self.assertNotEqual(a, b)

    def test_format(self):
        fid = _make_fact_id("CANDIDATE_FINDING", "lab-sqli-001", "sqli")
        self.assertTrue(fid.startswith("FACT-CAND-"))


# ===================== Normalizer Core =====================

class TestObservationNormalizer(unittest.TestCase):
    def setUp(self):
        self.normalizer = ObservationNormalizer()

    def test_normalize_zap_result(self):
        sr = {
            "source": "ZAP",
            "target_id": "lab-sqli-001",
            "endpoint_id": "http://lab-sqli-001/login",
            "finding_type": "sqli",
            "confidence": 0.9,
        }
        obs = self.normalizer.normalize([sr], "RUN-001", "ACTION-SCAN-001")
        self.assertEqual(obs["run_id"], "RUN-001")
        self.assertEqual(obs["action_id"], "ACTION-SCAN-001")
        self.assertIn(obs["outcome"], ("SUCCESS", "PARTIAL"))
        self.assertTrue(len(obs["new_facts"]) >= 1)

    def test_normalize_discovery_result(self):
        sr = {
            "source": "DISCOVERY",
            "target_id": "lab-sqli-001",
            "endpoint_id": None,
            "finding_type": "open_port",
            "confidence": 0.95,
        }
        obs = self.normalizer.normalize([sr], "RUN-001", "ACTION-RECON-001")
        facts = obs["new_facts"]
        service_facts = [f for f in facts if f["fact_type"] == "SERVICE"]
        self.assertTrue(len(service_facts) >= 1)

    def test_normalize_nuclei_result(self):
        sr = {
            "source": "NUCLEI",
            "target_id": "lab-xss-001",
            "endpoint_id": "http://lab-xss-001/search?q=test",
            "finding_type": "xss",
            "confidence": 0.7,
        }
        obs = self.normalizer.normalize([sr], "RUN-002", "ACTION-SCAN-002")
        facts = obs["new_facts"]
        findings = [f for f in facts if f["fact_type"] == "CANDIDATE_FINDING"]
        self.assertTrue(len(findings) >= 1)

    def test_deduplication_keeps_highest_confidence(self):
        sr1 = {
            "source": "ZAP",
            "target_id": "lab-sqli-001",
            "endpoint_id": None,
            "finding_type": "sqli",
            "confidence": 0.5,
        }
        sr2 = {
            "source": "ZAP",
            "target_id": "lab-sqli-001",
            "endpoint_id": None,
            "finding_type": "sqli",
            "confidence": 0.9,
        }
        obs = self.normalizer.normalize([sr1, sr2], "RUN-003", "ACTION-SCAN-001")
        # Same (type, subject, value) → deduplicated to 1
        candidate_facts = [f for f in obs["new_facts"] if f["fact_type"] == "CANDIDATE_FINDING"]
        self.assertEqual(len(candidate_facts), 1)
        self.assertEqual(candidate_facts[0]["confidence"], 0.9)

    def test_empty_results(self):
        obs = self.normalizer.normalize([], "RUN-004", "ACTION-RECON-001")
        self.assertEqual(obs["outcome"], "PARTIAL")
        self.assertEqual(obs["new_facts"], [])

    def test_invalid_action_id_rejected(self):
        with self.assertRaises(ValueError):
            self.normalizer.normalize([], "RUN-005", "bad-action")

    def test_auto_observation_id(self):
        obs = self.normalizer.normalize([], "RUN-006", "ACTION-RECON-001")
        self.assertTrue(obs["observation_id"].startswith("OBS-NORM-"))

    def test_custom_observation_id(self):
        obs = self.normalizer.normalize([], "RUN-007", "ACTION-RECON-001",
                                        observation_id="MY-OBS-001")
        self.assertEqual(obs["observation_id"], "MY-OBS-001")

    def test_confidence_clamped_in_output(self):
        sr = {
            "source": "ZAP",
            "target_id": "lab-sqli-001",
            "endpoint_id": None,
            "finding_type": "sqli",
            "confidence": 1.5,  # out of range
        }
        obs = self.normalizer.normalize([sr], "RUN-008", "ACTION-SCAN-001")
        for fact in obs["new_facts"]:
            self.assertLessEqual(fact["confidence"], 1.0)
            self.assertGreaterEqual(fact["confidence"], 0.0)

    def test_canonical_finding_type_mapping(self):
        sr = {
            "source": "NUCLEI",
            "target_id": "lab-sqli-001",
            "endpoint_id": None,
            "finding_type": "sql_injection",  # alternate name
            "confidence": 0.8,
        }
        obs = self.normalizer.normalize([sr], "RUN-009", "ACTION-SCAN-002")
        facts = obs["new_facts"]
        # Should be canonicalized to "sqli"
        values = [f["value"] for f in facts]
        self.assertTrue(any("sqli" in v for v in values))

    def test_endpoint_emits_endpoint_fact(self):
        sr = {
            "source": "ZAP",
            "target_id": "lab-sqli-001",
            "endpoint_id": "http://lab-sqli-001/login",
            "finding_type": "sqli",
            "confidence": 0.9,
        }
        obs = self.normalizer.normalize([sr], "RUN-010", "ACTION-SCAN-001")
        endpoint_facts = [f for f in obs["new_facts"] if f["fact_type"] == "ENDPOINT"]
        self.assertTrue(len(endpoint_facts) >= 1)

    def test_normalize_observation_passthrough(self):
        obs_in = {
            "observation_id": "OBS-001",
            "run_id": "RUN-001",
            "action_id": "ACTION-RECON-001",
            "timestamp_utc": "2025-01-01T00:00:00Z",
            "outcome": "SUCCESS",
            "new_facts": [
                {
                    "fact_id": "F1",
                    "fact_type": "SERVICE",
                    "subject": "lab-sqli-001",
                    "value": "http/80",
                    "confidence": 1.5,  # out of range
                }
            ],
        }
        obs_out = self.normalizer.normalize_observation(obs_in)
        self.assertEqual(obs_out["new_facts"][0]["confidence"], 1.0)  # clamped

    def test_reset_clears_state(self):
        sr = {
            "source": "ZAP",
            "target_id": "lab-sqli-001",
            "endpoint_id": None,
            "finding_type": "sqli",
            "confidence": 0.9,
        }
        self.normalizer.normalize([sr], "RUN-011", "ACTION-SCAN-001")
        self.normalizer.reset()
        # After reset, internal dedup state cleared
        obs = self.normalizer.normalize([sr], "RUN-012", "ACTION-SCAN-001")
        self.assertTrue(len(obs["new_facts"]) >= 1)

    def test_observation_has_timestamp(self):
        obs = self.normalizer.normalize([], "RUN-013", "ACTION-RECON-001")
        self.assertIn("timestamp_utc", obs)
        # ISO 8601 format check
        self.assertRegex(obs["timestamp_utc"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


# ===================== Feature Extractors =====================

class TestFeatureExtractors(unittest.TestCase):
    def setUp(self):
        self.facts = [
            {"fact_id": "F1", "fact_type": "SERVICE", "subject": "lab-sqli-001",
             "value": "http/80", "confidence": 0.95},
            {"fact_id": "F2", "fact_type": "ENDPOINT", "subject": "lab-sqli-001",
             "value": "/login", "confidence": 1.0},
            {"fact_id": "F3", "fact_type": "PARAMETER", "subject": "lab-sqli-001",
             "value": "username", "confidence": 0.8},
            {"fact_id": "F4", "fact_type": "CANDIDATE_FINDING", "subject": "lab-sqli-001",
             "value": "sqli", "confidence": 0.9},
            {"fact_id": "F5", "fact_type": "CONFIRMED_FINDING", "subject": "lab-sqli-001",
             "value": "xss", "confidence": 0.95},
            {"fact_id": "F6", "fact_type": "CANDIDATE_FINDING", "subject": "lab-xss-001",
             "value": "xss", "confidence": 0.3},
        ]

    def test_extract_services(self):
        result = extract_services(self.facts)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["fact_type"], "SERVICE")

    def test_extract_endpoints(self):
        result = extract_endpoints(self.facts)
        self.assertEqual(len(result), 1)

    def test_extract_parameters(self):
        result = extract_parameters(self.facts)
        self.assertEqual(len(result), 1)

    def test_extract_findings_all(self):
        result = extract_findings(self.facts)
        self.assertEqual(len(result), 3)  # 2 candidate + 1 confirmed

    def test_extract_findings_with_threshold(self):
        result = extract_findings(self.facts, min_confidence=0.5)
        self.assertEqual(len(result), 2)  # F4 (0.9) and F5 (0.95), F6 (0.3) excluded

    def test_group_by_subject(self):
        groups = group_by_subject(self.facts)
        self.assertIn("lab-sqli-001", groups)
        self.assertIn("lab-xss-001", groups)
        self.assertEqual(len(groups["lab-sqli-001"]), 5)
        self.assertEqual(len(groups["lab-xss-001"]), 1)

    def test_group_by_type(self):
        groups = group_by_type(self.facts)
        self.assertIn("SERVICE", groups)
        self.assertIn("CANDIDATE_FINDING", groups)
        self.assertEqual(len(groups["CANDIDATE_FINDING"]), 2)

    def test_extract_from_empty(self):
        self.assertEqual(extract_services([]), [])
        self.assertEqual(extract_findings([]), [])


# ===================== Ground-Truth Isolation Check =====================

class TestNoGroundTruthReferences(unittest.TestCase):
    """Verify no forbidden tokens in perception code."""

    FORBIDDEN = re.compile(r"ground[_-]?truth|truth_records|expected_detection", re.IGNORECASE)

    def _check_file(self, path):
        if path.exists():
            content = path.read_text(encoding="utf-8")
            matches = self.FORBIDDEN.findall(content)
            self.assertEqual(matches, [], f"forbidden token in {path}: {matches}")

    def test_normalizer_no_forbidden(self):
        root = Path(__file__).resolve().parents[2]
        self._check_file(root / "agent" / "perception" / "normalizers" / "observation_normalizer.py")

    def test_extractors_no_forbidden(self):
        root = Path(__file__).resolve().parents[2]
        self._check_file(root / "agent" / "perception" / "feature_extractors" / "extractors.py")


if __name__ == "__main__":
    unittest.main()
