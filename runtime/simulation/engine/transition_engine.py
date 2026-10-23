"""Canonical Simulator Transition Engine (RT-04B).

Evaluates Red Team actions against the hidden ground truth (Hidden Scenario and
True State) to produce state transitions, operational noise accumulation,
defender detection updates, and raw observation templates.

HARD INVARIANTS:
1. Eligible != Successful:
   ActionConstraintEvaluator evaluates logic purely against planner-visible Belief State.
   TransitionEngine evaluates actual outcome against hidden ground truth.
   Due to partial observability, an action may be eligible in Belief State but fail
   in ground truth (e.g. firewall filtering, absent vulnerability, invalid credential).
2. Physical & Architectural Isolation:
   TransitionEngine belongs strictly to the simulation/evaluation domain.
   It NEVER reads, mutates, or references BeliefState, Planner internal state, or LLM prompts.
3. Functional Copy-on-Write:
   The input TrueState is NEVER mutated in place; a new TrueState instance is produced.
4. Upstream Authorization Enforcement:
   Actions must be authorized by upstream policy/safety gate before execution.
   Unauthorized actions are rejected fail-closed.
5. Determinism:
   Transitions parameterized by the same seed and action sequence produce bit-for-bit
   identical TrueState mutations and replay traces.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import random
from typing import Any, Mapping, Sequence

from actions.catalog.action_registry import are_actions_equivalent
from runtime.simulation.models.scenario import (
    ACCESS_LEVELS,
    DETECTION_STATES,
    HiddenScenario,
    ObservationTemplate,
    ScenarioTransition,
    StateMutations,
    TransitionOutcome,
)
from runtime.simulation.models.true_state import (
    CredentialTruth,
    DefenderState,
    NodeTrueState,
    ObjectiveTruth,
    ReachabilityEdge,
    SimulatedSession,
    SimulatorActionRecord,
    TrueState,
)

ACCESS_RANK: dict[str, int] = {
    "NONE": 0,
    "FOOTHOLD": 1,
    "USER": 2,
    "PRIVILEGED": 3,
    "SYSTEM": 4,
}

DETECTION_RANK: dict[str, int] = {
    "QUIET": 0,
    "MONITORING": 1,
    "ALERTED": 2,
    "CONTAINED": 3,
}


def _now_utc() -> str:
    """Return ISO 8601 UTC timestamp."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class TransitionResult:
    """Typed result of a single simulator transition execution."""

    transition_id: str | None
    action_id: str
    target_id: str | None
    success: bool
    new_true_state: TrueState
    raw_observations: tuple[dict[str, Any], ...]
    noise_delta: float
    reason: str = ""
    timestamp_utc: str = ""

    def __bool__(self) -> bool:
        return self.success

    def to_dict(self) -> dict[str, Any]:
        """Serialize transition metadata (without leaking new_true_state to planner)."""
        return {
            "transition_id": self.transition_id,
            "action_id": self.action_id,
            "target_id": self.target_id,
            "success": self.success,
            "noise_delta": float(self.noise_delta),
            "reason": self.reason,
            "timestamp_utc": self.timestamp_utc,
            "raw_observations": list(self.raw_observations),
        }


