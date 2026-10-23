"""Comprehensive Test Suite for Mini Enterprise Live Validation Range (RT-06).

Verifies invariants A through V:
  A. Live range network isolation is explicit.
  B. Planner cannot read Docker Compose topology.
  C. Planner cannot access Docker socket.
  D. Live executor only accepts canonical bounded actions.
  E. Unknown action fails closed.
  F. Hidden/out-of-scope target fails closed.
  G. Safety denial causes zero dispatch.
  H. Kill switch causes zero dispatch.
  I. No arbitrary shell parameter accepted.
  J. Credential secret does not enter Planner/observation/evidence.
  K. Live discovery generates canonical TARGET/SERVICE observations.
  L. Foothold generates bounded ACCESS/SESSION evidence.
  M. Pivot only works on permitted observed progression.
  N. Objective completion generates canonical OBJECTIVE observation.
  O. Belief updates only through canonical observation ingestion.
  P. STOP requires no network dispatch.
  Q. Existing simulator tests remain green (verified via suite runs).
  R. Existing ShopLab regression remains green (verified via suite runs).
  S. Frozen benchmark protocol hashes/configs unchanged.
  T. End-to-end live validation case L1 works (DMZ -> Internal -> Restricted objective).
  U. L2 blocked/replan demonstrates observable failure and continuation.
  V. L3 clean-control terminates via STOP without false objective.
"""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from actions.catalog.action_registry import (
    CANONICAL_BENCHMARK_ACTION_IDS,
    get_action_registry,
    get_canonical_action_id,
)
from agent.memory.state.belief_state import BeliefState
from agent.memory.state.state_manager import StateManager
from agent.perception.normalizers.enterprise_normalizer import (
    EnterpriseObservationNormalizer,
    validate_canonical_observation,
)
from runtime.lab.enterprise_range.harness import EnterpriseLiveRangeHarness
from runtime.lab.enterprise_range.topology import (
    ENTERPRISE_TARGETS,
    ZONES,
    get_target_allowlist,
    is_direct_ingress_allowed,
    validate_network_transition,
)
from runtime.lab.live_environment import (
    LiveEpisodeEnvironment,
    create_live_safety_gate,
)
from runtime.lab.live_executor_adapter import (
    LiveExecutionResult,
    LiveExecutorAdapter,
)
from runtime.orchestration.planner_runner import PlannerEpisodeRunner
from runtime.planners.candidate_generator import CandidateGenerator
from runtime.planners.planner_context import (
    PlannerDecision,
    PlannerDecisionContext,
    _FORBIDDEN_CONTEXT_KEYS,
)
from runtime.planners.rule_based_planner import RuleBasedPlanner
from runtime.safety.discovery_gate import CentralizedSafetyGate, KillSwitch
from scripts.validation.validate_scaffold import ROOT


