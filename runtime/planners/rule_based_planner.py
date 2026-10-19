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
RULE_POLICY_VERSION = "RULE_POLICY_V1"
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
            if fact["subject"] in request.visible_target_ids:
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

    def _plan_context(self, context: Any) -> Any:
        """Execute deterministic rule baseline over PlannerDecisionContext (RT-05A)."""
        from actions.catalog.action_registry import get_canonical_action_id
        from runtime.planners.planner_context import PlannerDecision as ContextDecision
        belief = context.belief_state

        def _get_stop_proposal() -> dict:
            for p in context.eligible_proposals:
                if get_canonical_action_id(p.get("action_id", "")) == "ACTION-STOP-001":
                    return dict(p)
            return {"action_id": "ACTION-STOP-001"}

        # 1. Authoritative objective achievement check
        if belief.is_objective_achieved():
            return ContextDecision(
                proposal=_get_stop_proposal(),
                rationale="Objective authoritatively achieved under current belief; terminating engagement.",
                reason_code="OBJECTIVE_COMPLETE",
                confidence=1.0,
            )

        # 2. Budget or step limit bounds
        if context.remaining_budget <= 1 or context.step_index >= context.max_steps - 1:
            return ContextDecision(
                proposal=_get_stop_proposal(),
                rationale="Operational budget or max step limit reached; terminating cleanly.",
                reason_code="BUDGET_EXHAUSTED",
                confidence=1.0,
            )

        # 3. Aggregate observable history to prevent cycles and track failed paths
        attempted_proposals: set[tuple[str, str, str, str]] = set()
        failed_proposals: set[tuple[str, str, str, str]] = set()
        attempted_action_targets: set[tuple[str, str]] = set()
        attempted_recon_hosts: set[str] = set()
        attempted_scan_hosts: set[str] = set()
        attempted_harvest_hosts: set[str] = set()
        attempted_hostrecon_hosts: set[str] = set()
        failed_pivot_edges: set[tuple[str, str]] = set()

        history_items = list(getattr(context, "action_history", None) or [])
        if context.previous_outcome:
            history_items.append(context.previous_outcome)

        for h in history_items:
            if not isinstance(h, dict):
                continue
            raw_act = str(h.get("action_id") or "")
            can_act = get_canonical_action_id(raw_act)
            tgt = str(h.get("target_id") or "")
            src = str(h.get("from_node_id") or h.get("from_host") or "")
            cid = str(h.get("credential_id") or "")
            succ = bool(h.get("success", True))

            prop_key = (can_act, tgt, src, cid)
            attempted_proposals.add(prop_key)
            if can_act and tgt:
                attempted_action_targets.add((can_act, tgt))
                tgt_host = tgt.split(":")[0]
                attempted_action_targets.add((can_act, tgt_host))

                if can_act == "ACTION-DISCOVERY-001":
                    attempted_recon_hosts.add(tgt_host)
                elif can_act in ("ACTION-SCAN-001", "ACTION-SCAN-002"):
                    attempted_scan_hosts.add(tgt_host)
                elif can_act == "ACTION-CREDS-001":
                    attempted_harvest_hosts.add(tgt_host)
                elif can_act == "ACTION-HOSTRECON-001":
                    attempted_hostrecon_hosts.add(tgt_host)

            if not succ:
                failed_proposals.add(prop_key)
                if can_act == "ACTION-PIVOT-001" and src and tgt:
                    failed_pivot_edges.add((src, tgt))

        def _get_prop_key(p: dict) -> tuple[str, str, str, str]:
            return (
                get_canonical_action_id(str(p.get("action_id") or "")),
                str(p.get("target_id") or ""),
                str(p.get("from_node_id") or p.get("from_host") or ""),
                str(p.get("credential_id") or ""),
            )

        def is_failed(p: dict) -> bool:
            k = _get_prop_key(p)
            if k in failed_proposals:
                return True
            can_act = get_canonical_action_id(p.get("action_id", ""))
            src = str(p.get("from_node_id") or p.get("from_host") or "")
            tgt = str(p.get("target_id") or "")
            if can_act == "ACTION-PIVOT-001" and src and tgt:
                if (src, tgt) in failed_pivot_edges:
                    return True
            return False

        # 4. Semantic category priorities (canonical benchmark action vocabulary)
        category_specs = [
            (
                ("ACTION-DISCOVERY-001", "ACTION-RECON-001"),
                "NETWORK_RECON",
                "Discovering network services on visible target.",
            ),
            (
                ("ACTION-SCAN-001",),
                "SERVICE_SCAN",
                "Scanning discovered services for confirmed vulnerabilities.",
            ),
            (
                ("ACTION-FOOTHOLD-001", "ACTION-WEB-001"),
                "INITIAL_ACCESS_FOOTHOLD",
                "Exploiting remote service for initial foothold session.",
            ),
            (
                ("ACTION-HOSTRECON-001",),
                "HOST_RECON",
                "Enumerating host internal configuration from active session.",
            ),
            (
                ("ACTION-CREDS-001", "ACTION-AUTH-001"),
                "CREDENTIAL_DISCOVERY",
                "Harvesting credentials from compromised host memory.",
            ),
            (
                ("ACTION-PIVOT-001", "ACTION-FLOW-001"),
                "LATERAL_PIVOT",
                "Pivoting laterally to observed reachable internal host.",
            ),
            (
                ("ACTION-PRIVESC-001",),
                "PRIVILEGE_ESCALATION",
                "Escalating privileges on active host session.",
            ),
            (
                ("ACTION-OBJECTIVE-001", "ACTION-FLOW-002"),
                "PURSUING_MISSION_OBJECTIVE",
                "Accessing mission crown jewel objective.",
            ),
        ]

        active_hosts = {
            s.get("target_id") if isinstance(s, dict) else getattr(s, "target_id", None)
            for s in belief.active_sessions
        }
        compromised_hosts = {
            h for h, lvl in belief.access_state.items()
            if lvl in ("FOOTHOLD", "USER", "PRIVILEGED", "SYSTEM")
        } | active_hosts

        confirmed_findings = getattr(belief, "confirmed_findings", None) or []
        confirmed_hosts = {
            f.get("target") for f in confirmed_findings if isinstance(f, dict)
        }
        known_services = getattr(belief, "known_services", None) or []
        known_hosts_with_svc = {
            s.get("host") for s in known_services if isinstance(s, dict)
        }

        def is_useful(p: dict) -> bool:
            act = p.get("action_id", "")
            can_act = get_canonical_action_id(act)
            tgt = p.get("target_id", "")
            tgt_host = tgt.split(":")[0] if tgt else ""

            if can_act == "ACTION-DISCOVERY-001":
                return (
                    tgt not in known_hosts_with_svc
                    and tgt_host not in known_hosts_with_svc
                    and tgt_host not in attempted_recon_hosts
                )

            if can_act == "ACTION-SCAN-001":
                return (
                    (tgt in known_hosts_with_svc or tgt_host in known_hosts_with_svc)
                    and tgt_host not in attempted_scan_hosts
                    and (tgt not in confirmed_hosts and tgt_host not in confirmed_hosts)
                )

            if can_act == "ACTION-FOOTHOLD-001":
                return (
                    tgt not in compromised_hosts
                    and tgt_host not in compromised_hosts
                    and (can_act, tgt) not in attempted_action_targets
                )

            if can_act == "ACTION-CREDS-001":
                return (
                    (tgt in compromised_hosts or tgt_host in compromised_hosts)
                    and tgt_host not in attempted_harvest_hosts
                )

            if can_act == "ACTION-HOSTRECON-001":
                return (
                    (tgt in active_hosts or tgt_host in active_hosts)
                    and tgt_host not in attempted_hostrecon_hosts
                )

            if can_act == "ACTION-PIVOT-001":
                return tgt not in compromised_hosts and tgt_host not in compromised_hosts

            if can_act == "ACTION-OBJECTIVE-001":
                return not is_failed(p)

            return True

        # Scan categories in priority order
        for action_ids, reason_code, rationale_prefix in category_specs:
            candidates = [
                p for p in context.eligible_proposals
                if (p.get("action_id") in action_ids or get_canonical_action_id(p.get("action_id", "")) in action_ids)
                and is_useful(p)
                and not is_failed(p)
            ]
            if not candidates:
                continue

            # Deterministic stable sort: target_id, from_node_id, 0 if credential_id else 1, credential_id, action_id
            candidates.sort(
                key=lambda p: (
                    p.get("target_id") or "",
                    p.get("from_node_id") or "",
                    0 if p.get("credential_id") else 1,
                    p.get("credential_id") or "",
                    p.get("action_id") or "",
                )
            )

            top = candidates[0]
            tgt = top.get("target_id", "environment")
            return ContextDecision(
                proposal=dict(top),
                rationale=f"{rationale_prefix} Target: {tgt}.",
                reason_code=reason_code,
                confidence=0.9,
            )

        # Fallback to any unfailed non-stop eligible proposal
        other_candidates = [
            p for p in context.eligible_proposals
            if get_canonical_action_id(p.get("action_id", "")) != "ACTION-STOP-001"
            and not is_failed(p)
            and is_useful(p)
        ]
        if other_candidates:
            other_candidates.sort(
                key=lambda p: (
                    p.get("action_id") or "",
                    p.get("target_id") or "",
                )
            )
            top = other_candidates[0]
            return ContextDecision(
                proposal=dict(top),
                rationale=f"Executing fallback eligible action {top.get('action_id')}.",
                reason_code="FALLBACK_PROGRESS_ACTION",
                confidence=0.7,
            )

        # 5. No eligible progress action remaining -> Clean STOP
        return ContextDecision(
            proposal=_get_stop_proposal(),
            rationale="No meaningful eligible progress action remains; terminating engagement.",
            reason_code="NO_VALID_CANDIDATE",
            confidence=1.0,
        )

    def plan_decision(self, context: Any) -> Any:
        """Public entry point for enterprise episode planning under PlannerDecisionContext."""
        return self.plan(context)