class TransitionEngine:
    """Evaluates Red Team actions against hidden ground truth to compute state transitions.

    Operates purely inside runtime/simulation and evaluation environments.
    """

    def transition(
        self,
        true_state: TrueState,
        scenario: HiddenScenario,
        action: str | Any,
        target: str | None = None,
        rng: random.Random | int | None = None,
        *,
        from_node_id: str | None = None,
        credential_id: str | None = None,
        authorized: bool = True,
        authorization_token: str | None = None,
        step: int | None = None,
        timestamp_utc: str | None = None,
    ) -> TransitionResult:
        """Execute a state transition for the given authorized action and target.

        Args:
            true_state: Current ground truth state (will NOT be mutated).
            scenario: Hidden ground truth scenario.
            action: Action ID string or action object with `action_id` attribute.
            target: Target node ID (e.g. "lab-dmz-entry") or None for target-neutral actions.
            rng: Random generator or integer seed for deterministic outcome sampling.
            from_node_id: Optional source pivot node ID for lateral movements.
            credential_id: Optional credential ID used for authentication.
            authorized: Whether this action has been authorized by upstream safety gate.
            authorization_token: Optional approval token string.
            step: Explicit step counter override (defaults to true_state.current_step + 1).
            timestamp_utc: Explicit timestamp string override.

        Returns:
            TransitionResult containing success flag, updated TrueState, noise delta, and raw observations.
        """
        now_ts = timestamp_utc or _now_utc()
        target_id = str(target) if target is not None else getattr(action, "target_id", None)
        action_id = getattr(action, "action_id", action)
        if not isinstance(action_id, str):
            action_id = str(action_id)

        # 1. Enforcement of upstream authorization invariant
        if not authorized:
            return TransitionResult(
                transition_id=None,
                action_id=action_id,
                target_id=target_id,
                success=False,
                new_true_state=true_state,
                raw_observations=(),
                noise_delta=0.0,
                reason="UNAUTHORIZED: Action dispatch rejected by Safety Gate authorization check",
                timestamp_utc=now_ts,
            )

        # 2. Initialize deterministic RNG
        if isinstance(rng, random.Random):
            r = rng
        elif isinstance(rng, int):
            r = random.Random(rng)
        else:
            r = random.Random(true_state.random_seed + true_state.current_step + 1)

        new_step = (true_state.current_step + 1) if step is None else step

        # 3. Resolve candidate transition from scenario
        matched_transition = self._find_matching_transition(
            scenario=scenario,
            true_state=true_state,
            action_id=action_id,
            target_id=target_id,
            from_node_id=from_node_id,
            credential_id=credential_id,
        )

        if matched_transition is None:
            # No transition matched in the scenario definition
            noise_delta = 1.0
            new_state = self._apply_mutations(
                old_state=true_state,
                scenario=scenario,
                transition=None,
                outcome=None,
                is_success=False,
                target_id=target_id,
                new_step=new_step,
                noise_delta=noise_delta,
                timestamp_utc=now_ts,
                action_id=action_id,
            )
            return TransitionResult(
                transition_id=None,
                action_id=action_id,
                target_id=target_id,
                success=False,
                new_true_state=new_state,
                raw_observations=(),
                noise_delta=noise_delta,
                reason=f"NO_MATCHING_TRANSITION: Action '{action_id}' has no matching transition for target '{target_id}'",
                timestamp_utc=now_ts,
            )

        # 4. Evaluate ground truth preconditions (Partial Observability / Fog-of-War)
        gt_eligible, gt_reason = self._evaluate_ground_truth_conditions(
            transition=matched_transition,
            scenario=scenario,
            true_state=true_state,
            target_id=target_id,
            from_node_id=from_node_id,
            credential_id=credential_id,
        )

        # 5. Determine success / failure based on ground truth and stochastic probability
        if not gt_eligible:
            is_success = False
            outcome = matched_transition.failure_outcome
            reason = f"GROUND_TRUTH_CONDITION_FAILED: {gt_reason}"
        elif matched_transition.success_probability >= 1.0:
            is_success = True
            outcome = matched_transition.success_outcome
            reason = "TRANSITION_SUCCESS"
        elif matched_transition.success_probability <= 0.0:
            is_success = False
            outcome = matched_transition.failure_outcome
            reason = "DETERMINISTIC_TRANSITION_FAILURE"
        else:
            roll = r.random()
            if roll <= matched_transition.success_probability:
                is_success = True
                outcome = matched_transition.success_outcome
                reason = f"STOCHASTIC_SUCCESS (roll={roll:.4f} <= prob={matched_transition.success_probability:.4f})"
            else:
                is_success = False
                outcome = matched_transition.failure_outcome
                reason = f"STOCHASTIC_FAILURE (roll={roll:.4f} > prob={matched_transition.success_probability:.4f})"

        # 6. Compute noise delta
        noise_delta = matched_transition.noise_delta

        # 7. Apply mutations using functional copy-on-write
        new_true_state = self._apply_mutations(
            old_state=true_state,
            scenario=scenario,
            transition=matched_transition,
            outcome=outcome,
            is_success=is_success,
            target_id=target_id,
            new_step=new_step,
            noise_delta=noise_delta,
            timestamp_utc=now_ts,
            action_id=action_id,
        )

        # 8. Sample raw observations from outcome templates
        sampled_observations = self._sample_raw_observations(
            outcome=outcome,
            is_success=is_success,
            target_id=target_id,
            step=new_step,
            rng=r,
        )

        return TransitionResult(
            transition_id=matched_transition.transition_id,
            action_id=action_id,
            target_id=target_id,
            success=is_success,
            new_true_state=new_true_state,
            raw_observations=sampled_observations,
            noise_delta=noise_delta,
            reason=reason,
            timestamp_utc=now_ts,
        )

    def _find_matching_transition(
        self,
        scenario: HiddenScenario,
        true_state: TrueState,
        action_id: str,
        target_id: str | None,
        from_node_id: str | None,
        credential_id: str | None,
    ) -> ScenarioTransition | None:
        """Find the most specific transition definition matching action and target."""
        candidates: list[ScenarioTransition] = []
        for t in scenario.transitions:
            if t.action_id != action_id and not are_actions_equivalent(t.action_id, action_id):
                continue

            cond = t.match_conditions
            # Target check
            req_target = cond.get("target_node_id")
            if req_target is not None and req_target != target_id:
                continue
            if req_target is None and target_id is not None and "target_node_id" in cond:
                continue

            # Pivot from_node check
            req_from = cond.get("from_node_id")
            if req_from is not None:
                if from_node_id is not None and from_node_id != req_from:
                    continue
                if from_node_id is None:
                    # If from_node_id wasn't explicitly supplied, check if caller has an active session on req_from
                    if not true_state.has_active_session(req_from):
                        continue

            # Credential check
            req_cred = cond.get("require_credential")
            if req_cred is not None:
                if credential_id is not None and credential_id != req_cred:
                    continue

            candidates.append(t)

        if not candidates:
            return None

        # Return the most specific matching transition
        # Preference: exact action_id > equivalent action; then target + from_node match > generic
        def specificity(t: ScenarioTransition) -> int:
            score = 0
            if t.action_id == action_id:
                score += 20
            elif are_actions_equivalent(t.action_id, action_id):
                score += 10
            if t.match_conditions.get("target_node_id") is not None:
                score += 10
            if t.match_conditions.get("from_node_id") is not None:
                score += 5
            if t.match_conditions.get("require_credential") is not None:
                score += 3
            if t.match_conditions.get("require_vulnerability") is not None:
                score += 2
            return score

        candidates.sort(key=specificity, reverse=True)
        return candidates[0]

    def _evaluate_ground_truth_conditions(
        self,
        transition: ScenarioTransition,
        scenario: HiddenScenario,
        true_state: TrueState,
        target_id: str | None,
        from_node_id: str | None,
        credential_id: str | None,
    ) -> tuple[bool, str]:
        """Verify ground truth environment conditions required by the transition."""
        cond = transition.match_conditions

        # 1. Target node existence check (if target specified)
        target_node = scenario.get_node(target_id) if target_id else None
        if target_id is not None and target_node is None:
            return False, f"Target node '{target_id}' does not exist in scenario topology"

        # 2. Active session requirement
        if cond.get("require_active_session"):
            # Check source node if lateral movement, else target node
            session_check_node = cond.get("from_node_id") or from_node_id or target_id
            if not session_check_node or not true_state.has_active_session(session_check_node):
                return False, f"Active session required on node '{session_check_node}' in ground truth"

        # 3. Reachability requirement
        if cond.get("require_reachability"):
            source_node = cond.get("from_node_id") or from_node_id
            if source_node and target_id:
                # Must have an unblocked reachability edge from source to target
                unblocked = False
                for edge in true_state.reachability_truth:
                    if edge.source == source_node and edge.target == target_id and not edge.is_blocked:
                        unblocked = True
                        break
                if not unblocked:
                    return False, f"No unblocked reachability path from '{source_node}' to '{target_id}' in ground truth"

        # 4. Vulnerability requirement
        req_vuln = cond.get("require_vulnerability")
        if req_vuln and target_node:
            has_vuln = any(v.vulnerability_id == req_vuln for v in target_node.vulnerabilities)
            if not has_vuln:
                return False, f"Required vulnerability '{req_vuln}' is not present on target '{target_id}'"

        # 5. Credential requirement
        req_cred = cond.get("require_credential") or credential_id
        if req_cred:
            cred_truth = true_state.credentials_truth.get(req_cred)
            if cred_truth is None or cred_truth.validity_state not in ("VALID", "HONEY_TOKEN"):
                return False, f"Required credential '{req_cred}' is invalid, revoked, or non-existent in ground truth"
            # Verify credential is valid for target node
            scenario_cred = next((c for c in scenario.hidden_credentials if c.credential_id == req_cred), None)
            if scenario_cred and target_id and target_id not in scenario_cred.valid_nodes:
                return False, f"Credential '{req_cred}' is not authorized for target '{target_id}' in ground truth"

        # 6. Minimum required access level
        req_access = cond.get("required_access_level")
        if req_access:
            access_check_node = cond.get("from_node_id") or from_node_id or target_id
            if access_check_node:
                current_level = true_state.get_node_access_level(access_check_node)
                if ACCESS_RANK.get(current_level, 0) < ACCESS_RANK.get(req_access, 0):
                    return False, f"Node '{access_check_node}' access level '{current_level}' is below required '{req_access}'"

        return True, "ALL_CONDITIONS_SATISFIED"

    def _apply_mutations(
        self,
        old_state: TrueState,
        scenario: HiddenScenario,
        transition: ScenarioTransition | None,
        outcome: TransitionOutcome | None,
        is_success: bool,
        target_id: str | None,
        new_step: int,
        noise_delta: float,
        timestamp_utc: str,
        action_id: str,
    ) -> TrueState:
        """Construct a new TrueState applying outcome mutations (Copy-on-Write)."""
        mutations = outcome.mutations if outcome else StateMutations()

        # 1. Copy and mutate node states
        new_node_states: dict[str, NodeTrueState] = dict(old_state.node_states)
        new_active_sessions: dict[str, SimulatedSession] = dict(old_state.active_sessions)

        if is_success and target_id and target_id in new_node_states:
            old_node = new_node_states[target_id]
            grant_lvl = mutations.grant_access_level

            if grant_lvl:
                highest_lvl = (
                    grant_lvl
                    if ACCESS_RANK.get(grant_lvl, 0) > ACCESS_RANK.get(old_node.access_level, 0)
                    else old_node.access_level
                )
                is_comp = ACCESS_RANK.get(highest_lvl, 0) > 0
                is_foothold = ACCESS_RANK.get(highest_lvl, 0) >= 1
            else:
                highest_lvl = old_node.access_level
                is_comp = old_node.compromised
                is_foothold = old_node.foothold_established

            active_sess_ids = list(old_node.active_session_ids)

            # Session creation
            if mutations.create_session:
                sess_id = f"sess-{target_id}-{new_step}"
                new_session = SimulatedSession(
                    session_id=sess_id,
                    node_id=target_id,
                    access_level=highest_lvl,
                    established_at_step=new_step,
                    session_state="ACTIVE",
                )
                new_active_sessions[sess_id] = new_session
                if sess_id not in active_sess_ids:
                    active_sess_ids.append(sess_id)

            # Session closure
            if mutations.close_session:
                for sid in list(active_sess_ids):
                    if sid in new_active_sessions:
                        old_s = new_active_sessions[sid]
                        new_active_sessions[sid] = SimulatedSession(
                            session_id=old_s.session_id,
                            node_id=old_s.node_id,
                            access_level=old_s.access_level,
                            established_at_step=old_s.established_at_step,
                            session_state="CLOSED",
                        )
                active_sess_ids = [
                    sid for sid in active_sess_ids if new_active_sessions[sid].session_state == "ACTIVE"
                ]

            new_node_states[target_id] = NodeTrueState(
                node_id=old_node.node_id,
                access_level=highest_lvl,
                compromised=is_comp,
                foothold_established=is_foothold,
                active_session_ids=tuple(active_sess_ids),
            )

        # 2. Copy and mutate credentials truth
        new_credentials_truth: dict[str, CredentialTruth] = dict(old_state.credentials_truth)
        if is_success and mutations.reveal_credentials:
            for cred_id in mutations.reveal_credentials:
                if cred_id in new_credentials_truth:
                    c = new_credentials_truth[cred_id]
                    new_credentials_truth[cred_id] = CredentialTruth(
                        credential_id=c.credential_id,
                        principal=c.principal,
                        validity_state=c.validity_state,
                        discovered=True,
                        used_count=c.used_count,
                    )

        # 3. Copy and mutate reachability truth
        new_reachability_truth: list[ReachabilityEdge] = list(old_state.reachability_truth)
        if mutations.block_edges:
            blocked_map = {(e["source"], e["target"]) for e in mutations.block_edges}
            updated_reachability: list[ReachabilityEdge] = []
            for edge in new_reachability_truth:
                if (edge.source, edge.target) in blocked_map:
                    updated_reachability.append(
                        ReachabilityEdge(
                            source=edge.source,
                            target=edge.target,
                            protocol=edge.protocol,
                            port=edge.port,
                            is_blocked=True,
                        )
                    )
                else:
                    updated_reachability.append(edge)
            new_reachability_truth = updated_reachability

        # 4. Copy and mutate objective truth
        if is_success and mutations.set_objective_achieved:
            new_objective_truth = ObjectiveTruth(
                objective_id=old_state.objective_truth.objective_id,
                target_node_id=old_state.objective_truth.target_node_id,
                is_achieved=True,
                achieved_at_step=new_step,
            )
        else:
            new_objective_truth = old_state.objective_truth

        # 5. Compute defender state & noise accumulation
        new_accum_noise = round(old_state.defender_state.accumulated_noise + noise_delta, 4)
        det_model = scenario.detection_model

        if det_model.containment_threshold > 0.0 and new_accum_noise >= det_model.containment_threshold:
            new_det_state = "CONTAINED"
        elif new_accum_noise >= det_model.alert_threshold:
            new_det_state = "ALERTED"
        elif new_accum_noise >= det_model.noise_threshold:
            new_det_state = "MONITORING"
        else:
            new_det_state = "QUIET"

        # Detection state monotonicity (does not downgrade below current alert level)
        if DETECTION_RANK.get(old_state.defender_state.detection_state, 0) > DETECTION_RANK.get(new_det_state, 0):
            new_det_state = old_state.defender_state.detection_state

        alerts_triggered = old_state.defender_state.alerts_triggered
        if (
            new_det_state in ("ALERTED", "CONTAINED")
            and old_state.defender_state.detection_state not in ("ALERTED", "CONTAINED")
        ):
            alerts_triggered += 1

        new_defender_state = DefenderState(
            accumulated_noise=new_accum_noise,
            detection_state=new_det_state,
            alerts_triggered=alerts_triggered,
            contained_nodes=old_state.defender_state.contained_nodes,
        )

        # 6. Append action record
        new_history = list(old_state.action_history)
        new_history.append(
            SimulatorActionRecord(
                step=new_step,
                action_id=action_id,
                target_node_id=target_id,
                success=is_success,
                noise_delta=noise_delta,
                timestamp_utc=timestamp_utc,
            )
        )

        return TrueState(
            scenario_id=old_state.scenario_id,
            run_id=old_state.run_id,
            current_step=new_step,
            random_seed=old_state.random_seed,
            node_states=new_node_states,
            active_sessions=new_active_sessions,
            credentials_truth=new_credentials_truth,
            reachability_truth=tuple(new_reachability_truth),
            objective_truth=new_objective_truth,
            defender_state=new_defender_state,
            action_history=tuple(new_history),
        )

    def _sample_raw_observations(
        self,
        outcome: TransitionOutcome,
        is_success: bool,
        target_id: str | None,
        step: int,
        rng: random.Random,
    ) -> tuple[dict[str, Any], ...]:
        """Instantiate raw observation dictionaries from transition outcome templates."""
        raw_list: list[dict[str, Any]] = []
        for template in outcome.observations:
            emit_match = (
                template.emit_on == "ALWAYS"
                or (template.emit_on == "SUCCESS" and is_success)
                or (template.emit_on == "FAILURE" and not is_success)
            )
            if not emit_match:
                continue

            # Stochastic sampling per observation probability
            if template.probability < 1.0:
                if rng.random() > template.probability:
                    continue

            # Format subject template with target/step if placeholders present
            subject = template.subject_template
            if target_id and "{target}" in subject:
                subject = subject.replace("{target}", target_id)
            if "{step}" in subject:
                subject = subject.replace("{step}", str(step))

            # Deep copy value template
            value = copy.deepcopy(template.value_template)

            raw_list.append(
                {
                    "fact_type": template.fact_type,
                    "subject": subject,
                    "value": value,
                    "confidence": template.confidence,
                    "source_kind": template.source_kind or "SIMULATED",
                }
            )

        return tuple(raw_list)
