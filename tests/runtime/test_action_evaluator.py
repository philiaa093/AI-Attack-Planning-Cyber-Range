"""Unit tests for Action Constraint Evaluator (RT-03B).

Covers all 20 requirements (A through T) specified in RT-03B:
  A. Visible target passes target_visible.
  B. Hidden target fails target_visible.
  C. Observed host passes host_observed.
  D. PLANNER_INFERENCE host does not pass.
  E. Candidate finding does not satisfy confirmed finding.
  F. Confirmed finding does.
  G. Canonical access ordering: NONE < FOOTHOLD < USER < PRIVILEGED < SYSTEM.
  H. Closed session fails active-session requirement.
  I. Active matching session passes.
  J. Historical privileged access + closed session still fails session-required action.
  K. Valid authoritative credential passes relevant credential requirement.
  L. Planner-inferred credential fails.
  M. Observed reachability passes.
  N. Hidden topology cannot satisfy reachability.
  O. Objective achieved blocks objective_not_achieved.
  P. Same inputs produce identical result (determinism).
  Q. Evaluator does not mutate Belief State.
  R. Eligibility=true does not bypass Safety Gate.
  S. Enterprise action catalog remains target-neutral.
  T. RT-01/RT-02/RT-03A boundary and delegation remain PASS.
"""
import copy
import json
import unittest
from pathlib import Path

from actions.catalog.action_registry import (
    ActionDefinition,
    ActionRegistry,
    EffectContract,
    PreconditionContract,
    evaluate_precondition_contract,
)
from agent.memory.state.belief_state import ACCESS_LEVELS, BeliefState
from runtime.evaluators.action_evaluator import (
    ActionConstraintEvaluator,
    EvaluationReason,
    EvaluationResult,
)
from runtime.safety.discovery_gate import (
    ApprovalToken,
    CentralizedSafetyGate,
    DiscoveryRequest,
)

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "actions" / "catalog" / "action-catalog.json"


class ActionConstraintEvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.evaluator = ActionConstraintEvaluator()
        self.registry = ActionRegistry(CATALOG_PATH)

    # ------------------------------------------------------------------
    # A. Visible target passes target_visible
    # ------------------------------------------------------------------
    def test_requirement_a_visible_target_passes_target_visible(self):
        """Requirement A: Target within visible_target_ids passes target_visible check."""
        action = ActionDefinition(
            action_id="ACTION-TEST-001",
            name="TEST_ACTION",
            action_class="RECON",
            target_kind="HOST",
            preconditions=PreconditionContract(target_visible=True),
        )
        belief = BeliefState.from_facts([])
        visible_set = {"host-alpha", "host-beta"}

        result = self.evaluator.evaluate(
            action=action,
            target_id="host-alpha",
            belief_state=belief,
            visible_target_ids=visible_set,
        )
        self.assertTrue(result.eligible)
        self.assertIn("target_visible", result.satisfied_conditions)
        self.assertEqual(result.failed_conditions, ())

    # ------------------------------------------------------------------
    # B. Hidden target fails target_visible
    # ------------------------------------------------------------------
    def test_requirement_b_hidden_target_fails_target_visible(self):
        """Requirement B: Target outside visible_target_ids fails with TARGET_NOT_VISIBLE."""
        action = ActionDefinition(
            action_id="ACTION-TEST-001",
            name="TEST_ACTION",
            action_class="RECON",
            target_kind="HOST",
            preconditions=PreconditionContract(target_visible=True),
        )
        belief = BeliefState.from_facts([])
        visible_set = {"host-alpha"}

        result = self.evaluator.evaluate(
            action=action,
            target_id="host-hidden",
            belief_state=belief,
            visible_target_ids=visible_set,
        )
        self.assertFalse(result.eligible)
        self.assertIn("target_visible", result.failed_conditions)
        self.assertIn(EvaluationReason.TARGET_NOT_VISIBLE, result.reason_codes)

    # ------------------------------------------------------------------
    # C. Observed host passes host_observed
    # ------------------------------------------------------------------
    def test_requirement_c_observed_host_passes_host_observed(self):
        """Requirement C: Host authoritatively recorded in known_hosts passes host_observed."""
        action = ActionDefinition(
            action_id="ACTION-TEST-002",
            name="TEST_ACTION",
            action_class="HOST_RECON",
            target_kind="HOST",
            preconditions=PreconditionContract(host_observed=True),
        )
        facts = [
            {
                "fact_id": "F-HOST-01",
                "fact_type": "HOST",
                "subject": "srv-app-01",
                "value": {"ip": "10.0.1.5"},
                "confidence": 1.0,
                "source_kind": "OBSERVED",
            }
        ]
        belief = BeliefState.from_facts(facts)

        result = self.evaluator.evaluate(
            action=action,
            target_id="srv-app-01",
            belief_state=belief,
        )
        self.assertTrue(result.eligible)
        self.assertIn("host_observed", result.satisfied_conditions)
        self.assertIn("F-HOST-01", result.relevant_fact_ids)

    # ------------------------------------------------------------------
    # D. PLANNER_INFERENCE host does not pass
    # ------------------------------------------------------------------
    def test_requirement_d_planner_inference_host_does_not_pass(self):
        """Requirement D: Host from PLANNER_INFERENCE is quarantined into hypotheses and fails host_observed."""
        action = ActionDefinition(
            action_id="ACTION-TEST-002",
            name="TEST_ACTION",
            action_class="HOST_RECON",
            target_kind="HOST",
            preconditions=PreconditionContract(host_observed=True),
        )
        # Inferred host fact
        inferred_facts = [
            {
                "fact_id": "F-INF-01",
                "fact_type": "HOST",
                "subject": "srv-inferred-01",
                "value": {"ip": "10.0.1.99"},
                "confidence": 0.5,
                "source_kind": "PLANNER_INFERENCE",
            }
        ]
        belief = BeliefState.from_facts(inferred_facts)

        # Host is quarantined into hypotheses, NOT in known_hosts
        self.assertIn("srv-inferred-01", [h["subject"] for h in belief.hypotheses])
        self.assertNotIn("srv-inferred-01", belief.known_hosts)

        result = self.evaluator.evaluate(
            action=action,
            target_id="srv-inferred-01",
            belief_state=belief,
        )
        self.assertFalse(result.eligible)
        self.assertIn(EvaluationReason.HOST_NOT_OBSERVED, result.reason_codes)

    # ------------------------------------------------------------------
    # E. Candidate finding does not satisfy confirmed finding
    # ------------------------------------------------------------------
    def test_requirement_e_candidate_finding_does_not_satisfy_confirmed(self):
        """Requirement E: CANDIDATE_FINDING is provisional and fails finding_confirmed."""
        action = ActionDefinition(
            action_id="ACTION-TEST-003",
            name="TEST_ACTION",
            action_class="INITIAL_ACCESS",
            target_kind="SERVICE",
            preconditions=PreconditionContract(finding_confirmed=True),
        )
        candidate_facts = [
            {
                "fact_id": "F-CAND-01",
                "fact_type": "CANDIDATE_FINDING",
                "subject": "srv-web-01",
                "value": {"type": "CVE-2023-1234", "severity": "HIGH"},
                "confidence": 0.6,
                "source_kind": "OBSERVED",
            }
        ]
        belief = BeliefState.from_facts(candidate_facts)

        result = self.evaluator.evaluate(
            action=action,
            target_id="srv-web-01",
            belief_state=belief,
        )
        self.assertFalse(result.eligible)
        self.assertIn(EvaluationReason.CONFIRMED_FINDING_REQUIRED, result.reason_codes)

    # ------------------------------------------------------------------
    # F. Confirmed finding satisfies
    # ------------------------------------------------------------------
    def test_requirement_f_confirmed_finding_satisfies(self):
        """Requirement F: Authoritative CONFIRMED_FINDING satisfies finding_confirmed."""
        action = ActionDefinition(
            action_id="ACTION-TEST-003",
            name="TEST_ACTION",
            action_class="INITIAL_ACCESS",
            target_kind="SERVICE",
            preconditions=PreconditionContract(finding_confirmed=True),
        )
        confirmed_facts = [
            {
                "fact_id": "F-CONF-01",
                "fact_type": "CONFIRMED_FINDING",
                "subject": "srv-web-01",
                "value": {"type": "CVE-2023-1234", "verified": True},
                "confidence": 1.0,
                "source_kind": "OBSERVED",
            }
        ]
        belief = BeliefState.from_facts(confirmed_facts)

        result = self.evaluator.evaluate(
            action=action,
            target_id="srv-web-01",
            belief_state=belief,
        )
        self.assertTrue(result.eligible)
        self.assertIn("finding_confirmed", result.satisfied_conditions)
        self.assertIn("F-CONF-01", result.relevant_fact_ids)

    # ------------------------------------------------------------------
    # G. Canonical access ordering: NONE < FOOTHOLD < USER < PRIVILEGED < SYSTEM
    # ------------------------------------------------------------------
    def test_requirement_g_canonical_access_ordering(self):
        """Requirement G: Verify canonical access ordering and USER normalization."""
        # NONE < FOOTHOLD < USER < PRIVILEGED < SYSTEM
        for rank, level in enumerate(ACCESS_LEVELS):
            action = ActionDefinition(
                action_id=f"ACTION-REQ-{level}",
                name="REQ_LEVEL",
                action_class="TEST",
                target_kind="HOST",
                preconditions=PreconditionContract(min_access_level=level),
            )
            # Test against host with USER access
            user_access_facts = [
                {
                    "fact_id": "F-ACC-USER",
                    "fact_type": "ACCESS",
                    "subject": "srv-node-01",
                    "value": "USER",
                    "confidence": 1.0,
                    "source_kind": "OBSERVED",
                }
            ]
            belief = BeliefState.from_facts(user_access_facts)
            result = self.evaluator.evaluate(
                action=action,
                target_id="srv-node-01",
                belief_state=belief,
            )
            if level in ("NONE", "FOOTHOLD", "USER"):
                self.assertTrue(result.eligible, f"USER access should satisfy {level}")
            else:
                self.assertFalse(result.eligible, f"USER access must NOT satisfy {level}")
                self.assertIn(EvaluationReason.INSUFFICIENT_ACCESS, result.reason_codes)

        # Test normalization: legacy "UNPRIVILEGED" in action definition maps to USER
        legacy_action = ActionDefinition(
            action_id="ACTION-LEGACY-01",
            name="LEGACY",
            action_class="TEST",
            target_kind="HOST",
            preconditions=PreconditionContract(min_access_level="UNPRIVILEGED"),
        )
        # PreconditionContract.from_dict normalizes UNPRIVILEGED to USER
        self.assertEqual(legacy_action.preconditions.min_access_level, "USER")

    # ------------------------------------------------------------------
    # H. Closed session fails active-session requirement
    # ------------------------------------------------------------------
    def test_requirement_h_closed_session_fails_active_session_requirement(self):
        """Requirement H: Session in state CLOSED fails require_active_session."""
        action = ActionDefinition(
            action_id="ACTION-NEED-SESS",
            name="NEED_SESSION",
            action_class="HOST_RECON",
            target_kind="HOST",
            preconditions=PreconditionContract(require_active_session=True),
        )
        closed_session_facts = [
            {
                "fact_id": "F-SESS-CLOSED",
                "fact_type": "SESSION",
                "subject": "sess-01",
                "value": {
                    "session_id": "sess-01",
                    "target_id": "srv-alpha",
                    "access_level": "USER",
                    "state": "CLOSED",
                },
                "confidence": 1.0,
                "source_kind": "OBSERVED",
            }
        ]
        belief = BeliefState.from_facts(closed_session_facts)
        result = self.evaluator.evaluate(
            action=action,
            target_id="srv-alpha",
            belief_state=belief,
        )
        self.assertFalse(result.eligible)
        self.assertIn(EvaluationReason.ACTIVE_SESSION_REQUIRED, result.reason_codes)

    # ------------------------------------------------------------------
    # I. Active matching session passes
    # ------------------------------------------------------------------
    def test_requirement_i_active_matching_session_passes(self):
        """Requirement I: Session in state ACTIVE matching target satisfies require_active_session."""
        action = ActionDefinition(
            action_id="ACTION-NEED-SESS",
            name="NEED_SESSION",
            action_class="HOST_RECON",
            target_kind="HOST",
            preconditions=PreconditionContract(require_active_session=True),
        )
        active_session_facts = [
            {
                "fact_id": "F-SESS-ACTIVE",
                "fact_type": "SESSION",
                "subject": "sess-02",
                "value": {
                    "session_id": "sess-02",
                    "target_id": "srv-alpha",
                    "access_level": "USER",
                    "state": "ACTIVE",
                },
                "confidence": 1.0,
                "source_kind": "OBSERVED",
            }
        ]
        belief = BeliefState.from_facts(active_session_facts)
        result = self.evaluator.evaluate(
            action=action,
            target_id="srv-alpha",
            belief_state=belief,
        )
        self.assertTrue(result.eligible)
        self.assertIn("require_active_session", result.satisfied_conditions)
        self.assertIn("sess-02", result.relevant_fact_ids)

    # ------------------------------------------------------------------
    # J. Historical privileged access + closed session fails session requirement
    # ------------------------------------------------------------------
    def test_requirement_j_historical_privileged_access_plus_closed_session_fails(self):
        """Requirement J: Historical access=PRIVILEGED but all sessions CLOSED evaluates to INELIGIBLE."""
        action = ActionDefinition(
            action_id="ACTION-EXEC-001",
            name="REMOTE_EXEC",
            action_class="HOST_RECON",
            target_kind="HOST",
            preconditions=PreconditionContract(
                min_access_level="PRIVILEGED",
                require_active_session=True,
            ),
        )
        facts = [
            # Proven historical privileged access
            {
                "fact_id": "F-ACC-PRIV",
                "fact_type": "ACCESS",
                "subject": "srv-dc-01",
                "value": "PRIVILEGED",
                "confidence": 1.0,
                "source_kind": "OBSERVED",
            },
            # But the session was CLOSED
            {
                "fact_id": "F-SESS-DC",
                "fact_type": "SESSION",
                "subject": "sess-dc-01",
                "value": {
                    "session_id": "sess-dc-01",
                    "target_id": "srv-dc-01",
                    "access_level": "PRIVILEGED",
                    "state": "CLOSED",
                },
                "confidence": 1.0,
                "source_kind": "OBSERVED",
            },
        ]
        belief = BeliefState.from_facts(facts)

        result = self.evaluator.evaluate(
            action=action,
            target_id="srv-dc-01",
            belief_state=belief,
        )
        self.assertFalse(result.eligible)
        # min_access_level was satisfied, but require_active_session failed!
        self.assertIn("min_access_level", result.satisfied_conditions)
        self.assertIn("require_active_session", result.failed_conditions)
        self.assertIn(EvaluationReason.ACTIVE_SESSION_REQUIRED, result.reason_codes)

    # ------------------------------------------------------------------
    # K. Valid authoritative credential passes
    # ------------------------------------------------------------------
    def test_requirement_k_valid_authoritative_credential_passes(self):
        """Requirement K: Authoritative credential with VALID state satisfies require_valid_credential."""
        action = ActionDefinition(
            action_id="ACTION-PIVOT-001",
            name="PIVOT",
            action_class="LATERAL_MOVEMENT",
            target_kind="HOST",
            preconditions=PreconditionContract(require_valid_credential=True),
        )
        facts = [
            {
                "fact_id": "F-CRED-01",
                "fact_type": "CREDENTIAL",
                "subject": "srv-db-01",
                "value": {
                    "credential_id": "cred-h-99",
                    "principal": "dbadmin",
                    "credential_kind": "OPAQUE_HANDLE",
                    "observed_scope": "srv-db-01",
                    "validity_state": "VALID",
                },
                "confidence": 1.0,
                "source_kind": "OBSERVED",
            }
        ]
        belief = BeliefState.from_facts(facts)
        result = self.evaluator.evaluate(
            action=action,
            target_id="srv-db-01",
            belief_state=belief,
        )
        self.assertTrue(result.eligible)
        self.assertIn("require_valid_credential", result.satisfied_conditions)
        self.assertIn("cred-h-99", result.relevant_fact_ids)

    # ------------------------------------------------------------------
    # L. Planner-inferred credential fails
    # ------------------------------------------------------------------
    def test_requirement_l_planner_inferred_credential_fails(self):
        """Requirement L: Credential from PLANNER_INFERENCE or CANDIDATE state fails validation."""
        action = ActionDefinition(
            action_id="ACTION-PIVOT-001",
            name="PIVOT",
            action_class="LATERAL_MOVEMENT",
            target_kind="HOST",
            preconditions=PreconditionContract(require_valid_credential=True),
        )
        # Case 1: Inferred credential (quarantined)
        inf_facts = [
            {
                "fact_id": "F-CRED-INF",
                "fact_type": "CREDENTIAL",
                "subject": "srv-db-01",
                "value": {
                    "credential_id": "cred-inf-01",
                    "observed_scope": "srv-db-01",
                    "validity_state": "VALID",
                },
                "confidence": 0.5,
                "source_kind": "PLANNER_INFERENCE",
            }
        ]
        belief_inf = BeliefState.from_facts(inf_facts)
        result_inf = self.evaluator.evaluate(
            action=action,
            target_id="srv-db-01",
            belief_state=belief_inf,
        )
        self.assertFalse(result_inf.eligible)
        self.assertIn(EvaluationReason.NO_VALID_CREDENTIAL, result_inf.reason_codes)

        # Case 2: Candidate credential (not yet validated)
        cand_facts = [
            {
                "fact_id": "F-CRED-CAND",
                "fact_type": "CREDENTIAL",
                "subject": "srv-db-01",
                "value": {
                    "credential_id": "cred-cand-01",
                    "observed_scope": "srv-db-01",
                    "validity_state": "CANDIDATE",
                },
                "confidence": 0.7,
                "source_kind": "OBSERVED",
            }
        ]
        belief_cand = BeliefState.from_facts(cand_facts)
        result_cand = self.evaluator.evaluate(
            action=action,
            target_id="srv-db-01",
            belief_state=belief_cand,
        )
        self.assertFalse(result_cand.eligible)
        self.assertIn(EvaluationReason.NO_VALID_CREDENTIAL, result_cand.reason_codes)

    # ------------------------------------------------------------------
    # M. Observed reachability passes
    # ------------------------------------------------------------------
    def test_requirement_m_observed_reachability_passes(self):
        """Requirement M: Observed edge in observed_reachability satisfies require_reachability."""
        action = ActionDefinition(
            action_id="ACTION-REACH-001",
            name="PROBE_REACH",
            action_class="DISCOVERY",
            target_kind="HOST",
            preconditions=PreconditionContract(require_reachability=True),
        )
        reach_facts = [
            {
                "fact_id": "F-REACH-01",
                "fact_type": "REACHABILITY",
                "subject": "host-a -> host-b",
                "value": {"from_host": "host-a", "to_host": "host-b", "protocol": "tcp"},
                "confidence": 1.0,
                "source_kind": "OBSERVED",
            }
        ]
        belief = BeliefState.from_facts(reach_facts)
        result = self.evaluator.evaluate(
            action=action,
            target_id="host-b",
            belief_state=belief,
        )
        self.assertTrue(result.eligible)
        self.assertIn("require_reachability", result.satisfied_conditions)

    # ------------------------------------------------------------------
    # N. Hidden topology cannot satisfy reachability
    # ------------------------------------------------------------------
    def test_requirement_n_hidden_topology_cannot_satisfy_reachability(self):
        """Requirement N: Hidden network paths without observed reachability edge fail."""
        action = ActionDefinition(
            action_id="ACTION-REACH-001",
            name="PROBE_REACH",
            action_class="DISCOVERY",
            target_kind="HOST",
            preconditions=PreconditionContract(require_reachability=True),
        )
        # Empty reachability in belief state
        belief = BeliefState.from_facts([])
        result = self.evaluator.evaluate(
            action=action,
            target_id="hidden-internal-db",
            belief_state=belief,
        )
        self.assertFalse(result.eligible)
        self.assertIn(EvaluationReason.REACHABILITY_NOT_OBSERVED, result.reason_codes)

    # ------------------------------------------------------------------
    # O. Objective achieved blocks objective_not_achieved
    # ------------------------------------------------------------------
    def test_requirement_o_objective_achieved_blocks_action(self):
        """Requirement O: When objective is ACHIEVED, action with objective_not_achieved fails."""
        action = ActionDefinition(
            action_id="ACTION-OBJ-001",
            name="ACCESS_OBJ",
            action_class="OBJECTIVE_ACCESS",
            target_kind="OBJECTIVE",
            preconditions=PreconditionContract(objective_not_achieved=True),
        )
        achieved_facts = [
            {
                "fact_id": "F-OBJ-01",
                "fact_type": "OBJECTIVE",
                "subject": "crown-jewel-01",
                "value": {"status": "ACHIEVED"},
                "confidence": 1.0,
                "source_kind": "OBSERVED",
            }
        ]
        belief = BeliefState.from_facts(achieved_facts)
        result = self.evaluator.evaluate(
            action=action,
            target_id="crown-jewel-01",
            belief_state=belief,
        )
        self.assertFalse(result.eligible)
        self.assertIn(EvaluationReason.OBJECTIVE_ALREADY_ACHIEVED, result.reason_codes)

    # ------------------------------------------------------------------
    # P. Determinism: same inputs produce identical result
    # ------------------------------------------------------------------
    def test_requirement_p_determinism_same_inputs_produce_identical_result(self):
        """Requirement P: Evaluator is pure and deterministic across repeated invocations."""
        action = self.registry.get_action("ACTION-FOOTHOLD-001")
        self.assertIsNotNone(action)
        facts = [
            {"fact_id": "F-H1", "fact_type": "HOST", "subject": "srv-web", "value": {"ip": "10.0.0.1"}, "confidence": 1.0, "source_kind": "OBSERVED"},
            {"fact_id": "F-S1", "fact_type": "SERVICE", "subject": "srv-web:80", "value": {"port": 80, "protocol": "http"}, "confidence": 1.0, "source_kind": "OBSERVED"},
            {"fact_id": "F-F1", "fact_type": "CONFIRMED_FINDING", "subject": "srv-web", "value": {"vuln": "CVE-2021-1234"}, "confidence": 1.0, "source_kind": "OBSERVED"},
            {"fact_id": "F-R1", "fact_type": "REACHABILITY", "subject": "gw -> srv-web", "value": {"from_host": "gw", "to_host": "srv-web"}, "confidence": 1.0, "source_kind": "OBSERVED"},
        ]
        belief = BeliefState.from_facts(facts)

        results = [
            self.evaluator.evaluate(action=action, target_id="srv-web", belief_state=belief).to_dict()
            for _ in range(10)
        ]
        first = json.dumps(results[0], sort_keys=True)
        for idx, res in enumerate(results[1:], start=1):
            current = json.dumps(res, sort_keys=True)
            self.assertEqual(first, current, f"Run {idx} diverged from deterministic baseline")

    # ------------------------------------------------------------------
    # Q. Evaluator does not mutate Belief State
    # ------------------------------------------------------------------
    def test_requirement_q_evaluator_does_not_mutate_belief_state(self):
        """Requirement Q: Evaluation performs zero mutation on BeliefState."""
        action = self.registry.get_action("ACTION-FOOTHOLD-001")
        facts = [
            {"fact_id": "F-H1", "fact_type": "HOST", "subject": "srv-01", "value": {"ip": "10.0.0.1"}, "confidence": 1.0, "source_kind": "OBSERVED"},
            {"fact_id": "F-S1", "fact_type": "SERVICE", "subject": "srv-01:80", "value": {"port": 80, "protocol": "http"}, "confidence": 1.0, "source_kind": "OBSERVED"},
        ]
        belief = BeliefState.from_facts(facts)
        snapshot_before = copy.deepcopy(belief.to_dict())

        _ = self.evaluator.evaluate(action=action, target_id="srv-01", belief_state=belief)

        snapshot_after = belief.to_dict()
        self.assertEqual(snapshot_before, snapshot_after, "BeliefState must remain completely unmutated")

    # ------------------------------------------------------------------
    # R. Eligibility=true does not bypass Safety Gate
    # ------------------------------------------------------------------
    def test_requirement_r_eligibility_does_not_bypass_safety_gate(self):
        """Requirement R: Eligible action cannot execute if rejected by CentralizedSafetyGate."""
        action = ActionDefinition(
            action_id="ACTION-SCAN-001",
            name="NETWORK_PORT_SCAN",
            action_class="SCAN",
            target_kind="HOST",
            preconditions=PreconditionContract(target_visible=True),
        )
        belief = BeliefState.from_facts([])
        target = "target-unauthorized-01"

        # 1. Evaluator says action is logically feasible based on visible target
        result = self.evaluator.evaluate(
            action=action,
            target_id=target,
            belief_state=belief,
            visible_target_ids={target},
        )
        self.assertTrue(result.eligible, "Action is logically eligible from Planner view")

        # 2. But CentralizedSafetyGate retains supreme authorization authority and denies it
        gate = CentralizedSafetyGate(
            base_origin="http://127.0.0.1:18088",
            target_registry={target: {"host": "127.0.0.1", "port": 18088}},
            target_allowlist=set(),  # target is NOT authorized in safety gate allowlist!
            canonical_target_allowlist=set(),
            action_allowlist={"ACTION-SCAN-001"},
            lab_mode=True,
        )
        approval = ApprovalToken(
            approval_id="APP-DENY-01",
            run_id="run-test-01",
            target_id=target,
            action_id="ACTION-SCAN-001",
            not_before=0,
            expires_at=2000000000,
        )
        req = DiscoveryRequest(
            run_id="run-test-01",
            action_id="ACTION-SCAN-001",
            target_id=target,
            url=f"http://127.0.0.1:18088/targets/{target}",
            approval=approval,
        )
        resp = gate.dispatch(req)
        self.assertEqual(resp.outcome, "DENIED", "Safety Gate must deny unauthorized target despite evaluator eligibility")
        self.assertEqual(resp.refusal_reason, "TARGET_NOT_ALLOWLISTED")

    # ------------------------------------------------------------------
    # S. Enterprise action catalog remains target-neutral
    # ------------------------------------------------------------------
    def test_requirement_s_enterprise_action_catalog_remains_target_neutral(self):
        """Requirement S: Action definitions define capabilities, not hardcoded targets."""
        catalog_text = CATALOG_PATH.read_text(encoding="utf-8")
        forbidden_patterns = ["lab-sqli-001", "lab-xss-001", "127.0.0.1", "192.168.", "http://localhost"]
        for pattern in forbidden_patterns:
            self.assertNotIn(
                pattern,
                catalog_text,
                f"Action catalog contains forbidden hardcoded target pattern: {pattern!r}",
            )

    # ------------------------------------------------------------------
    # T. Delegation and backward compatibility
    # ------------------------------------------------------------------
    def test_requirement_t_delegation_and_backward_compatibility(self):
        """Requirement T: evaluate_precondition_contract delegates cleanly to ActionConstraintEvaluator."""
        action = self.registry.get_action("ACTION-STOP-001")
        self.assertIsNotNone(action)
        belief = BeliefState.from_facts([])

        # evaluate_precondition_contract wrapper returns (bool, list[str])
        eligible, reasons = evaluate_precondition_contract(action, belief, target_id=None)
        self.assertTrue(eligible)
        self.assertEqual(reasons, [])

    # ------------------------------------------------------------------
    # Additional Coverage: STOP action and evaluate_all cross-product
    # ------------------------------------------------------------------
    def test_stop_action_semantics(self):
        """Verify ACTION-STOP-001 is planner-safe and environment-scoped."""
        stop_action = self.registry.get_action("ACTION-STOP-001")
        self.assertIsNotNone(stop_action)
        self.assertEqual(stop_action.target_kind, "ENVIRONMENT")

        res = self.evaluator.evaluate(stop_action, target_id=None, belief_state={})
        self.assertTrue(res.eligible)
        self.assertEqual(res.step_cost, 0)
        self.assertEqual(res.noise_cost, 0.0)

    def test_evaluate_all_cross_product(self):
        """Verify evaluate_all produces deterministically sorted results."""
        action_a = ActionDefinition(action_id="ACTION-A", name="A", action_class="T", target_kind="HOST")
        action_b = ActionDefinition(action_id="ACTION-B", name="B", action_class="T", target_kind="HOST")
        targets = ["host-2", "host-1"]

        results = self.evaluator.evaluate_all(
            actions=[action_b, action_a],
            targets=targets,
            belief_state={},
        )
        self.assertEqual(len(results), 4)
        pairs = [(r.action_id, r.target_id) for r in results]
        self.assertEqual(
            pairs,
            [
                ("ACTION-A", "host-1"),
                ("ACTION-A", "host-2"),
                ("ACTION-B", "host-1"),
                ("ACTION-B", "host-2"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
