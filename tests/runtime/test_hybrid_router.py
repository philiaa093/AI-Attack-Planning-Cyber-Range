"""Synthetic offline routing tests; no provider, scanner or executor calls."""
import json
import unittest
from dataclasses import FrozenInstanceError, replace

from agent.memory.state.state_manager import StateManager
from runtime.planners.hybrid_router import HybridReviewRouter, RoutingHistory, RoutingPolicy
from runtime.state.knowledge_state_store import StoreContext
from runtime.planners.planner_interface import Feedback, PlanningDecision, PlanningInput, PlanProposal, StateSnapshot
from runtime.planners.rule_based_planner import RuleBasedPlanner

CONTEXT = StoreContext("RUN-027-FIXTURE", "SESSION-1", "EPISODE-1")
TARGET = "lab-fixture"
ACTION = "ACTION-PLAN-003"


def request(*, two=True, confidence=0.2, **changes):
    state = StateManager(CONTEXT.run_id, "SCN-001", "OBJ-027",
                         dict(actions=5, requests=10, seconds=60.0)).get_state()
    state["phase"] = "ANALYSIS"
    state["observed_facts"] = [dict(
        fact_id="FACT-" + str(i), fact_type="CANDIDATE_FINDING", subject=TARGET,
        value="UNTRUSTED-FIXTURE-TEXT", confidence=confidence,
        source_observation_id="OBS-" + str(i),
    ) for i in range(1, 3 if two else 2)]
    state.update(changes)
    return PlanningInput(StateSnapshot.from_state(state, context=CONTEXT), {ACTION}, {TARGET})


def feedback(previous, outcome="FAILURE", **changes):
    data = dict(context=CONTEXT, input_revision=previous.input_revision,
                action_id=ACTION, outcome=outcome, reason_code="FIXTURE_RESULT",
                observation_ids=("OBS-RESULT",))
    data.update(changes)
    return Feedback(**data)


def llm_fixture(previous):
    # Synthetic LLM-shaped DTO for routing tests, not a real provider decision.
    plan = previous.proposal.to_dict()
    plan["plan_id"] = "PLAN-022-" + plan["plan_id"].rsplit("-", 1)[1]
    return PlanningDecision(CONTEXT, previous.input_revision, "LLM", "LLM",
                            proposal=PlanProposal.from_dict(plan))


