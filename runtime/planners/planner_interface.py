"""TASK-020: interchangeable, proposal-only planners over TASK-019 snapshots.

This module contains no planner strategy, provider call or executor integration.
Scope here is a candidate filter; only the safety gate can authorize execution.
"""
from __future__ import annotations

import hashlib
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, final

from runtime.evidence.discovery_recorder import redact_secrets
from runtime.state.knowledge_state_store import StoreContext
from scripts.validation.validate_scaffold import validate_shape

Mode = Literal["RULE", "LLM", "RL", "HYBRID"]
StopReason = Literal["OBJECTIVE_COMPLETE", "BUDGET_EXHAUSTED", "NO_VALID_CANDIDATE"]
_MODES = ("RULE", "LLM", "RL", "HYBRID")
_STOPS = ("OBJECTIVE_COMPLETE", "BUDGET_EXHAUSTED", "NO_VALID_CANDIDATE")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
_ACTION = re.compile(r"ACTION-[A-Z]+-[0-9]{3}")
_TARGET = re.compile(r"lab-[a-z0-9-]+")
_REVISION = re.compile(r"[0-9a-f]{64}")
_CONTRACTS = Path(__file__).resolve().parents[2] / "agent/planner/contracts"
_MAX_BYTES = 1024 * 1024


def _identifier(value: str, pattern=_ID) -> None:
    if type(value) is not str or len(value) > 128 or not pattern.fullmatch(value):
        raise ValueError("invalid planner identifier")


def _canonical(data) -> str:
    # Reject non-JSON types rather than silently converting tuples or dict keys.
    def check(value):
        if type(value) is dict:
            if any(type(key) is not str for key in value):
                raise ValueError("JSON keys must be strings")
            for item in value.values():
                check(item)
        elif type(value) is list:
            for item in value:
                check(item)
        elif type(value) not in (str, int, float, bool, type(None)):
            raise ValueError("plain JSON data required")

    try:
        check(data)
        text = json.dumps(data, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False)
        if len(text.encode("utf-8")) > _MAX_BYTES:
            raise ValueError("planner document exceeds size limit")
        return text
    except (TypeError, OverflowError, UnicodeError, RecursionError) as exc:
        raise ValueError("invalid planner JSON") from exc


def _document(text: str, schema_name: str) -> tuple[str, dict]:
    if type(text) is not str or len(text) > _MAX_BYTES:
        raise ValueError("invalid planner document")
    try:
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ValueError("duplicate JSON key")
                result[key] = value
            return result

        data = json.loads(text, object_pairs_hook=pairs)
        canonical = _canonical(data)
        if type(data) is not dict:
            raise ValueError("planner document must be an object")
        schema = json.loads((_CONTRACTS / schema_name).read_text("utf-8"))
        if validate_shape(data, schema):
            raise ValueError("planner document violates canonical schema")
        if redact_secrets(data) != data:
            raise ValueError("planner data must already be redacted")
        return canonical, data
    except (OverflowError, UnicodeError, RecursionError) as exc:
        raise ValueError("invalid planner document") from exc


class StateReader(Protocol):
    """Minimal read API; a planner never receives the writable store."""

    def get_state(self, context: StoreContext) -> dict: ...


@dataclass(frozen=True)
class StateSnapshot:
    context: StoreContext
    state_json: str

    def __post_init__(self):
        if type(self.context) is not StoreContext:
            raise ValueError("StoreContext required")
        canonical, state = _document(self.state_json, "state.schema.json")
        for key in ("schema_version", "run_id", "objective_id"):
            _identifier(state[key])
        if state["run_id"] != self.context.run_id:
            raise ValueError("snapshot run does not match context")
        facts = state["observed_facts"]
        if len({fact["fact_id"] for fact in facts}) != len(facts):
            raise ValueError("duplicate fact identity")
        object.__setattr__(self, "state_json", canonical)

    @classmethod
    def from_state(cls, state: dict, *, context: StoreContext) -> StateSnapshot:
        return cls(context, _canonical(state))

    @classmethod
    def from_store(cls, store: StateReader, context: StoreContext) -> StateSnapshot:
        return cls.from_state(store.get_state(context), context=context)

    def to_dict(self) -> dict:
        """A detached copy, including detached facts and budget."""
        return json.loads(self.state_json)

    @property
    def revision(self) -> str:
        # Include session/episode: identical state in another context is distinct.
        value = self.context.key + "\n" + self.state_json
        return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PlanProposal:
    """Closed canonical plan document; provenance belongs to the envelope."""
    plan_json: str

    def __post_init__(self):
        canonical, plan = _document(self.plan_json, "plan.schema.json")
        for key, value in plan.items():
            if type(value) is str:
                if not value or len(value) > 2048:
                    raise ValueError("invalid plan text")
                if key not in ("resource_ref", "parameter_name"):
                    _identifier(value)
        for ref in plan.get("evidence_refs", []):
            _identifier(ref)
        object.__setattr__(self, "plan_json", canonical)

    @classmethod
    def from_dict(cls, plan: dict) -> PlanProposal:
        return cls(_canonical(plan))

    def to_dict(self) -> dict:
        return json.loads(self.plan_json)


@dataclass(frozen=True)
class PlanningInput:
    state: StateSnapshot
    allowed_action_ids: frozenset[str]
    allowed_target_ids: frozenset[str]
    fallback_allowed: bool = False

    def __post_init__(self):
        if type(self.state) is not StateSnapshot or type(self.fallback_allowed) is not bool:
            raise ValueError("invalid planning input")
        for field, pattern in (("allowed_action_ids", _ACTION),
                               ("allowed_target_ids", _TARGET)):
            values = getattr(self, field)
            if type(values) not in (set, frozenset):
                raise ValueError("candidate scope must be a set")
            for value in values:
                _identifier(value, pattern)
            object.__setattr__(self, field, frozenset(values))


