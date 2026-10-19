"""Autonomous Closed-Loop Runner for Isolated Cyber-Range AI Attack Planning.

Implements the canonical closed control loop:
  OBSERVATION
  -> STATE (StateManager / PlannerStateAdapter)
  -> AI PLANNER (ObservedStatePlanner: RULE / LLM / MOCK)
  -> PROPOSAL (plan.schema.json validated)
  -> SAFETY GATE (CentralizedSafetyGate evaluation: target, action, budget, approval, kill switch)
  -> EXECUTOR (bounded execution strictly through gate / zero direct transport)
  -> NEW OBSERVATION (normalized via ObservationNormalizer)
  -> STATE UPDATE (applied to StateManager)
  -> AI REPLAN
  -> ...
  -> STOP (bounded clean termination)

Key Safety Invariants:
  - ZERO DIRECT HTTP TRANSPORT: runner contains no http.client, urllib, socket, or requests network clients.
  - All target network I/O flows exclusively through CentralizedSafetyGate.
  - Fail-closed evidence persistence: pre-dispatch intent and post-dispatch result; halting on recorder failure.
  - No preset route assumptions, no ground-truth leak, no arbitrary shell/URL/target.
  - Mode provenance transparently preserved (RULE, LLM, LLM_MOCK, fallback reasons).
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import threading
import time
import urllib.parse
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agent.memory.state.state_manager import StateManager
from agent.perception.normalizers.observation_normalizer import ObservationNormalizer
from runtime.lab.capability_registry import (
    CapabilityRegistry,
    VerificationFinding,
    ACTION_EXECUTION_DETAILS,
)
from runtime.discovery.discovery_engine import (
    DiscoveryRunResult,
    InventoryStore,
    ObservationDrivenDiscovery,
)
from runtime.safety.discovery_gate import (
    ApprovalToken,
    CentralizedSafetyGate,
    DiscoveryRequest,
    DispatchResponse,
    load_canonical_action_allowlist,
    load_canonical_target_allowlist,
)
from runtime.evidence.discovery_recorder import (
    DurableEvidenceRecorder,
    EvidenceFailure,
    redact_secrets,
)
from runtime.planners.observed_planner import (
    ACTION_CATALOG,
    ObservedStatePlanner,
    PlannerResult,
    ProviderConfig,
)
from runtime.planners.planner_adapter import (
    PlannerStateAdapter,
)
from runtime.planners.planner_interface import project_visible_targets
from scripts.validation.validate_scaffold import ROOT
from shared.schema_validation import validate_shape


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class DecisionTrace:
    """Detailed immutable trace of a single decision iteration in the autonomous loop."""
    iteration: int
    decision_id: str
    timestamp_utc: str
    state_fingerprint: str
    planner_requested_mode: str
    planner_actual_mode: str
    proposal: dict[str, Any]
    safety_decision: str  # "APPROVED", "DENIED"
    safety_reason: str
    dispatched: bool
    intent_evidence_id: str | None
    result_evidence_id: str | None
    observation_ids: list[str]
    new_facts_count: int
    outcome: str  # "SUCCESS", "FAILURE", "DENIED", "HALT", "STOP"


@dataclass
class AutonomousRunReport:
    """Comprehensive final report of the autonomous run."""
    run_id: str
    target_id: str
    requested_planner_mode: str
    actual_planner_mode: str
    provider: str
    model: str
    decisions_count: int
    approved_actions_count: int
    denied_actions_count: int
    network_dispatch_count: int
    unsafe_dispatch_count: int
    observations_added_count: int
    stop_reason: str
    traces: list[DecisionTrace]
    final_state: dict[str, Any]
    evidence_refs: list[str]
    findings: list[dict[str, Any]] = field(default_factory=list)
    active_verifications_count: int = 0
    control_mode: str = "AUTONOMOUS"
    pause_count: int = 0
    operator_approvals_count: int = 0
    operator_rejections_count: int = 0


class AutonomousRunner:
    """Safe, closed-loop autonomous runner driving observation -> state -> plan -> gate -> execute -> replan."""

    def __init__(
        self,
        target_id: str,
        gate: CentralizedSafetyGate,
        recorder: DurableEvidenceRecorder,
        approval: ApprovalToken | None,
        run_id: str | None = None,
        objective_id: str = "OBJ-AUTONOMOUS-001",
        requested_planner_mode: str = "RULE",
        planner_fallback_allowed: bool = True,
        planner_provider_callable: Callable[[str, str], str | None] | None = None,
        max_decisions: int = 10,
        max_no_progress_cycles: int = 3,
        max_repeated_state: int = 3,
        seed_path: str = "/",
        event_hook: Callable[[dict[str, Any]], None] | None = None,
        control_mode: str = "AUTONOMOUS",
        planner_provider_config: ProviderConfig | None = None,
        external_scanners: tuple[str, ...] = (),
    ) -> None:
        self.target_id = target_id
        self.gate = gate
        self.recorder = recorder
        self.approval = approval
        self.run_id = run_id or recorder.run_id
        self.objective_id = objective_id
        self.requested_planner_mode = requested_planner_mode.upper().strip()
        self.planner_fallback_allowed = planner_fallback_allowed
        self.planner_provider_callable = planner_provider_callable
        self.max_decisions = max_decisions
        self.max_no_progress_cycles = max_no_progress_cycles
        self.max_repeated_state = max_repeated_state
        self.seed_path = seed_path
        self.event_hook = event_hook
        self.control_mode = control_mode.upper().strip()

        # Orchestration state & cooperative synchronization primitives
        self.lifecycle_state = "IDLE"
        self._pause_requested = threading.Event()
        self._is_paused = threading.Event()
        self._resume_requested = threading.Event()
        self._stop_requested = threading.Event()
        self._approval_event = threading.Event()
        self._pending_proposal: dict[str, Any] | None = None
        self._pending_provenance: dict[str, Any] | None = None
        self._pending_iteration: int | None = None
        self._pending_state_fp: str | None = None
        self._pending_approval_decision: str | None = None
        self._pending_rejection_reason: str | None = None
        self._pause_count = 0
        self._operator_approvals = 0
        self._operator_rejections = 0

        # State management
        self.state_manager = StateManager(
            run_id=self.run_id,
            scenario_id="SCN-001",
            objective_id=self.objective_id,
            budget={
                "actions": self.gate.budget_tracker.max_requests,
                "requests": self.gate.budget_tracker.max_requests,
                "seconds": getattr(self.gate.budget_tracker, "max_duration_seconds", 3600.0),
            },
        )
        self.state_adapter = PlannerStateAdapter(self.state_manager)
        self.normalizer = ObservationNormalizer()

        # Zero-knowledge invariant: planner visibility is strictly discovery-driven
        # Safety gate knows full allowlist; planner starts with entry target seed only.
        self.visible_targets: set[str] = {self.target_id} if self.target_id else set()

        # Planner
        self.planner = ObservedStatePlanner(
            target_id=self.target_id,
            objective_id=self.objective_id,
            requested_mode=self.requested_planner_mode,
            fallback_allowed=self.planner_fallback_allowed,
            visible_targets=self.visible_targets,
            provider_callable=self.planner_provider_callable,
            provider_config=planner_provider_config,
            effective_actions={action for action in self.gate.effective_actions
                               if action.startswith("ACTION-END-") or
                               (self.approval is not None and self.approval.action_id in ("*", action))},
            event_hook=self._on_planner_event,
        )

        # Inventory & Trace tracking
        self.inventory = InventoryStore()
        self.traces: list[DecisionTrace] = []
        self.evidence_refs: list[str] = []
        self.unsafe_dispatch_count = 0
        self.capability_registry = CapabilityRegistry()
        # Authenticated mutations are a separately approved fixed workflow, not planner proposals.
        self.planner.effective_actions.difference_update({"ACTION-AUTH-001", "ACTION-FLOW-001", "ACTION-FLOW-002"})
        self.scanner_executor = None
        if external_scanners:
            from runtime.lab.external_scanners import ExternalScannerExecutor
            self.scanner_executor = ExternalScannerExecutor(
                external_scanners, cancelled=self._stop_requested.is_set, event_hook=self._emit_event)
            self.capability_registry.register("ACTION-SCAN-002", self.scanner_executor)
        else:
            self.planner.effective_actions.discard("ACTION-SCAN-002")
        self.findings: list[dict[str, Any]] = []
        self.active_verifications_count = 0

        # Load schemas for validation
        self._plan_schema = json.loads(
            (ROOT / "agent" / "planner" / "contracts" / "plan.schema.json").read_text(encoding="utf-8")
        )
        self._obs_schema = json.loads(
            (ROOT / "agent" / "planner" / "contracts" / "observation.schema.json").read_text(encoding="utf-8")
        )

    def _on_planner_event(self, ev: dict[str, Any]) -> None:
        """Forward planner lifecycle events to the central event sink."""
        ev_type = ev.get("type", "")
        payload = ev.get("payload", {})
        self._emit_event(ev_type, payload=payload)

    def _ingest_and_update_visibility(self, obs: dict[str, Any]) -> bool:
        """Ingest observation into state adapter and project any newly discovered targets into planner visibility."""
        applied = self.state_adapter.ingest_observation(obs)
        if applied:
            if obs.get("source_kind") == "PLANNER_INFERENCE":
                # Invariant 10: Inferred hypotheses must never unlock target visibility
                return applied
            for fact in obs.get("new_facts", []):
                if not isinstance(fact, dict):
                    continue
                ft = fact.get("fact_type")
                val = fact.get("value")
                subj = fact.get("subject")
                target_id = fact.get("target_id")
                if ft in ("TARGET", "TARGET_DISCOVERED", "HOST"):
                    if isinstance(val, str) and val.startswith("lab-"):
                        self.visible_targets.add(val)
                    if isinstance(subj, str) and subj.startswith("lab-"):
                        self.visible_targets.add(subj)
                elif ft in ("SERVICE", "ENDPOINT"):
                    if isinstance(subj, str):
                        h = subj.split(":")[0]
                        if h.startswith("lab-"):
                            self.visible_targets.add(h)
                if isinstance(target_id, str) and target_id.startswith("lab-"):
                    self.visible_targets.add(target_id)
            self.planner.update_visible_targets(self.visible_targets)
        return applied

    def request_pause(self) -> bool:
        """Cooperatively request pause before next safe boundary."""
        if self.lifecycle_state in ("COMPLETED", "FAILED", "BLOCKED", "STOPPING"):
            return False
        self._pause_requested.set()
        self.lifecycle_state = "PAUSING"
        self._emit_event("RUN_PAUSE_REQUESTED", payload={"run_id": self.run_id})
        return True

    def request_resume(self) -> bool:
        """Resume execution from paused state."""
        if self.lifecycle_state != "PAUSED":
            return False
        if self.gate.kill_switch.is_active():
            return False
        self.lifecycle_state = "RESUMING"
        self._pause_requested.clear()
        self._resume_requested.set()
        self._emit_event("RUN_RESUME_REQUESTED", payload={"run_id": self.run_id})
        return True

    def request_stop(self, reason: str = "OPERATOR_STOP_REQUESTED") -> bool:
        """Request clean termination."""
        self._stop_requested.set()
        if self.scanner_executor is not None:
            self.gate.kill_switch.activate()
        self.lifecycle_state = "STOPPING"
        self._resume_requested.set()
        self._approval_event.set()
        return True

    def is_paused(self) -> bool:
        return self._is_paused.is_set() or self.lifecycle_state == "PAUSED"

    def approve_proposal(self, proposal_id: str) -> dict[str, Any]:
        """Operator approves pending proposal in MANUAL or ASSISTED mode."""
        if self.lifecycle_state != "WAITING_FOR_APPROVAL" or not self._pending_proposal:
            return {"success": False, "message": f"Runner not waiting for approval (state: {self.lifecycle_state})"}
        curr_plan_id = self._pending_proposal.get("plan_id")
        if curr_plan_id != proposal_id:
            return {"success": False, "message": f"Proposal ID mismatch: pending '{curr_plan_id}' != provided '{proposal_id}'"}
        if self.gate.kill_switch.is_active():
            return {"success": False, "message": "Emergency kill switch is active"}

        self._pending_approval_decision = "APPROVED"
        self._approval_event.set()
        return {"success": True, "message": "Proposal approved", "proposal_id": proposal_id}

    def reject_proposal(self, proposal_id: str, reason: str | None = None) -> dict[str, Any]:
        """Operator rejects pending proposal in MANUAL or ASSISTED mode."""
        if self.lifecycle_state != "WAITING_FOR_APPROVAL" or not self._pending_proposal:
            return {"success": False, "message": f"Runner not waiting for approval (state: {self.lifecycle_state})"}
        curr_plan_id = self._pending_proposal.get("plan_id")
        if curr_plan_id != proposal_id:
            return {"success": False, "message": f"Proposal ID mismatch: pending '{curr_plan_id}' != provided '{proposal_id}'"}

        self._pending_approval_decision = "REJECTED"
        self._pending_rejection_reason = reason or "OPERATOR_REJECTED"
        self._approval_event.set()
        return {"success": True, "message": "Proposal rejected", "proposal_id": proposal_id}

    def get_pending_proposal(self) -> dict[str, Any] | None:
        if self.lifecycle_state == "WAITING_FOR_APPROVAL" and self._pending_proposal:
            return dict(self._pending_proposal)
        return None

    def _requires_operator_approval(self, proposal: dict[str, Any]) -> bool:
        action_id = proposal.get("action_id", "")
        # Terminal actions never require operator approval to terminate
        if action_id in ("ACTION-END-001", "ACTION-END-002", "ACTION-END-003"):
            return False

        if self.control_mode == "MANUAL":
            return True

        if self.control_mode == "ASSISTED":
            action_class = ACTION_CATALOG.get(action_id, {}).get("class", "")
            # Safe read-only actions: RECON, passive SCAN, PLAN
            # Approval-required actions: active WEB_TEST and active SCAN
            if action_class in ("WEB_TEST",) or action_id == "ACTION-SCAN-002":
                return True
            return False

        return False

    def _emit_event(
        self,
        event_type: str,
        phase: str | None = None,
        iteration: int | None = None,
        action_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Fail-safe event emission. Telemetry failure NEVER alters safety/execution semantics."""
        if self.event_hook is None:
            return
        event = {
            "event_id": f"EVT-{uuid.uuid4().hex[:12]}",
            "run_id": self.run_id,
            "type": event_type,
            "timestamp_utc": _utc_now_iso(),
            "phase": phase or (self.state_manager.phase if hasattr(self, "state_manager") else "RECON"),
            "iteration": iteration,
            "action_id": action_id,
            "payload": {**ACTION_EXECUTION_DETAILS.get(action_id, {}), **(payload or {})},
        }
        try:
            self.event_hook(event)
        except Exception:
            # Telemetry failure is suppressed so safety gate and runner execution semantics are preserved
            pass

    def _compute_state_fingerprint(self, state: dict[str, Any]) -> str:
        """Compute semantic fingerprint of planner state independent of ordering."""
        facts_summary = sorted(
            [f"{f.get('fact_type')}:{f.get('subject')}:{f.get('value')}" for f in state.get("observed_facts", [])]
        )
        endpoints_summary = sorted(state.get("discovered_endpoints", []))
        prev_actions = state.get("previous_actions", [])
        raw = f"{state.get('phase')}|{facts_summary}|{endpoints_summary}|{prev_actions}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def _evaluate_safety(self, proposal: dict[str, Any]) -> tuple[str, str]:
        """Strict safety evaluation before any dispatch: checks catalog, targets, actions, approval, kill switch, budget."""
        target = proposal.get("target_id")
        action = proposal.get("action_id")

        # 1. Action catalog check
        if action not in ACTION_CATALOG:
            return "DENIED", f"UNKNOWN_ACTION_ID_{action}"

        # 2. Lab mode check
        if not self.gate.lab_mode:
            return "DENIED", "LAB_MODE_DISABLED"

        # 3. Target allowlist check (effective targets = canonical allowlist INTERSECT run approved targets)
        if target != self.target_id or target not in self.gate.effective_targets:
            return "DENIED", f"TARGET_NOT_ALLOWLISTED_{target}"

        # 4. Action allowlist check
        if action not in self.gate.effective_actions:
            return "DENIED", f"ACTION_NOT_ALLOWLISTED_{action}"
        if action == "ACTION-SCAN-002":
            if not self.scanner_executor:
                return "DENIED", "SCANNER_NOT_SELECTED"
            if self.scanner_executor.results:
                return "DENIED", "SCANNER_ALREADY_EXECUTED"
            if not self.inventory.items:
                return "DENIED", "UNOBSERVED_RESOURCE"

        # 5. Approval token freshness & validity
        if self.approval is None:
            return "DENIED", "MISSING_APPROVAL"
        is_app_valid, app_reason = self.approval.is_valid()
        if not is_app_valid:
            return "DENIED", app_reason

        # 6. Approval scope check
        if self.approval.target_id != target:
            return "DENIED", "APPROVAL_TARGET_MISMATCH"
        if self.approval.action_id != "*" and self.approval.action_id != action:
            return "DENIED", f"APPROVAL_ACTION_MISMATCH_{action}"

        # 7. Kill switch check
        if self.gate.kill_switch.is_active():
            return "DENIED", "KILL_SWITCH_ACTIVE"

        # 8. Budget check
        if not self.gate.budget_tracker.can_request():
            return "DENIED", "BUDGET_EXHAUSTED"

        # 9. Recorder readiness
        if self.recorder is None or not self.recorder.directory.is_dir():
            return "DENIED", "RECORDER_NOT_READY"

        # 10. Resource provenance check for active verification capabilities
        if action in ("ACTION-WEB-001", "ACTION-WEB-002", "ACTION-WEB-003"):
            res = proposal.get("resource_ref")
            if not res:
                return "DENIED", "UNOBSERVED_RESOURCE"

            # Lookup item either by exact key or by item.path
            item = self.inventory.items.get(res)
            if not item:
                for it in self.inventory.items.values():
                    if it.path == res or it.canonical_url == res:
                        item = it
                        break
            if not item:
                return "DENIED", "UNOBSERVED_RESOURCE"

            # 11. Parameter provenance check
            param = proposal.get("parameter_name")
            if not param:
                return "DENIED", "UNOBSERVED_INPUT"

            observed_inputs: set[str] = set()
            # 1. Query parameters directly on this item's URL
            parsed = urllib.parse.urlsplit(item.path)
            if parsed.query:
                for qk, _ in urllib.parse.parse_qsl(parsed.query):
                    observed_inputs.add(qk)

            # 2. GET form inputs whose action endpoint resolves to this item
            item_clean = item.canonical_url.split("?")[0].rstrip("/")
            for inv_item in self.inventory.items.values():
                for f in inv_item.forms:
                    raw_act = f.get("action", "").strip()
                    f_method = f.get("method", "GET").upper().strip()
                    f_target = urllib.parse.urljoin(inv_item.canonical_url, raw_act) if raw_act else inv_item.canonical_url
                    f_clean = f_target.split("?")[0].rstrip("/")
                    if f_clean == item_clean and f_method == "GET":
                        for inp in f.get("inputs", []):
                            inp_name = inp.get("name")
                            if inp_name:
                                observed_inputs.add(inp_name)

            if param not in observed_inputs:
                return "DENIED", "UNOBSERVED_INPUT"

        return "APPROVED", "SAFETY_GATE_PASSED"

    def _create_refusal_observation(self, proposal: dict[str, Any], reason: str) -> dict[str, Any]:
        """Construct schema-bound refusal observation matching observation.schema.json."""
        action_id = proposal.get("action_id", "ACTION-PLAN-001")
        if not re.match(r"^ACTION-[A-Z]+-[0-9]{3}$", action_id):
            action_id = "ACTION-PLAN-001"

        obs_id = f"OBS-REFUSAL-{uuid.uuid4().hex[:8]}"
        action_ref = proposal.get("action_id", "ACTION_UNKNOWN")
        fact_id = f"FACT-REF-{action_ref}"

        obs = {
            "observation_id": obs_id,
            "run_id": self.run_id,
            "action_id": action_id,
            "timestamp_utc": _utc_now_iso(),
            "outcome": "DENIED",
            "new_facts": [
                {
                    "fact_id": fact_id,
                    "fact_type": "ACTION_OUTCOME",
                    "subject": action_ref,
                    "value": "REFUSED",
                    "confidence": 1.0,
                }
            ],
            "evidence_refs": [],
        }
        return obs

    def _handle_safety_denial(
        self,
        proposal: dict[str, Any],
        reason: str,
        provenance: dict[str, Any],
        iteration: int,
        state_fp: str,
    ) -> DecisionTrace:
        """Process safety denial: record decision artifact, persist refusal observation, update state for replan."""
        decision_id = f"DEC-{uuid.uuid4().hex[:8]}"

        # Persist decision evidence
        dec_art = self.recorder.persist_phase_artifact(
            "decision",
            {
                "run_id": self.run_id,
                "proposal": proposal,
                "decision": "DENIED",
                "reason": reason,
                "timestamp_utc": _utc_now_iso(),
            },
        )
        self.evidence_refs.append(dec_art["evidence_id"])

        # Construct and persist refusal observation
        obs = self._create_refusal_observation(proposal, reason)
        obs["evidence_refs"] = [dec_art["evidence_id"]]
        obs_art = self.recorder.persist_phase_artifact("refusal_obs", obs)
        self.evidence_refs.append(obs_art["evidence_id"])

        # Ingest into state manager via adapter (updates state with refusal fact and projects visibility)
        self._ingest_and_update_visibility(obs)

        # Emit structured events for safety denial, recorded evidence, refusal observation, and state update
        self._emit_event(
            "SAFETY_DENIED",
            iteration=iteration,
            action_id=proposal.get("action_id"),
            payload={
                "decision_id": decision_id,
                "target_id": proposal.get("target_id"),
                "action_id": proposal.get("action_id"),
                "reason": reason,
                "dispatched": False,
            },
        )
        self._emit_event(
            "EVIDENCE_RECORDED",
            iteration=iteration,
            action_id=proposal.get("action_id"),
            payload={"evidence_id": dec_art["evidence_id"], "evidence_type": "decision"},
        )
        self._emit_event(
            "OBSERVATION_RECEIVED",
            iteration=iteration,
            action_id=proposal.get("action_id"),
            payload={"observation_id": obs["observation_id"], "outcome": "DENIED", "new_facts_count": len(obs["new_facts"])},
        )
        self._emit_event(
            "STATE_UPDATED",
            iteration=iteration,
            payload={"facts_count": self.state_manager.get_fact_count(), "phase": self.state_manager.phase},
        )

        return DecisionTrace(
            iteration=iteration,
            decision_id=decision_id,
            timestamp_utc=_utc_now_iso(),
            state_fingerprint=state_fp,
            planner_requested_mode=provenance.get("requested_mode", self.requested_planner_mode),
            planner_actual_mode=provenance.get("actual_mode", "RULE"),
            proposal=proposal,
            safety_decision="DENIED",
            safety_reason=reason,
            dispatched=False,
            intent_evidence_id=None,
            result_evidence_id=dec_art["evidence_id"],
            observation_ids=[obs["observation_id"]],
            new_facts_count=len(obs["new_facts"]),
            outcome="DENIED",
        )

    def _execute_approved_action(
        self,
        proposal: dict[str, Any],
        provenance: dict[str, Any],
        iteration: int,
        state_fp: str,
    ) -> DecisionTrace:
        """Execute approved action strictly through CentralizedSafetyGate / safe capabilities."""
        action_id = proposal["action_id"]
        decision_id = f"DEC-{uuid.uuid4().hex[:8]}"

        self._emit_event(
            "SAFETY_PERMITTED",
            iteration=iteration,
            action_id=action_id,
            payload={"decision_id": decision_id, "target_id": proposal.get("target_id"), "action_id": action_id},
        )
        self._emit_event(
            "ACTION_DISPATCH_STARTED",
            iteration=iteration,
            action_id=action_id,
            payload={"target_id": proposal.get("target_id"),
                     "resource_ref": proposal.get("resource_ref"), "parameter_name": proposal.get("parameter_name")},
        )

        # -------------------------------------------------------------
        # Action Dispatch Branching
        # -------------------------------------------------------------
        if action_id == "ACTION-RECON-001":
            # Target identification probe via gate
            req = DiscoveryRequest(
                run_id=self.run_id,
                target_id=self.target_id,
                action_id="ACTION-RECON-001",
                url=f"{self.gate.base_origin}/health",
                method="GET",
                approval=self.approval,
            )
            # Dispatch strictly through gate (gate persists intent before dispatch and result after dispatch)
            resp: DispatchResponse = self.gate.dispatch(req)
            if self.gate.halted_due_to_evidence or (
                not resp.durable_confirmed and "EVIDENCE" in (resp.refusal_reason or "")
            ):
                raise EvidenceFailure(resp.refusal_reason or "Gate halted due to evidence failure")

            # Collect intent and result artifacts recorded by gate
            intent_art_id = None
            result_art_id = None
            for art in reversed(self.recorder.artifacts):
                ev = art.get("evidence_id", "")
                if not result_art_id and "result" in ev.lower():
                    result_art_id = ev
                elif not intent_art_id and "intent" in ev.lower():
                    intent_art_id = ev
                if intent_art_id and result_art_id:
                    break

            if intent_art_id:
                self.evidence_refs.append(intent_art_id)
            if result_art_id:
                self.evidence_refs.append(result_art_id)

            # Normalize observation
            obs_id = f"OBS-TGT-{uuid.uuid4().hex[:8]}"
            obs = {
                "observation_id": obs_id,
                "run_id": self.run_id,
                "action_id": action_id,
                "timestamp_utc": _utc_now_iso(),
                "outcome": "SUCCESS" if resp.status_code == 200 else "FAILURE",
                "new_facts": [
                    {
                        "fact_id": f"FACT-TGT-{self.target_id}",
                        "fact_type": "TARGET",
                        "subject": self.target_id,
                        "value": self.target_id,
                        "confidence": 1.0,
                    }
                ],
                "evidence_refs": [result_art_id] if result_art_id else [],
            }
            self._ingest_and_update_visibility(obs)

            return DecisionTrace(
                iteration=iteration,
                decision_id=decision_id,
                timestamp_utc=_utc_now_iso(),
                state_fingerprint=state_fp,
                planner_requested_mode=provenance.get("requested_mode", self.requested_planner_mode),
                planner_actual_mode=provenance.get("actual_mode", "RULE"),
                proposal=proposal,
                safety_decision="APPROVED",
                safety_reason="SAFETY_GATE_PASSED",
                dispatched=True,
                intent_evidence_id=intent_art_id,
                result_evidence_id=result_art_id,
                observation_ids=[obs_id],
                new_facts_count=len(obs["new_facts"]),
                outcome=obs["outcome"],
            )

        elif action_id == "ACTION-RECON-002":
            # Web surface discovery via ObservationDrivenDiscovery
            # Single authoritative ingestion boundary: discovery produces observations, adapter ingests
            discovery = ObservationDrivenDiscovery(
                gate=self.gate,
                run_id=self.run_id,
                target_id=self.target_id,
                approval=self.approval,  # type: ignore[arg-type]
                action_id="ACTION-RECON-002",
                state_manager=None,
            )
            run_res: DiscoveryRunResult = discovery.run(seed_path=self.seed_path)

            self.inventory = run_res.inventory
            obs_ids = []
            for obs in run_res.normalized_observations:
                obs_ids.append(obs.get("observation_id", ""))
                self._ingest_and_update_visibility(obs)

            # Persist summary
            summary_art = self.recorder.persist_phase_artifact(
                "action_recon_002_summary",
                {
                    "run_id": self.run_id,
                    "target_id": self.target_id,
                    "status": "COMPLETED" if run_res.status in ("COMPLETED", "COMPLETED_BOUNDED") else "ERROR",
                    "discovery_outcome": run_res.status,
                    "stop_reason": run_res.stop_reason,
                    "dispatches": run_res.network_dispatch_count,
                    "inventory_count": len(self.inventory.items),
                },
            )
            self.evidence_refs.append(summary_art["evidence_id"])

            return DecisionTrace(
                iteration=iteration,
                decision_id=decision_id,
                timestamp_utc=_utc_now_iso(),
                state_fingerprint=state_fp,
                planner_requested_mode=provenance.get("requested_mode", self.requested_planner_mode),
                planner_actual_mode=provenance.get("actual_mode", "RULE"),
                proposal=proposal,
                safety_decision="APPROVED",
                safety_reason="SAFETY_GATE_PASSED",
                dispatched=run_res.network_dispatch_count > 0,
                intent_evidence_id=None,
                result_evidence_id=summary_art["evidence_id"],
                observation_ids=obs_ids,
                new_facts_count=len(obs_ids),
                outcome="SUCCESS" if run_res.status in ("COMPLETED", "COMPLETED_BOUNDED") else "FAILURE",
            )

        elif action_id == "ACTION-SCAN-001":
            # Passive analysis of currently observed inventory — zero target network dispatches
            analyzer = self.capability_registry.get_executor("ACTION-SCAN-001")
            if analyzer:
                cap_res = analyzer.execute(
                    proposal=proposal,
                    gate=self.gate,
                    recorder=self.recorder,
                    run_id=self.run_id,
                    target_id=self.target_id,
                    inventory=self.inventory,
                    approval=self.approval,
                )
                obs_id = f"OBS-SCAN-{uuid.uuid4().hex[:8]}"
                obs = {
                    "observation_id": obs_id,
                    "run_id": self.run_id,
                    "action_id": action_id,
                    "timestamp_utc": _utc_now_iso(),
                    "outcome": cap_res.outcome,
                    "new_facts": cap_res.new_facts,
                    "evidence_refs": [cap_res.result_evidence_id] if cap_res.result_evidence_id else [],
                }
                if cap_res.result_evidence_id:
                    self.evidence_refs.append(cap_res.result_evidence_id)
                self._ingest_and_update_visibility(obs)

                return DecisionTrace(
                    iteration=iteration,
                    decision_id=decision_id,
                    timestamp_utc=_utc_now_iso(),
                    state_fingerprint=state_fp,
                    planner_requested_mode=provenance.get("requested_mode", self.requested_planner_mode),
                    planner_actual_mode=provenance.get("actual_mode", "RULE"),
                    proposal=proposal,
                    safety_decision="APPROVED",
                    safety_reason="SAFETY_GATE_PASSED",
                    dispatched=False,
                    intent_evidence_id=None,
                    result_evidence_id=cap_res.result_evidence_id,
                    observation_ids=[obs_id],
                    new_facts_count=len(cap_res.new_facts),
                    outcome=cap_res.outcome,
                )
            else:
                candidate_facts: list[dict[str, Any]] = []
                for path, item in self.inventory.items.items():
                    if item.forms:
                        candidate_facts.append({
                            "fact_id": f"FACT-CAND-{uuid.uuid4().hex[:8]}",
                            "fact_type": "CANDIDATE_FINDING",
                            "subject": path,
                            "value": f"forms_inputs_count_{len(item.forms)}",
                            "confidence": 0.40,
                        })

                if not candidate_facts:
                    candidate_facts.append({
                        "fact_id": f"FACT-NEG-{uuid.uuid4().hex[:8]}",
                        "fact_type": "CONTROL",
                        "subject": self.target_id,
                        "value": "passive_clean_surface",
                        "confidence": 0.90,
                    })

                obs_id = f"OBS-SCAN-{uuid.uuid4().hex[:8]}"
                obs = {
                    "observation_id": obs_id,
                    "run_id": self.run_id,
                    "action_id": action_id,
                    "timestamp_utc": _utc_now_iso(),
                    "outcome": "SUCCESS",
                    "new_facts": candidate_facts,
                    "evidence_refs": [],
                }
                obs_art = self.recorder.persist_phase_artifact("passive_scan_obs", obs)
                self.evidence_refs.append(obs_art["evidence_id"])
                obs["evidence_refs"] = [obs_art["evidence_id"]]
                self._ingest_and_update_visibility(obs)

                return DecisionTrace(
                    iteration=iteration,
                    decision_id=decision_id,
                    timestamp_utc=_utc_now_iso(),
                    state_fingerprint=state_fp,
                    planner_requested_mode=provenance.get("requested_mode", self.requested_planner_mode),
                    planner_actual_mode=provenance.get("actual_mode", "RULE"),
                    proposal=proposal,
                    safety_decision="APPROVED",
                    safety_reason="SAFETY_GATE_PASSED",
                    dispatched=False,
                    intent_evidence_id=None,
                    result_evidence_id=obs_art["evidence_id"],
                    observation_ids=[obs_id],
                    new_facts_count=len(candidate_facts),
                    outcome="SUCCESS",
                )

        elif action_id in ("ACTION-WEB-001", "ACTION-WEB-002", "ACTION-WEB-003", "ACTION-SCAN-002"):
            executor = self.capability_registry.get_executor(action_id)
            if not executor:
                obs_id = f"OBS-NOEXEC-{uuid.uuid4().hex[:8]}"
                obs = {
                    "observation_id": obs_id,
                    "run_id": self.run_id,
                    "action_id": action_id,
                    "timestamp_utc": _utc_now_iso(),
                    "outcome": "FAILURE",
                    "new_facts": [
                        {
                            "fact_id": f"FACT-NOEXEC-{action_id}",
                            "fact_type": "ACTION_OUTCOME",
                            "subject": action_id,
                            "value": "EXECUTOR_UNAVAILABLE",
                            "confidence": 1.0,
                        }
                    ],
                    "evidence_refs": [],
                }
                obs_art = self.recorder.persist_phase_artifact("executor_unavailable_obs", obs)
                self.evidence_refs.append(obs_art["evidence_id"])
                self._ingest_and_update_visibility(obs)

                return DecisionTrace(
                    iteration=iteration,
                    decision_id=decision_id,
                    timestamp_utc=_utc_now_iso(),
                    state_fingerprint=state_fp,
                    planner_requested_mode=provenance.get("requested_mode", self.requested_planner_mode),
                    planner_actual_mode=provenance.get("actual_mode", "RULE"),
                    proposal=proposal,
                    safety_decision="APPROVED",
                    safety_reason="NO_APPROVED_EXECUTOR",
                    dispatched=False,
                    intent_evidence_id=None,
                    result_evidence_id=obs_art["evidence_id"],
                    observation_ids=[obs_id],
                    new_facts_count=1,
                    outcome="FAILURE",
                )

            # Bounded execution strictly through CentralizedSafetyGate
            cap_res = executor.execute(
                proposal=proposal,
                gate=self.gate,
                recorder=self.recorder,
                run_id=self.run_id,
                target_id=self.target_id,
                inventory=self.inventory,
                approval=self.approval,
            )
            self.active_verifications_count += 1
            if cap_res.intent_evidence_id:
                self.evidence_refs.append(cap_res.intent_evidence_id)
            if cap_res.result_evidence_id:
                self.evidence_refs.append(cap_res.result_evidence_id)

            for f in cap_res.findings:
                self.findings.append(asdict(f))

            self._emit_event("VERIFICATION_COMPLETED", iteration=iteration, action_id=action_id,
                             payload={"classification": cap_res.classification, "outcome": cap_res.outcome,
                                      "resource_ref": proposal.get("resource_ref"),
                                      "parameter_name": proposal.get("parameter_name"),
                                      "findings": [asdict(f) for f in cap_res.findings],
                                      "result_evidence_id": cap_res.result_evidence_id})

            obs_id = f"OBS-VERIF-{uuid.uuid4().hex[:8]}"
            obs = {
                "observation_id": obs_id,
                "run_id": self.run_id,
                "action_id": action_id,
                "timestamp_utc": _utc_now_iso(),
                "outcome": cap_res.outcome,
                "new_facts": cap_res.new_facts,
                "evidence_refs": [cap_res.result_evidence_id] if cap_res.result_evidence_id else [],
            }
            self._ingest_and_update_visibility(obs)

            return DecisionTrace(
                iteration=iteration,
                decision_id=decision_id,
                timestamp_utc=_utc_now_iso(),
                state_fingerprint=state_fp,
                planner_requested_mode=provenance.get("requested_mode", self.requested_planner_mode),
                planner_actual_mode=provenance.get("actual_mode", "RULE"),
                proposal=proposal,
                safety_decision="APPROVED",
                safety_reason="SAFETY_GATE_PASSED",
                dispatched=cap_res.network_dispatch_count > 0,
                intent_evidence_id=cap_res.intent_evidence_id,
                result_evidence_id=cap_res.result_evidence_id,
                observation_ids=[obs_id],
                new_facts_count=len(cap_res.new_facts),
                outcome=cap_res.outcome,
            )

        elif action_id in ("ACTION-PLAN-001", "ACTION-PLAN-002", "ACTION-PLAN-003"):
            # Internal planning adjustment actions — zero network dispatches
            obs_id = f"OBS-PLAN-{uuid.uuid4().hex[:8]}"
            obs = {
                "observation_id": obs_id,
                "run_id": self.run_id,
                "action_id": action_id,
                "timestamp_utc": _utc_now_iso(),
                "outcome": "SUCCESS",
                "new_facts": [
                    {
                        "fact_id": f"FACT-PLAN-{action_id}",
                        "fact_type": "CONTROL",
                        "subject": self.target_id,
                        "value": f"plan_updated_{action_id}",
                        "confidence": 1.0,
                    }
                ],
                "evidence_refs": [],
            }
            obs_art = self.recorder.persist_phase_artifact("plan_action_obs", obs)
            self.evidence_refs.append(obs_art["evidence_id"])
            self._ingest_and_update_visibility(obs)

            return DecisionTrace(
                iteration=iteration,
                decision_id=decision_id,
                timestamp_utc=_utc_now_iso(),
                state_fingerprint=state_fp,
                planner_requested_mode=provenance.get("requested_mode", self.requested_planner_mode),
                planner_actual_mode=provenance.get("actual_mode", "RULE"),
                proposal=proposal,
                safety_decision="APPROVED",
                safety_reason="SAFETY_GATE_PASSED",
                dispatched=False,
                intent_evidence_id=None,
                result_evidence_id=obs_art["evidence_id"],
                observation_ids=[obs_id],
                new_facts_count=1,
                outcome="SUCCESS",
            )

        else:
            # Action has no approved executor capability in isolated ShopLab
            obs_id = f"OBS-NOEXEC-{uuid.uuid4().hex[:8]}"
            obs = {
                "observation_id": obs_id,
                "run_id": self.run_id,
                "action_id": action_id,
                "timestamp_utc": _utc_now_iso(),
                "outcome": "FAILURE",
                "new_facts": [
                    {
                        "fact_id": f"FACT-NOEXEC-{action_id}",
                        "fact_type": "ACTION_OUTCOME",
                        "subject": action_id,
                        "value": "EXECUTOR_UNAVAILABLE",
                        "confidence": 1.0,
                    }
                ],
                "evidence_refs": [],
            }
            obs_art = self.recorder.persist_phase_artifact("executor_unavailable_obs", obs)
            self.evidence_refs.append(obs_art["evidence_id"])
            self._ingest_and_update_visibility(obs)

            return DecisionTrace(
                iteration=iteration,
                decision_id=decision_id,
                timestamp_utc=_utc_now_iso(),
                state_fingerprint=state_fp,
                planner_requested_mode=provenance.get("requested_mode", self.requested_planner_mode),
                planner_actual_mode=provenance.get("actual_mode", "RULE"),
                proposal=proposal,
                safety_decision="APPROVED",
                safety_reason="NO_APPROVED_EXECUTOR",
                dispatched=False,
                intent_evidence_id=None,
                result_evidence_id=obs_art["evidence_id"],
                observation_ids=[obs_id],
                new_facts_count=1,
                outcome="FAILURE",
            )

    def run(self) -> AutonomousRunReport:
        """Execute the autonomous control loop until bounded termination."""
        iteration = 0
        no_progress_counter = 0
        state_history: list[str] = []
        last_fact_count = self.state_manager.get_fact_count()
        stop_reason = "UNSPECIFIED"

        last_provenance: dict[str, Any] = {
            "requested_mode": self.requested_planner_mode,
            "actual_mode": "RULE",
            "provider": "rule_engine",
            "model": "none",
        }

        self.lifecycle_state = "RUNNING"
        self._emit_event(
            "RUN_STARTED",
            iteration=0,
            payload={"run_id": self.run_id, "target_id": self.target_id, "mode": self.requested_planner_mode, "control_mode": self.control_mode},
        )

        while True:
            iteration += 1

            self._emit_event(
                "AGENT_ITERATION_STARTED",
                iteration=iteration,
                payload={"iteration": iteration, "phase": self.state_manager.phase},
            )

            # Check bounded limits before proposing
            if iteration > self.max_decisions:
                stop_reason = "MAX_DECISIONS_REACHED"
                self._emit_event("STOP_CONDITION_REACHED", iteration=iteration, payload={"reason": stop_reason})
                break

            if self._stop_requested.is_set():
                stop_reason = "OPERATOR_STOP_REQUESTED"
                self._emit_event("STOP_CONDITION_REACHED", iteration=iteration, payload={"reason": stop_reason})
                break

            if self.gate.kill_switch.is_active():
                stop_reason = "KILL_SWITCH_ACTIVE"
                self._emit_event("STOP_CONDITION_REACHED", iteration=iteration, payload={"reason": stop_reason})
                break

            # Cooperative PAUSE safe point before state fetch and planner invocation
            if self._pause_requested.is_set() and not self.gate.kill_switch.is_active():
                self.lifecycle_state = "PAUSED"
                self._is_paused.set()
                self._pause_count += 1
                self._emit_event("RUN_PAUSED", iteration=iteration, payload={"run_id": self.run_id, "pause_count": self._pause_count})

                while not self._resume_requested.is_set():
                    if self._stop_requested.is_set() or self.gate.kill_switch.is_active():
                        break
                    time.sleep(0.05)

                self._resume_requested.clear()
                self._is_paused.clear()

                if self._stop_requested.is_set():
                    stop_reason = "OPERATOR_STOP_REQUESTED"
                    self._emit_event("STOP_CONDITION_REACHED", iteration=iteration, payload={"reason": stop_reason})
                    break
                if self.gate.kill_switch.is_active():
                    stop_reason = "KILL_SWITCH_ACTIVE"
                    self._emit_event("STOP_CONDITION_REACHED", iteration=iteration, payload={"reason": stop_reason})
                    break

                self.lifecycle_state = "RUNNING"
                self._emit_event("RUN_RESUMED", iteration=iteration, payload={"run_id": self.run_id})

            planner_state = self.state_adapter.get_minimized_planner_state()
            # Fog of War invariant: planner visibility is strictly projected from verified state + entry seed
            projected = project_visible_targets(planner_state, initial_seed=self.target_id)
            self.visible_targets.update(projected)
            self.planner.update_visible_targets(self.visible_targets)

            remaining_actions = planner_state.get("remaining_budget", {}).get("actions", 0)
            if remaining_actions <= 0:
                stop_reason = "BUDGET_EXHAUSTED"
                self._emit_event("STOP_CONDITION_REACHED", iteration=iteration, payload={"reason": stop_reason})
                break

            # Compute state fingerprint for no-progress cycle detection
            state_fp = self._compute_state_fingerprint(planner_state)
            state_history.append(state_fp)

            # Propose next action from observed state
            self._emit_event("PLANNER_STARTED", iteration=iteration, payload={"requested_mode": self.requested_planner_mode})
            plan_res = self.planner.propose(planner_state)
            proposal = plan_res.proposal
            provenance = plan_res.mode_provenance
            last_provenance = provenance

            action_id = proposal.get("action_id", "")
            self._emit_event(
                "PLANNER_PROPOSED",
                iteration=iteration,
                action_id=action_id,
                payload={
                    "plan_id": proposal.get("plan_id"),
                    "action_id": action_id,
                    "target_id": proposal.get("target_id"),
                    "reason_code": proposal.get("reason_code"),
                    "confidence": proposal.get("confidence"),
                    "actual_mode": provenance.get("actual_mode"),
                    "decision_origin": provenance.get("decision_origin"),
                    "fallback_reason": provenance.get("fallback_reason"),
                },
            )

            if provenance.get("fallback_reason"):
                self._emit_event(
                    "PLANNER_FALLBACK",
                    iteration=iteration,
                    action_id=action_id,
                    payload={"actual_mode": provenance.get("actual_mode"), "reason": provenance.get("fallback_reason")},
                )

            # Check terminal actions from planner
            if action_id in ("ACTION-END-001", "ACTION-END-002", "ACTION-END-003"):
                decision_id = f"DEC-{uuid.uuid4().hex[:8]}"
                dec_art = self.recorder.persist_phase_artifact(
                    "decision",
                    {
                        "run_id": self.run_id,
                        "proposal": proposal,
                        "decision": "STOP",
                        "reason": proposal.get("reason_code", "PLANNER_TERMINAL_STOP"),
                        "timestamp_utc": _utc_now_iso(),
                    },
                )
                self.evidence_refs.append(dec_art["evidence_id"])
                self._emit_event(
                    "STOP_CONDITION_REACHED",
                    iteration=iteration,
                    action_id=action_id,
                    payload={"reason_code": proposal.get("reason_code")},
                )
                self._emit_event(
                    "EVIDENCE_RECORDED",
                    iteration=iteration,
                    action_id=action_id,
                    payload={"evidence_id": dec_art["evidence_id"], "type": "terminal_decision"},
                )
                self.traces.append(
                    DecisionTrace(
                        iteration=iteration,
                        decision_id=decision_id,
                        timestamp_utc=_utc_now_iso(),
                        state_fingerprint=state_fp,
                        planner_requested_mode=provenance.get("requested_mode", self.requested_planner_mode),
                        planner_actual_mode=provenance.get("actual_mode", "RULE"),
                        proposal=proposal,
                        safety_decision="STOP",
                        safety_reason=proposal.get("reason_code", "PLANNER_TERMINAL_STOP"),
                        dispatched=False,
                        intent_evidence_id=None,
                        result_evidence_id=dec_art["evidence_id"],
                        observation_ids=[],
                        new_facts_count=0,
                        outcome="STOP",
                    )
                )
                terminal_reason = proposal.get("reason_code", "PLANNER_TERMINAL_STOP")
                if action_id == "ACTION-END-003" and provenance.get("fallback_reason"):
                    terminal_reason = f"{terminal_reason}:{provenance['fallback_reason']}"
                stop_reason = terminal_reason
                break

            # Check for no-progress cycle (same state repeated beyond threshold)
            if state_history.count(state_fp) >= self.max_repeated_state:
                no_progress_counter += 1
                if no_progress_counter >= self.max_no_progress_cycles:
                    stop_reason = "NO_PROGRESS_LOOP"
                    self._emit_event("STOP_CONDITION_REACHED", iteration=iteration, payload={"reason": stop_reason})
                    break

            # Safety Gate evaluation
            self._emit_event(
                "SAFETY_EVALUATION_STARTED",
                iteration=iteration,
                action_id=action_id,
                payload={"target_id": proposal.get("target_id")},
            )
            safety_decision, safety_reason = self._evaluate_safety(proposal)

            if safety_decision == "DENIED":
                # Gate refused proposed action -> record, add REFUSAL observation, and replan!
                refusal_trace = self._handle_safety_denial(
                    proposal, safety_reason, provenance, iteration, state_fp
                )
                self.traces.append(refusal_trace)
                self._emit_event("AGENT_REPLANNING", iteration=iteration, payload={"reason": "safety_denial"})
                continue

            # Control Mode check: Operator Approval for MANUAL or ASSISTED modes
            if self._requires_operator_approval(proposal):
                self.lifecycle_state = "WAITING_FOR_APPROVAL"
                self._pending_proposal = copy.deepcopy(proposal)
                self._pending_provenance = copy.deepcopy(provenance)
                self._pending_iteration = iteration
                self._pending_state_fp = state_fp
                self._approval_event.clear()
                self._pending_approval_decision = None
                self._pending_rejection_reason = None

                self._emit_event(
                    "PROPOSAL_WAITING_APPROVAL",
                    iteration=iteration,
                    action_id=action_id,
                    payload={
                        "plan_id": proposal.get("plan_id"),
                        "action_id": action_id,
                        "action_name": ACTION_CATALOG.get(action_id, {}).get("name", action_id),
                        "action_class": ACTION_CATALOG.get(action_id, {}).get("class", "UNKNOWN"),
                        "target_id": proposal.get("target_id"),
                        "reason_code": proposal.get("reason_code"),
                        "confidence": proposal.get("confidence"),
                        "resource_ref": proposal.get("resource_ref"),
                        "parameter_name": proposal.get("parameter_name"),
                        "safety_decision": safety_decision,
                        "requested_mode": provenance.get("requested_mode"),
                        "actual_mode": provenance.get("actual_mode"),
                        "decision_origin": provenance.get("decision_origin"),
                        "provider": provenance.get("provider"),
                        "model": provenance.get("model"),
                        "control_mode": self.control_mode,
                    },
                )

                # Cooperative wait for operator approval/rejection or stop/kill switch
                while not self._approval_event.is_set():
                    if self._stop_requested.is_set() or self.gate.kill_switch.is_active():
                        break
                    time.sleep(0.05)

                if self._stop_requested.is_set():
                    stop_reason = "OPERATOR_STOP_REQUESTED"
                    self._pending_proposal = None
                    self._emit_event("STOP_CONDITION_REACHED", iteration=iteration, payload={"reason": stop_reason})
                    break

                if self.gate.kill_switch.is_active():
                    stop_reason = "KILL_SWITCH_ACTIVE"
                    self._pending_proposal = None
                    self._emit_event("STOP_CONDITION_REACHED", iteration=iteration, payload={"reason": stop_reason})
                    break

                decision = self._pending_approval_decision
                rej_reason = self._pending_rejection_reason
                self._pending_proposal = None
                self._pending_approval_decision = None
                self._pending_rejection_reason = None

                if decision == "REJECTED":
                    self._operator_rejections += 1
                    self.lifecycle_state = "RUNNING"
                    self._emit_event(
                        "PROPOSAL_REJECTED",
                        iteration=iteration,
                        action_id=action_id,
                        payload={"plan_id": proposal.get("plan_id"), "reason": rej_reason or "OPERATOR_REJECTED"},
                    )
                    refusal_trace = self._handle_safety_denial(
                        proposal, rej_reason or "OPERATOR_REJECTED", provenance, iteration, state_fp
                    )
                    self.traces.append(refusal_trace)
                    self._emit_event("AGENT_REPLANNING", iteration=iteration, payload={"reason": "operator_rejection"})
                    continue

                elif decision == "APPROVED":
                    self._operator_approvals += 1
                    self.lifecycle_state = "RUNNING"
                    self._emit_event(
                        "PROPOSAL_APPROVED",
                        iteration=iteration,
                        action_id=action_id,
                        payload={"plan_id": proposal.get("plan_id")},
                    )

                    # INVARIANT 36: Safety Gate re-validates after manual approval
                    safety_decision_recheck, safety_reason_recheck = self._evaluate_safety(proposal)
                    if safety_decision_recheck == "DENIED":
                        refusal_trace = self._handle_safety_denial(
                            proposal, f"SAFETY_DENIED_AFTER_APPROVAL:{safety_reason_recheck}", provenance, iteration, state_fp
                        )
                        self.traces.append(refusal_trace)
                        self._emit_event("AGENT_REPLANNING", iteration=iteration, payload={"reason": "safety_denial_post_approval"})
                        continue
                else:
                    stop_reason = "APPROVAL_ABORTED"
                    break

            # Action approved by Gate (and operator if required) -> execute strictly through gate / safe capabilities
            try:
                trace = self._execute_approved_action(
                    proposal, provenance, iteration, state_fp
                )
                self.traces.append(trace)

                if trace.dispatched:
                    self._emit_event(
                        "ACTION_DISPATCHED",
                        iteration=iteration,
                        action_id=action_id,
                        payload={"target_id": self.target_id, "action_id": action_id},
                    )

                event_name = "ACTION_COMPLETED" if trace.outcome == "SUCCESS" else "ACTION_FAILED"
                self._emit_event(
                    event_name,
                    iteration=iteration,
                    action_id=action_id,
                    payload={"decision_id": trace.decision_id, "outcome": trace.outcome, "dispatched": trace.dispatched},
                )

                if trace.result_evidence_id:
                    self._emit_event(
                        "EVIDENCE_RECORDED",
                        iteration=iteration,
                        action_id=action_id,
                        payload={"evidence_id": trace.result_evidence_id, "type": "result"},
                    )

                if trace.observation_ids:
                    self._emit_event(
                        "OBSERVATION_RECEIVED",
                        iteration=iteration,
                        action_id=action_id,
                        payload={"observation_ids": trace.observation_ids, "new_facts_count": trace.new_facts_count},
                    )

                self._emit_event(
                    "STATE_UPDATED",
                    iteration=iteration,
                    payload={"facts_count": self.state_manager.get_fact_count(), "phase": self.state_manager.phase},
                )
                self._emit_event(
                    "BUDGET_UPDATED",
                    iteration=iteration,
                    payload={"remaining_budget": self.state_manager.get_state().get("remaining_budget", {})},
                )
                if self.findings:
                    self._emit_event(
                        "FINDING_CREATED",
                        iteration=iteration,
                        action_id=action_id,
                        payload={"findings_count": len(self.findings)},
                    )

            except EvidenceFailure as exc:
                stop_reason = f"EVIDENCE_FAILURE:{exc}"
                self._emit_event("EVIDENCE_VERIFICATION_FAILED", iteration=iteration, payload={"error": str(exc)})
                break

            # Progress check
            current_fact_count = self.state_manager.get_fact_count()
            if current_fact_count > last_fact_count:
                last_fact_count = current_fact_count
                no_progress_counter = 0
            else:
                no_progress_counter += 1
                if no_progress_counter >= self.max_no_progress_cycles:
                    stop_reason = "NO_PROGRESS_LOOP"
                    self._emit_event("STOP_CONDITION_REACHED", iteration=iteration, payload={"reason": stop_reason})
                    break

            self._emit_event(
                "AGENT_REPLANNING",
                iteration=iteration,
                payload={"next_iteration": iteration + 1},
            )

        # Calculate final counts
        approved_count = sum(1 for t in self.traces if t.safety_decision == "APPROVED")
        denied_count = sum(1 for t in self.traces if t.safety_decision == "DENIED")
        obs_added_count = sum(t.new_facts_count for t in self.traces)

        if self.gate.kill_switch.is_active() or self._stop_requested.is_set():
            self.lifecycle_state = "STOPPED"
            self._emit_event("RUN_STOPPED", payload={"stop_reason": stop_reason})
        else:
            self.lifecycle_state = "COMPLETED"
            self._emit_event(
                "RUN_COMPLETED",
                payload={
                    "stop_reason": stop_reason,
                    "decisions_count": len(self.traces),
                    "network_dispatch_count": self.gate.network_dispatch_count,
                    "approved_actions_count": approved_count,
                    "denied_actions_count": denied_count,
                },
            )

        return AutonomousRunReport(
            run_id=self.run_id,
            target_id=self.target_id,
            requested_planner_mode=self.requested_planner_mode,
            actual_planner_mode=last_provenance.get("actual_mode", "RULE"),
            provider=last_provenance.get("provider", "rule_engine"),
            model=last_provenance.get("model", "none"),
            decisions_count=len(self.traces),
            approved_actions_count=approved_count,
            denied_actions_count=denied_count,
            network_dispatch_count=self.gate.network_dispatch_count,
            unsafe_dispatch_count=self.unsafe_dispatch_count,
            observations_added_count=obs_added_count,
            stop_reason=stop_reason,
            traces=self.traces,
            final_state=self.state_manager.get_state(),
            evidence_refs=list(self.evidence_refs),
            findings=list(self.findings),
            active_verifications_count=self.active_verifications_count,
            control_mode=self.control_mode,
            pause_count=self._pause_count,
            operator_approvals_count=self._operator_approvals,
            operator_rejections_count=self._operator_rejections,
        )
