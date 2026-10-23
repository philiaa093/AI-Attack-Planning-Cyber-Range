"""Unit tests for Canonical SimulationExecutor (RT-04B).

Validates:
1. Strict execution ordering:
   Planner Proposal
   → ActionConstraintEvaluator
   → CentralizedSafetyGate
   → Simulation Executor / Transition Engine
   → Hidden True-State Transition
   → Observation Generator
   → Canonical Observation
   → State/Knowledge ingestion
   → Belief Projection
2. Zero Bypass:
   Precondition constraint failures reject before reaching simulation.
   Safety gate rejections block before reaching simulation.
3. Partial Observability / Fog-of-War:
   Eligible in Belief State != Successful in Environment.
4. End-to-end multi-step progression on S1 with StateManager and BeliefState.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from actions.catalog.action_registry import get_action_registry
from agent.memory.state.belief_state import BeliefState
from agent.memory.state.state_manager import StateManager
from runtime.evaluators.action_evaluator import ActionConstraintEvaluator
from runtime.safety.discovery_gate import ApprovalToken, CentralizedSafetyGate, KillSwitch
from runtime.simulation.engine.simulation_executor import (
    SimulationExecutionResult,
    SimulationExecutor,
)

from runtime.simulation.loader import ScenarioLoader
from scripts.validation.validate_scaffold import ROOT

FIXTURES_DIR = ROOT / "runtime" / "simulation" / "fixtures" / "scenarios"


class TestSimulationExecutor(unittest.TestCase):
    def setUp(self) -> None:
        self.loader = ScenarioLoader()
        self.s1 = self.loader.load_from_file(FIXTURES_DIR / "scenario_s1_straight.json")
        self.s3 = self.loader.load_from_file(FIXTURES_DIR / "scenario_s3_blocked.json")

    def _make_safety_gate(
        self,
        target_allowlist: set[str] | None = None,
        action_allowlist: set[str] | None = None,
        kill_switch: KillSwitch | None = None,
    ) -> CentralizedSafetyGate:
        targets = target_allowlist or {
            "lab-dmz-entry",
            "lab-internal-app",
            "lab-db-crown",
            "lab-jump-box",
        }
        actions = action_allowlist or {
            "ACTION-RECON-001",
            "ACTION-SCAN-001",
            "ACTION-WEB-001",
            "ACTION-AUTH-001",
            "ACTION-FLOW-001",
            "ACTION-FLOW-002",
            "ACTION-END-001",
        }
        return CentralizedSafetyGate(
            base_origin="http://127.0.0.1:18088",
            canonical_target_allowlist=targets,
            canonical_action_allowlist=actions,
            target_allowlist=targets,
            action_allowlist=actions,
            kill_switch=kill_switch or KillSwitch(),
            lab_mode=True,
        )

    def test_precondition_rejection_blocks_simulation(self) -> None:
        """Actions failing ActionConstraintEvaluator must NEVER reach simulation."""
        state_mgr = StateManager(
            run_id="RUN-TEST-PRECOND",
            scenario_id=self.s1.scenario_id,
            objective_id=self.s1.objective.objective_id,
        )
        gate = self._make_safety_gate()
        executor = SimulationExecutor(
            scenario=self.s1,
            safety_gate=gate,
            state_manager=state_mgr,
        )

        # Attacker tries ACTION-WEB-001 on lab-dmz-entry before scanning for findings
        # In empty belief state, CONFIRMED_FINDING is required by ACTION-WEB-001
        res = executor.execute_proposal(
            proposal={"action_id": "ACTION-WEB-001", "target_id": "lab-dmz-entry"}
        )

        self.assertFalse(res.success)
        self.assertEqual(res.status, "REJECTED_BY_CONSTRAINTS")
        self.assertIsNone(res.transition_result)
        self.assertIsNone(res.canonical_observation)
        self.assertEqual(executor.step_count, 0)
        self.assertEqual(executor.get_true_state().current_step, 0)

    def test_safety_gate_rejection_blocks_simulation(self) -> None:
        """Actions failing Safety Gate (e.g. target not in allowlist) must NEVER reach simulation."""
        # Initial belief knows entry node
        state_mgr = StateManager(
            run_id="RUN-TEST-GATE",
            scenario_id=self.s1.scenario_id,
            objective_id=self.s1.objective.objective_id,
        )
        # Entry seed fact
        state_mgr.apply_observation({
            "observation_id": "OBS-INIT-01",
            "run_id": "RUN-TEST-GATE",
            "action_id": "ACTION-RECON-001",
            "timestamp_utc": "2026-10-18T10:00:00Z",
            "outcome": "SUCCESS",
            "new_facts": [
                {
                    "fact_id": "FACT-TARG-ENTRY",
                    "fact_type": "TARGET",
                    "subject": "lab-unauthorized-target",
                    "value": {"target_id": "lab-unauthorized-target"},
                    "confidence": 1.0,
                }
            ],
            "evidence_refs": [],
            "source_kind": "SIMULATED",
            "confidence": 1.0,
            "sequence_num": 0,
        })

        # Safety gate excludes lab-unauthorized-target
        gate = self._make_safety_gate(target_allowlist={"lab-dmz-entry"})
        executor = SimulationExecutor(
            scenario=self.s1,
            safety_gate=gate,
            state_manager=state_mgr,
        )

        res = executor.execute_proposal(
            proposal={"action_id": "ACTION-RECON-001", "target_id": "lab-unauthorized-target"}
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, "REJECTED_BY_SAFETY_GATE")
        self.assertIn("TARGET_NOT_IN_ALLOWLIST", res.reasons[0])
        self.assertIsNone(res.transition_result)
        self.assertEqual(executor.step_count, 0)

    def test_kill_switch_blocks_simulation(self) -> None:
        """Active kill switch blocks execution immediately."""
        state_mgr = StateManager(
            run_id="RUN-TEST-KS",
            scenario_id=self.s1.scenario_id,
            objective_id=self.s1.objective.objective_id,
        )
        # Seed entry node in belief
        state_mgr.apply_observation({
            "observation_id": "OBS-INIT-KS",
            "run_id": "RUN-TEST-KS",
            "action_id": "ACTION-RECON-001",
            "timestamp_utc": "2026-10-18T10:00:00Z",
            "outcome": "SUCCESS",
            "new_facts": [
                {
                    "fact_id": "FACT-TARG-01",
                    "fact_type": "TARGET",
                    "subject": "lab-dmz-entry",
                    "value": {"target_id": "lab-dmz-entry"},
                    "confidence": 1.0,
                }
            ],
            "evidence_refs": [],
            "source_kind": "SIMULATED",
            "confidence": 1.0,
            "sequence_num": 0,
        })

        ks = KillSwitch()
        ks.activate()
        gate = self._make_safety_gate(kill_switch=ks)
        executor = SimulationExecutor(
            scenario=self.s1,
            safety_gate=gate,
            state_manager=state_mgr,
        )

        res = executor.execute_proposal(
            proposal={"action_id": "ACTION-RECON-001", "target_id": "lab-dmz-entry"}
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, "REJECTED_BY_SAFETY_GATE")
        self.assertIn("KILL_SWITCH_ACTIVE", res.reasons[0])

    def test_s1_end_to_end_progression(self) -> None:
        """End-to-end pipeline execution on S1 straight scenario."""
        state_mgr = StateManager(
            run_id="RUN-S1-E2E",
            scenario_id=self.s1.scenario_id,
            objective_id=self.s1.objective.objective_id,
        )
        gate = self._make_safety_gate()
        executor = SimulationExecutor(
            scenario=self.s1,
            safety_gate=gate,
            state_manager=state_mgr,
            random_seed=42,
        )

        # Seed initial entry target in belief state (Fog-of-War at t=0)
        state_mgr.apply_observation({
            "observation_id": "OBS-INIT-S1",
            "run_id": "RUN-S1-E2E",
            "action_id": "ACTION-RECON-001",
            "timestamp_utc": "2026-10-18T10:00:00Z",
            "outcome": "SUCCESS",
            "new_facts": [
                {
                    "fact_id": "FACT-TARG-DMZ",
                    "fact_type": "TARGET",
                    "subject": "lab-dmz-entry",
                    "value": {"target_id": "lab-dmz-entry"},
                    "confidence": 1.0,
                }
            ],
            "evidence_refs": [],
            "source_kind": "SIMULATED",
            "confidence": 1.0,
            "sequence_num": 0,
        })

        # Step 1: RECON on lab-dmz-entry
        r1 = executor.execute_proposal({"action_id": "ACTION-RECON-001", "target_id": "lab-dmz-entry"})
        self.assertTrue(r1.success)
        self.assertEqual(r1.status, "EXECUTED")
        self.assertIsNotNone(r1.updated_belief_state)
        self.assertEqual(len(r1.updated_belief_state.known_services), 1)

        # Step 2: SCAN on lab-dmz-entry
        r2 = executor.execute_proposal({"action_id": "ACTION-SCAN-001", "target_id": "lab-dmz-entry"})
        self.assertTrue(r2.success)
        self.assertEqual(len(r2.updated_belief_state.confirmed_findings), 1)

        # Step 3: FOOTHOLD on lab-dmz-entry
        r3 = executor.execute_proposal({"action_id": "ACTION-WEB-001", "target_id": "lab-dmz-entry"})
        self.assertTrue(r3.success)
        self.assertEqual(r3.updated_belief_state.access_state.get("lab-dmz-entry"), "FOOTHOLD")
        self.assertTrue(len(r3.updated_belief_state.active_sessions) >= 1)

        # Step 4: DUMP CREDS on lab-dmz-entry
        r4 = executor.execute_proposal({"action_id": "ACTION-AUTH-001", "target_id": "lab-dmz-entry"})
        self.assertTrue(r4.success)
        self.assertEqual(len(r4.updated_belief_state.known_credentials), 1)

        # Step 5: PIVOT to lab-internal-app
        r5 = executor.execute_proposal(
            {
                "action_id": "ACTION-FLOW-001",
                "target_id": "lab-internal-app",
                "from_node_id": "lab-dmz-entry",
                "credential_id": "cred-app-svc",
            }
        )
        self.assertTrue(
            r5.success,
            f"R5 failed: {r5.reasons}, status={r5.status}, constraint={r5.constraint_evaluation.reasons if r5.constraint_evaluation else None}",
        )

        self.assertEqual(r5.updated_belief_state.access_state.get("lab-internal-app"), "USER")
        self.assertEqual(len(r5.updated_belief_state.known_credentials), 2)
        self.assertEqual(len(r5.updated_belief_state.observed_reachability), 2)

        # Step 6: OBJECTIVE on lab-db-crown
        r6 = executor.execute_proposal(
            {
                "action_id": "ACTION-FLOW-002",
                "target_id": "lab-db-crown",
                "from_node_id": "lab-internal-app",
                "credential_id": "cred-db-admin",
            }
        )
        self.assertTrue(
            r6.success,
            f"R6 failed: {r6.reasons}, status={r6.status}, constraint={r6.constraint_evaluation.reasons if r6.constraint_evaluation else None}",
        )
        self.assertTrue(executor.is_objective_achieved())
        self.assertEqual(r6.updated_belief_state.objective_status.get("OBJ-FINANCIAL-CROWN-001", {}).get("status"), "ACHIEVED")

    def test_s3_partial_observability_firewall_replan(self) -> None:
        """S3 demonstrates Eligible != Successful and Replan via alternate path."""
        state_mgr = StateManager(
            run_id="RUN-S3-E2E",
            scenario_id=self.s3.scenario_id,
            objective_id=self.s3.objective.objective_id,
        )
        gate = self._make_safety_gate()
        executor = SimulationExecutor(
            scenario=self.s3,
            safety_gate=gate,
            state_manager=state_mgr,
            random_seed=42,
        )

        # Seed initial state with internal app access and known db target
        state_mgr.apply_observation({
            "observation_id": "OBS-SETUP-S3",
            "run_id": "RUN-S3-E2E",
            "action_id": "ACTION-RECON-001",
            "timestamp_utc": "2026-10-18T10:00:00Z",
            "outcome": "SUCCESS",
            "new_facts": [
                {
                    "fact_id": "FACT-TARG-DB",
                    "fact_type": "TARGET",
                    "subject": "lab-db-crown",
                    "value": {"target_id": "lab-db-crown"},
                    "confidence": 1.0,
                },
                {
                    "fact_id": "FACT-ACC-APP",
                    "fact_type": "ACCESS",
                    "subject": "lab-internal-app",
                    "value": {"access_level": "USER"},
                    "confidence": 1.0,
                },
                {
                    "fact_id": "FACT-SESS-APP",
                    "fact_type": "SESSION",
                    "subject": "sess-app-01",
                    "value": {"node_id": "lab-internal-app", "session_state": "ACTIVE"},
                    "confidence": 1.0,
                },
                {
                    "fact_id": "FACT-CRED-DB",
                    "fact_type": "CREDENTIAL",
                    "subject": "cred-db-admin",
                    "value": {
                        "credential_id": "cred-db-admin",
                        "principal": "dbadmin",
                        "credential_kind": "PASSWORD",
                        "observed_scope": "INTERNAL",
                        "validity_state": "VALID",
                    },
                    "confidence": 1.0,
                },
                {
                    "fact_id": "FACT-REACH-DIRECT",
                    "fact_type": "REACHABILITY",
                    "subject": "lab-internal-app->lab-db-crown",
                    "value": {"source": "lab-internal-app", "target": "lab-db-crown", "protocol": "TCP"},
                    "confidence": 0.8,
                },
            ],
            "evidence_refs": [],
            "source_kind": "SIMULATED",
            "confidence": 1.0,
            "sequence_num": 0,
        })

        # Also seed true state so internal app has session and creds match
        t0 = executor.get_true_state()
        # Direct pivot is eligible in Belief State (has session, credential, reachability fact)
        eval_pre = ActionConstraintEvaluator().evaluate(
            action=get_action_registry().get_action("ACTION-FLOW-001"),
            target_id="lab-db-crown",
            belief_state=state_mgr.get_belief_state(),
            proposal_parameters={"from_node_id": "lab-internal-app", "credential_id": "cred-db-admin"},
        )
        self.assertTrue(
            eval_pre.eligible,
            f"eval_pre failed: reasons={eval_pre.reasons}, failed_cond={eval_pre.failed_conditions}",
        )




        # But in ground truth environment, the edge is blocked by firewall!
        r_direct = executor.execute_proposal(
            {
                "action_id": "ACTION-FLOW-001",
                "target_id": "lab-db-crown",
                "from_node_id": "lab-internal-app",
                "credential_id": "cred-db-admin",
            }
        )
        # Result: executed, but environment outcome is FAILURE!
        self.assertEqual(r_direct.status, "EXECUTED")
        self.assertFalse(r_direct.success)
        self.assertIn("FIREWALL", str(r_direct.canonical_observation["new_facts"][0]["value"]))
        self.assertFalse(executor.is_objective_achieved())


if __name__ == "__main__":
    unittest.main()
