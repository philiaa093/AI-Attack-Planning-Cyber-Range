"""Unit tests for RT-02A: Enterprise Observation Model.

Validates:
  A. Existing observation types still validate.
  B. Every new Enterprise fact type has a valid canonical fixture.
  C. Invalid / malformed Enterprise observations fail closed.
  D. Provenance fields validate properly.
  E. Credential observation does not expose plaintext secrets in Planner-facing state.
  F. Reachability does not appear from global topology configs.
  G. Detection signal rejects defender-private Ground Truth fields.
  H. Objective cannot be synthesized from hidden manifests.
  I. Inferred hypotheses carry source_kind="PLANNER_INFERENCE".
"""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from agent.perception.normalizers import (
    CANONICAL_FACT_TYPES,
    EnterpriseObservationNormalizer,
    ObservationNormalizer,
    make_enterprise_fact_id,
    validate_canonical_observation,
)
from scripts.validation.validate_scaffold import ROOT, validate_shape


class EnterpriseObservationModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.normalizer = EnterpriseObservationNormalizer()
        self.legacy_normalizer = ObservationNormalizer()
        self.schema = json.loads(
            (ROOT / "agent" / "planner" / "contracts" / "observation.schema.json").read_text(encoding="utf-8")
        )
        self.run_id = "RUN-ENT-TEST-001"
        self.action_id = "ACTION-RECON-001"

    def test_01_existing_observation_types_still_validate(self) -> None:
        """Requirement A: All 8 legacy fact types validate against updated schema."""
        legacy_fact_types = [
            ("TARGET", "lab-target-01", "active"),
            ("SERVICE", "lab-target-01:80", "http"),
            ("ENDPOINT", "lab-target-01", "/api/v1"),
            ("PARAMETER", "lab-target-01", "username"),
            ("CANDIDATE_FINDING", "lab-target-01", "sqli"),
            ("CONFIRMED_FINDING", "lab-target-01", "xss"),
            ("ACTION_OUTCOME", "lab-target-01", "SUCCESS"),
            ("CONTROL", "lab-target-01", "REVIEW_REQUIRED"),
        ]

        facts = []
        for ft, subj, val in legacy_fact_types:
            facts.append({
                "fact_id": make_enterprise_fact_id(ft, subj, val),
                "fact_type": ft,
                "subject": subj,
                "value": val,
                "confidence": 0.9,
            })

        obs = {
            "observation_id": "OBS-LEGACY-001",
            "run_id": self.run_id,
            "action_id": self.action_id,
            "timestamp_utc": "2026-10-17T12:00:00Z",
            "outcome": "SUCCESS",
            "new_facts": facts,
            "evidence_refs": ["EV-LEGACY-001"],
        }

        errors = validate_shape(obs, self.schema)
        self.assertEqual(errors, [])
        self.assertEqual(validate_canonical_observation(obs), [])

    def test_02_each_new_enterprise_fact_type_has_valid_canonical_fixture(self) -> None:
        """Requirement B: Valid canonical fixtures for all 7 new Enterprise fact types."""
        fixtures = {
            "HOST": {
                "fact_id": "FACT-HOST-001",
                "fact_type": "HOST",
                "subject": "host-internal-01",
                "value": "10.0.1.50",
                "confidence": 1.0,
            },
            "ACCESS": {
                "fact_id": "FACT-ACCE-001",
                "fact_type": "ACCESS",
                "subject": "host-internal-01",
                "value": "USER",
                "confidence": 0.95,
            },
            "CREDENTIAL": {
                "fact_id": "FACT-CRED-001",
                "fact_type": "CREDENTIAL",
                "subject": "CORP.LOCAL",
                "value": {
                    "credential_id": "CRED-OPAQ-a1b2c3d4e5f6",
                    "principal": "svc_backup",
                    "credential_kind": "NTLM_HASH",
                    "observed_scope": "CORP.LOCAL",
                    "validity_state": "VALID",
                },
                "confidence": 0.9,
            },
            "SESSION": {
                "fact_id": "FACT-SESS-001",
                "fact_type": "SESSION",
                "subject": "host-internal-01",
                "value": {
                    "session_id": "SESS-OPAQ-998877665544",
                    "target_id": "host-internal-01",
                    "access_level": "USER",
                    "state": "ACTIVE",
                },
                "confidence": 1.0,
            },
            "REACHABILITY": {
                "fact_id": "FACT-REAC-001",
                "fact_type": "REACHABILITY",
                "subject": "host-entry-01",
                "value": {
                    "from_host": "host-entry-01",
                    "to_host": "host-internal-01",
                    "protocol": "tcp",
                    "port": 445,
                },
                "confidence": 0.85,
            },
            "DETECTION_SIGNAL": {
                "fact_id": "FACT-DETE-001",
                "fact_type": "DETECTION_SIGNAL",
                "subject": "host-internal-01",
                "value": {
                    "signal_type": "WAF_REJECTION",
                    "target_id": "host-internal-01",
                    "observed_effect": "HTTP 403 Forbidden with custom block banner",
                    "status_code": 403,
                },
                "confidence": 0.99,
            },
            "OBJECTIVE": {
                "fact_id": "FACT-OBJE-001",
                "fact_type": "OBJECTIVE",
                "subject": "OBJ-DOMAIN-ADMIN",
                "value": {
                    "objective_id": "OBJ-DOMAIN-ADMIN",
                    "status": "ACHIEVED",
                    "milestone": "FLAG_CAPTURED",
                },
                "confidence": 1.0,
            },
        }

        self.assertEqual(len(fixtures), 7)
        for name, fact in fixtures.items():
            obs = {
                "observation_id": f"OBS-FIXTURE-{name}-001",
                "run_id": self.run_id,
                "action_id": self.action_id,
                "timestamp_utc": "2026-10-17T12:00:00Z",
                "outcome": "SUCCESS",
                "new_facts": [fact],
                "evidence_refs": [f"EV-{name}-001"],
            }
            with self.subTest(fact_type=name):
                errors = validate_shape(obs, self.schema)
                self.assertEqual(errors, [])
                self.assertEqual(validate_canonical_observation(obs), [])

    def test_03_invalid_malformed_enterprise_observations_fail_closed(self) -> None:
        """Requirement C: Invalid or malformed Enterprise observations fail closed."""
        base_obs = {
            "observation_id": "OBS-VALID-001",
            "run_id": self.run_id,
            "action_id": self.action_id,
            "timestamp_utc": "2026-10-17T12:00:00Z",
            "outcome": "SUCCESS",
            "new_facts": [{
                "fact_id": "FACT-HOST-001",
                "fact_type": "HOST",
                "subject": "host-01",
                "value": "10.0.0.1",
                "confidence": 0.8,
            }],
        }

        # 1. Missing required observation_id
        bad1 = copy.deepcopy(base_obs)
        del bad1["observation_id"]
        self.assertTrue(validate_canonical_observation(bad1))

        # 2. Invalid action_id pattern
        bad2 = copy.deepcopy(base_obs)
        bad2["action_id"] = "INVALID-ACTION-ID"
        self.assertTrue(validate_canonical_observation(bad2))

        # 3. Invalid fact_type
        bad3 = copy.deepcopy(base_obs)
        bad3["new_facts"][0]["fact_type"] = "MAGIC_VULNERABILITY"
        self.assertTrue(validate_canonical_observation(bad3))

        # 4. Out of range confidence
        bad4 = copy.deepcopy(base_obs)
        bad4["new_facts"][0]["confidence"] = 1.5
        self.assertTrue(validate_canonical_observation(bad4))

        # 5. Non-UTC timestamp
        bad5 = copy.deepcopy(base_obs)
        bad5["timestamp_utc"] = "2026-10-17 12:00:00"
        self.assertTrue(validate_canonical_observation(bad5))

        # 6. Unknown property (additionalProperties: false)
        bad6 = copy.deepcopy(base_obs)
        bad6["arbitrary_field"] = "malicious_injection"
        self.assertTrue(validate_canonical_observation(bad6))

    def test_04_provenance_fields_validate_properly(self) -> None:
        """Requirement D: Observation provenance fields validate and support tracing."""
        obs = {
            "observation_id": "OBS-PROV-001",
            "run_id": self.run_id,
            "action_id": "ACTION-SCAN-001",
            "timestamp_utc": "2026-10-17T12:34:56Z",
            "outcome": "PARTIAL",
            "source_kind": "TOOL_ADAPTER",
            "source_target": "lab-target-01",
            "source_session": "SESS-001",
            "confidence": 0.85,
            "sequence_num": 42,
            "evidence_refs": ["EV-SCAN-001", "EV-SCAN-002"],
            "new_facts": [{
                "fact_id": "FACT-SERV-001",
                "fact_type": "SERVICE",
                "subject": "lab-target-01:445",
                "value": "smb",
                "confidence": 0.85,
            }],
        }

        # Valid provenance validates cleanly
        self.assertEqual(validate_shape(obs, self.schema), [])
        self.assertEqual(validate_canonical_observation(obs), [])

        # Invalid source_kind rejected
        bad_source = copy.deepcopy(obs)
        bad_source["source_kind"] = "UNKNOWN_SOURCE_KIND"
        self.assertTrue(validate_canonical_observation(bad_source))

        # Negative sequence_num rejected
        bad_seq = copy.deepcopy(obs)
        bad_seq["sequence_num"] = -5
        self.assertTrue(validate_canonical_observation(bad_seq))

    def test_05_credential_observation_does_not_expose_plaintext_secrets(self) -> None:
        """Requirement E: Plaintext secrets are stripped into opaque references."""
        raw_cred_input = [{
            "username": "domain_admin",
            "password": "SuperSecretPassword123!",  # Plaintext password in raw dump!
            "cleartext": "SuperSecretPassword123!",
            "scope": "CORP.LOCAL",
            "kind": "NTLM_HASH",
        }]

        # Normalizer must strip plaintext password and emit opaque reference
        obs = self.normalizer.normalize_credentials(
            raw_cred_input,
            run_id=self.run_id,
            action_id="ACTION-SCAN-001",
            evidence_refs=["EV-CRED-001"],
        )

        self.assertEqual(obs["outcome"], "SUCCESS")
        facts = obs["new_facts"]
        self.assertEqual(len(facts), 1)
        cred_fact = facts[0]
        self.assertEqual(cred_fact["fact_type"], "CREDENTIAL")

        val = cred_fact["value"]
        self.assertIsInstance(val, dict)
        self.assertTrue(val["credential_id"].startswith("CRED-OPAQ-"))
        self.assertEqual(val["principal"], "domain_admin")
        self.assertEqual(val["observed_scope"], "CORP.LOCAL")

        # Invariant: Plaintext password must NOT appear anywhere in the observation
        obs_json = json.dumps(obs)
        self.assertNotIn("SuperSecretPassword123!", obs_json)
        self.assertNotIn("password", obs_json)
        self.assertNotIn("cleartext", obs_json)

        # Attempt to inject plaintext secret key into fact directly must fail closed
        malicious_fact = {
            "observation_id": "OBS-LEAK-001",
            "run_id": self.run_id,
            "action_id": self.action_id,
            "timestamp_utc": "2026-10-17T12:00:00Z",
            "outcome": "SUCCESS",
            "new_facts": [{
                "fact_id": "FACT-LEAK-001",
                "fact_type": "CREDENTIAL",
                "subject": "CORP",
                "value": {"password": "exposed_plaintext"},
                "confidence": 1.0,
            }],
        }
        self.assertTrue(validate_canonical_observation(malicious_fact))

    def test_06_reachability_does_not_appear_from_global_topology_config(self) -> None:
        """Requirement F: Reachability cannot be synthesized from global topology configs."""
        # Attempt to normalize reachability with is_topology_config=True must raise ValueError
        with self.assertRaisesRegex(ValueError, "topology config"):
            self.normalizer.normalize_reachability(
                [{"from_host": "host-A", "to_host": "host-B"}],
                run_id=self.run_id,
                action_id=self.action_id,
                is_topology_config=True,
            )

        # Observed reachability from legitimate probe succeeds
        obs = self.normalizer.normalize_reachability(
            [{"from_host": "host-A", "to_host": "host-B", "protocol": "tcp", "port": 445}],
            run_id=self.run_id,
            action_id=self.action_id,
            source_kind="AGENT_PROBE",
            evidence_refs=["EV-ROUTE-001"],
        )
        self.assertEqual(obs["outcome"], "SUCCESS")
        self.assertEqual(obs["new_facts"][0]["fact_type"], "REACHABILITY")
        self.assertEqual(obs["new_facts"][0]["value"]["from_host"], "host-A")
        self.assertEqual(obs["new_facts"][0]["value"]["to_host"], "host-B")

    def test_07_detection_signal_rejects_defender_private_fields(self) -> None:
        """Requirement G: Detection signal rejects defender-private Ground Truth fields."""
        # Valid attacker-observable signal succeeds
        obs = self.normalizer.normalize_detection_signal(
            [{"signal_type": "WAF_REJECTION", "target": "lab-target-01", "status_code": 403}],
            run_id=self.run_id,
            action_id=self.action_id,
            evidence_refs=["EV-DET-001"],
        )
        self.assertEqual(obs["new_facts"][0]["fact_type"], "DETECTION_SIGNAL")
        self.assertEqual(obs["new_facts"][0]["value"]["signal_type"], "WAF_REJECTION")

        # Invalid non-observable signal rejected
        with self.assertRaisesRegex(ValueError, "invalid detection signal"):
            self.normalizer.normalize_detection_signal(
                [{"signal_type": "INTERNAL_SIEM_CORRELATION_ALERT", "target": "lab-target-01"}],
                run_id=self.run_id,
                action_id=self.action_id,
            )

        # Defender-private fields in input rejected
        for forbidden in ("siem_alert_id", "siem_rule_id", "ground_truth", "hidden_detection_score"):
            with self.subTest(forbidden=forbidden):
                with self.assertRaisesRegex(ValueError, "defender-private field"):
                    self.normalizer.normalize_detection_signal(
                        [{"signal_type": "BLOCKED", "target": "lab-target-01", forbidden: "private_val"}],
                        run_id=self.run_id,
                        action_id=self.action_id,
                    )

    def test_08_objective_cannot_be_synthesized_from_hidden_manifest(self) -> None:
        """Requirement H: Objective requires observed action and evidence; cannot synthesize from manifest."""
        with self.assertRaisesRegex(ValueError, "hidden manifest"):
            self.normalizer.normalize_objective(
                [{"objective_id": "OBJ-FLAG-01"}],
                run_id=self.run_id,
                action_id=self.action_id,
                is_hidden_manifest=True,
            )

        # Without evidence_refs, also rejected
        with self.assertRaisesRegex(ValueError, "evidence"):
            self.normalizer.normalize_objective(
                [{"objective_id": "OBJ-FLAG-01"}],
                run_id=self.run_id,
                action_id=self.action_id,
                evidence_refs=[],
            )

        # Legitimate objective with evidence succeeds
        obs = self.normalizer.normalize_objective(
            [{"objective_id": "OBJ-FLAG-01", "status": "ACHIEVED"}],
            run_id=self.run_id,
            action_id=self.action_id,
            evidence_refs=["EV-OBJ-001"],
        )
        self.assertEqual(obs["new_facts"][0]["fact_type"], "OBJECTIVE")
        self.assertEqual(obs["new_facts"][0]["value"]["status"], "ACHIEVED")

    def test_09_session_normalizer_sanitizes_raw_shell(self) -> None:
        """Requirement E & 6: SESSION facts sanitize raw shell and emit opaque handle."""
        raw_session_input = [{
            "target": "host-db-01",
            "access_level": "ADMIN",
            "raw_handle": "<subprocess.Popen object at 0x7f8b2c>",  # Raw process leak!
            "state": "ACTIVE",
        }]

        obs = self.normalizer.normalize_session(
            raw_session_input,
            run_id=self.run_id,
            action_id=self.action_id,
            evidence_refs=["EV-SESS-001"],
        )

        facts = obs["new_facts"]
        session_facts = [f for f in facts if f["fact_type"] == "SESSION"]
        access_facts = [f for f in facts if f["fact_type"] == "ACCESS"]

        self.assertEqual(len(session_facts), 1)
        self.assertEqual(len(access_facts), 1)

        val = session_facts[0]["value"]
        self.assertTrue(val["session_id"].startswith("SESS-OPAQ-"))
        self.assertEqual(val["access_level"], "ADMIN")
        self.assertEqual(val["state"], "ACTIVE")

        # Invariant: Raw subprocess representation is NOT in the observation
        self.assertNotIn("subprocess", json.dumps(obs))

    def test_10_facts_vs_hypotheses_provenance(self) -> None:
        """Requirement 10: Inferred hypotheses carry source_kind='PLANNER_INFERENCE'."""
        inferred = [{"fact_type": "HOST", "subject": "host-hypothesis-01", "value": "10.0.99.1"}]
        obs = self.normalizer.normalize_hypothesis(
            inferred,
            run_id=self.run_id,
            action_id=self.action_id,
        )

        self.assertEqual(obs["source_kind"], "PLANNER_INFERENCE")
        self.assertEqual(obs["outcome"], "PARTIAL")
        self.assertEqual(obs["confidence"], 0.3)


if __name__ == "__main__":
    unittest.main()
