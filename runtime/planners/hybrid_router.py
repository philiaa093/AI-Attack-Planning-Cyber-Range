"""TASK-027 reference routing policy for offline evidence review only.

Returns routing data and minimized memory; never calls a backend or executor.
History is supplied by a trusted coordinator, not a policy authorization token.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from runtime.state.knowledge_state_store import StoreContext
from runtime.planners.planner_interface import Feedback, PlanningDecision, PlanningInput
from runtime.planners.hybrid_planner import (
    FakeHybridRankingProvider,
    HYBRID_PLANNER_PROMPT_V1,
    HYBRID_PLANNER_SYSTEM_PROMPT,
    HybridPlanner,
    parse_hybrid_ranking_json,
)
from runtime.planners.symbolic_scorer import (
    CandidateScoreBreakdown,
    HybridScoringConfig,
    SymbolicScorer,
)

REVIEW_ACTION = "ACTION-PLAN-003"
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
_VERSION = re.compile(r"[0-9a-f]{64}")


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def _candidate_version(context_key, objective_id, fact):
    return hashlib.sha256(_json([
        context_key, objective_id, REVIEW_ACTION, fact,
    ]).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RoutingPolicy:
    llm_enabled: bool = True
    max_delegations: int = 2
    max_no_progress: int = 3

    def __post_init__(self):
        if (type(self.llm_enabled) is not bool
                or type(self.max_delegations) is not int
                or type(self.max_no_progress) is not int
                or not 1 <= self.max_delegations <= 32
                or not 1 <= self.max_no_progress <= 32):
            raise ValueError("invalid offline routing policy")


@dataclass(frozen=True)
class RoutingHistory:
    context: StoreContext
    delegation_count: int = 0
    no_progress_count: int = 0
    excluded_versions: tuple[str, ...] = ()

    def __post_init__(self):
        if (type(self.context) is not StoreContext
                or type(self.delegation_count) is not int
                or type(self.no_progress_count) is not int
                or self.delegation_count < 0 or self.no_progress_count < 0
                or type(self.excluded_versions) is not tuple
                or len(self.excluded_versions) > 128
                or any(type(v) is not str or not _VERSION.fullmatch(v)
                       for v in self.excluded_versions)
                or len(set(self.excluded_versions)) != len(self.excluded_versions)):
            raise ValueError("invalid context-bound routing history")


@dataclass(frozen=True)
class RoutingResult:
    operation: str
    backend: str
    reason_code: str
    input_revision: str
    handoff_json: str | None = None


class HybridReviewRouter:
    """Pure state machine; no mutable session counters or transport hooks."""

    def __init__(self, policy: RoutingPolicy = RoutingPolicy()):
        if type(policy) is not RoutingPolicy:
            raise ValueError("RoutingPolicy required")
        self.policy = policy

    @staticmethod
    def _check_decision(request, decision, *, current=False):
        if type(decision) is not PlanningDecision:
            raise ValueError("PlanningDecision required")
        if decision.context != request.state.context:
            raise ValueError("decision context mismatch")
        if current and decision.input_revision != request.state.revision:
            raise ValueError("stale rule decision")
        if (decision.actual_mode not in ("RULE", "LLM")
                or decision.requested_mode != decision.actual_mode):
            raise ValueError("original backend decision required; do not relabel fallback")
        if decision.proposal is not None:
            plan = decision.proposal.to_dict()
            state = request.state.to_dict()
            prefix = "PLAN-021-" if decision.actual_mode == "RULE" else "PLAN-022-"
            plan_id = plan.get("plan_id", "")
            if (plan["action_id"] != REVIEW_ACTION
                    or plan["objective_id"] != state["objective_id"]
                    or not plan_id.startswith(prefix)
                    or not _VERSION.fullmatch(plan_id[len(prefix):])):
                raise ValueError("original Task 21/22 evidence-review proposal required")
            if current and not any(
                fact["fact_type"] == "CANDIDATE_FINDING"
                and fact["subject"] == plan["target_id"]
                and fact["source_observation_id"] == plan.get("source_observation_id")
                and _candidate_version(request.state.context.key, state["objective_id"], fact) == plan_id[len(prefix):]
                for fact in state["observed_facts"]
            ):
                raise ValueError("rule proposal does not bind an observed candidate version")

    @staticmethod
    def _memory(request, history, previous, feedback):
        state = request.state.to_dict()
        excluded = set(history.excluded_versions)
        if feedback is not None and feedback.outcome != "SUCCESS":
            excluded.add(previous.proposal.to_dict()["plan_id"].rsplit("-", 1)[1])
        candidates = []
        for fact in state["observed_facts"]:
            if fact["fact_type"] != "CANDIDATE_FINDING":
                continue
            if any(not _ID.fullmatch(fact[key]) for key in (
                    "fact_id", "subject", "source_observation_id")):
                raise ValueError("invalid review metadata identity")
            version = _candidate_version(request.state.context.key, state["objective_id"], fact)
            if fact["subject"] in request.allowed_target_ids and version not in excluded:
                candidates.append({
                    "fact_id": fact["fact_id"], "target_id": fact["subject"],
                    "source_observation_id": fact["source_observation_id"],
                    "candidate_version": version, "confidence": fact["confidence"],
                })
        candidates.sort(key=lambda entry: entry["fact_id"])
        selected = candidates[:32]
        document = {
            "requested_mode": "HYBRID", "decision_source": "LLM_HANDOFF",
            "control": {
                "run_id": request.state.context.run_id,
                "session_id": request.state.context.session_id,
                "episode_id": request.state.context.episode_id,
                "objective_id": state["objective_id"], "phase": state["phase"],
                "input_revision": request.state.revision,
                "candidate_action_id": REVIEW_ACTION,
                "remaining_budget": state["remaining_budget"],
            },
            "coverage": {
                "eligible_metadata_count": len(candidates), "included_count": len(selected),
                "omitted_count": len(candidates) - len(selected), "raw_values_included": False,
            },
            "candidates": selected,
            "feedback": None if feedback is None else {
                "previous_plan_id": previous.proposal.to_dict()["plan_id"],
                "previous_backend": previous.actual_mode,
                "previous_input_revision": previous.input_revision,
                "outcome": feedback.outcome, "reason_code": feedback.reason_code,
                "observation_ids": list(feedback.observation_ids),
            },
        }
        return _json(document), bool(selected)

    def route(self, request: PlanningInput, *, history: RoutingHistory,
              rule_decision: PlanningDecision | None = None,
              previous: PlanningDecision | None = None,
              feedback: Feedback | None = None) -> RoutingResult:
        if type(request) is not PlanningInput or type(history) is not RoutingHistory:
            raise ValueError("typed request and history required")
        if history.context != request.state.context:
            raise ValueError("history context mismatch")
        if not request.allowed_action_ids <= {REVIEW_ACTION}:
            raise ValueError("router only supports offline evidence review")
        if (previous is None) != (feedback is None):
            raise ValueError("previous and feedback must be supplied together")
        if previous is not None:
            if rule_decision is not None:
                raise ValueError("initial rule decision cannot accompany feedback")
            self._check_decision(request, previous)
            if (type(feedback) is not Feedback or previous.proposal is None
                    or feedback.context != previous.context
                    or feedback.input_revision != previous.input_revision
                    or feedback.action_id != REVIEW_ACTION):
                raise ValueError("feedback binding mismatch")
        if rule_decision is not None:
            self._check_decision(request, rule_decision, current=True)
            if rule_decision.actual_mode != "RULE":
                raise ValueError("initial RULE decision required")

        def result(operation, backend, reason, memory=None):
            return RoutingResult(operation, backend, reason, request.state.revision, memory)

        state = request.state.to_dict()
        if feedback is not None and feedback.outcome == "DENIED":
            return result("STOP", "NONE", "POLICY_DENIED")
        if state["phase"] not in ("ANALYSIS", "REPLAN"):
            return result("STOP", "NONE", "UNSUPPORTED_REVIEW_PHASE")
        if any(value == 0 for value in state["remaining_budget"].values()):
            return result("STOP", "NONE", "BUDGET_EXHAUSTED")
        if not request.allowed_action_ids or not request.allowed_target_ids:
            return result("STOP", "NONE", "NO_VALID_CANDIDATE")
        if (previous is not None
                and previous.proposal.to_dict()["target_id"] not in request.allowed_target_ids):
            return result("STOP", "NONE", "SCOPE_REVOKED")
        if history.no_progress_count >= self.policy.max_no_progress:
            return result("STOP", "NONE", "NO_PROGRESS_LIMIT")
        if feedback is not None:
            if not feedback.observation_ids:
                return result("STOP", "NONE", "FEEDBACK_EVIDENCE_REQUIRED")
            if feedback.outcome == "SUCCESS":
                # The original backend must verify its completion CONTROL receipt.
                if previous.actual_mode == "LLM":
                    if not self.policy.llm_enabled:
                        return result("STOP", "NONE", "LLM_DELEGATION_DISABLED")
                    if history.delegation_count >= self.policy.max_delegations:
                        return result("STOP", "NONE", "DELEGATION_LIMIT")
                return result("REPLAN", previous.actual_mode, "CHECK_COMPLETION_RECEIPT")
        elif rule_decision is None:
            return result("PLAN", "RULE", "RULE_FIRST")
        elif rule_decision.proposal is not None:
            if rule_decision.proposal.to_dict()["target_id"] not in request.allowed_target_ids:
                raise ValueError("rule proposal outside candidate scope")
            version = rule_decision.proposal.to_dict()["plan_id"].rsplit("-", 1)[1]
            if version not in history.excluded_versions:
                return result("ACCEPT_RULE", "RULE", "RULE_MATCHED")
        elif rule_decision.stop_reason != "NO_VALID_CANDIDATE":
            return result("STOP", "NONE", rule_decision.stop_reason)

        if not self.policy.llm_enabled:
            return result("STOP", "NONE", "LLM_DELEGATION_DISABLED")
        if history.delegation_count >= self.policy.max_delegations:
            return result("STOP", "NONE", "DELEGATION_LIMIT")
        memory, has_candidates = self._memory(request, history, previous, feedback)
        if not has_candidates:
            return result("STOP", "NONE", "NO_VALID_CANDIDATE")
        operation = "REPLAN" if previous is not None and previous.actual_mode == "LLM" else "HANDOFF"
        if feedback is not None:
            reason = "REVIEW_" + feedback.outcome
        else:
            reason = "RULE_BLOCKED_VERSION" if rule_decision.proposal else "RULE_NO_MATCH"
        return result(operation, "LLM", reason, memory)