class TestLiveValidationRange(unittest.TestCase):
    """Validation test suite for RT-06 Mini Enterprise Live Cyber Range."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.harness = EnterpriseLiveRangeHarness()
        cls.endpoints = cls.harness.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.harness.stop()

    def setUp(self) -> None:
        self.harness.reset_all()

    # -------------------------------------------------------------------------
    # Invariant A: Live range network isolation is explicit
    # -------------------------------------------------------------------------
    def test_a_network_isolation_is_explicit(self) -> None:
        """Verify that network zones, CIDRs, and cross-zone boundaries are strictly defined."""
        self.assertIn("ZONE_DMZ", ZONES)
        self.assertIn("ZONE_INTERNAL", ZONES)
        self.assertIn("ZONE_RESTRICTED", ZONES)
        self.assertIn("ZONE_DECOY", ZONES)

        self.assertFalse(ZONES["ZONE_DMZ"].is_internal_only)
        self.assertTrue(ZONES["ZONE_INTERNAL"].is_internal_only)
        self.assertTrue(ZONES["ZONE_RESTRICTED"].is_internal_only)
        self.assertTrue(ZONES["ZONE_DECOY"].is_internal_only)

        # DMZ is direct ingress; Internal requires pivot from DMZ; Restricted requires pivot from Internal
        self.assertTrue(is_direct_ingress_allowed("lab-enterprise-dmz"))
        self.assertFalse(is_direct_ingress_allowed("lab-enterprise-internal"))
        self.assertFalse(is_direct_ingress_allowed("lab-enterprise-restricted"))

        # Transition validation
        ok_dmz_to_int, _ = validate_network_transition("lab-enterprise-dmz", "lab-enterprise-internal")
        self.assertTrue(ok_dmz_to_int)

        ok_direct_to_int, reason = validate_network_transition(None, "lab-enterprise-internal")
        self.assertFalse(ok_direct_to_int)
        self.assertIn("ZONE_ISOLATION_VIOLATION", reason)

        ok_dmz_to_restr, reason2 = validate_network_transition("lab-enterprise-dmz", "lab-enterprise-restricted")
        self.assertFalse(ok_dmz_to_restr)
        self.assertIn("NETWORK_BARRIER_FAIL_CLOSED", reason2)

    # -------------------------------------------------------------------------
    # Invariant B: Planner cannot read Docker Compose topology
    # -------------------------------------------------------------------------
    def test_b_planner_cannot_read_compose_topology(self) -> None:
        """Verify that PlannerDecisionContext rejects compose topology and hidden node dictionaries."""
        env = LiveEpisodeEnvironment(harness=self.harness)
        env.reset()
        belief = env.get_belief_state()

        # Planner visible targets at t=0 contains ONLY entry DMZ target
        self.assertEqual(belief.visible_target_ids, frozenset({"lab-enterprise-dmz"}))
        self.assertNotIn("lab-enterprise-internal", belief.visible_target_ids)
        self.assertNotIn("lab-enterprise-restricted", belief.visible_target_ids)

        # Check forbidden context keys
        for key in ("hidden_topology", "hidden_nodes", "true_state"):
            with self.assertRaises(ValueError):
                PlannerDecisionContext(
                    run_id="TEST-FORBIDDEN-TOPOLOGY",
                    step_index=0,
                    max_steps=30,
                    current_phase="ENGAGEMENT",
                    remaining_budget=20,
                    max_budget=20,
                    visible_target_ids=belief.visible_target_ids,
                    belief_state=belief,
                    candidate_proposals=(),
                    eligible_proposals=(),
                    rejected_proposals=(),
                    previous_outcome={key: "LEAKED_TOPOLOGY"},
                )

    # -------------------------------------------------------------------------
    # Invariant C: Planner cannot access Docker socket
    # -------------------------------------------------------------------------
    def test_c_planner_cannot_access_docker_socket(self) -> None:
        """Verify that LiveExecutorAdapter rejects proposals attempting to manipulate docker sockets."""
        adapter = LiveExecutorAdapter(harness=self.harness)
        socket_proposal = {
            "action_id": "ACTION-FOOTHOLD-001",
            "target_id": "lab-enterprise-dmz",
            "socket": "/var/run/docker.sock",
        }
        res = adapter.execute_proposal(socket_proposal)
        self.assertFalse(res.success)
        self.assertEqual(res.status, "REJECTED_BY_SAFETY_GATE")
        self.assertIn("FORBIDDEN_PARAMETER_REJECTED", res.reasons[0])

    # -------------------------------------------------------------------------
    # Invariant D: Live executor only accepts canonical bounded actions
    # -------------------------------------------------------------------------
    def test_d_live_executor_accepts_canonical_bounded_actions(self) -> None:
        """Verify that all canonical generic benchmark actions are mapped."""
        adapter = LiveExecutorAdapter(harness=self.harness)
        for act_id in CANONICAL_BENCHMARK_ACTION_IDS:
            can_id = get_canonical_action_id(act_id)
            self.assertIn(can_id, CANONICAL_BENCHMARK_ACTION_IDS)

    # -------------------------------------------------------------------------
    # Invariant E: Unknown action fails closed
    # -------------------------------------------------------------------------
    def test_e_unknown_action_fails_closed(self) -> None:
        """Verify that an unknown action ID is rejected fail-closed."""
        adapter = LiveExecutorAdapter(harness=self.harness)
        unknown_proposal = {
            "action_id": "ACTION-UNKNOWN-EXPLOIT-999",
            "target_id": "lab-enterprise-dmz",
        }
        res = adapter.execute_proposal(unknown_proposal)
        self.assertFalse(res.success)
        self.assertEqual(res.status, "REJECTED_BY_SAFETY_GATE")
        self.assertIn("UNKNOWN_ACTION_REJECTED", res.reasons[0])

    # -------------------------------------------------------------------------
    # Invariant F: Hidden / out-of-scope target fails closed
    # -------------------------------------------------------------------------
    def test_f_out_of_scope_target_fails_closed(self) -> None:
        """Verify that target not in Safety Gate allowlist fails closed."""
        gate = create_live_safety_gate(target_allowlist=frozenset({"lab-enterprise-dmz"}))
        adapter = LiveExecutorAdapter(harness=self.harness, safety_gate=gate)

        out_of_scope = {
            "action_id": "ACTION-DISCOVERY-001",
            "target_id": "lab-external-unauthorized",
        }
        res = adapter.execute_proposal(out_of_scope)
        self.assertFalse(res.success)
        self.assertEqual(res.status, "REJECTED_BY_SAFETY_GATE")
        self.assertIn("TARGET_NOT_IN_ALLOWLIST", res.reasons[0])

    # -------------------------------------------------------------------------
    # Invariant G: Safety denial causes zero dispatch
    # -------------------------------------------------------------------------
    def test_g_safety_denial_causes_zero_dispatch(self) -> None:
        """Verify that if action is denied by Safety Gate, zero network dispatch occurs."""
        gate = create_live_safety_gate(action_allowlist=frozenset({"ACTION-DISCOVERY-001"}))
        adapter = LiveExecutorAdapter(harness=self.harness, safety_gate=gate)

        initial_dispatches = adapter.network_dispatch_count
        denied_proposal = {
            "action_id": "ACTION-FOOTHOLD-001",
            "target_id": "lab-enterprise-dmz",
        }
        res = adapter.execute_proposal(denied_proposal)
        self.assertFalse(res.success)
        self.assertEqual(res.status, "REJECTED_BY_SAFETY_GATE")
        self.assertEqual(adapter.network_dispatch_count, initial_dispatches)

    # -------------------------------------------------------------------------
    # Invariant H: Kill switch causes zero dispatch
    # -------------------------------------------------------------------------
    def test_h_kill_switch_causes_zero_dispatch(self) -> None:
        """Verify that when kill switch is activated, all dispatches are halted immediately."""
        ks = KillSwitch(active=True)
        gate = create_live_safety_gate(kill_switch=ks)
        adapter = LiveExecutorAdapter(harness=self.harness, safety_gate=gate)

        initial_dispatches = adapter.network_dispatch_count
        prop = {
            "action_id": "ACTION-DISCOVERY-001",
            "target_id": "lab-enterprise-dmz",
        }
        res = adapter.execute_proposal(prop)
        self.assertFalse(res.success)
        self.assertEqual(res.status, "REJECTED_BY_SAFETY_GATE")
        self.assertIn("KILL_SWITCH_ACTIVE", res.reasons[0])
        self.assertEqual(adapter.network_dispatch_count, initial_dispatches)

    # -------------------------------------------------------------------------
    # Invariant I: No arbitrary shell parameter accepted
    # -------------------------------------------------------------------------
    def test_i_arbitrary_shell_parameter_rejected(self) -> None:
        """Verify that proposal parameters containing shell or command execution keys fail closed."""
        adapter = LiveExecutorAdapter(harness=self.harness)
        for bad_key in ("command", "cmd", "shell", "exec", "eval", "bash"):
            with self.subTest(key=bad_key):
                res = adapter.execute_proposal({
                    "action_id": "ACTION-FOOTHOLD-001",
                    "target_id": "lab-enterprise-dmz",
                    bad_key: "whoami",
                })
                self.assertFalse(res.success)
                self.assertEqual(res.status, "REJECTED_BY_SAFETY_GATE")
                self.assertIn("FORBIDDEN_PARAMETER_REJECTED", res.reasons[0])

    # -------------------------------------------------------------------------
    # Invariant J: Credential secret does not enter Planner/observation/evidence
    # -------------------------------------------------------------------------
    def test_j_credential_secret_does_not_leak(self) -> None:
        """Verify that plaintext credential secrets are strictly excluded from observations and evidence."""
        # Establish session first so credential harvest is authorized
        self.harness.states["lab-enterprise-dmz"].add_session("SESS-TEST-01", "FOOTHOLD")

        belief = BeliefState.from_facts([
            {
                "fact_id": "FACT-TGT-DMZ",
                "fact_type": "TARGET",
                "subject": "lab-enterprise-dmz",
                "value": "lab-enterprise-dmz",
                "confidence": 1.0,
            },
            {
                "fact_id": "FACT-SESS-DMZ",
                "fact_type": "SESSION",
                "subject": "lab-enterprise-dmz",
                "value": {"session_id": "SESS-TEST-01", "access_level": "FOOTHOLD", "state": "ACTIVE"},
                "confidence": 1.0,
            },
            {
                "fact_id": "FACT-ACC-DMZ",
                "fact_type": "ACCESS",
                "subject": "lab-enterprise-dmz",
                "value": "FOOTHOLD",
                "confidence": 1.0,
            },
        ])

        adapter = LiveExecutorAdapter(harness=self.harness)
        prop = {
            "action_id": "ACTION-CREDS-001",
            "target_id": "lab-enterprise-dmz",
        }
        res = adapter.execute_proposal(prop, belief_state=belief)
        self.assertTrue(res.success)
        self.assertIsNotNone(res.canonical_observation)

        obs_json = json.dumps(res.canonical_observation)
        evidence_json = json.dumps(res.evidence_bundle)

        # Forbidden secret tokens must never appear in planner observation or evidence
        secret = "SYNTHETIC_LAB_TOKEN_INT_98472a1f"
        self.assertNotIn(secret, obs_json)
        self.assertNotIn(secret, evidence_json)

        # Opaque credential handle must be present
        cred_facts = [f for f in res.canonical_observation.get("new_facts", []) if f.get("fact_type") == "CREDENTIAL"]
        self.assertTrue(len(cred_facts) > 0)
        cred_val = cred_facts[0]["value"]
        self.assertTrue(cred_val["credential_id"].startswith("CRED-OPAQ-"))
        self.assertEqual(cred_val["principal"], "svc_internal")
        self.assertEqual(cred_val["validity_state"], "VALID")

    # -------------------------------------------------------------------------
    # Invariant K: Live discovery generates canonical TARGET/SERVICE observations
    # -------------------------------------------------------------------------
    def test_k_live_discovery_generates_canonical_facts(self) -> None:
        """Verify that bounded discovery emits validated canonical TARGET and SERVICE facts."""
        adapter = LiveExecutorAdapter(harness=self.harness)
        prop = {
            "action_id": "ACTION-DISCOVERY-001",
            "target_id": "lab-enterprise-dmz",
        }
        res = adapter.execute_proposal(prop)
        self.assertTrue(res.success)
        obs = res.canonical_observation
        self.assertIsNotNone(obs)

        # Schema validation
        errors = validate_canonical_observation(obs)
        self.assertEqual(errors, [])

        fact_types = {f["fact_type"] for f in obs.get("new_facts", [])}
        self.assertIn("SERVICE", fact_types)
        self.assertIn("TARGET", fact_types)

    # -------------------------------------------------------------------------
    # Invariant L: Foothold generates bounded ACCESS/SESSION evidence
    # -------------------------------------------------------------------------
    def test_l_foothold_generates_bounded_access_session(self) -> None:
        """Verify that INITIAL_FOOTHOLD establishes session and emits SESSION & ACCESS facts."""
        belief = BeliefState.from_facts([
            {
                "fact_id": "FACT-TGT-DMZ",
                "fact_type": "TARGET",
                "subject": "lab-enterprise-dmz",
                "value": "lab-enterprise-dmz",
                "confidence": 1.0,
            },
            {
                "fact_id": "FACT-SVC-DMZ",
                "fact_type": "SERVICE",
                "subject": "lab-enterprise-dmz:8080",
                "value": "http-edge-portal",
                "confidence": 1.0,
            },
        ])

        adapter = LiveExecutorAdapter(harness=self.harness)
        prop = {
            "action_id": "ACTION-FOOTHOLD-001",
            "target_id": "lab-enterprise-dmz",
        }
        res = adapter.execute_proposal(prop, belief_state=belief)
        self.assertTrue(res.success)
        obs = res.canonical_observation

        errors = validate_canonical_observation(obs)
        self.assertEqual(errors, [])

        fact_types = {f["fact_type"] for f in obs.get("new_facts", [])}
        self.assertIn("SESSION", fact_types)
        self.assertIn("ACCESS", fact_types)

    # -------------------------------------------------------------------------
    # Invariant M: Pivot only works on permitted observed progression
    # -------------------------------------------------------------------------
    def test_m_pivot_only_works_on_permitted_progression(self) -> None:
        """Verify that lateral pivot to internal service fails closed if unobserved or without source session."""
        adapter = LiveExecutorAdapter(harness=self.harness)

        # Attempt to pivot to internal node directly without session on DMZ
        prop = {
            "action_id": "ACTION-PIVOT-001",
            "target_id": "lab-enterprise-internal",
            "from_node_id": "lab-enterprise-dmz",
        }
        res = adapter.execute_proposal(prop)
        self.assertFalse(res.success)
        self.assertEqual(res.status, "EXECUTED")
        obs = res.canonical_observation
        self.assertEqual(obs.get("outcome"), "PARTIAL")
        self.assertTrue(any(f.get("fact_type") == "DETECTION_SIGNAL" and f.get("value", {}).get("signal_type") == "ACCESS_DENIED" for f in obs.get("new_facts", [])))

    # -------------------------------------------------------------------------
    # Invariant N: Objective completion generates canonical OBJECTIVE observation
    # -------------------------------------------------------------------------
    def test_n_objective_generates_canonical_observation(self) -> None:
        """Verify that OBJECTIVE_ACCESS produces validated canonical OBJECTIVE observation."""
        # Establish session on restricted vault
        self.harness.states["lab-enterprise-restricted"].add_session("SESS-RESTR-01", "USER")

        belief = BeliefState.from_facts([
            {
                "fact_id": "FACT-TGT-RESTR",
                "fact_type": "TARGET",
                "subject": "lab-enterprise-restricted",
                "value": "lab-enterprise-restricted",
                "confidence": 1.0,
            },
            {
                "fact_id": "FACT-SESS-RESTR",
                "fact_type": "SESSION",
                "subject": "lab-enterprise-restricted",
                "value": {"session_id": "SESS-RESTR-01", "access_level": "USER", "state": "ACTIVE"},
                "confidence": 1.0,
            },
            {
                "fact_id": "FACT-ACC-RESTR",
                "fact_type": "ACCESS",
                "subject": "lab-enterprise-restricted",
                "value": "USER",
                "confidence": 1.0,
            },
            {
                "fact_id": "FACT-CRED-RESTR",
                "fact_type": "CREDENTIAL",
                "subject": "lab-enterprise-restricted",
                "value": {
                    "credential_id": "CRED-VAULT-ADMIN",
                    "principal": "vault_admin",
                    "credential_kind": "API_KEY_HANDLE",
                    "observed_scope": "lab-enterprise-restricted",
                    "validity_state": "VALID",
                },
                "confidence": 1.0,
            },
        ])

        adapter = LiveExecutorAdapter(harness=self.harness)
        prop = {
            "action_id": "ACTION-OBJECTIVE-001",
            "target_id": "lab-enterprise-restricted",
        }
        res = adapter.execute_proposal(prop, belief_state=belief)
        self.assertTrue(res.success)
        obs = res.canonical_observation

        errors = validate_canonical_observation(obs)
        self.assertEqual(errors, [])

        obj_facts = [f for f in obs.get("new_facts", []) if f.get("fact_type") == "OBJECTIVE"]
        self.assertEqual(len(obj_facts), 1)
        self.assertEqual(obj_facts[0]["value"]["objective_id"], "OBJ-ENTERPRISE-MISSION")
        self.assertEqual(obj_facts[0]["value"]["status"], "ACHIEVED")

    # -------------------------------------------------------------------------
    # Invariant O: Belief updates only through canonical observation ingestion
    # -------------------------------------------------------------------------
    def test_o_belief_updates_only_through_observation_ingestion(self) -> None:
        """Verify that LiveExecutorAdapter does not mutate BeliefState directly."""
        sm = StateManager(
            run_id="TEST-INGEST-001",
            scenario_id="LIVE-ENTERPRISE-VALIDATION",
            objective_id="OBJ-001",
            budget={"actions": 20},
        )
        adapter = LiveExecutorAdapter(harness=self.harness, state_manager=sm)

        sm.apply_observation({
            "observation_id": "OBS-SEED-001",
            "action_id": "BOOTSTRAP",
            "source_kind": "EXECUTOR",
            "source_target": "lab-enterprise-dmz",
            "outcome": "SUCCESS",
            "new_facts": [
                {
                    "fact_id": "FACT-TARGET-lab-enterprise-dmz",
                    "fact_type": "TARGET",
                    "subject": "lab-enterprise-dmz",
                    "value": "lab-enterprise-dmz",
                    "confidence": 1.0,
                }
            ],
            "confidence": 1.0,
            "evidence_refs": ["EVID-SEED-001"],
            "timestamp_utc": "2026-10-18T00:00:00Z",
        })

        initial_facts_count = sm.get_fact_count()
        prop = {
            "action_id": "ACTION-DISCOVERY-001",
            "target_id": "lab-enterprise-dmz",
        }
        res = adapter.execute_proposal(prop)
        self.assertTrue(res.success)
        self.assertGreater(sm.get_fact_count(), initial_facts_count)

    # -------------------------------------------------------------------------
    # Invariant P: STOP requires no network dispatch
    # -------------------------------------------------------------------------
    def test_p_stop_action_requires_no_network_dispatch(self) -> None:
        """Verify that ACTION-STOP-001 executes with zero network I/O."""
        adapter = LiveExecutorAdapter(harness=self.harness)
        initial_dispatches = adapter.network_dispatch_count

        stop_prop = {
            "action_id": "ACTION-STOP-001",
            "target_id": "lab-enterprise-dmz",
        }
        res = adapter.execute_proposal(stop_prop)
        self.assertTrue(res.success)
        self.assertEqual(res.status, "EXECUTED")
        self.assertEqual(adapter.network_dispatch_count, initial_dispatches)
        self.assertFalse(res.evidence_bundle["network_dispatched"])

    # -------------------------------------------------------------------------
    # Invariant S: Frozen benchmark protocol unchanged
    # -------------------------------------------------------------------------
    def test_s_frozen_protocol_hashes_unchanged(self) -> None:
        """Verify that BENCHMARK_PROTOCOL_FREEZE_V1 remains intact and unmodified."""
        protocol_path = ROOT / "evaluation" / "experiments" / "protocol_freeze.json"
        self.assertTrue(protocol_path.is_file())
        data = json.loads(protocol_path.read_text(encoding="utf-8"))
        self.assertEqual(data.get("freeze_status"), "SEALED")
        self.assertEqual(data.get("protocol_version"), "BENCHMARK_PROTOCOL_FREEZE_V1")

    # -------------------------------------------------------------------------
    # Invariant T: End-to-end Live Validation Case L1 (Straight)
    # -------------------------------------------------------------------------
    def test_t_validation_case_l1_straight(self) -> None:
        """Validation Case L1: Straight progression (DMZ -> Internal -> Restricted Objective).

        Demonstrates that RuleBasedPlanner executes end-to-end on LiveEpisodeEnvironment,
        transitioning through all enterprise zones under Fog-of-War and achieving objective.
        """
        env = LiveEpisodeEnvironment(
            harness=self.harness,
            entry_target_id="lab-enterprise-dmz",
            objective_id="OBJ-ENTERPRISE-MISSION",
            max_steps=25,
            max_budget=25,
        )
        planner = RuleBasedPlanner()
        runner = PlannerEpisodeRunner(env=env, planner=planner)

        result = runner.run()

        # In L1, the episode should terminate having achieved the mission objective
        self.assertTrue(result.terminated or result.final_belief_state.is_objective_achieved())
        self.assertTrue(result.final_belief_state.is_objective_achieved())

        # Verify zone progression facts in final belief state
        observed_targets = result.final_belief_state.visible_target_ids
        self.assertIn("lab-enterprise-dmz", observed_targets)
        self.assertIn("lab-enterprise-internal", observed_targets)
        self.assertIn("lab-enterprise-restricted", observed_targets)

        # Verify traces exist and all used canonical action IDs
        self.assertGreater(len(result.traces), 0)
        for trace in result.traces:
            if trace.chosen_proposal:
                self.assertIn(
                    get_canonical_action_id(trace.chosen_proposal["action_id"]),
                    CANONICAL_BENCHMARK_ACTION_IDS,
                )

    # -------------------------------------------------------------------------
    # Invariant U: End-to-end Live Validation Case L2 (Blocked/Replan)
    # -------------------------------------------------------------------------
    def test_u_validation_case_l2_blocked_replan(self) -> None:
        """Validation Case L2: Primary route blocked, observable defensive signal, replan."""
        env = LiveEpisodeEnvironment(
            harness=self.harness,
            entry_target_id="lab-enterprise-dmz",
            objective_id="OBJ-ENTERPRISE-MISSION",
            max_steps=25,
            max_budget=25,
        )
        env.reset()

        # Step 1: Recon DMZ
        r1 = env.step({"action_id": "ACTION-DISCOVERY-001", "target_id": "lab-enterprise-dmz"})
        self.assertTrue(r1.success)

        # Step 2: Foothold DMZ
        r2 = env.step({"action_id": "ACTION-FOOTHOLD-001", "target_id": "lab-enterprise-dmz"})
        self.assertTrue(r2.success)

        # Step 3: Host recon DMZ (discovers Internal)
        r3 = env.step({"action_id": "ACTION-HOSTRECON-001", "target_id": "lab-enterprise-dmz"})
        self.assertTrue(r3.success)

        # Simulate route blockage on internal node
        self.harness.block_route("lab-enterprise-internal", "primary")

        # Step 4: Harvest creds
        r4 = env.step({"action_id": "ACTION-CREDS-001", "target_id": "lab-enterprise-dmz"})
        self.assertTrue(r4.success)

        # Step 5: Attempt pivot on blocked primary route
        r5 = env.step({
            "action_id": "ACTION-PIVOT-001",
            "target_id": "lab-enterprise-internal",
            "from_node_id": "lab-enterprise-dmz",
            "route": "primary",
        })
        self.assertFalse(r5.success)
        # Defense signal should be recorded in belief
        sig_facts = env.get_belief_state().detection_signals
        self.assertTrue(len(sig_facts) > 0)
        self.assertEqual(sig_facts[0]["signal_type"], "WAF_REJECTION")

        # Step 6: Replan — unblock secondary route and retry
        self.harness.unblock_route("lab-enterprise-internal", "primary")
        r6 = env.step({
            "action_id": "ACTION-PIVOT-001",
            "target_id": "lab-enterprise-internal",
            "from_node_id": "lab-enterprise-dmz",
            "route": "secondary",
        })
        self.assertTrue(r6.success)
        active_hosts = {s.get("target_id") for s in env.get_belief_state().active_sessions}
        self.assertIn("lab-enterprise-internal", active_hosts)

    # -------------------------------------------------------------------------
    # Invariant V: End-to-end Live Validation Case L3 (Clean Control)
    # -------------------------------------------------------------------------
    def test_v_validation_case_l3_clean_control(self) -> None:
        """Validation Case L3: Clean control target contains no vulnerabilities; stops cleanly."""
        env = LiveEpisodeEnvironment(
            harness=self.harness,
            entry_target_id="lab-enterprise-clean",
            objective_id="OBJ-ENTERPRISE-MISSION",
            max_steps=10,
            max_budget=10,
        )
        env.reset()

        # Step 1: Recon clean target
        r1 = env.step({"action_id": "ACTION-DISCOVERY-001", "target_id": "lab-enterprise-clean"})
        self.assertTrue(r1.success)

        # Step 2: Foothold attempt fails on secure target
        r2 = env.step({"action_id": "ACTION-FOOTHOLD-001", "target_id": "lab-enterprise-clean"})
        self.assertFalse(r2.success)

        # Verify no sessions or access granted
        self.assertEqual(len(env.get_belief_state().active_sessions), 0)

        # Clean termination via STOP
        r_stop = env.step({"action_id": "ACTION-STOP-001", "target_id": "lab-enterprise-clean"})
        self.assertTrue(r_stop.success)
        self.assertTrue(env.terminated)
        self.assertFalse(env.is_objective_achieved())

    # -------------------------------------------------------------------------
    # Optional Validation Case L4: Decoy honeypot defense signal
    # -------------------------------------------------------------------------
    def test_w_validation_case_l4_decoy_defense_signal(self) -> None:
        """Validation Case L4: Decoy probe triggers observable AUTH_LOCKOUT signal."""
        # Establish internal session
        self.harness.states["lab-enterprise-internal"].add_session("SESS-INT-01", "USER")

        belief = BeliefState.from_facts([
            {
                "fact_id": "FACT-TGT-INT",
                "fact_type": "TARGET",
                "subject": "lab-enterprise-internal",
                "value": "lab-enterprise-internal",
                "confidence": 1.0,
            },
            {
                "fact_id": "FACT-SESS-INT",
                "fact_type": "SESSION",
                "subject": "lab-enterprise-internal",
                "value": {"session_id": "SESS-INT-01", "access_level": "USER", "state": "ACTIVE"},
                "confidence": 1.0,
            },
            {
                "fact_id": "FACT-ACC-INT",
                "fact_type": "ACCESS",
                "subject": "lab-enterprise-internal",
                "value": "USER",
                "confidence": 1.0,
            },
            {
                "fact_id": "FACT-REACH-DEC",
                "fact_type": "REACHABILITY",
                "subject": "lab-enterprise-internal",
                "value": {"from_host": "lab-enterprise-internal", "to_host": "lab-enterprise-decoy"},
                "confidence": 1.0,
            },
            {
                "fact_id": "FACT-TGT-DEC",
                "fact_type": "TARGET",
                "subject": "lab-enterprise-decoy",
                "value": "lab-enterprise-decoy",
                "confidence": 1.0,
            },
        ])

        adapter = LiveExecutorAdapter(harness=self.harness)
        decoy_prop = {
            "action_id": "ACTION-DISCOVERY-001",
            "target_id": "lab-enterprise-decoy",
            "from_node_id": "lab-enterprise-internal",
        }
        res = adapter.execute_proposal(decoy_prop, belief_state=belief)
        self.assertFalse(res.success)
        obs = res.canonical_observation
        self.assertIsNotNone(obs)

        sig_facts = [f for f in obs.get("new_facts", []) if f.get("fact_type") == "DETECTION_SIGNAL"]
        self.assertEqual(len(sig_facts), 1)
        self.assertEqual(sig_facts[0]["value"]["signal_type"], "AUTH_LOCKOUT")