@dataclass(frozen=True)
class PlanningDecision:
    context: StoreContext
    input_revision: str
    requested_mode: Mode
    actual_mode: Mode
    proposal: PlanProposal | None = None
    stop_reason: StopReason | None = None
    fallback_reason: str | None = None

    def __post_init__(self):
        if type(self.context) is not StoreContext:
            raise ValueError("StoreContext required")
        _identifier(self.input_revision, _REVISION)
        if self.requested_mode not in _MODES or self.actual_mode not in _MODES:
            raise ValueError("unsupported planner mode")
        if (self.proposal is None) == (self.stop_reason is None):
            raise ValueError("exactly one proposal or stop reason required")
        if self.proposal is not None and type(self.proposal) is not PlanProposal:
            raise ValueError("PlanProposal required")
        if self.stop_reason is not None and self.stop_reason not in _STOPS:
            raise ValueError("unsupported stop reason")
        if self.fallback_reason is not None:
            _identifier(self.fallback_reason)
        if (self.requested_mode != self.actual_mode) != (self.fallback_reason is not None):
            raise ValueError("mode change requires explicit fallback reason")


@dataclass(frozen=True)
class Feedback:
    context: StoreContext
    input_revision: str  # Binds feedback to the previous decision.
    action_id: str
    outcome: Literal["SUCCESS", "FAILURE", "PARTIAL", "DENIED", "ERROR"]
    reason_code: str
    observation_ids: tuple[str, ...] = ()

    def __post_init__(self):
        if type(self.context) is not StoreContext:
            raise ValueError("StoreContext required")
        _identifier(self.input_revision, _REVISION)
        _identifier(self.action_id, _ACTION)
        _identifier(self.reason_code)
        if self.outcome not in ("SUCCESS", "FAILURE", "PARTIAL", "DENIED", "ERROR"):
            raise ValueError("unsupported feedback outcome")
        if type(self.observation_ids) is not tuple:
            raise ValueError("immutable observation IDs required")
        for value in self.observation_ids:
            _identifier(value)
        if len(set(self.observation_ids)) != len(self.observation_ids):
            raise ValueError("duplicate observation identity")


class Planner(ABC):
    """Template methods validate every strategy's input and output.

    Subclasses implement mode and _plan(); override _replan() when history matters.
    Strategies are trusted Python implementations; this ABC is not a sandbox.
    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if "plan" in cls.__dict__ or "replan" in cls.__dict__:
            raise TypeError("override _plan/_replan, not validated entry points")

    @property
    @abstractmethod
    def mode(self) -> Mode:
        raise NotImplementedError

    @abstractmethod
    def _plan(self, request: PlanningInput) -> PlanningDecision:
        raise NotImplementedError

    def _replan(self, request: PlanningInput, *, previous: PlanningDecision,
                feedback: Feedback) -> PlanningDecision:
        return self._plan(request)

    def _preflight(self, request: PlanningInput) -> PlanningDecision | None:
        if type(request) is not PlanningInput or self.mode not in _MODES:
            raise ValueError("invalid planner request or mode")
        state = request.state.to_dict()
        reason = None
        if state["phase"] == "TERMINAL":
            reason = "NO_VALID_CANDIDATE"  # Terminal does not prove success.
        elif any(value == 0 for value in state["remaining_budget"].values()):
            reason = "BUDGET_EXHAUSTED"
        elif not request.allowed_action_ids or not request.allowed_target_ids:
            reason = "NO_VALID_CANDIDATE"
        if reason:
            return PlanningDecision(request.state.context, request.state.revision,
                                    self.mode, self.mode, stop_reason=reason)
        return None

    def _validate_result(self, request: PlanningInput,
                         decision: PlanningDecision) -> PlanningDecision:
        if type(decision) is not PlanningDecision:
            raise ValueError("PlanningDecision required")
        if (decision.context != request.state.context or
                decision.input_revision != request.state.revision):
            raise ValueError("decision context or snapshot mismatch")
        if decision.requested_mode != self.mode:
            raise ValueError("requested mode mismatch")
        if decision.actual_mode != self.mode and not request.fallback_allowed:
            raise ValueError("fallback was not allowed")
        if decision.proposal is not None:
            plan = decision.proposal.to_dict()
            if plan["objective_id"] != request.state.to_dict()["objective_id"]:
                raise ValueError("proposal objective mismatch")
            if (plan["action_id"] not in request.allowed_action_ids or
                    plan["target_id"] not in request.allowed_target_ids):
                raise ValueError("proposal outside candidate scope")
        return decision

    @final
    def plan(self, request: PlanningInput) -> PlanningDecision:
        stop = self._preflight(request)
        return stop if stop is not None else self._validate_result(request, self._plan(request))

    @final
    def replan(self, request: PlanningInput, *, previous: PlanningDecision,
               feedback: Feedback) -> PlanningDecision:
        stop = self._preflight(request)
        if type(previous) is not PlanningDecision or type(feedback) is not Feedback:
            raise ValueError("typed previous decision and feedback required")
        if previous.context != request.state.context or feedback.context != previous.context:
            raise ValueError("replan context mismatch")
        if previous.input_revision != feedback.input_revision:
            raise ValueError("feedback revision mismatch")
        if (previous.proposal is None or
                previous.proposal.to_dict()["action_id"] != feedback.action_id):
            raise ValueError("feedback action mismatch")
        return stop if stop is not None else self._validate_result(
            request, self._replan(request, previous=previous, feedback=feedback))