class HybridRouterTests(unittest.TestCase):
    def setUp(self):
        self.router = HybridReviewRouter()
        self.history = RoutingHistory(CONTEXT)
        self.request = request()
        self.previous = RuleBasedPlanner().plan(self.request)

    def route(self, **kwargs):
        return self.router.route(self.request, history=self.history, **kwargs)

    def test_rule_first_and_rule_match_require_no_handoff(self):
        self.assertEqual(self.route().backend, "RULE")
        routed = self.route(rule_decision=self.previous)
        self.assertEqual((routed.operation, routed.backend), ("ACCEPT_RULE", "RULE"))
        self.assertIsNone(routed.handoff_json)

    def test_no_rule_match_delegates_metadata(self):
        decision = RuleBasedPlanner(rules=()).plan(self.request)
        routed = self.route(rule_decision=decision)
        self.assertEqual((routed.operation, routed.backend), ("HANDOFF", "LLM"))
        self.assertEqual(len(json.loads(routed.handoff_json)["candidates"]), 2)

    def test_failure_error_and_partial_handoff_preserve_original_provenance(self):
        for outcome in ("FAILURE", "ERROR", "PARTIAL"):
            with self.subTest(outcome=outcome):
                routed = self.route(previous=self.previous, feedback=feedback(self.previous, outcome))
                memory = json.loads(routed.handoff_json)
                self.assertEqual(routed.operation, "HANDOFF")
                self.assertEqual(memory["feedback"]["previous_backend"], "RULE")
                self.assertEqual(memory["feedback"]["outcome"], outcome)
                self.assertEqual([c["fact_id"] for c in memory["candidates"]], ["FACT-2"])
                self.assertNotIn("UNTRUSTED-FIXTURE-TEXT", routed.handoff_json)

    def test_denial_stops_without_handoff(self):
        result = self.route(previous=self.previous, feedback=feedback(self.previous, "DENIED"))
        self.assertEqual(result.reason_code, "POLICY_DENIED")
        self.assertIsNone(result.handoff_json)

    def test_success_requires_original_backend_completion_check(self):
        routed = self.route(previous=self.previous, feedback=feedback(self.previous, "SUCCESS"))
        self.assertEqual((routed.operation, routed.backend), ("REPLAN", "RULE"))
        self.assertEqual(routed.reason_code, "CHECK_COMPLETION_RECEIPT")

    def test_unchanged_failed_candidate_stops_but_new_version_is_available(self):
        req = request(two=False)
        previous = RuleBasedPlanner().plan(req)
        result = self.router.route(req, history=self.history, previous=previous, feedback=feedback(previous))
        self.assertEqual(result.reason_code, "NO_VALID_CANDIDATE")
        state = req.state.to_dict()
        state["observed_facts"][0]["source_observation_id"] = "OBS-NEW"
        updated = replace(req, state=StateSnapshot.from_state(state, context=CONTEXT))
        result = self.router.route(updated, history=self.history, previous=previous, feedback=feedback(previous))
        self.assertEqual(result.operation, "HANDOFF")

    def test_limits_and_disabled_delegation_stop(self):
        decision = RuleBasedPlanner(rules=()).plan(self.request)
        for policy, history, reason in (
            (RoutingPolicy(llm_enabled=False), self.history, "LLM_DELEGATION_DISABLED"),
            (RoutingPolicy(), replace(self.history, delegation_count=2), "DELEGATION_LIMIT"),
            (RoutingPolicy(), replace(self.history, no_progress_count=3), "NO_PROGRESS_LIMIT"),
        ):
            with self.subTest(reason=reason):
                result = HybridReviewRouter(policy).route(self.request, history=history, rule_decision=decision)
                self.assertEqual(result.reason_code, reason)

    def test_scope_revocation_and_exhausted_budget_stop(self):
        exhausted = request(remaining_budget=dict(actions=0, requests=10, seconds=60.0))
        self.assertEqual(self.router.route(exhausted, history=self.history).reason_code, "BUDGET_EXHAUSTED")
        revoked = replace(self.request, allowed_target_ids=frozenset({"lab-other"}))
        result = self.router.route(revoked, history=self.history, previous=self.previous,
                                   feedback=feedback(self.previous))
        self.assertEqual(result.reason_code, "SCOPE_REVOKED")

    def test_cross_context_and_feedback_revision_rejected(self):
        other = StoreContext(CONTEXT.run_id, "SESSION-OTHER", CONTEXT.episode_id)
        with self.assertRaises(ValueError):
            self.router.route(self.request, history=RoutingHistory(other))
        with self.assertRaises(ValueError):
            self.route(previous=self.previous, feedback=feedback(self.previous, input_revision="0" * 64))

    def test_stale_rule_decision_and_live_actions_rejected(self):
        with self.assertRaises(ValueError):
            self.route(rule_decision=replace(self.previous, input_revision="0" * 64))
        with self.assertRaises(ValueError):
            self.router.route(replace(self.request, allowed_action_ids=frozenset({"ACTION-WEB-001"})),
                              history=self.history)

    def test_fallback_is_not_relabelled_as_task21(self):
        fallback = replace(self.previous, requested_mode="LLM", fallback_reason="PROVIDER_TIMEOUT")
        with self.assertRaises(ValueError):
            self.route(previous=fallback, feedback=feedback(fallback))

    def test_missing_feedback_evidence_stops(self):
        result = self.route(previous=self.previous, feedback=feedback(self.previous, observation_ids=()))
        self.assertEqual(result.reason_code, "FEEDBACK_EVIDENCE_REQUIRED")

    def test_snapshot_budget_history_and_results_are_immutable(self):
        before = self.request.state.state_json
        result = self.route(previous=self.previous, feedback=feedback(self.previous))
        self.assertEqual(self.request.state.state_json, before)
        self.assertEqual(self.history.delegation_count, 0)
        with self.assertRaises(FrozenInstanceError):
            result.backend = "RULE"

    def test_history_blocks_older_failed_versions_across_calls(self):
        initial = self.route(rule_decision=RuleBasedPlanner(rules=()).plan(self.request))
        versions = tuple(c["candidate_version"] for c in json.loads(initial.handoff_json)["candidates"])
        history = replace(self.history, excluded_versions=versions)
        result = self.router.route(self.request, history=history,
                                   rule_decision=RuleBasedPlanner(rules=()).plan(self.request))
        self.assertEqual(result.reason_code, "NO_VALID_CANDIDATE")

    def test_rule_match_cannot_reintroduce_a_history_excluded_version(self):
        version = self.previous.proposal.to_dict()["plan_id"].rsplit("-", 1)[1]
        history = replace(self.history, excluded_versions=(version,))
        result = self.router.route(self.request, history=history, rule_decision=self.previous)
        self.assertEqual((result.operation, result.reason_code), ("HANDOFF", "RULE_BLOCKED_VERSION"))
        self.assertEqual([c["fact_id"] for c in json.loads(result.handoff_json)["candidates"]], ["FACT-2"])

    def test_llm_failure_routes_native_replan(self):
        previous = llm_fixture(self.previous)
        result = self.route(previous=previous, feedback=feedback(previous))
        self.assertEqual((result.operation, result.backend), ("REPLAN", "LLM"))

    def test_success_does_not_bypass_llm_disable_or_delegation_limit(self):
        previous = llm_fixture(self.previous)
        for policy, history, reason in (
            (RoutingPolicy(llm_enabled=False), self.history, "LLM_DELEGATION_DISABLED"),
            (RoutingPolicy(), replace(self.history, delegation_count=2), "DELEGATION_LIMIT"),
        ):
            with self.subTest(reason=reason):
                result = HybridReviewRouter(policy).route(self.request, history=history,
                                                          previous=previous, feedback=feedback(previous, "SUCCESS"))
                self.assertEqual(result.reason_code, reason)

    def test_rule_decision_must_bind_observed_candidate_metadata(self):
        for change in (dict(plan_id="PLAN-021-" + "0" * 64),
                       dict(source_observation_id="OBS-INVENTED")):
            plan = self.previous.proposal.to_dict() | change
            decision = replace(self.previous, proposal=PlanProposal.from_dict(plan))
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.route(rule_decision=decision)

    def test_current_task22_cannot_consume_original_rule_feedback_directly(self):
        from runtime.planners.llm_planner import LLMPlanner
        class NeverCalled:
            def complete(self, document):
                raise AssertionError("cross-backend feedback must not call provider")
        decision = LLMPlanner(NeverCalled(), count_tokens=lambda text: 1).replan(
            self.request, previous=self.previous, feedback=feedback(self.previous),
        )
        self.assertIsNone(decision.proposal)
        self.assertEqual(decision.stop_reason, "NO_VALID_CANDIDATE")

    def test_bad_policy_and_history_rejected(self):
        for kwargs in (dict(max_delegations=True), dict(max_no_progress=0), dict(llm_enabled=1)):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                RoutingPolicy(**kwargs)
        for kwargs in (dict(delegation_count=True), dict(no_progress_count=-1),
                       dict(excluded_versions=("invalid",))):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                RoutingHistory(CONTEXT, **kwargs)


if __name__ == "__main__":
    unittest.main()
