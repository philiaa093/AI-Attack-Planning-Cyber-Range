"""Canonical Action Constraint Evaluator (RT-03B).

Evaluates whether candidate action capabilities are feasible against the
current Planner-visible Belief State.

Hard Invariants:
  1. Single Canonical Evaluator: All precondition constraint evaluation routes
     through this module; ActionRegistry delegates to this engine.
  2. Pure & Read-Only: Zero state mutation, zero network calls, zero Ground Truth inspection.
  3. Quarantined Hypotheses: PLANNER_INFERENCE and hypothesis facts NEVER satisfy
     authoritative preconditions.
  4. Current vs Historical Access: Historical proven access level != active execution capability.
     If require_active_session is True, an unclosed session with state=='ACTIVE' is mandatory.
  5. Eligibility != Authorization: Evaluator answers whether an action is logically feasible
     under current observations; CentralizedSafetyGate retains final authorization authority.
  6. Canonical Access Hierarchy: NONE < FOOTHOLD < USER < PRIVILEGED < SYSTEM.
     (UNPRIVILEGED is normalized to USER for backwards compatibility).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from agent.memory.state.belief_state import (
    ACCESS_LEVEL_ORDER,
    ACCESS_LEVELS,
    BeliefState,
)


class EvaluationReason:
    """Canonical reason codes emitted when precondition constraints fail."""
    ACTIVE_SESSION_REQUIRED = "ACTIVE_SESSION_REQUIRED"
    TARGET_NOT_VISIBLE = "TARGET_NOT_VISIBLE"
    HOST_NOT_OBSERVED = "HOST_NOT_OBSERVED"
    SERVICE_NOT_OBSERVED = "SERVICE_NOT_OBSERVED"
    SERVICE_TYPE_MISMATCH = "SERVICE_TYPE_MISMATCH"
    CONFIRMED_FINDING_REQUIRED = "CONFIRMED_FINDING_REQUIRED"
    INSUFFICIENT_ACCESS = "INSUFFICIENT_ACCESS"
    NO_VALID_CREDENTIAL = "NO_VALID_CREDENTIAL"
    REACHABILITY_NOT_OBSERVED = "REACHABILITY_NOT_OBSERVED"
    OBJECTIVE_ALREADY_ACHIEVED = "OBJECTIVE_ALREADY_ACHIEVED"
    PHASE_NOT_ALLOWED = "PHASE_NOT_ALLOWED"
    INVALID_TARGET_KIND = "INVALID_TARGET_KIND"


@dataclass(frozen=True)
class EvaluationResult:
    """Rich evaluation outcome returned by ActionConstraintEvaluator."""
    eligible: bool
    action_id: str
    target_id: str | None
    satisfied_conditions: tuple[str, ...] = ()
    failed_conditions: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    relevant_fact_ids: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    step_cost: int = 1
    noise_cost: float = 0.0
    action_class: str = ""
    target_kind: str = ""

    def __bool__(self) -> bool:
        return self.eligible

    def to_dict(self) -> dict[str, Any]:
        return {
            "eligible": self.eligible,
            "action_id": self.action_id,
            "target_id": self.target_id,
            "satisfied_conditions": list(self.satisfied_conditions),
            "failed_conditions": list(self.failed_conditions),
            "reason_codes": list(self.reason_codes),
            "relevant_fact_ids": list(self.relevant_fact_ids),
            "reasons": list(self.reasons),
            "step_cost": self.step_cost,
            "noise_cost": self.noise_cost,
            "action_class": self.action_class,
            "target_kind": self.target_kind,
        }


def _normalize_access_level(level: str | None) -> str:
    """Normalize access level string to canonical vocabulary."""
    if not level:
        return "NONE"
    normalized = str(level).strip().upper()
    if normalized == "UNPRIVILEGED":
        return "USER"
    if normalized in ACCESS_LEVEL_ORDER:
        return normalized
    return "NONE"


def _is_quarantined(item: Any) -> bool:
    """Return True if item represents a hypothesis or inference that must not satisfy authoritative preconditions."""
    if not isinstance(item, (dict, Mapping)):
        return False
    if item.get("hypothesis") is True:
        return True
    source_kind = item.get("source_kind")
    if not source_kind and isinstance(item.get("provenance"), Mapping):
        source_kind = item["provenance"].get("source_kind")
    if source_kind in ("PLANNER_INFERENCE", "INFERENCE"):
        return True
    return False


def _get_known_hosts(belief: Any) -> dict[str, Any]:
    raw = getattr(belief, "known_hosts", None)
    if raw is None and isinstance(belief, Mapping):
        raw = belief.get("known_hosts")
    return dict(raw) if isinstance(raw, Mapping) else {}


def _get_known_services(belief: Any) -> list[dict[str, Any]]:
    raw = getattr(belief, "known_services", None)
    if raw is None and isinstance(belief, Mapping):
        raw = belief.get("known_services")
    return list(raw) if isinstance(raw, (list, tuple)) else []


def _get_known_endpoints(belief: Any) -> list[dict[str, Any]]:
    raw = getattr(belief, "known_endpoints", None)
    if raw is None and isinstance(belief, Mapping):
        raw = belief.get("known_endpoints")
    return list(raw) if isinstance(raw, (list, tuple)) else []


def _get_confirmed_findings(belief: Any) -> list[dict[str, Any]]:
    raw = getattr(belief, "confirmed_findings", None)
    if raw is None and isinstance(belief, Mapping):
        raw = belief.get("confirmed_findings")
    return list(raw) if isinstance(raw, (list, tuple)) else []


def _get_access_state(belief: Any) -> dict[str, str]:
    raw = getattr(belief, "access_state", None)
    if raw is None and isinstance(belief, Mapping):
        raw = belief.get("access_state")
    return dict(raw) if isinstance(raw, Mapping) else {}


def _get_known_credentials(belief: Any) -> list[dict[str, Any]]:
    raw = getattr(belief, "known_credentials", None)
    if raw is None and isinstance(belief, Mapping):
        raw = belief.get("known_credentials")
    if isinstance(raw, Mapping):
        return list(raw.values())
    return list(raw) if isinstance(raw, (list, tuple)) else []


def _get_sessions(belief: Any) -> list[dict[str, Any]]:
    raw = getattr(belief, "sessions", None)
    if raw is None and isinstance(belief, Mapping):
        raw = belief.get("sessions")
    if isinstance(raw, Mapping):
        return list(raw.values())
    return list(raw) if isinstance(raw, (list, tuple)) else []


def _get_observed_reachability(belief: Any) -> list[dict[str, Any]]:
    raw = getattr(belief, "observed_reachability", None)
    if raw is None and isinstance(belief, Mapping):
        raw = belief.get("observed_reachability")
    if isinstance(raw, Mapping):
        return list(raw.values())
    return list(raw) if isinstance(raw, (list, tuple)) else []


def _get_objective_status(belief: Any) -> dict[str, Any]:
    raw = getattr(belief, "objective_status", None)
    if raw is None and isinstance(belief, Mapping):
        raw = belief.get("objective_status")
    return dict(raw) if isinstance(raw, Mapping) else {}


class ActionConstraintEvaluator:
    """Canonical evaluator for action precondition feasibility against Belief State."""

    def evaluate(
        self,
        action: Any,
        target_id: str | None = None,
        belief_state: Any = None,
        visible_target_ids: Sequence[str] | set[str] | None = None,
        proposal_parameters: Mapping[str, Any] | None = None,
        current_phase: str | None = None,
    ) -> EvaluationResult:
        """Evaluate action feasibility deterministically against Belief State.

        Args:
            action: ActionDefinition dataclass or dictionary representation.
            target_id: Proposed target identifier (host, service, objective, etc.).
            belief_state: BeliefState instance or dictionary.
            visible_target_ids: Explicit planner-visible targets set (RT-01 boundary).
            proposal_parameters: Optional action proposal arguments.
            current_phase: Current planner phase string.

        Returns:
            EvaluationResult detailing eligibility, reason codes, and provenance fact IDs.
        """
        # 1. Unpack Action Definition metadata
        if isinstance(action, Mapping):
            action_id = action.get("action_id", "UNKNOWN")
            action_class = action.get("action_class", "")
            target_kind = action.get("target_kind", "HOST")
            step_cost = int(action.get("step_cost", 1))
            noise_cost = float(action.get("noise_cost", 0.0))
            raw_pre = action.get("preconditions", {})
            if isinstance(raw_pre, Mapping):
                pre_dict = raw_pre
            elif hasattr(raw_pre, "__dict__"):
                pre_dict = raw_pre.__dict__
            else:
                pre_dict = {}
        else:
            action_id = getattr(action, "action_id", "UNKNOWN")
            action_class = getattr(action, "action_class", "")
            target_kind = getattr(action, "target_kind", "HOST")
            step_cost = int(getattr(action, "step_cost", 1))
            noise_cost = float(getattr(action, "noise_cost", 0.0))
            raw_pre = getattr(action, "preconditions", None)
            if raw_pre is None:
                pre_dict = {}
            elif isinstance(raw_pre, Mapping):
                pre_dict = raw_pre
            elif hasattr(raw_pre, "__dict__"):
                pre_dict = raw_pre.__dict__
            else:
                pre_dict = {}

        # Precondition field extraction
        pre_target_visible = bool(pre_dict.get("target_visible", False))
        pre_host_observed = bool(pre_dict.get("host_observed", False))
        pre_service_observed = bool(pre_dict.get("service_observed", False))
        pre_required_service_type = pre_dict.get("required_service_type")
        pre_finding_confirmed = bool(pre_dict.get("finding_confirmed", False))
        pre_min_access_level = _normalize_access_level(pre_dict.get("min_access_level", "NONE"))
        pre_require_active_session = bool(pre_dict.get("require_active_session", False))
        pre_require_valid_credential = bool(pre_dict.get("require_valid_credential", False))
        pre_require_reachability = bool(pre_dict.get("require_reachability", False))
        pre_objective_not_achieved = bool(pre_dict.get("objective_not_achieved", False))
        pre_allowed_phases = tuple(pre_dict.get("allowed_phases", ()))

        satisfied_conditions: list[str] = []
        failed_conditions: list[str] = []
        reason_codes: list[str] = []
        reasons: list[str] = []
        relevant_fact_ids: list[str] = []

        # Read-only belief snapshots
        known_hosts = _get_known_hosts(belief_state)
        known_services = _get_known_services(belief_state)
        known_endpoints = _get_known_endpoints(belief_state)
        confirmed_findings = _get_confirmed_findings(belief_state)
        access_state = _get_access_state(belief_state)
        credentials = _get_known_credentials(belief_state)
        sessions = _get_sessions(belief_state)
        reachability_edges = _get_observed_reachability(belief_state)
        objective_status = _get_objective_status(belief_state)

        # Determine host component if target_id is composite (e.g. host:port)
        target_host: str | None = None
        if target_id is not None:
            target_host = target_id.split(":")[0] if ":" in target_id else target_id

        # ---------------------------------------------------------
        # Check 0: Target Kind Compatibility
        # ---------------------------------------------------------
        if target_kind == "ENVIRONMENT":
            # STOP and internal actions do not require network target
            satisfied_conditions.append("target_kind")
        elif target_id is None:
            failed_conditions.append("target_kind")
            reason_codes.append(EvaluationReason.INVALID_TARGET_KIND)
            reasons.append(f"action {action_id} requires target of kind {target_kind!r}, but target_id is None")
        else:
            satisfied_conditions.append("target_kind")

        # ---------------------------------------------------------
        # Check 1: Target Visibility (RT-01 Boundary)
        # ---------------------------------------------------------
        if pre_target_visible:
            if target_id is None:
                failed_conditions.append("target_visible")
                reason_codes.append(EvaluationReason.TARGET_NOT_VISIBLE)
                reasons.append(f"action {action_id} requires target visibility, but target_id is None")
            else:
                is_visible = False
                if visible_target_ids is not None:
                    is_visible = (target_id in visible_target_ids or (target_host is not None and target_host in visible_target_ids))
                elif hasattr(belief_state, "visible_target_ids") and getattr(belief_state, "visible_target_ids") is not None:
                    vis = getattr(belief_state, "visible_target_ids")
                    is_visible = (target_id in vis or (target_host is not None and target_host in vis))
                elif isinstance(belief_state, Mapping) and belief_state.get("visible_target_ids") is not None:
                    vis = belief_state["visible_target_ids"]
                    is_visible = (target_id in vis or (target_host is not None and target_host in vis))
                else:
                    # Fallback when no explicit visible set is provided: must be an observed host/service
                    is_visible = (target_id in known_hosts or (target_host is not None and target_host in known_hosts))

                if is_visible:
                    satisfied_conditions.append("target_visible")
                else:
                    failed_conditions.append("target_visible")
                    reason_codes.append(EvaluationReason.TARGET_NOT_VISIBLE)
                    reasons.append(f"target {target_id!r} not in planner visible scope")

        # ---------------------------------------------------------
        # Check 2: Host Observation (Authoritative vs Hypothesis)
        # ---------------------------------------------------------
        if pre_host_observed:
            if target_id is None or target_host is None:
                failed_conditions.append("host_observed")
                reason_codes.append(EvaluationReason.HOST_NOT_OBSERVED)
                reasons.append(f"action {action_id} requires observed host, but target_id is None")
            else:
                host_entry = known_hosts.get(target_host)
                if host_entry is not None and not _is_quarantined(host_entry):
                    satisfied_conditions.append("host_observed")
                    if isinstance(host_entry, Mapping):
                        for p in host_entry.get("provenance", []):
                            if p and p not in relevant_fact_ids:
                                relevant_fact_ids.append(p)
                else:
                    failed_conditions.append("host_observed")
                    reason_codes.append(EvaluationReason.HOST_NOT_OBSERVED)
                    reasons.append(f"host {target_host!r} not observed in authoritative belief state")

        # ---------------------------------------------------------
        # Check 3: Service Observation
        # ---------------------------------------------------------
        if pre_service_observed:
            if target_id is None:
                failed_conditions.append("service_observed")
                reason_codes.append(EvaluationReason.SERVICE_NOT_OBSERVED)
                reasons.append(f"action {action_id} requires observed service, but target_id is None")
            else:
                target_port: int | None = None
                if ":" in target_id:
                    try:
                        target_port = int(target_id.split(":")[1].split("/")[0])
                    except (ValueError, IndexError):
                        pass

                matching_services = [
                    s for s in known_services
                    if not _is_quarantined(s) and (
                        s.get("service_id") == target_id
                        or (
                            target_host is not None
                            and s.get("host") == target_host
                            and (target_port is None or s.get("port") == target_port)
                        )
                    )
                ]
                if matching_services:
                    satisfied_conditions.append("service_observed")
                    for s in matching_services:
                        if isinstance(s, Mapping):
                            for p in s.get("provenance", []):
                                if p and p not in relevant_fact_ids:
                                    relevant_fact_ids.append(p)
                else:
                    failed_conditions.append("service_observed")
                    reason_codes.append(EvaluationReason.SERVICE_NOT_OBSERVED)
                    reasons.append(f"no service observed on target {target_id!r}")

        # ---------------------------------------------------------
        # Check 4: Required Service Type
        # ---------------------------------------------------------
        if pre_required_service_type:
            req_type = str(pre_required_service_type).lower()
            matching_typed_services = [
                s for s in known_services
                if not _is_quarantined(s)
                and (
                    target_id is None
                    or s.get("service_id") == target_id
                    or (target_host is not None and s.get("host") == target_host)
                )
                and str(s.get("protocol", "")).lower() == req_type
            ]
            if matching_typed_services:
                satisfied_conditions.append("required_service_type")
                for s in matching_typed_services:
                    if isinstance(s, Mapping):
                        for p in s.get("provenance", []):
                            if p and p not in relevant_fact_ids:
                                relevant_fact_ids.append(p)
            else:
                failed_conditions.append("required_service_type")
                reason_codes.append(EvaluationReason.SERVICE_TYPE_MISMATCH)
                reasons.append(
                    f"action {action_id} requires service type {pre_required_service_type!r} on {target_id!r}"
                )

        # ---------------------------------------------------------
        # Check 5: Confirmed Finding (Confirms vs Candidate)
        # ---------------------------------------------------------
        if pre_finding_confirmed:
            param_finding_id = (proposal_parameters or {}).get("finding_id")
            matching_findings = [
                f for f in confirmed_findings
                if not _is_quarantined(f) and (
                    (param_finding_id and f.get("fact_id") == param_finding_id)
                    or (target_id and f.get("target") in (target_id, target_host))
                    or (not target_id and not param_finding_id)
                )
            ]
            if matching_findings:
                satisfied_conditions.append("finding_confirmed")
                for f in matching_findings:
                    fid = f.get("fact_id")
                    if fid and fid not in relevant_fact_ids:
                        relevant_fact_ids.append(fid)
                    for p in f.get("provenance", []):
                        if p and p not in relevant_fact_ids:
                            relevant_fact_ids.append(p)
            else:
                failed_conditions.append("finding_confirmed")
                reason_codes.append(EvaluationReason.CONFIRMED_FINDING_REQUIRED)
                reasons.append(
                    f"action {action_id} requires confirmed finding on {target_id!r}, candidate or hypothesis not eligible"
                )

        # ---------------------------------------------------------
        # Check 6: Minimum Access Level (Canonical Ordering)
        # ---------------------------------------------------------
        if pre_min_access_level != "NONE":
            required_rank = ACCESS_LEVEL_ORDER.get(pre_min_access_level, 0)
            current_level = "NONE"
            if target_host is not None:
                current_level = access_state.get(target_host, "NONE")
                if current_level == "NONE" and target_host in known_hosts:
                    hval = known_hosts[target_host]
                    current_level = hval.get("access_level") if isinstance(hval, Mapping) else getattr(hval, "access_level", "NONE")
            current_level = _normalize_access_level(current_level)
            current_rank = ACCESS_LEVEL_ORDER.get(current_level, 0)

            if current_rank >= required_rank:
                satisfied_conditions.append("min_access_level")
            else:
                failed_conditions.append("min_access_level")
                reason_codes.append(EvaluationReason.INSUFFICIENT_ACCESS)
                reasons.append(
                    f"action {action_id} requires min_access_level {pre_min_access_level} (rank {required_rank}), "
                    f"current proven level on {target_host!r} is {current_level} (rank {current_rank})"
                )

        # ---------------------------------------------------------
        # Check 7: Active Session Requirement (Historical != Capability)
        # ---------------------------------------------------------
        if pre_require_active_session:
            if target_id is None or target_host is None:
                failed_conditions.append("require_active_session")
                reason_codes.append(EvaluationReason.ACTIVE_SESSION_REQUIRED)
                reasons.append(f"action {action_id} requires active session, but target_id is None")
            else:
                session_target = (proposal_parameters or {}).get("from_host") or (proposal_parameters or {}).get("from_node_id") or target_id
                session_host = session_target.split(":")[0] if session_target and ":" in session_target else session_target

                target_sessions = [
                    s for s in sessions
                    if not _is_quarantined(s) and (
                        (s.get("target_id") if isinstance(s, Mapping) else getattr(s, "target_id", None)) in (session_target, session_host, target_id, target_host)
                    )
                ]

                active_sessions = [
                    s for s in target_sessions
                    if (s.get("state") if isinstance(s, Mapping) else getattr(s, "state", None)) == "ACTIVE"
                ]

                if active_sessions:
                    satisfied_conditions.append("require_active_session")
                    for s in active_sessions:
                        sid = s.get("session_id") if isinstance(s, Mapping) else getattr(s, "session_id", None)
                        if sid and sid not in relevant_fact_ids:
                            relevant_fact_ids.append(sid)
                else:
                    failed_conditions.append("require_active_session")
                    reason_codes.append(EvaluationReason.ACTIVE_SESSION_REQUIRED)
                    reasons.append(
                        f"action {action_id} requires active session on {target_id!r}, "
                        f"found {len(target_sessions)} total sessions (active=0)"
                    )

        # ---------------------------------------------------------
        # Check 8: Valid Credential Requirement
        # ---------------------------------------------------------
        if pre_require_valid_credential:
            if target_id is None or target_host is None:
                failed_conditions.append("require_valid_credential")
                reason_codes.append(EvaluationReason.NO_VALID_CREDENTIAL)
                reasons.append(f"action {action_id} requires valid credential, but target_id is None")
            else:
                param_cred_id = (proposal_parameters or {}).get("credential_id")
                valid_creds = [
                    c for c in credentials
                    if not _is_quarantined(c)
                    and (c.get("validity_state") if isinstance(c, Mapping) else getattr(c, "validity_state", None)) == "VALID"
                    and (
                        (param_cred_id and (c.get("credential_id") if isinstance(c, Mapping) else getattr(c, "credential_id", None)) == param_cred_id)
                        or (
                            not param_cred_id
                            and (c.get("observed_scope") if isinstance(c, Mapping) else getattr(c, "observed_scope", None)) in (target_id, target_host, "*", "domain")
                        )
                    )
                ]
                if valid_creds:
                    satisfied_conditions.append("require_valid_credential")
                    for c in valid_creds:
                        cid = c.get("credential_id") if isinstance(c, Mapping) else getattr(c, "credential_id", None)
                        if cid and cid not in relevant_fact_ids:
                            relevant_fact_ids.append(cid)
                else:
                    failed_conditions.append("require_valid_credential")
                    reason_codes.append(EvaluationReason.NO_VALID_CREDENTIAL)
                    reasons.append(f"action {action_id} requires valid credential matching {target_id!r}")

        # ---------------------------------------------------------
        # Check 9: Reachability Requirement
        # ---------------------------------------------------------
        if pre_require_reachability:
            if target_id is None or target_host is None:
                failed_conditions.append("require_reachability")
                reason_codes.append(EvaluationReason.REACHABILITY_NOT_OBSERVED)
                reasons.append(f"action {action_id} requires observed reachability, but target_id is None")
            else:
                param_from = (proposal_parameters or {}).get("from_host") or (proposal_parameters or {}).get("from_node_id")
                matching_edges = [
                    r for r in reachability_edges
                    if not _is_quarantined(r)
                    and (r.get("to_host") if isinstance(r, Mapping) else getattr(r, "to_host", None)) in (target_id, target_host)
                    and (param_from is None or (r.get("from_host") if isinstance(r, Mapping) else getattr(r, "from_host", None)) == param_from)
                ]
                if matching_edges:
                    satisfied_conditions.append("require_reachability")
                    for r in matching_edges:
                        if isinstance(r, Mapping):
                            for p in r.get("provenance", []):
                                if p and p not in relevant_fact_ids:
                                    relevant_fact_ids.append(p)
                elif (
                    param_from is None
                    and getattr(action, "action_class", "") not in ("LATERAL_MOVEMENT", "LATERAL_PIVOT")
                    and (
                        (visible_target_ids and (target_id in visible_target_ids or target_host in visible_target_ids))
                        or (target_host in known_hosts and not _is_quarantined(known_hosts[target_host]))
                    )
                ):
                    satisfied_conditions.append("require_reachability")
                    if target_host in known_hosts and isinstance(known_hosts[target_host], Mapping):
                        for p in known_hosts[target_host].get("provenance", []):
                            if p and p not in relevant_fact_ids:
                                relevant_fact_ids.append(p)
                else:
                    failed_conditions.append("require_reachability")
                    reason_codes.append(EvaluationReason.REACHABILITY_NOT_OBSERVED)
                    reasons.append(f"target {target_id!r} has no observed reachability edge")

        # ---------------------------------------------------------
        # Check 10: Objective Not Already Achieved
        # ---------------------------------------------------------
        if pre_objective_not_achieved:
            is_achieved = False
            if target_id is not None and target_id in objective_status:
                entry = objective_status[target_id]
                status = entry.get("status") if isinstance(entry, Mapping) else getattr(entry, "status", None)
                if status == "ACHIEVED":
                    is_achieved = True
            else:
                for oid, oval in objective_status.items():
                    status = oval.get("status") if isinstance(oval, Mapping) else getattr(oval, "status", None)
                    if status == "ACHIEVED":
                        is_achieved = True
                        break

            if is_achieved:
                failed_conditions.append("objective_not_achieved")
                reason_codes.append(EvaluationReason.OBJECTIVE_ALREADY_ACHIEVED)
                reasons.append(f"mission objective already achieved; action {action_id} not applicable")
            else:
                satisfied_conditions.append("objective_not_achieved")

        # ---------------------------------------------------------
        # Check 11: Allowed Phases
        # ---------------------------------------------------------
        if pre_allowed_phases:
            active_phase = current_phase or getattr(belief_state, "current_phase", None)
            if active_phase is None and isinstance(belief_state, Mapping):
                active_phase = belief_state.get("current_phase")

            if active_phase is not None and active_phase in pre_allowed_phases:
                satisfied_conditions.append("allowed_phases")
            else:
                failed_conditions.append("allowed_phases")
                reason_codes.append(EvaluationReason.PHASE_NOT_ALLOWED)
                reasons.append(
                    f"action {action_id} allowed in phases {pre_allowed_phases}, current phase is {active_phase!r}"
                )

        eligible = len(failed_conditions) == 0

        # Sort fact IDs deterministically
        sorted_fact_ids = tuple(sorted(set(relevant_fact_ids)))

        return EvaluationResult(
            eligible=eligible,
            action_id=action_id,
            target_id=target_id,
            satisfied_conditions=tuple(satisfied_conditions),
            failed_conditions=tuple(failed_conditions),
            reason_codes=tuple(reason_codes),
            relevant_fact_ids=sorted_fact_ids,
            reasons=tuple(reasons),
            step_cost=step_cost,
            noise_cost=noise_cost,
            action_class=action_class,
            target_kind=target_kind,
        )

    def evaluate_all(
        self,
        actions: Sequence[Any],
        targets: Sequence[str | None],
        belief_state: Any = None,
        visible_target_ids: Sequence[str] | set[str] | None = None,
        proposal_parameters: Mapping[str, Any] | None = None,
        current_phase: str | None = None,
    ) -> list[EvaluationResult]:
        """Evaluate cross-product of candidate actions and targets deterministically.

        Returns:
            List of EvaluationResults ordered deterministically by (action_id, target_id).
        """
        results: list[EvaluationResult] = []
        for action in actions:
            for target in targets:
                res = self.evaluate(
                    action=action,
                    target_id=target,
                    belief_state=belief_state,
                    visible_target_ids=visible_target_ids,
                    proposal_parameters=proposal_parameters,
                    current_phase=current_phase,
                )
                results.append(res)
        results.sort(key=lambda r: (r.action_id, r.target_id or ""))
        return results
