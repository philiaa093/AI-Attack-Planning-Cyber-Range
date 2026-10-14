"""Synthetic, offline TASK-020 contracts; no strategy or live dispatch."""
import copy
import hashlib
import json
import unittest
from dataclasses import FrozenInstanceError, replace
from unittest.mock import patch

from agent.memory.state.state_manager import StateManager
from runtime.state.knowledge_state_store import KnowledgeStateStore, StoreContext
from runtime.planners.planner_interface import (
    Feedback, Planner, PlanningDecision, PlanningInput, PlanProposal, StateSnapshot,
)


CONTEXT = StoreContext("RUN-020", "SESSION-1", "EPISODE-1")
ACTION = "ACTION-PLAN-003"
TARGET = "lab-fixture"


def state():
    return StateManager(CONTEXT.run_id, "SCN-001", "OBJ-020",
                        dict(actions=5, requests=10, seconds=60.0)).get_state()


def request(data=None, context=CONTEXT, **kwargs):
    return PlanningInput(StateSnapshot.from_state(state() if data is None else data,
                                                  context=context),
                         {ACTION}, {TARGET}, **kwargs)


def proposal(**changes):
    data = dict(objective_id="OBJ-020", action_id=ACTION, target_id=TARGET,
                reason_code="revisit_evidence", confidence=0.5, evidence_refs=[])
    data.update(changes)
    return PlanProposal.from_dict(data)


class FixturePlanner(Planner):
    """Returns test data; its mode label does not mean a real backend ran."""
    def __init__(self, mode="RULE", result=None):
        self._mode = mode
        self.result = result
        self.calls = 0

    @property
    def mode(self):
        return self._mode

    def _plan(self, req):
        self.calls += 1
        if self.result is not None:
            return self.result
        return PlanningDecision(req.state.context, req.state.revision,
                                self.mode, self.mode, proposal=proposal())


def feedback(previous, **kwargs):
    fields = dict(context=previous.context, input_revision=previous.input_revision,
                  action_id=ACTION, outcome="DENIED", reason_code="policy_refusal",
                  observation_ids=("OBS-020",))
    fields.update(kwargs)
    return Feedback(**fields)


