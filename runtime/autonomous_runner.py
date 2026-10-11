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
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agent.memory.state.state_manager import StateManager
from agent.perception.normalizers.observation_normalizer import ObservationNormalizer
from runtime.discovery_engine import (
    DiscoveryRunResult,
    InventoryStore,
    ObservationDrivenDiscovery,
)
from runtime.discovery_gate import (
    ApprovalToken,
    CentralizedSafetyGate,
    DiscoveryRequest,
    DispatchResponse,
    load_canonical_action_allowlist,
    load_canonical_target_allowlist,
)
from runtime.discovery_recorder import (
    DurableEvidenceRecorder,
    EvidenceFailure,
    redact_secrets,
)
from runtime.observed_planner import (
    ACTION_CATALOG,
    ObservedStatePlanner,
    PlannerResult,
)
from runtime.planner_adapter import (
    PlannerStateAdapter,
)
from scripts.validation.validate_scaffold import ROOT, validate_shape


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

        # Planner
        self.planner = ObservedStatePlanner(
            target_id=self.target_id,
            objective_id=self.objective_id,
            requested_mode=self.requested_planner_mode,
            fallback_allowed=self.planner_fallback_allowed,
            effective_targets=self.gate.effective_targets,
            provider_callable=self.planner_provider_callable,
        )

        # Inventory & Trace tracking
        self.inventory = InventoryStore()
        self.traces: list[DecisionTrace] = []
        self.evidence_refs: list[str] = []
        self.unsafe_dispatch_count = 0

        # Load schemas for validation
        self._plan_schema = json.loads(
            (ROOT / "agent" / "planner" / "contracts" / "plan.schema.json").read_text(encoding="utf-8")
        )
        self._obs_schema = json.loads(
            (ROOT / "agent" / "planner" / "contracts" / "observation.schema.json").read_text(encoding="utf-8")
        )

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

        # Ingest into state manager via adapter (updates state with refusal fact)
        self.state_adapter.ingest_observation(obs)

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
            self.state_adapter.ingest_observation(obs)

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
            # Reuses StateManager to prevent double apply/decrement
            discovery = ObservationDrivenDiscovery(
                gate=self.gate,
                run_id=self.run_id,
                target_id=self.target_id,
                approval=self.approval,  # type: ignore[arg-type]
                action_id="ACTION-RECON-002",
                state_manager=self.state_manager,
            )
            run_res: DiscoveryRunResult = discovery.run(seed_path=self.seed_path)

            self.inventory = run_res.inventory
            obs_ids = []
            for obs in run_res.normalized_observations:
                obs_ids.append(obs.get("observation_id", ""))
                # Track in adapter seen_observations to maintain adapter consistency
                digest = hashlib.sha256(json.dumps(obs, sort_keys=True).encode("utf-8")).hexdigest()
                self.state_adapter.seen_observations[obs.get("observation_id", "")] = digest

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
            self.state_adapter.ingest_observation(obs)

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
            self.state_adapter.ingest_observation(obs)

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
            self.state_adapter.ingest_observation(obs)

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

        while True:
            iteration += 1

            # Check bounded limits before proposing
            if iteration > self.max_decisions:
                stop_reason = "MAX_DECISIONS_REACHED"
                break

            if self.gate.kill_switch.is_active():
                stop_reason = "KILL_SWITCH_ACTIVE"
                break

            planner_state = self.state_adapter.get_minimized_planner_state()
            remaining_actions = planner_state.get("remaining_budget", {}).get("actions", 0)
            if remaining_actions <= 0:
                stop_reason = "BUDGET_EXHAUSTED"
                break

            # Compute state fingerprint for no-progress cycle detection
            state_fp = self._compute_state_fingerprint(planner_state)
            state_history.append(state_fp)

            # Propose next action from observed state
            plan_res = self.planner.propose(planner_state)
            proposal = plan_res.proposal
            provenance = plan_res.mode_provenance
            last_provenance = provenance

            action_id = proposal.get("action_id", "")

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
                    break

            # Safety Gate evaluation
            safety_decision, safety_reason = self._evaluate_safety(proposal)

            if safety_decision == "DENIED":
                # Gate refused proposed action -> record, add REFUSAL observation, and replan!
                refusal_trace = self._handle_safety_denial(
                    proposal, safety_reason, provenance, iteration, state_fp
                )
                self.traces.append(refusal_trace)
                continue

            # Action approved by Gate -> execute strictly through gate / safe capabilities
            try:
                trace = self._execute_approved_action(
                    proposal, provenance, iteration, state_fp
                )
                self.traces.append(trace)
            except EvidenceFailure as exc:
                stop_reason = f"EVIDENCE_FAILURE:{exc}"
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
                    break

        # Calculate final counts
        approved_count = sum(1 for t in self.traces if t.safety_decision == "APPROVED")
        denied_count = sum(1 for t in self.traces if t.safety_decision == "DENIED")
        obs_added_count = sum(t.new_facts_count for t in self.traces)

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
        )
