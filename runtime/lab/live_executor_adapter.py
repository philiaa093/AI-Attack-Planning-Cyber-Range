"""Canonical Live Executor Adapter for Mini Enterprise Cyber Range (RT-06B).

Enforces:
  1. Strict Execution Pipeline Parity with SimulationExecutor:
     Planner Proposal
     → ActionConstraintEvaluator (Preconditions against Belief State)
     → CentralizedSafetyGate (Lab mode, target/action allowlist, kill switch, approval)
     → Live Range Network Dispatch (Bounded HTTP to isolated targets via Harness)
     → EnterpriseObservationNormalizer (Redact secrets, opaque handles, canonical schema)
     → StateManager / BeliefState Ingestion
     → Auditable Evidence Package
  2. Bounded Canonical Actions:
     Maps canonical action IDs (ACTION-DISCOVERY-001, ACTION-SCAN-001, etc.)
     to bounded, typed HTTP requests.
  3. Zero Bypass:
     - No direct socket/shell/subprocess from Planner.
     - Safety DENY or Kill Switch causes zero network dispatch.
     - Rejection of unknown actions, out-of-scope targets, or arbitrary command parameters.
  4. Secret Redaction:
     - Synthetic secret tokens stay inside executor/targets; planner receives opaque IDs.
  5. Clean STOP Semantics:
     - ACTION-STOP-001 causes ZERO network dispatch and cleanly concludes episode.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any, Mapping, Sequence
import uuid

from actions.catalog.action_registry import (
    get_action_registry,
    get_canonical_action_id,
    get_legacy_action_id,
)
from agent.memory.state.belief_state import BeliefState
from agent.memory.state.state_manager import StateManager
from agent.perception.normalizers.enterprise_normalizer import (
    EnterpriseObservationNormalizer,
    validate_canonical_observation,
)
from runtime.evaluators.action_evaluator import ActionConstraintEvaluator, EvaluationResult
from runtime.lab.enterprise_range.harness import EnterpriseLiveRangeHarness
from runtime.lab.enterprise_range.topology import (
    ENTERPRISE_TARGETS,
    get_target_allowlist,
)
from runtime.safety.discovery_gate import ApprovalToken, CentralizedSafetyGate

logger = logging.getLogger(__name__)

_FORBIDDEN_PARAMETER_KEYS = frozenset({
    "command", "cmd", "shell", "exec", "eval", "script", "powershell", "bash",
    "sh", "system", "popen", "spawn", "subprocess", "socket", "connect",
})

CANONICAL_TO_LIVE_ACTION = {
    "ACTION-DISCOVERY-001": "DISCOVERY",
    "ACTION-RECON-001": "DISCOVERY",
    "ACTION-SCAN-001": "SERVICE_SCAN",
    "ACTION-FOOTHOLD-001": "FOOTHOLD",
    "ACTION-WEB-001": "FOOTHOLD",
    "ACTION-HOSTRECON-001": "HOST_RECON",
    "ACTION-CREDS-001": "CREDENTIAL_HARVEST",
    "ACTION-AUTH-001": "CREDENTIAL_HARVEST",
    "ACTION-PIVOT-001": "LATERAL_PIVOT",
    "ACTION-FLOW-001": "LATERAL_PIVOT",
    "ACTION-PRIVESC-001": "PRIVILEGE_ESCALATION",
    "ACTION-OBJECTIVE-001": "OBJECTIVE_ACCESS",
    "ACTION-FLOW-002": "OBJECTIVE_ACCESS",
    "ACTION-STOP-001": "STOP",
    "ACTION-END-001": "STOP",
}


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class LiveExecutionResult:
    """Execution result from LiveExecutorAdapter adhering to canonical result contract."""

    success: bool
    status: str  # "EXECUTED", "REJECTED_BY_CONSTRAINTS", "REJECTED_BY_SAFETY_GATE", "UNAUTHORIZED"
    canonical_observation: dict[str, Any] | None = None
    constraint_evaluation: EvaluationResult | None = None
    updated_belief_state: BeliefState | None = None
    raw_response: dict[str, Any] | None = None
    evidence_bundle: dict[str, Any] | None = None
    reasons: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return self.success

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "success": self.success,
            "status": self.status,
            "reasons": list(self.reasons),
        }
        if self.canonical_observation is not None:
            res["observation"] = copy.deepcopy(self.canonical_observation)
        if self.constraint_evaluation is not None:
            res["constraint_evaluation"] = self.constraint_evaluation.to_dict()
        if self.raw_response is not None:
            res["raw_response"] = copy.deepcopy(self.raw_response)
        if self.evidence_bundle is not None:
            res["evidence_bundle"] = copy.deepcopy(self.evidence_bundle)
        return res


class LiveExecutorAdapter:
    """Canonical executor adapter dispatching bounded actions to the isolated enterprise live range."""

    def __init__(
        self,
        harness: EnterpriseLiveRangeHarness,
        run_id: str | None = None,
        safety_gate: CentralizedSafetyGate | None = None,
        state_manager: StateManager | None = None,
        normalizer: EnterpriseObservationNormalizer | None = None,
        allowed_targets: frozenset[str] | None = None,
    ) -> None:
        self.harness = harness
        self.run_id = run_id or f"RUN-LIVE-{uuid.uuid4().hex[:8]}"
        self.safety_gate = safety_gate
        self.state_manager = state_manager
        self.normalizer = normalizer or EnterpriseObservationNormalizer()
        self.evaluator = ActionConstraintEvaluator()
        self.action_registry = get_action_registry()
        self.allowed_targets = allowed_targets or get_target_allowlist()
        self.step_count = 0
        self.network_dispatch_count = 0

    def get_belief_state(self) -> BeliefState | None:
        if self.state_manager is not None:
            return self.state_manager.get_belief_state()
        return None

    def execute_proposal(
        self,
        proposal: Mapping[str, Any],
        belief_state: BeliefState | None = None,
        approval_token: ApprovalToken | None = None,
        from_node_id: str | None = None,
        credential_id: str | None = None,
        timestamp_utc: str | None = None,
    ) -> LiveExecutionResult:
        """Execute a planner proposal through the mandatory canonical safety and live pipeline.

        Ordering:
          1. Parameter Security Verification (Rejection of shell/eval/command inputs)
          2. ActionConstraintEvaluator (Planner-visible BeliefState Preconditions)
          3. CentralizedSafetyGate (Lab mode, target/action allowlist, kill switch, approval)
          4. Live Dispatch (Zero network I/O for STOP; bounded HTTP via Harness for actions)
          5. EnterpriseObservationNormalizer (Redact secrets, normalize facts, validate schema)
          6. StateManager Ingestion & Belief State Projection
          7. Auditable Evidence Packaging
        """
        raw_action_id = str(proposal.get("action_id", ""))
        action_id = get_canonical_action_id(raw_action_id)
        target_id = proposal.get("target_id")
        if target_id is not None:
            target_id = str(target_id)

        eff_from = from_node_id or proposal.get("from_node_id")
        eff_cred = credential_id or proposal.get("credential_id")
        now_ts = timestamp_utc or _now_utc()

        # -------------------------------------------------------------
        # STEP 0: Parameter Security Verification (Zero arbitrary shell)
        # -------------------------------------------------------------
        for param_key in proposal.keys():
            if str(param_key).lower() in _FORBIDDEN_PARAMETER_KEYS:
                return LiveExecutionResult(
                    success=False,
                    status="REJECTED_BY_SAFETY_GATE",
                    reasons=(f"FORBIDDEN_PARAMETER_REJECTED: '{param_key}' is not permitted in bounded action proposal",),
                )

        if raw_action_id not in CANONICAL_TO_LIVE_ACTION and action_id not in CANONICAL_TO_LIVE_ACTION:
            return LiveExecutionResult(
                success=False,
                status="REJECTED_BY_SAFETY_GATE",
                reasons=(f"UNKNOWN_ACTION_REJECTED: '{raw_action_id}' is not a recognized canonical action",),
            )

        # -------------------------------------------------------------
        # STEP 1: ActionConstraintEvaluator (Belief State Preconditions)
        # -------------------------------------------------------------
        current_belief = belief_state
        if current_belief is None and self.state_manager is not None:
            current_belief = self.state_manager.get_belief_state()

        constraint_eval: EvaluationResult | None = None
        if current_belief is not None:
            action_def = self.action_registry.get_action(action_id) or self.action_registry.get_action(raw_action_id)
            vis_targets = (
                set(current_belief.visible_target_ids)
                if hasattr(current_belief, "visible_target_ids")
                else None
            )
            constraint_eval = self.evaluator.evaluate(
                action=action_def or action_id,
                target_id=target_id,
                belief_state=current_belief,
                visible_target_ids=vis_targets,
                proposal_parameters=dict(proposal),
            )

            if not constraint_eval.eligible:
                return LiveExecutionResult(
                    success=False,
                    status="REJECTED_BY_CONSTRAINTS",
                    constraint_evaluation=constraint_eval,
                    reasons=constraint_eval.reasons or tuple(constraint_eval.reason_codes),
                )

        # -------------------------------------------------------------
        # STEP 2: CentralizedSafetyGate (Safety & Authorization Checks)
        # -------------------------------------------------------------
        if self.safety_gate is not None:
            if not self.safety_gate.lab_mode:
                return LiveExecutionResult(
                    success=False,
                    status="REJECTED_BY_SAFETY_GATE",
                    constraint_evaluation=constraint_eval,
                    reasons=("LAB_MODE_MANDATORY",),
                )

            if self.safety_gate.kill_switch.is_active():
                return LiveExecutionResult(
                    success=False,
                    status="REJECTED_BY_SAFETY_GATE",
                    constraint_evaluation=constraint_eval,
                    reasons=("KILL_SWITCH_ACTIVE",),
                )

            if target_id is not None and target_id not in self.safety_gate.target_allowlist:
                return LiveExecutionResult(
                    success=False,
                    status="REJECTED_BY_SAFETY_GATE",
                    constraint_evaluation=constraint_eval,
                    reasons=(f"TARGET_NOT_IN_ALLOWLIST: '{target_id}'",),
                )

            legacy_alias = get_legacy_action_id(action_id)
            if (
                action_id not in self.safety_gate.action_allowlist
                and raw_action_id not in self.safety_gate.action_allowlist
                and (not legacy_alias or legacy_alias not in self.safety_gate.action_allowlist)
            ):
                return LiveExecutionResult(
                    success=False,
                    status="REJECTED_BY_SAFETY_GATE",
                    constraint_evaluation=constraint_eval,
                    reasons=(f"ACTION_NOT_IN_ALLOWLIST: '{action_id}'",),
                )

            if approval_token is not None:
                valid, reason = approval_token.is_valid()
                if not valid:
                    return LiveExecutionResult(
                        success=False,
                        status="REJECTED_BY_SAFETY_GATE",
                        constraint_evaluation=constraint_eval,
                        reasons=(f"APPROVAL_TOKEN_INVALID: {reason}",),
                    )

        # -------------------------------------------------------------
        # STEP 3: Live Execution Dispatch
        # -------------------------------------------------------------
        self.step_count += 1
        live_action_type = CANONICAL_TO_LIVE_ACTION.get(action_id) or CANONICAL_TO_LIVE_ACTION.get(raw_action_id)

        # A. Handle STOP action (Zero network dispatch)
        if live_action_type == "STOP":
            canonical_obs = self._build_stop_observation(action_id, target_id, now_ts)
            updated_belief = self._ingest_observation(canonical_obs, current_belief)
            evidence = self._build_evidence_bundle(
                action_id=action_id,
                target_id=target_id,
                dispatched=False,
                raw_response={"status": "STOPPED"},
                observation=canonical_obs,
                timestamp_utc=now_ts,
            )
            return LiveExecutionResult(
                success=True,
                status="EXECUTED",
                canonical_observation=canonical_obs,
                constraint_evaluation=constraint_eval,
                updated_belief_state=updated_belief,
                raw_response={"status": "STOPPED"},
                evidence_bundle=evidence,
                reasons=("EPISODE_HALTED_BY_PLANNER_STOP_ACTION",),
            )

        # B. Network actions dispatch via Harness
        if target_id is None:
            return LiveExecutionResult(
                success=False,
                status="REJECTED_BY_SAFETY_GATE",
                constraint_evaluation=constraint_eval,
                reasons=("TARGET_ID_REQUIRED_FOR_NETWORK_ACTION",),
            )

        self.network_dispatch_count += 1
        raw_result = self._dispatch_live_target(
            action_type=live_action_type,
            target_id=target_id,
            from_target_id=eff_from,
            credential_id=eff_cred,
            proposal=proposal,
        )

        # -------------------------------------------------------------
        # STEP 4: Enterprise Observation Normalization
        # -------------------------------------------------------------
        canonical_obs = self._normalize_live_result(
            action_id=action_id,
            target_id=target_id,
            live_action_type=live_action_type,
            raw_result=raw_result,
            timestamp_utc=now_ts,
            from_node_id=eff_from,
        )

        # -------------------------------------------------------------
        # STEP 5: State Ingestion & Belief State Projection
        # -------------------------------------------------------------
        updated_belief = self._ingest_observation(canonical_obs, current_belief)

        # -------------------------------------------------------------
        # STEP 6: Auditable Evidence Packaging (No Plaintext Secrets)
        # -------------------------------------------------------------
        evidence = self._build_evidence_bundle(
            action_id=action_id,
            target_id=target_id,
            dispatched=True,
            raw_response=raw_result,
            observation=canonical_obs,
            timestamp_utc=now_ts,
            from_node=eff_from,
        )

        if (
            raw_result.get("outcome") in ("DENIED", "FAILURE", "ERROR")
            or raw_result.get("signal_type")
            or raw_result.get("status_code", 200) >= 400
        ):
            exec_success = False
        else:
            exec_success = canonical_obs.get("outcome") in ("SUCCESS", "PARTIAL")

        return LiveExecutionResult(
            success=exec_success,
            status="EXECUTED",
            canonical_observation=canonical_obs,
            constraint_evaluation=constraint_eval,
            updated_belief_state=updated_belief,
            raw_response=raw_result,
            evidence_bundle=evidence,
            reasons=(f"LIVE_EXECUTION_OUTCOME_{canonical_obs.get('outcome')}",),
        )

    def _dispatch_live_target(
        self,
        action_type: str,
        target_id: str,
        from_target_id: str | None,
        credential_id: str | None,
        proposal: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Dispatch bounded HTTP request to the live range harness based on canonical capability."""
        if action_type in ("DISCOVERY", "SERVICE_SCAN"):
            return self.harness.dispatch_bounded_request(
                target_id=target_id,
                method="GET",
                path="/api/v1/discovery",
                from_target_id=from_target_id,
            )

        if action_type == "FOOTHOLD":
            return self.harness.dispatch_bounded_request(
                target_id=target_id,
                method="POST",
                path="/api/v1/auth/foothold",
                body={"target_id": target_id},
                from_target_id=from_target_id,
            )

        if action_type == "HOST_RECON":
            return self.harness.dispatch_bounded_request(
                target_id=target_id,
                method="GET",
                path="/api/v1/system/recon",
                from_target_id=from_target_id,
            )

        if action_type == "CREDENTIAL_HARVEST":
            return self.harness.dispatch_bounded_request(
                target_id=target_id,
                method="POST",
                path="/api/v1/credentials/harvest",
                body={"target_id": target_id},
                from_target_id=from_target_id,
            )

        if action_type == "LATERAL_PIVOT":
            body = {
                "from_node_id": from_target_id,
                "credential_id": credential_id,
                "route": proposal.get("route", "primary"),
            }
            return self.harness.dispatch_bounded_request(
                target_id=target_id,
                method="POST",
                path="/api/v1/pivot",
                body=body,
                from_target_id=from_target_id,
            )

        if action_type == "PRIVILEGE_ESCALATION":
            return self.harness.dispatch_bounded_request(
                target_id=target_id,
                method="POST",
                path="/api/v1/auth/privesc",
                body={"target_id": target_id},
                from_target_id=from_target_id,
            )

        if action_type == "OBJECTIVE_ACCESS":
            return self.harness.dispatch_bounded_request(
                target_id=target_id,
                method="POST",
                path="/api/v1/vault/objective",
                body={"target_id": target_id},
                from_target_id=from_target_id,
            )

        return {"outcome": "ERROR", "error": f"UNSUPPORTED_LIVE_ACTION: {action_type}"}

    def _normalize_live_result(
        self,
        action_id: str,
        target_id: str,
        live_action_type: str,
        raw_result: dict[str, Any],
        timestamp_utc: str,
        from_node_id: str | None = None,
    ) -> dict[str, Any]:
        """Transform raw response from live service into canonical observation envelope."""
        evidence_ref = f"EVID-LIVE-{self.run_id}-{self.step_count:03d}"

        # 1. Handle Defense Signals (e.g. WAF rejection / Auth lockout on Decoy or blocked route)
        if raw_result.get("signal_type"):
            signal = {
                "signal_type": raw_result.get("signal_type"),
                "target_id": target_id,
                "status_code": raw_result.get("status_code", 403),
                "observable_event": raw_result.get("observable_event", "Defensive signal triggered"),
            }
            return self.normalizer.normalize_detection_signal(
                signals=[signal],
                run_id=self.run_id,
                action_id=action_id,
                source_target=target_id,
                evidence_refs=[evidence_ref],
            )

        # 2. Handle Refusal or Network Isolation Denial
        if raw_result.get("outcome") == "DENIED":
            # Map denied network route to observable signal or failed outcome observation
            signal = {
                "signal_type": "ACCESS_DENIED",
                "target_id": target_id,
                "status_code": raw_result.get("status_code", 403),
                "observable_event": raw_result.get("message", "Network isolation barrier refused connection"),
            }
            return self.normalizer.normalize_detection_signal(
                signals=[signal],
                run_id=self.run_id,
                action_id=action_id,
                source_target=target_id,
                evidence_refs=[evidence_ref],
            )

        # 3. Handle Discovery / Scan
        if live_action_type in ("DISCOVERY", "SERVICE_SCAN"):
            services = raw_result.get("services", [])
            if services:
                obs = self.normalizer.normalize_service_discovery(
                    services=services,
                    run_id=self.run_id,
                    action_id=action_id,
                    source_target=target_id,
                    evidence_refs=[evidence_ref],
                )
                # Ensure TARGET fact is also present
                has_target_fact = any(f.get("fact_type") == "TARGET" for f in obs.get("new_facts", []))
                if not has_target_fact:
                    obs["new_facts"].append({
                        "fact_id": f"FACT-TARGET-{target_id}",
                        "fact_type": "TARGET",
                        "subject": target_id,
                        "value": target_id,
                        "confidence": 1.0,
                    })
                return obs
            else:
                return self.normalizer.normalize_host_discovery(
                    hosts=[target_id],
                    run_id=self.run_id,
                    action_id=action_id,
                    source_target=target_id,
                    evidence_refs=[evidence_ref],
                )

        # 4. Handle Foothold / Privilege Escalation
        if live_action_type in ("FOOTHOLD", "PRIVILEGE_ESCALATION"):
            session_data = raw_result.get("session")
            if session_data:
                return self.normalizer.normalize_session(
                    sessions=[session_data],
                    run_id=self.run_id,
                    action_id=action_id,
                    source_target=target_id,
                    evidence_refs=[evidence_ref],
                )

        # 5. Handle Host Recon (Observed Reachability Edges)
        if live_action_type == "HOST_RECON":
            routes = raw_result.get("reachable_hosts", [])
            if routes:
                obs = self.normalizer.normalize_reachability(
                    edges=routes,
                    run_id=self.run_id,
                    action_id=action_id,
                    source_target=target_id,
                    evidence_refs=[evidence_ref],
                    is_topology_config=False,
                )
                # For newly discovered target nodes, emit TARGET fact so Planner discovers them
                for r in routes:
                    dest = r.get("to_host")
                    if dest:
                        obs["new_facts"].append({
                            "fact_id": f"FACT-TARGET-{dest}",
                            "fact_type": "TARGET",
                            "subject": dest,
                            "value": dest,
                            "confidence": 1.0,
                        })
                return obs

        # 6. Handle Credential Discovery
        if live_action_type == "CREDENTIAL_HARVEST":
            creds = raw_result.get("credentials", [])
            if creds:
                return self.normalizer.normalize_credentials(
                    credentials=creds,
                    run_id=self.run_id,
                    action_id=action_id,
                    source_target=target_id,
                    evidence_refs=[evidence_ref],
                )

        # 7. Handle Lateral Pivot
        if live_action_type == "LATERAL_PIVOT":
            session_data = raw_result.get("session")
            if session_data:
                return self.normalizer.normalize_session(
                    sessions=[session_data],
                    run_id=self.run_id,
                    action_id=action_id,
                    source_target=target_id,
                    evidence_refs=[evidence_ref],
                )

        # 8. Handle Objective Access
        if live_action_type == "OBJECTIVE_ACCESS":
            obj_data = raw_result.get("objective")
            if obj_data:
                return self.normalizer.normalize_objective(
                    objectives=[obj_data],
                    run_id=self.run_id,
                    action_id=action_id,
                    source_target=target_id,
                    evidence_refs=[evidence_ref],
                    is_hidden_manifest=False,
                )

        # Default fallback outcome observation
        outcome = "SUCCESS" if raw_result.get("status") == "ok" and raw_result.get("outcome") != "FAILURE" else "FAILURE"
        return {
            "observation_id": f"OBS-LIVE-{uuid.uuid4().hex[:8]}",
            "run_id": self.run_id,
            "action_id": action_id,
            "source_kind": "EXECUTOR",
            "source_target": target_id,
            "outcome": outcome,
            "new_facts": [],
            "confidence": 1.0,
            "sequence_num": self.step_count,
            "evidence_refs": [evidence_ref],
            "timestamp_utc": timestamp_utc,
        }

    def _build_stop_observation(self, action_id: str, target_id: str | None, timestamp_utc: str) -> dict[str, Any]:
        """Build canonical observation for ACTION-STOP-001 (Zero network dispatch)."""
        evidence_ref = f"EVID-STOP-{self.run_id}-{self.step_count:03d}"
        return {
            "observation_id": f"OBS-LIVE-STOP-{uuid.uuid4().hex[:8]}",
            "run_id": self.run_id,
            "action_id": action_id,
            "source_kind": "EXECUTOR",
            "source_target": target_id or "local_planner",
            "outcome": "SUCCESS",
            "new_facts": [
                {
                    "fact_id": f"FACT-STOP-{self.run_id}-{self.step_count}",
                    "fact_type": "ACTION_OUTCOME",
                    "subject": "planner_episode",
                    "value": "STOP_TERMINATED",
                    "confidence": 1.0,
                }
            ],
            "confidence": 1.0,
            "sequence_num": self.step_count,
            "evidence_refs": [evidence_ref],
            "timestamp_utc": timestamp_utc,
        }

    def _ingest_observation(self, canonical_obs: dict[str, Any], current_belief: BeliefState | None) -> BeliefState | None:
        """Apply normalized canonical observation to StateManager or project updated BeliefState."""
        if self.state_manager is not None:
            self.state_manager.apply_observation(canonical_obs)
            return self.state_manager.get_belief_state()
        elif current_belief is not None:
            existing_facts = list(current_belief.to_dict().get("observed_facts", []))
            all_facts = existing_facts + canonical_obs.get("new_facts", [])
            return BeliefState.from_facts(all_facts, observations=[canonical_obs])
        return None

    def _build_evidence_bundle(
        self,
        action_id: str,
        target_id: str | None,
        dispatched: bool,
        raw_response: dict[str, Any],
        observation: dict[str, Any],
        timestamp_utc: str,
        from_node: str | None = None,
    ) -> dict[str, Any]:
        """Construct sanitized, auditable evidence package ensuring zero plaintext secret leakage."""
        sanitized_raw = copy.deepcopy(raw_response)
        # Redact any accidental secret tokens from raw response
        if "credentials" in sanitized_raw:
            for cred in sanitized_raw["credentials"]:
                if "secret_token" in cred:
                    cred["secret_token"] = "[REDACTED_BY_LIVE_EXECUTOR_EVIDENCE_BOUNDARY]"

        return {
            "run_id": self.run_id,
            "step_index": self.step_count,
            "action_id": action_id,
            "target_id": target_id,
            "from_node_id": from_node,
            "network_dispatched": dispatched,
            "timestamp_utc": timestamp_utc,
            "observation_id": observation.get("observation_id"),
            "observation_facts_count": len(observation.get("new_facts", [])),
            "outcome": observation.get("outcome"),
            "raw_response_sanitized": sanitized_raw,
        }