class PlannerInterfaceTests(unittest.TestCase):
    def test_abstract_planner_and_missing_strategy_cannot_instantiate(self):
        with self.assertRaises(TypeError):
            Planner()

        class MissingStrategy(Planner):
            mode = "RULE"

        with self.assertRaises(TypeError):
            MissingStrategy()

    def test_validated_entry_points_cannot_be_overridden(self):
        for name in ("plan", "replan"):
            with self.subTest(name=name), self.assertRaises(TypeError):
                type("Bypass", (FixturePlanner,), {name: lambda *args: None})

    def test_modes_share_interface_and_canonical_output(self):
        for mode in ("RULE", "LLM", "RL", "HYBRID"):
            with self.subTest(mode=mode):
                decision = FixturePlanner(mode).plan(request())
                self.assertEqual((decision.requested_mode, decision.actual_mode), (mode, mode))
                self.assertEqual(decision.proposal.to_dict(), proposal().to_dict())
                self.assertIsNone(decision.stop_reason)

    def test_snapshot_detaches_input_and_returned_nested_data(self):
        original = state()
        req = request(original)
        revision = req.state.revision
        original["remaining_budget"]["actions"] = 0
        returned = req.state.to_dict()
        returned["remaining_budget"]["actions"] = 0
        returned["observed_facts"].append({})
        self.assertEqual(req.state.to_dict()["remaining_budget"]["actions"], 5)
        self.assertEqual(req.state.to_dict()["observed_facts"], [])
        self.assertEqual(req.state.revision, revision)
        with self.assertRaises(FrozenInstanceError):
            req.state.state_json = "{}"

    def test_snapshot_canonical_hash_is_order_independent_and_context_bound(self):
        original = state()
        reordered = dict(reversed(list(original.items())))
        self.assertEqual(request(original).state.revision, request(reordered).state.revision)
        for context in (StoreContext(CONTEXT.run_id, "SESSION-2", CONTEXT.episode_id),
                        StoreContext(CONTEXT.run_id, CONTEXT.session_id, "EPISODE-2")):
            self.assertNotEqual(request(context=context).state.revision, request().state.revision)
        original["remaining_budget"]["requests"] -= 1
        self.assertNotEqual(request(original).state.revision, request().state.revision)

    def test_mutable_scope_is_frozen(self):
        actions, targets = {ACTION}, {TARGET}
        req = PlanningInput(request().state, actions, targets)
        actions.clear()
        targets.clear()
        self.assertEqual(req.allowed_action_ids, frozenset({ACTION}))
        self.assertEqual(req.allowed_target_ids, frozenset({TARGET}))

    def test_state_schema_unknown_fields_and_invalid_budgets_rejected(self):
        invalid = []
        for key in ("ground_truth", "expected_state", "source_code", "credentials"):
            data = state()
            data[key] = {}
            invalid.append(data)
        for value in (True, -1, float("nan"), float("inf"), "5"):
            data = state()
            data["remaining_budget"]["actions"] = value
            invalid.append(data)
        invalid.extend([None, [], {"run_id": CONTEXT.run_id}])
        data = state()
        data["run_id"] = "RUN-OTHER"
        invalid.append(data)
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(ValueError):
                StateSnapshot.from_state(data, context=CONTEXT)

    def test_secret_facts_and_duplicate_fact_identity_rejected(self):
        fact = dict(fact_id="FACT-1", fact_type="CONTROL", subject=TARGET,
                    value="password=synthetic", confidence=0.5,
                    source_observation_id="OBS-1")
        data = state()
        data["observed_facts"] = [fact]
        with self.assertRaisesRegex(ValueError, "redacted"):
            request(data)
        fact["value"] = "already_redacted"
        data["observed_facts"] = [fact, copy.deepcopy(fact)]
        with self.assertRaisesRegex(ValueError, "duplicate fact"):
            request(data)

    def test_non_json_values_keys_and_oversized_documents_rejected(self):
        for data in ({1: "invalid"}, {"tuple": (1,)}, {"set": {1}},
                     {"value": "x" * (1024 * 1024 + 1)}):
            with self.subTest(kind=type(data)), self.assertRaises(ValueError):
                StateSnapshot.from_state(data, context=CONTEXT)
        recursive = {}
        recursive["self"] = recursive
        with self.assertRaises(ValueError):
            StateSnapshot.from_state(recursive, context=CONTEXT)

    def test_direct_json_constructors_reject_duplicate_keys_and_nonfinite_numbers(self):
        text = json.dumps(state())
        with self.assertRaises(ValueError):
            StateSnapshot(CONTEXT, text[:-1] + ', "run_id":"RUN-020"}')
        for text in ('{"confidence": NaN}', '{"confidence": Infinity}', '[]', '{'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                PlanProposal(text)

    def test_proposal_rejects_extra_fields_invalid_confidence_and_secrets(self):
        for changes in (dict(command="synthetic"), dict(payload="synthetic"),
                        dict(confidence=True), dict(confidence=float("nan")),
                        dict(confidence=1.1), dict(target_id="outside-lab"),
                        dict(reason_code=""), dict(evidence_refs=[None]),
                        dict(resource_ref="password=synthetic")):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                proposal(**changes)

    def test_proposal_preserves_optional_schema_fields_and_copy_isolation(self):
        data = proposal().to_dict() | dict(schema_version="1.0", plan_id="PLAN-020",
            hypothesis_id="HYP-020", resource_ref="RESOURCE-020", parameter_name="field",
            source_observation_id="OBS-020", evidence_refs=["EV-020"])
        prop = PlanProposal.from_dict(data)
        self.assertEqual(prop.to_dict(), data)
        prop.to_dict()["evidence_refs"].clear()
        data["evidence_refs"].clear()
        self.assertEqual(prop.to_dict()["evidence_refs"], ["EV-020"])

    def test_invalid_scope_input_and_modes_rejected(self):
        for actions, targets in (([ACTION], {TARGET}), ({"dynamic"}, {TARGET}),
                                 ({ACTION}, {"public.example"})):
            with self.assertRaises(ValueError):
                PlanningInput(request().state, actions, targets)
        with self.assertRaises(ValueError):
            PlanningInput(request().state, {ACTION}, {TARGET}, fallback_allowed=1)
        with self.assertRaises(ValueError):
            FixturePlanner("UNKNOWN").plan(request())
        with self.assertRaises(ValueError):
            FixturePlanner().plan({})

    def test_decision_requires_one_proposal_or_stop(self):
        req = request()
        for fields in ({}, dict(proposal=proposal(), stop_reason="NO_VALID_CANDIDATE"),
                       dict(proposal={}), dict(stop_reason="UNKNOWN")):
            with self.assertRaises(ValueError):
                PlanningDecision(CONTEXT, req.state.revision, "RULE", "RULE", **fields)

    def test_strategy_output_type_and_identity_are_checked(self):
        req = request()
        valid = FixturePlanner().plan(req)
        invalid = [dict(proposal=proposal()),
                   replace(valid, input_revision="0" * 64),
                   replace(valid, context=StoreContext(CONTEXT.run_id, "SESSION-2", "EPISODE-1")),
                   replace(valid, requested_mode="LLM", actual_mode="LLM")]
        for decision in invalid:
            with self.subTest(kind=type(decision)), self.assertRaises(ValueError):
                FixturePlanner(result=decision).plan(req)

    def test_output_objective_and_candidate_scope_are_checked(self):
        req = request()
        valid = FixturePlanner().plan(req)
        for prop in (proposal(objective_id="OBJ-OTHER"),
                     proposal(target_id="lab-other"), proposal(action_id="ACTION-PLAN-002")):
            with self.assertRaises(ValueError):
                FixturePlanner(result=replace(valid, proposal=prop)).plan(req)

    def test_fallback_requires_explicit_reason_and_permission(self):
        req = request()
        with self.assertRaises(ValueError):
            PlanningDecision(CONTEXT, req.state.revision, "LLM", "RULE", proposal=proposal())
        with self.assertRaises(ValueError):
            PlanningDecision(CONTEXT, req.state.revision, "RULE", "RULE",
                             proposal=proposal(), fallback_reason="provider_error")
        result = PlanningDecision(CONTEXT, req.state.revision, "LLM", "RULE",
                                  proposal=proposal(), fallback_reason="provider_error")
        planner = FixturePlanner("LLM", result)
        with self.assertRaisesRegex(ValueError, "not allowed"):
            planner.plan(req)
        self.assertEqual(planner.plan(replace(req, fallback_allowed=True)), result)

    def test_zero_budgets_short_circuit_before_strategy(self):
        for field in ("actions", "requests", "seconds"):
            data = state()
            data["remaining_budget"][field] = 0
            planner = FixturePlanner()
            result = planner.plan(request(data))
            self.assertEqual(result.stop_reason, "BUDGET_EXHAUSTED")
            self.assertEqual(planner.calls, 0)

    def test_empty_scope_and_terminal_do_not_claim_success(self):
        req = request()
        terminal = state()
        terminal["phase"] = "TERMINAL"
        for req in (replace(req, allowed_action_ids=frozenset()),
                    replace(req, allowed_target_ids=frozenset()), request(terminal)):
            planner = FixturePlanner()
            self.assertEqual(planner.plan(req).stop_reason, "NO_VALID_CANDIDATE")
            self.assertEqual(planner.calls, 0)

    def test_default_replan_uses_new_snapshot_without_charging_budget(self):
        planner = FixturePlanner()
        old = request()
        previous = planner.plan(old)
        updated = state()
        updated["phase"] = "REPLAN"
        updated["remaining_budget"]["actions"] -= 1
        req = request(updated)
        before = req.state.to_dict()
        decision = planner.replan(req, previous=previous, feedback=feedback(previous))
        self.assertEqual(decision.input_revision, req.state.revision)
        self.assertNotEqual(decision.input_revision, previous.input_revision)
        self.assertEqual(req.state.to_dict(), before)
        self.assertEqual(planner.calls, 2)

    def test_replan_override_receives_previous_and_refusal(self):
        class HistoryPlanner(FixturePlanner):
            def _replan(self, req, *, previous, feedback):
                self.received = (previous, feedback)
                return PlanningDecision(req.state.context, req.state.revision,
                                        self.mode, self.mode, stop_reason="NO_VALID_CANDIDATE")

        planner = HistoryPlanner()
        req = request()
        previous = planner.plan(req)
        fb = feedback(previous)
        result = planner.replan(req, previous=previous, feedback=fb)
        self.assertEqual(planner.received, (previous, fb))
        self.assertEqual(result.stop_reason, "NO_VALID_CANDIDATE")

    def test_replan_override_output_is_validated(self):
        class InvalidHistoryPlanner(FixturePlanner):
            def _replan(self, req, *, previous, feedback):
                return replace(previous, input_revision="0" * 64)

        planner = InvalidHistoryPlanner()
        req = request()
        previous = planner.plan(req)
        with self.assertRaisesRegex(ValueError, "snapshot mismatch"):
            planner.replan(req, previous=previous, feedback=feedback(previous))

    def test_switching_planner_keeps_shared_replan_contract(self):
        req = request()
        previous = FixturePlanner("RULE").plan(req)
        result = FixturePlanner("RL").replan(req, previous=previous,
                                              feedback=feedback(previous))
        self.assertEqual((result.requested_mode, result.actual_mode), ("RL", "RL"))
        self.assertIsNone(result.fallback_reason)

    def test_replan_rejects_cross_context_stale_revision_and_wrong_action(self):
        req = request()
        planner = FixturePlanner()
        previous = planner.plan(req)
        for fb in (feedback(previous, context=StoreContext(CONTEXT.run_id, "SESSION-2", "EPISODE-1")),
                   feedback(previous, input_revision="0" * 64),
                   feedback(previous, action_id="ACTION-PLAN-002")):
            with self.assertRaises(ValueError):
                planner.replan(req, previous=previous, feedback=fb)
        with self.assertRaises(ValueError):
            planner.replan(req, previous=None, feedback=feedback(previous))
        self.assertEqual(planner.calls, 1)

    def test_replan_feedback_checked_even_when_budget_is_exhausted(self):
        planner = FixturePlanner()
        previous = planner.plan(request())
        data = state()
        data["remaining_budget"]["actions"] = 0
        with self.assertRaises(ValueError):
            planner.replan(request(data), previous=previous,
                           feedback=feedback(previous, input_revision="0" * 64))
        result = planner.replan(request(data), previous=previous, feedback=feedback(previous))
        self.assertEqual(result.stop_reason, "BUDGET_EXHAUSTED")
        self.assertEqual(planner.calls, 1)

    def test_feedback_rejects_malformed_identity_outcome_and_mutable_ids(self):
        previous = FixturePlanner().plan(request())
        for fields in (dict(outcome="UNKNOWN"), dict(reason_code=""),
                       dict(observation_ids=["OBS-1"]),
                       dict(observation_ids=("OBS-1", "OBS-1"))):
            with self.assertRaises(ValueError):
                feedback(previous, **fields)

    def test_store_snapshot_adapter_is_read_only_and_isolated(self):
        with KnowledgeStateStore() as store:
            store.create_context(CONTEXT, scenario_id="SCN-001", objective_id="OBJ-020",
                                 budget=dict(actions=5, requests=10, seconds=60.0),
                                 allowed_subjects={TARGET}, allowed_actions={ACTION})
            before = store.get_state(CONTEXT)
            snapshot = StateSnapshot.from_store(store, CONTEXT)
            planner = FixturePlanner()
            with patch("socket.socket", side_effect=AssertionError("network forbidden")), \
                 patch("subprocess.Popen", side_effect=AssertionError("process forbidden")):
                planner.plan(PlanningInput(snapshot, {ACTION}, {TARGET}))
            self.assertEqual(store.get_state(CONTEXT), before)
            self.assertEqual(store.observations(CONTEXT), [])
            self.assertEqual(snapshot.to_dict(), before)

    def test_store_observation_update_replans_without_double_budget_charge(self):
        with KnowledgeStateStore() as store:
            store.create_context(CONTEXT, scenario_id="SCN-001", objective_id="OBJ-020",
                                 budget=dict(actions=5, requests=10, seconds=60.0),
                                 allowed_subjects={TARGET}, allowed_actions={ACTION})
            planner = FixturePlanner()
            old = StateSnapshot.from_store(store, CONTEXT)
            previous = planner.plan(PlanningInput(old, {ACTION}, {TARGET}))
            store.ingest(CONTEXT, dict(observation_id="OBS-020", run_id=CONTEXT.run_id,
                action_id=ACTION, timestamp_utc="2026-10-12T00:00:00Z", outcome="DENIED",
                evidence_refs=[], new_facts=[dict(fact_id="FACT-020", fact_type="CONTROL",
                subject=TARGET, value="synthetic_refusal", confidence=1.0)]),
                source="SYNTHETIC-FIXTURE", source_sha256=hashlib.sha256(b"fixture").hexdigest(),
                requests=0, seconds=0, phase="REPLAN")
            before = store.get_state(CONTEXT)
            snapshot = StateSnapshot.from_store(store, CONTEXT)
            result = planner.replan(PlanningInput(snapshot, {ACTION}, {TARGET}),
                                    previous=previous, feedback=feedback(previous))
            snapshot.to_dict()["observed_facts"][0]["value"] = "changed"
            self.assertEqual(store.get_state(CONTEXT), before)
            self.assertEqual(before["remaining_budget"],
                             dict(actions=4, requests=10, seconds=60.0))
            self.assertEqual(len(store.observations(CONTEXT)), 1)
            self.assertEqual(result.input_revision, snapshot.revision)
            self.assertNotEqual(snapshot.revision, old.revision)


if __name__ == "__main__":
    unittest.main()
