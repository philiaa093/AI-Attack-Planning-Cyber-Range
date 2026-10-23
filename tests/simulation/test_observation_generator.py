"""Unit tests for Simulator ObservationGenerator (RT-04B).

Validates:
1. Canonical schema compliance (validated by validate_canonical_observation).
2. Canonical 15-fact vocabulary usage.
3. Secret redaction and forbidden ground truth key sanitization.
4. Deterministic fact_id and observation_id generation.
5. Fallback ACTION_OUTCOME fact on failure transitions.
"""
from __future__ import annotations

import unittest

from agent.perception.normalizers.enterprise_normalizer import (
    CANONICAL_FACT_TYPES,
    validate_canonical_observation,
)
from runtime.simulation.engine.observation_generator import ObservationGenerator
from runtime.simulation.engine.transition_engine import TransitionEngine
from runtime.simulation.loader import ScenarioLoader
from scripts.validation.validate_scaffold import ROOT

FIXTURES_DIR = ROOT / "runtime" / "simulation" / "fixtures" / "scenarios"


class TestObservationGenerator(unittest.TestCase):
    def setUp(self) -> None:
        self.loader = ScenarioLoader()
        self.engine = TransitionEngine()
        self.obs_gen = ObservationGenerator()
        self.s1 = self.loader.load_from_file(FIXTURES_DIR / "scenario_s1_straight.json")
        self.s4 = self.loader.load_from_file(FIXTURES_DIR / "scenario_s4_clean.json")

    def test_canonical_schema_compliance_success(self) -> None:
        """Observation emitted from successful transition validates against observation.schema.json."""
        state = self.s1.create_initial_true_state(run_id="RUN-OBS-01")
        res = self.engine.transition(state, self.s1, "ACTION-RECON-001", "lab-dmz-entry")

        obs = self.obs_gen.generate_observation(
            transition_result=res,
            run_id="RUN-OBS-01",
            action_id="ACTION-RECON-001",
            target_id="lab-dmz-entry",
            step=1,
        )

        errors = validate_canonical_observation(obs)
        self.assertEqual(errors, [])
        self.assertEqual(obs["outcome"], "SUCCESS")
        self.assertEqual(obs["source_kind"], "SIMULATED")
        self.assertEqual(len(obs["new_facts"]), 1)
        self.assertEqual(obs["new_facts"][0]["fact_type"], "SERVICE")
        self.assertTrue(obs["new_facts"][0]["fact_id"].startswith("FACT-SERV-"))

    def test_canonical_schema_compliance_failure(self) -> None:
        """Observation emitted from failure transition validates against observation.schema.json."""
        state = self.s4.create_initial_true_state(run_id="RUN-OBS-02")
        res = self.engine.transition(state, self.s4, "ACTION-WEB-001", "lab-dmz-entry")

        obs = self.obs_gen.generate_observation(
            transition_result=res,
            run_id="RUN-OBS-02",
            action_id="ACTION-WEB-001",
            target_id="lab-dmz-entry",
            step=1,
        )

        errors = validate_canonical_observation(obs)
        self.assertEqual(errors, [])
        self.assertEqual(obs["outcome"], "FAILURE")
        self.assertEqual(obs["new_facts"][0]["fact_type"], "ACTION_OUTCOME")
        self.assertEqual(obs["new_facts"][0]["value"]["outcome"], "FAILURE")

    def test_vocabulary_adherence(self) -> None:
        """All emitted facts must belong strictly to the 15-fact canonical vocabulary."""
        state = self.s1.create_initial_true_state(run_id="RUN-OBS-03")
        # Step through foothold
        r1 = self.engine.transition(state, self.s1, "ACTION-RECON-001", "lab-dmz-entry")
        r2 = self.engine.transition(r1.new_true_state, self.s1, "ACTION-SCAN-001", "lab-dmz-entry")
        r3 = self.engine.transition(r2.new_true_state, self.s1, "ACTION-WEB-001", "lab-dmz-entry")

        for r in (r1, r2, r3):
            obs = self.obs_gen.generate_observation(r, run_id="RUN-OBS-03")
            for fact in obs["new_facts"]:
                self.assertIn(fact["fact_type"], CANONICAL_FACT_TYPES)

    def test_secret_and_ground_truth_sanitization(self) -> None:
        """Raw observation with injected secret tokens or ground truth keys is sanitized fail-closed."""
        state = self.s1.create_initial_true_state(run_id="RUN-OBS-04")
        res = self.engine.transition(state, self.s1, "ACTION-RECON-001", "lab-dmz-entry")

        # Create a modified result with tainted raw observations
        tainted_raw = (
            {
                "fact_type": "SERVICE",
                "subject": "lab-dmz-entry:80",
                "value": {
                    "port": 80,
                    "password": "SUPER_SECRET_PLAINTEXT",
                    "ground_truth": "FLAG{LEAKED_TRUTH}",
                    "service_type": "HTTP",
                },
                "confidence": 0.95,
            },
        )
        tainted_res = type(res)(
            transition_id=res.transition_id,
            action_id=res.action_id,
            target_id=res.target_id,
            success=res.success,
            new_true_state=res.new_true_state,
            raw_observations=tainted_raw,
            noise_delta=res.noise_delta,
            reason=res.reason,
            timestamp_utc=res.timestamp_utc,
        )

        obs = self.obs_gen.generate_observation(tainted_res, run_id="RUN-OBS-04")
        # Confirm secrets were stripped
        val = obs["new_facts"][0]["value"]
        self.assertNotIn("password", val)
        self.assertNotIn("ground_truth", val)
        self.assertEqual(val["port"], 80)
        self.assertEqual(val["service_type"], "HTTP")
        # Confirm passes validation
        errors = validate_canonical_observation(obs)
        self.assertEqual(errors, [])

    def test_fallback_action_outcome_sanitizes_reasons(self) -> None:
        """Requirement S: Fallback ACTION_OUTCOME failure fact never leaks firewall, vuln, or guard names."""
        state = self.s4.create_initial_true_state(run_id="RUN-OBS-05")

        # Create a failure TransitionResult with sensitive internal reason
        leaky_reason = "GUARD_FAILED: requires vulnerability CVE-2024-9999 and firewall_allow=False on node s4-node-02"
        res = type(self.engine.transition(state, self.s4, "ACTION-WEB-001", "lab-dmz-entry"))(
            transition_id=None,
            action_id="ACTION-WEB-001",
            target_id="lab-dmz-entry",
            success=False,
            new_true_state=state,
            raw_observations=(),
            noise_delta=0.0,
            reason=leaky_reason,
            timestamp_utc="2026-01-01T00:00:00Z",
        )

        obs = self.obs_gen.generate_observation(res, run_id="RUN-OBS-05")
        self.assertEqual(obs["outcome"], "FAILURE")
        self.assertEqual(len(obs["new_facts"]), 1)
        outcome_fact = obs["new_facts"][0]
        self.assertEqual(outcome_fact["fact_type"], "ACTION_OUTCOME")
        failure_reason = outcome_fact["value"].get("reason", "")

        # Verify sensitive internal simulator details are stripped/sanitized
        self.assertNotIn("CVE-2024-9999", failure_reason)
        self.assertNotIn("firewall_allow", failure_reason)
        self.assertNotIn("s4-node-02", failure_reason)
        self.assertNotIn("GUARD_FAILED", failure_reason)
        self.assertEqual(failure_reason, "ACTION_EXECUTION_FAILED")


if __name__ == "__main__":
    unittest.main()
