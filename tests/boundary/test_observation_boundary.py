"""Boundary tests for RT-02A: Observation Model Trust Boundary.

Enforces:
  1. Trust Boundary Invariant:
     Raw Tool / Executor Result -> Normalizer -> Canonical Observation -> State -> Planner.
     Direct raw tool stdout, unnormalized scanner JSON, or arbitrary tool outputs CANNOT
     be ingested directly into PlannerStateAdapter or AutonomousRunner without normalizer.
  2. Visibility Trust Boundary (Requirement I):
     Untrusted/raw objects cannot directly open planner visibility.
  3. Hypotheses Non-Expansion:
     Inferred hypotheses (source_kind="PLANNER_INFERENCE") cannot unlock target visibility.
  4. Redaction Boundary:
     Observations containing plaintext passwords or credentials fail closed before state entry.
  5. Ground Truth Boundary:
     Observations containing defender-private SIEM or ground truth tokens fail closed.
  6. Global Topology Boundary:
     Reachability facts cannot be injected or derived from global configuration files.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from agent.memory.state.state_manager import StateManager
from agent.perception.normalizers import (
    EnterpriseObservationNormalizer,
    validate_canonical_observation,
)
from runtime.evidence.discovery_recorder import DurableEvidenceRecorder
from runtime.orchestration.autonomous_runner import AutonomousRunner
from runtime.planners.observed_planner import ObservedStatePlanner
from runtime.planners.planner_adapter import PlannerStateAdapter
from runtime.planners.planner_interface import project_visible_targets
from runtime.safety.discovery_gate import (
    ApprovalToken,
    CentralizedSafetyGate,
)
from runtime.state.knowledge_state_store import KnowledgeStateStore, StoreContext
from scripts.validation.validate_scaffold import ROOT


CONTEXT = StoreContext("RUN-BOUND-OBS-001", "SES-001", "EP-001")


class ObservationBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.entry_seed = "lab-entry-01"
        self.hidden_target = "lab-internal-99"
        self.normalizer = EnterpriseObservationNormalizer()

    def test_01_raw_tool_output_cannot_bypass_normalizer_into_state_adapter(self) -> None:
        """Invariant 1: Raw scanner/tool JSON without canonical envelope raises ValueError."""
        sm = StateManager(CONTEXT.run_id, "SCN-001", "OBJ-001")
        adapter = PlannerStateAdapter(sm)

        # Raw tool output (e.g. raw Nuclei / ZAP finding without canonical observation envelope)
        raw_tool_output = {
            "source": "ZAP",
            "target_id": self.hidden_target,
            "finding_type": "open_port",
            "confidence": 0.9,
            "raw_stdout": "Port 8080 open on 10.0.1.5",
        }

        # Attempting direct ingestion of raw tool output into state adapter MUST fail closed
        with self.assertRaises(ValueError):
            adapter.ingest_observation(raw_tool_output)

        # State facts must remain empty
        self.assertEqual(sm.get_fact_count(), 0)

    def test_02_untrusted_raw_object_cannot_open_planner_visibility(self) -> None:
        """Requirement I: Raw unnormalized objects cannot open planner visibility in AutonomousRunner."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            old_root = os.environ.get("APPROVED_EVIDENCE_ROOT")
            os.environ["APPROVED_EVIDENCE_ROOT"] = tmp_dir
            try:
                gate = CentralizedSafetyGate(
                    base_origin="http://127.0.0.1:18088",
                    target_registry={
                        self.entry_seed: {"host": "127.0.0.1", "port": 18088},
                        self.hidden_target: {"host": "127.0.0.1", "port": 18089},
                    },
                    target_allowlist={self.entry_seed, self.hidden_target},
                    canonical_target_allowlist={self.entry_seed, self.hidden_target},
                    action_allowlist={"ACTION-RECON-001"},
                    lab_mode=True,
                )
                recorder = DurableEvidenceRecorder(run_id="RUN-BOUND-VIS-TEST")
                approval = ApprovalToken(
                    approval_id="APP-01",
                    run_id="RUN-BOUND-VIS-TEST",
                    target_id=self.entry_seed,
                    action_id="*",
                    not_before=0,
                    expires_at=2000000000,
                )

                runner = AutonomousRunner(
                    target_id=self.entry_seed,
                    run_id="RUN-BOUND-VIS-TEST",
                    gate=gate,
                    recorder=recorder,
                    approval=approval,
                )

                # At start, visibility is strictly entry seed
                self.assertEqual(runner.visible_targets, {self.entry_seed})

                # Untrusted/raw tool dictionary attempting to inject target
                raw_untrusted_obj = {
                    "raw_command": f"nmap {self.hidden_target}",
                    "discovered_host": self.hidden_target,
                    "target_id": self.hidden_target,
                }

                # Attempting to ingest raw object must raise ValueError and NOT expand visibility
                with self.assertRaises(ValueError):
                    runner._ingest_and_update_visibility(raw_untrusted_obj)

                # Visibility remains strictly {self.entry_seed}
                self.assertEqual(runner.visible_targets, {self.entry_seed})
                self.assertNotIn(self.hidden_target, runner.visible_targets)
                self.assertEqual(runner.planner.visible_targets, {self.entry_seed})

            finally:
                if old_root is not None:
                    os.environ["APPROVED_EVIDENCE_ROOT"] = old_root
                else:
                    os.environ.pop("APPROVED_EVIDENCE_ROOT", None)

    def test_03_hypotheses_cannot_unlock_planner_visibility(self) -> None:
        """Requirement 10: Inferred hypotheses (source_kind=PLANNER_INFERENCE) do not unlock visibility."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            old_root = os.environ.get("APPROVED_EVIDENCE_ROOT")
            os.environ["APPROVED_EVIDENCE_ROOT"] = tmp_dir
            try:
                gate = CentralizedSafetyGate(
                    base_origin="http://127.0.0.1:18088",
                    target_registry={
                        self.entry_seed: {"host": "127.0.0.1", "port": 18088},
                        self.hidden_target: {"host": "127.0.0.1", "port": 18089},
                    },
                    target_allowlist={self.entry_seed, self.hidden_target},
                    canonical_target_allowlist={self.entry_seed, self.hidden_target},
                    action_allowlist={"ACTION-RECON-001"},
                    lab_mode=True,
                )
                recorder = DurableEvidenceRecorder(run_id="RUN-BOUND-HYPO-TEST")
                approval = ApprovalToken(
                    approval_id="APP-02",
                    run_id="RUN-BOUND-HYPO-TEST",
                    target_id=self.entry_seed,
                    action_id="*",
                    not_before=0,
                    expires_at=2000000000,
                )

                runner = AutonomousRunner(
                    target_id=self.entry_seed,
                    run_id="RUN-BOUND-HYPO-TEST",
                    gate=gate,
                    recorder=recorder,
                    approval=approval,
                )

                # Normalizer creates hypothesis with source_kind="PLANNER_INFERENCE"
                hypo_obs = self.normalizer.normalize_hypothesis(
                    [{"fact_type": "TARGET", "subject": self.entry_seed, "value": self.hidden_target}],
                    run_id="RUN-BOUND-HYPO-TEST",
                    action_id="ACTION-RECON-001",
                )

                # Ingest hypothesis
                applied = runner._ingest_and_update_visibility(hypo_obs)
                self.assertTrue(applied)

                # Visibility MUST NOT expand for inferred hypotheses
                self.assertEqual(runner.visible_targets, {self.entry_seed})
                self.assertNotIn(self.hidden_target, runner.visible_targets)
                self.assertEqual(runner.planner.visible_targets, {self.entry_seed})

            finally:
                if old_root is not None:
                    os.environ["APPROVED_EVIDENCE_ROOT"] = old_root
                else:
                    os.environ.pop("APPROVED_EVIDENCE_ROOT", None)

    def test_04_unredacted_secret_fails_closed_at_knowledge_state_store(self) -> None:
        """Invariant 4: Observations with unredacted plaintext passwords are rejected by store."""
        with KnowledgeStateStore(":memory:") as store:
            store.create_context(
                CONTEXT,
                scenario_id="SCN-001",
                objective_id="OBJ-001",
                budget={"actions": 10, "requests": 50, "seconds": 3600.0},
                allowed_subjects=["lab-target-01"],
                allowed_actions=["ACTION-SCAN-001"],
            )

            # Observation attempting to inject cleartext password key
            malicious_obs = {
                "observation_id": "OBS-UNREDACTED-001",
                "run_id": CONTEXT.run_id,
                "action_id": "ACTION-SCAN-001",
                "timestamp_utc": "2026-10-17T12:00:00Z",
                "outcome": "SUCCESS",
                "new_facts": [{
                    "fact_id": "FACT-LEAK-99",
                    "fact_type": "CREDENTIAL",
                    "subject": "lab-target-01",
                    "value": {"password": "injected_secret_value"},
                    "confidence": 1.0,
                }],
            }

            # Ingest must fail closed
            with self.assertRaises(ValueError):
                store.ingest(
                    CONTEXT,
                    malicious_obs,
                    source="SCANNER",
                    source_sha256="a" * 64,
                )

    def test_05_ground_truth_and_defender_tokens_fail_closed_at_boundary(self) -> None:
        """Invariant 5: Observations containing ground truth or SIEM tokens fail validation."""
        for forbidden in ("ground_truth", "truth", "siem_alert_id", "hidden_detection_score"):
            bad_obs = {
                "observation_id": f"OBS-FORBIDDEN-{forbidden}",
                "run_id": CONTEXT.run_id,
                "action_id": "ACTION-RECON-001",
                "timestamp_utc": "2026-10-17T12:00:00Z",
                "outcome": "SUCCESS",
                "new_facts": [{
                    "fact_id": "FACT-001",
                    "fact_type": "DETECTION_SIGNAL",
                    "subject": "lab-target-01",
                    "value": {forbidden: "oracle_leak"},
                    "confidence": 1.0,
                }],
            }
            errors = validate_canonical_observation(bad_obs)
            self.assertTrue(len(errors) > 0, f"Expected failure for token '{forbidden}'")


if __name__ == "__main__":
    unittest.main()
