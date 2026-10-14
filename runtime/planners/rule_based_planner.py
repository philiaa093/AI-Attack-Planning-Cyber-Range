"""TASK-021: deterministic, offline evidence-review proposals over TASK-020.

Only REVISIT_EVIDENCE is supported. No scanner, executor, provider, writable
store, dynamic predicate, or policy authorization belongs to this module.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from runtime.planners.planner_interface import (
    Feedback, Planner, PlanningDecision, PlanningInput, PlanProposal,
)


REVIEW_ACTION = "ACTION-PLAN-003"
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
_TARGET = re.compile(r"lab-[a-z0-9-]{1,124}")
_PLAN = re.compile(r"PLAN-021-[0-9a-f]{64}")
_CONTROL = re.compile(r"REVIEW-021-[0-9a-f]{64}")
_PHASES = frozenset({"ANALYSIS", "REPLAN"})


def _identity(value: str) -> None:
    if type(value) is not str or not _ID.fullmatch(value):
        raise ValueError("invalid rule/fact/observation identity")


@dataclass(frozen=True)
class Rule:
    """Closed predicate: a candidate in a phase, optionally below a threshold.

    Rules are trusted static configuration, never instructions from fact values.
    A confidence threshold ranks review work; it does not confirm a vulnerability.
    """

    rule_id: str
    priority: int
    confidence_below: float | None = None
    phases: frozenset[str] = _PHASES

    def __post_init__(self):
        _identity(self.rule_id)
        if type(self.priority) is not int or not 0 <= self.priority <= 10000:
            raise ValueError("priority must be an integer in [0, 10000]")
        threshold = self.confidence_below
        if threshold is not None and (
            type(threshold) not in (int, float) or not 0 <= threshold <= 1
        ):
            raise ValueError("threshold must be finite in [0, 1]")
        if (type(self.phases) is not frozenset or not self.phases
                or any(type(p) is not str or p not in _PHASES for p in self.phases)):
            raise ValueError("rule phases must be ANALYSIS/REPLAN in a frozenset")

    def matches(self, phase: str, fact: dict) -> bool:
        return (
            phase in self.phases
            and fact["fact_type"] == "CANDIDATE_FINDING"
            and (self.confidence_below is None
                 or fact["confidence"] < self.confidence_below)
        )


DEFAULT_RULES = (
    Rule("REVIEW_LOW_CONFIDENCE", 100, confidence_below=0.8),
    Rule("REVIEW_CANDIDATE", 50),
)


def review_control_id(proposal: PlanProposal) -> str:
    """ID for the coordinator's completion fact; does not create evidence.

    CONTROL fact: this ID, subject=proposal target, value=True, confidence=1.0,
    source_observation_id assigned by the normalizer/store. Record only after
    verified completion; never manufacture a receipt when selecting a proposal.
    """
    if type(proposal) is not PlanProposal:
        raise ValueError("PlanProposal required")
    plan = proposal.to_dict()
    if (plan["action_id"] != REVIEW_ACTION
            or not _PLAN.fullmatch(plan.get("plan_id", ""))):
        raise ValueError("Task 21 evidence-review proposal required")
    return "REVIEW-021-" + plan["plan_id"][len("PLAN-021-"):]


class RuleBasedPlanner(Planner):
    """Pure selection with deterministic priority, rule ID and fact ID ordering.

    Completion is snapshot data, not hidden per-instance history. All candidate
    scopes remain caller filters; dispatch still requires the safety gate.
    """

    def __init__(self, rules: tuple[Rule, ...] = DEFAULT_RULES):
        if (type(rules) is not tuple or len(rules) > 64
                or any(type(rule) is not Rule for rule in rules)):
            raise ValueError("at most 64 immutable Rule entries required")
        if len({rule.rule_id for rule in rules}) != len(rules):
            raise ValueError("duplicate rule identity")
        self._rules = tuple(sorted(rules, key=lambda r: (-r.priority, r.rule_id)))

    @property
    def rules(self) -> tuple[Rule, ...]:
        return self._rules

    @property
    def mode(self):
        return "RULE"

    @staticmethod
    def _decision(request: PlanningInput, proposal=None) -> PlanningDecision:
        return PlanningDecision(
            context=request.state.context,
            input_revision=request.state.revision,
            requested_mode="RULE", actual_mode="RULE", proposal=proposal,
            stop_reason="NO_VALID_CANDIDATE" if proposal is None else None,
        )

    @staticmethod
    def _receipts(state: dict) -> dict[str, dict]:
        receipts = {}
        for fact in state["observed_facts"]:
            if (fact["fact_type"] != "CONTROL"
                    or not fact["fact_id"].startswith("REVIEW-021-")):
                continue
            if (not _CONTROL.fullmatch(fact["fact_id"])
                    or not _TARGET.fullmatch(fact["subject"])
                    or fact["value"] is not True or fact["confidence"] != 1.0):
                raise ValueError("malformed review completion fact")
            _identity(fact["source_observation_id"])
            receipts[fact["fact_id"]] = fact
        return receipts

    @staticmethod
    def _proposal(request: PlanningInput, state: dict, rule: Rule,
                  fact: dict) -> PlanProposal:
        # Intent identity is independent of budgets, input list order and rule
        # priority. One receipt suppresses all rules for this candidate version.
        identity = [request.state.context.key, state["objective_id"], REVIEW_ACTION, fact]
        text = json.dumps(identity, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return PlanProposal.from_dict({
            "plan_id": "PLAN-021-" + digest,
            "objective_id": state["objective_id"], "action_id": REVIEW_ACTION,
            "target_id": fact["subject"], "reason_code": rule.rule_id,
            "confidence": 0.5,
            "source_observation_id": fact["source_observation_id"],
            "evidence_refs": [],
        })

    def _plan(self, request: PlanningInput) -> PlanningDecision:
        state = request.state.to_dict()
        receipts = self._receipts(state)
        if REVIEW_ACTION not in request.allowed_action_ids:
            return self._decision(request)
        candidates = []
        for fact in state["observed_facts"]:
            if fact["fact_type"] != "CANDIDATE_FINDING":
                continue
            _identity(fact["fact_id"])
            _identity(fact["source_observation_id"])
            if not _TARGET.fullmatch(fact["subject"]):
                raise ValueError("candidate must have an explicit lab target subject")
            if fact["subject"] in request.allowed_target_ids:
                candidates.append(fact)
        candidates.sort(key=lambda fact: fact["fact_id"])
        for rule in self.rules:
            for fact in candidates:
                if not rule.matches(state["phase"], fact):
                    continue
                proposal = self._proposal(request, state, rule, fact)
                receipt = receipts.get(review_control_id(proposal))
                if receipt is not None:
                    if receipt["subject"] != fact["subject"]:
                        raise ValueError("completion fact target mismatch")
                    continue
                return self._decision(request, proposal)
        return self._decision(request)

    def _replan(self, request: PlanningInput, *, previous: PlanningDecision,
                feedback: Feedback) -> PlanningDecision:
        if feedback.outcome != "SUCCESS" or previous.actual_mode != "RULE":
            return self._decision(request)
        plan = previous.proposal.to_dict()
        if (plan["objective_id"] != request.state.to_dict()["objective_id"]
                or plan["action_id"] != REVIEW_ACTION
                or not _PLAN.fullmatch(plan.get("plan_id", ""))):
            return self._decision(request)
        receipt = self._receipts(request.state.to_dict()).get(
            review_control_id(previous.proposal))
        if (receipt is None or receipt["subject"] != plan["target_id"]
                or receipt["source_observation_id"] not in feedback.observation_ids):
            return self._decision(request)
        return self._plan(request)
