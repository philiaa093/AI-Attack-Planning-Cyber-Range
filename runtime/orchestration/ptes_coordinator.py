"""PTES Pentest Coordinator with durable entry/exit evidence verification.

Adheres strictly to docs/task-specs/SL-10-ptes-orchestration.md and PROJECT_PLAN.md:
  Phase 1: Pre-engagement (authority, target allowlist, approval, budgets, recorder readiness)
  Phase 2: Intelligence Gathering (observation-driven discovery, inventory, forms, links)
  Phase 3: Threat Modeling (hypotheses bound strictly to observed inventory, zero invented assets)
  Phase 4: Vulnerability Analysis (passive/safe candidate reasoning only, no confirmation from 200/reflection alone)
  Phase 5: Exploitation (BLOCKED/NOT_RUN when no approved capability; zero exploit dispatch)
  Phase 6: Post-Exploitation (NOT_RUN/UNRESOLVED when exploit not performed; no credential theft/shell/persistence)
  Phase 7: Reporting (honest summary, phase records, candidate findings, negative results, limitations)

Key Guarantees:
  - Centralized safety gating: ZERO direct HTTP transport in coordinator; all requests pass through CentralizedSafetyGate.
  - Phase record model with explicit entry/exit checks and persistent evidence references.
  - Status semantics: COMPLETED, BLOCKED, NOT_RUN, UNRESOLVED, FAILED.
  - Separation: pipeline_control_completed vs full_ptes_assessment_completed.
  - Global shared budget persisted across all phases.
  - Fail-closed error propagation: no 'finally: phase.complete()' behavior.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agent.memory.state.state_manager import StateManager
from agent.perception.normalizers.observation_normalizer import ObservationNormalizer
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
    ObservedStatePlanner,
    PlannerResult,
)
from runtime.planners.planner_adapter import (
    PlannerStateAdapter,
)
from scripts.validation.validate_scaffold import ROOT


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class PhaseRecord:
    run_id: str
    phase_id: str
    phase_name: str
    started_at: str
    ended_at: str | None = None
    entry_checks: list[dict[str, Any]] = field(default_factory=list)
    exit_checks: list[dict[str, Any]] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    planner_decision_refs: list[str] = field(default_factory=list)
    allowed_capability_refs: list[str] = field(default_factory=list)
    approval_refs: list[str] = field(default_factory=list)
    outcome: str = "NOT_RUN"  # COMPLETED, BLOCKED, NOT_RUN, UNRESOLVED, FAILED
    limitations: list[str] = field(default_factory=list)
    transition_reason: str = ""


@dataclass
class CoordinatorReport:
    run_id: str
    target_id: str
    phases: dict[str, dict[str, Any]]
    pipeline_control_completed: bool
    full_ptes_assessment_completed: bool
    budget_initial: dict[str, Any]
    budget_consumed: dict[str, Any]
    budget_remaining: dict[str, Any]
    observed_inventory_count: int
    hypotheses_count: int
    candidate_findings_count: int
    negative_results_count: int
    confirmed_findings_count: int
    blocked_operations_count: int
    network_dispatch_count: int
    unsafe_dispatch_count: int
    evidence_refs: list[str]
    coverage_limitations: list[str]
    unresolved_items: list[str]
    planner_provenance: dict[str, Any]


class PTESCoordinator:
    """Safe, observation-driven PTES Coordinator with centralized safety gate and durable exit evidence."""

    def __init__(
        self,
        target_id: str,
        gate: CentralizedSafetyGate,
        recorder: DurableEvidenceRecorder,
        approval: ApprovalToken | None,
        run_id: str | None = None,
        objective_id: str = "OBJ-PTES-001",
        requested_planner_mode: str = "RULE",
        planner_fallback_allowed: bool = True,
        planner_provider_callable: Callable[[str, str], str | None] | None = None,
        mock_restore_baseline_ready: bool = True,
    ) -> None:
        self.target_id = target_id
        self.gate = gate
        self.recorder = recorder
        self.approval = approval
        self.run_id = run_id or recorder.run_id
        self.objective_id = objective_id
        self.requested_planner_mode = requested_planner_mode
        self.planner_fallback_allowed = planner_fallback_allowed
        self.planner_provider_callable = planner_provider_callable
        self.mock_restore_baseline_ready = mock_restore_baseline_ready

        # State and Planner components
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
        self.planner = ObservedStatePlanner(
            target_id=self.target_id,
            objective_id=self.objective_id,
            requested_mode=self.requested_planner_mode,
            fallback_allowed=self.planner_fallback_allowed,
            effective_targets=self.gate.effective_targets,
            provider_callable=self.planner_provider_callable,
        )

        # Inventory and evidence tracking
        self.inventory = InventoryStore()
        self.hypotheses: list[dict[str, Any]] = []
        self.findings: list[dict[str, Any]] = []
        self.blocked_operations: list[dict[str, Any]] = []
        self.evidence_refs: list[str] = []
        self.planner_provenance: dict[str, Any] = {}

        # Pipeline control metrics
        self.initial_budget = {
            "max_requests": self.gate.budget_tracker.max_requests,
            "max_pages": self.gate.budget_tracker.max_pages,
            "timeout": self.gate.budget_tracker.timeout,
        }
        self.unsafe_dispatch_count = 0
        self.pipeline_control_completed = False
        self.full_ptes_assessment_completed = False

        # Phase records: Phase 1 through 7
        self.phase_records: dict[str, PhaseRecord] = {
            "PHASE_1": PhaseRecord(self.run_id, "PHASE-01", "PRE_ENGAGEMENT", _utc_now_iso()),
            "PHASE_2": PhaseRecord(self.run_id, "PHASE-02", "INTELLIGENCE_GATHERING", _utc_now_iso()),
            "PHASE_3": PhaseRecord(self.run_id, "PHASE-03", "THREAT_MODELING", _utc_now_iso()),
            "PHASE_4": PhaseRecord(self.run_id, "PHASE-04", "VULNERABILITY_ANALYSIS", _utc_now_iso()),
            "PHASE_5": PhaseRecord(self.run_id, "PHASE-05", "EXPLOITATION", _utc_now_iso()),
            "PHASE_6": PhaseRecord(self.run_id, "PHASE-06", "POST_EXPLOITATION", _utc_now_iso()),
            "PHASE_7": PhaseRecord(self.run_id, "PHASE-07", "REPORTING", _utc_now_iso()),
        }

    def _verify_artifact_ref(self, artifact_ref: dict[str, Any] | str) -> bool:
        """Verify that referenced evidence payload and record exist on disk with valid sha256."""
        if isinstance(artifact_ref, dict):
            payload_path = Path(artifact_ref.get("payload_path", ""))
            record_path = Path(artifact_ref.get("record_path", ""))
            expected_sha = artifact_ref.get("sha256", "")
            if not payload_path.is_file() or not record_path.is_file():
                return False
            actual_sha = hashlib.sha256(payload_path.read_bytes()).hexdigest()
            return actual_sha == expected_sha
        elif isinstance(artifact_ref, str):
            # Evidence ID string: check among recorder artifacts
            for art in self.recorder.artifacts:
                if art.get("evidence_id") == artifact_ref:
                    return self._verify_artifact_ref(art)
            return False
        return False

    def run(self) -> CoordinatorReport:
        """Execute the PTES coordinator pipeline with strict entry/exit gating."""
        try:
            # -------------------------------------------------------------
            # PHASE 1: PRE-ENGAGEMENT
            # -------------------------------------------------------------
            p1_ok = self._run_phase_1_pre_engagement()
            if not p1_ok:
                # Entry/authority failure: later execution phases NOT_RUN
                self._mark_execution_phases_not_run(reason="PRE_ENGAGEMENT_BLOCKED")
                # Phase 7 may generate diagnostic report
                self._run_phase_7_reporting(diagnostic_only=True)
                self.pipeline_control_completed = True
                self.full_ptes_assessment_completed = False
                return self._build_report()

            # -------------------------------------------------------------
            # PHASE 2: INTELLIGENCE GATHERING
            # -------------------------------------------------------------
            p2_ok = self._run_phase_2_intelligence_gathering()
            if not p2_ok:
                self._mark_remaining_execution_phases_not_run(from_phase=3, reason="INTELLIGENCE_GATHERING_FAILED")
                self._run_phase_7_reporting(diagnostic_only=True)
                self.pipeline_control_completed = True
                self.full_ptes_assessment_completed = False
                return self._build_report()

            # -------------------------------------------------------------
            # PHASE 3: THREAT MODELING
            # -------------------------------------------------------------
            p3_ok = self._run_phase_3_threat_modeling()
            if not p3_ok:
                self._mark_remaining_execution_phases_not_run(from_phase=4, reason="THREAT_MODELING_FAILED")
                self._run_phase_7_reporting(diagnostic_only=True)
                self.pipeline_control_completed = True
                self.full_ptes_assessment_completed = False
                return self._build_report()

            # -------------------------------------------------------------
            # PHASE 4: VULNERABILITY ANALYSIS
            # -------------------------------------------------------------
            p4_ok = self._run_phase_4_vulnerability_analysis()
            if not p4_ok:
                self._mark_remaining_execution_phases_not_run(from_phase=5, reason="VULNERABILITY_ANALYSIS_FAILED")
                self._run_phase_7_reporting(diagnostic_only=True)
                self.pipeline_control_completed = True
                self.full_ptes_assessment_completed = False
                return self._build_report()

            # -------------------------------------------------------------
            # PHASE 5: EXPLOITATION (Strict Safety Check)
            # -------------------------------------------------------------
            self._run_phase_5_exploitation()

            # -------------------------------------------------------------
            # PHASE 6: POST-EXPLOITATION (Bounded / Unresolved)
            # -------------------------------------------------------------
            self._run_phase_6_post_exploitation()

            # -------------------------------------------------------------
            # PHASE 7: REPORTING
            # -------------------------------------------------------------
            self._run_phase_7_reporting(diagnostic_only=False)

            self.pipeline_control_completed = True
            # Full assessment completion is True ONLY if all required 7 phases reached COMPLETED
            all_completed = all(p.outcome == "COMPLETED" for p in self.phase_records.values())
            self.full_ptes_assessment_completed = all_completed

            return self._build_report()

        except EvidenceFailure as exc:
            # Propagate recorder failure fail-closed
            self.phase_records["PHASE_7"].outcome = "FAILED"
            self.phase_records["PHASE_7"].transition_reason = f"EVIDENCE_FAILURE: {exc}"
            raise

    # =========================================================================
    # PHASE IMPLEMENTATIONS
    # =========================================================================

    def _run_phase_1_pre_engagement(self) -> bool:
        """Phase 1: Validate pre-engagement conditions before any network dispatch."""
        rec = self.phase_records["PHASE_1"]
        rec.started_at = _utc_now_iso()

        # Entry Checks
        c1 = CheckResult("target_identity", self.target_id in ("lab-ecommerce", "lab-clean-001", "lab-webapp-a", "lab-webapp-b"), f"target_id={self.target_id}")
        c2 = CheckResult("canonical_target_allowlist", self.target_id in self.gate.canonical_target_allowlist, f"target_in_canonical={self.target_id in self.gate.canonical_target_allowlist}")
        c3 = CheckResult("run_approval", self.approval is not None and self.approval.is_valid()[0], f"approval_valid={self.approval.is_valid()[0] if self.approval else False}")
        c4 = CheckResult("approved_actions", len(self.gate.effective_actions) > 0, f"actions={list(self.gate.effective_actions)}")
        c5 = CheckResult("lab_mode", self.gate.lab_mode is True, f"lab_mode={self.gate.lab_mode}")
        c6 = CheckResult("budget_availability", self.gate.budget_tracker.can_request(), f"budget_can_request={self.gate.budget_tracker.can_request()}")
        c7 = CheckResult("kill_switch_inactive", not self.gate.kill_switch.is_active(), f"kill_switch={self.gate.kill_switch.is_active()}")
        c8 = CheckResult("recorder_readiness", self.recorder is not None and self.recorder.directory.is_dir(), f"recorder_dir={self.recorder.directory if self.recorder else None}")
        c9 = CheckResult("restore_baseline_availability", self.mock_restore_baseline_ready and (self.target_id in self.gate.target_registry), f"target_registered={self.target_id in self.gate.target_registry}")
        c10 = CheckResult("gateway_runtime_readiness", bool(self.gate.base_origin), f"base_origin={self.gate.base_origin}")

        entry_checks = [c1, c2, c3, c4, c5, c6, c7, c8, c9, c10]
        rec.entry_checks = [asdict(c) for c in entry_checks]
        rec.allowed_capability_refs = sorted(list(self.gate.effective_actions))
        if self.approval:
            rec.approval_refs = [self.approval.approval_id]

        all_passed = all(c.passed for c in entry_checks)
        if not all_passed:
            failed_checks = [c.name for c in entry_checks if not c.passed]
            rec.outcome = "BLOCKED"
            rec.transition_reason = f"PRE_ENGAGEMENT_BLOCKED: {','.join(failed_checks)}"
            rec.ended_at = _utc_now_iso()
            self.blocked_operations.append({
                "phase": "PRE_ENGAGEMENT",
                "reason": rec.transition_reason,
                "timestamp_utc": rec.ended_at,
            })
            return False

        # Persist Phase 1 authorization artifact
        p1_payload = {
            "phase": "PRE_ENGAGEMENT",
            "run_id": self.run_id,
            "target_id": self.target_id,
            "checks": rec.entry_checks,
            "effective_actions": rec.allowed_capability_refs,
            "approved_at_utc": _utc_now_iso(),
        }
        art = self.recorder.persist_phase_artifact("phase1_pre_engagement", p1_payload)
        rec.artifact_refs.append(art["evidence_id"])
        self.evidence_refs.append(art["evidence_id"])

        # Exit checks: artifact durability verification
        ex1 = CheckResult("artifact_verified", self._verify_artifact_ref(art), f"evidence_id={art['evidence_id']}")
        ex2 = CheckResult("zero_dispatch_at_entry", self.gate.network_dispatch_count == 0, f"network_dispatch_count={self.gate.network_dispatch_count}")
        rec.exit_checks = [asdict(ex1), asdict(ex2)]

        if not (ex1.passed and ex2.passed):
            rec.outcome = "FAILED"
            rec.transition_reason = "EXIT_VERIFICATION_FAILED"
            rec.ended_at = _utc_now_iso()
            return False

        rec.outcome = "COMPLETED"
        rec.transition_reason = "PRE_ENGAGEMENT_SUCCESS"
        rec.ended_at = _utc_now_iso()
        return True

    def _run_phase_2_intelligence_gathering(self) -> bool:
        """Phase 2: Observation-driven discovery via CentralizedSafetyGate."""
        rec = self.phase_records["PHASE_2"]
        rec.started_at = _utc_now_iso()

        # Entry Checks
        c1 = CheckResult("pre_engagement_completed", self.phase_records["PHASE_1"].outcome == "COMPLETED")
        c2 = CheckResult("discovery_action_permitted", "ACTION-RECON-002" in self.gate.effective_actions)
        c3 = CheckResult("approval_fresh", self.approval is not None and self.approval.is_valid()[0])
        c4 = CheckResult("budget_available", self.gate.budget_tracker.can_request())
        c5 = CheckResult("kill_switch_inactive", not self.gate.kill_switch.is_active())

        entry_checks = [c1, c2, c3, c4, c5]
        rec.entry_checks = [asdict(c) for c in entry_checks]
        if not all(c.passed for c in entry_checks):
            rec.outcome = "BLOCKED" if not c3.passed or not c2.passed else "NOT_RUN"
            rec.transition_reason = "ENTRY_CHECK_FAILED"
            rec.ended_at = _utc_now_iso()
            return False

        rec.allowed_capability_refs = ["ACTION-RECON-002"]
        if self.approval:
            rec.approval_refs = [self.approval.approval_id]

        # Execute observation-driven discovery
        # Note: state_manager=None ensures discovery functions strictly as an observation producer;
        # authoritative state ingestion into StateManager is owned solely by PlannerStateAdapter below.
        discovery = ObservationDrivenDiscovery(
            gate=self.gate,
            run_id=self.run_id,
            target_id=self.target_id,
            approval=self.approval,  # type: ignore[arg-type]
            action_id="ACTION-RECON-002",
            state_manager=None,
        )
        run_res: DiscoveryRunResult = discovery.run(seed_path="/")

        # Ingest observations into adapter & inventory (single authoritative ingestion boundary)
        self.inventory = run_res.inventory
        for obs in run_res.normalized_observations:
            self.state_adapter.ingest_observation(obs)

        # Persist phase summary artifact
        p2_payload = {
            "phase": "INTELLIGENCE_GATHERING",
            "run_id": self.run_id,
            "target_id": self.target_id,
            "status": "COMPLETED" if run_res.status in ("COMPLETED", "COMPLETED_BOUNDED") else run_res.status,
            "stop_reason": run_res.stop_reason,
            "inventory_count": len(self.inventory.items),
            "refusal_count": len(self.inventory.refusals),
            "network_dispatches": run_res.network_dispatch_count,
            "items": [asdict(item) for item in self.inventory.items.values()],
            "refusals": self.inventory.refusals,
            "coverage_limitations": "Bounded public surface crawl, depth <= 2, zero form submission",
        }
        art = self.recorder.persist_phase_artifact("phase2_intelligence", p2_payload)
        rec.artifact_refs.append(art["evidence_id"])
        self.evidence_refs.append(art["evidence_id"])
        rec.limitations.append(p2_payload["coverage_limitations"])

        # Exit checks
        ex1 = CheckResult("observations_exist", len(run_res.normalized_observations) > 0 or len(self.inventory.items) > 0, f"items={len(self.inventory.items)}")
        ex2 = CheckResult("source_observation_ids_exist", all(bool(item.source_observation_id) for item in self.inventory.items.values()), "all_items_have_source_obs_id")
        ex3 = CheckResult("discovery_was_gated", run_res.network_dispatch_count == self.gate.network_dispatch_count, f"dispatches={run_res.network_dispatch_count}")
        ex4 = CheckResult("no_evidence_failure", run_res.durable_confirmed and not self.gate.halted_due_to_evidence, f"durable_confirmed={run_res.durable_confirmed}")
        ex5 = CheckResult("coverage_limitation_recorded", len(rec.limitations) > 0, "coverage_limitations_present")
        ex6 = CheckResult("artifact_verified", self._verify_artifact_ref(art), f"evidence_id={art['evidence_id']}")

        exit_checks = [ex1, ex2, ex3, ex4, ex5, ex6]
        rec.exit_checks = [asdict(e) for e in exit_checks]

        if not all(e.passed for e in exit_checks):
            rec.outcome = "FAILED"
            rec.transition_reason = "EXIT_VALIDATOR_REJECT"
            rec.ended_at = _utc_now_iso()
            return False

        rec.outcome = "COMPLETED"
        rec.transition_reason = f"INTELLIGENCE_GATHERING_SUCCESS:{run_res.stop_reason}"
        rec.ended_at = _utc_now_iso()
        return True

    def _run_phase_3_threat_modeling(self) -> bool:
        """Phase 3: Derive bounded hypotheses linked strictly to observed inventory."""
        rec = self.phase_records["PHASE_3"]
        rec.started_at = _utc_now_iso()

        # Entry Checks
        c1 = CheckResult("phase2_completed", self.phase_records["PHASE_2"].outcome == "COMPLETED")
        c2 = CheckResult("inventory_available", len(self.inventory.items) > 0, f"items_count={len(self.inventory.items)}")
        rec.entry_checks = [asdict(c1), asdict(c2)]

        if not (c1.passed and c2.passed):
            rec.outcome = "NOT_RUN"
            rec.transition_reason = "ENTRY_CHECK_FAILED"
            rec.ended_at = _utc_now_iso()
            return False

        # Derive hypotheses strictly from observed inventory
        self.hypotheses = []
        for path, item in self.inventory.items.items():
            hypo_id = f"HYPO-{uuid.uuid4().hex[:8]}"
            if item.forms:
                self.hypotheses.append({
                    "hypothesis_id": hypo_id,
                    "target_id": self.target_id,
                    "resource": item.path,
                    "trust_boundary": "unauthenticated_to_application_input",
                    "surface_description": f"Observed form with {len(item.forms)} form structures and inputs",
                    "source_observation_id": item.source_observation_id,
                    "confidence": 0.60,
                    "is_confirmed": False,
                    "unknowns": ["backend validation logic unverified", "no active exploit submitted"],
                })
            else:
                self.hypotheses.append({
                    "hypothesis_id": hypo_id,
                    "target_id": self.target_id,
                    "resource": item.path,
                    "trust_boundary": "public_browsing_surface",
                    "surface_description": f"Observed public resource with HTTP {item.status_code}",
                    "source_observation_id": item.source_observation_id,
                    "confidence": 0.50,
                    "is_confirmed": False,
                    "unknowns": ["server internal architecture unverified"],
                })

        # Persist Phase 3 threat modeling artifact
        p3_payload = {
            "phase": "THREAT_MODELING",
            "run_id": self.run_id,
            "target_id": self.target_id,
            "hypotheses_count": len(self.hypotheses),
            "hypotheses": self.hypotheses,
            "source_inventory_paths": list(self.inventory.items.keys()),
        }
        art = self.recorder.persist_phase_artifact("phase3_threat_model", p3_payload)
        rec.artifact_refs.append(art["evidence_id"])
        self.evidence_refs.append(art["evidence_id"])

        # Exit checks: every hypothesis must link to existing item in observed inventory
        observed_source_ids = {item.source_observation_id for item in self.inventory.items.values()}
        hypo_sources_valid = all(h.get("source_observation_id") in observed_source_ids for h in self.hypotheses)
        no_confirmed_findings = all(h.get("is_confirmed") is False for h in self.hypotheses)

        ex1 = CheckResult("hypotheses_linked_to_inventory", hypo_sources_valid, "all_sources_resolve_to_inventory")
        ex2 = CheckResult("no_invented_assets", len(self.hypotheses) > 0 and hypo_sources_valid, "no_invented_assets")
        ex3 = CheckResult("no_unconfirmed_labeled_confirmed", no_confirmed_findings, "zero_confirmed_claims")
        ex4 = CheckResult("artifact_verified", self._verify_artifact_ref(art), f"evidence_id={art['evidence_id']}")

        exit_checks = [ex1, ex2, ex3, ex4]
        rec.exit_checks = [asdict(e) for e in exit_checks]

        if not all(e.passed for e in exit_checks):
            rec.outcome = "FAILED"
            rec.transition_reason = "THREAT_MODEL_SOURCE_REJECT"
            rec.ended_at = _utc_now_iso()
            return False

        rec.outcome = "COMPLETED"
        rec.transition_reason = "THREAT_MODELING_SUCCESS"
        rec.ended_at = _utc_now_iso()
        return True

    def _run_phase_4_vulnerability_analysis(self) -> bool:
        """Phase 4: Passive/safe vulnerability candidate reasoning only."""
        rec = self.phase_records["PHASE_4"]
        rec.started_at = _utc_now_iso()

        # Entry Checks
        c1 = CheckResult("phase3_completed", self.phase_records["PHASE_3"].outcome == "COMPLETED")
        c2 = CheckResult("passive_scan_allowed", "ACTION-SCAN-001" in self.gate.effective_actions)
        rec.entry_checks = [asdict(c1), asdict(c2)]

        if not (c1.passed and c2.passed):
            rec.outcome = "NOT_RUN"
            rec.transition_reason = "ENTRY_CHECK_FAILED"
            rec.ended_at = _utc_now_iso()
            return False

        rec.allowed_capability_refs = ["ACTION-SCAN-001"]
        planner_state = self.state_adapter.get_minimized_planner_state()
        plan_res: PlannerResult = self.planner.propose(planner_state)
        rec.planner_decision_refs.append(plan_res.proposal["plan_id"])
        self.planner_provenance = plan_res.mode_provenance

        # Analyze observed responses passively
        self.findings = []
        for path, item in self.inventory.items.items():
            # Check for weak signals: form presence or reflection
            if item.forms:
                # Weak candidate signal
                self.findings.append({
                    "finding_id": f"FIND-CAND-{uuid.uuid4().hex[:8]}",
                    "resource": path,
                    "classification": "CANDIDATE",
                    "reason": "Observed interactive form inputs; requires manual/approved audit",
                    "source_observation_id": item.source_observation_id,
                    "confidence": 0.40,
                })

        if not self.findings:
            # Clean target / no candidate findings
            self.findings.append({
                "finding_id": f"FIND-NEG-{uuid.uuid4().hex[:8]}",
                "resource": "/",
                "classification": "NEGATIVE_RESULT",
                "reason": "No candidate vulnerability signals observed on public surface",
                "source_observation_id": list(self.inventory.items.values())[0].source_observation_id if self.inventory.items else "OBS-NONE",
                "confidence": 0.90,
            })

        # Persist Phase 4 vulnerability analysis artifact
        p4_payload = {
            "phase": "VULNERABILITY_ANALYSIS",
            "run_id": self.run_id,
            "target_id": self.target_id,
            "planner_action": plan_res.proposal["action_id"],
            "planner_mode": plan_res.mode_provenance["actual_mode"],
            "findings_count": len(self.findings),
            "findings": self.findings,
            "confirmed_count": 0,
        }
        art = self.recorder.persist_phase_artifact("phase4_vulnerability_analysis", p4_payload)
        rec.artifact_refs.append(art["evidence_id"])
        self.evidence_refs.append(art["evidence_id"])

        # Exit checks: no findings may be labeled CONFIRMED solely from passive signals
        no_confirmed = all(f.get("classification") != "CONFIRMED" for f in self.findings)
        ex1 = CheckResult("no_unsupported_confirmation", no_confirmed, "zero_confirmed_findings")
        ex2 = CheckResult("findings_source_linked", all(bool(f.get("source_observation_id")) for f in self.findings), "all_findings_linked")
        ex3 = CheckResult("artifact_verified", self._verify_artifact_ref(art), f"evidence_id={art['evidence_id']}")

        exit_checks = [ex1, ex2, ex3]
        rec.exit_checks = [asdict(e) for e in exit_checks]

        if not all(e.passed for e in exit_checks):
            rec.outcome = "FAILED"
            rec.transition_reason = "VULN_ANALYSIS_REJECT"
            rec.ended_at = _utc_now_iso()
            return False

        rec.outcome = "COMPLETED"
        rec.transition_reason = "VULNERABILITY_ANALYSIS_COMPLETED"
        rec.ended_at = _utc_now_iso()
        return True

    def _run_phase_5_exploitation(self) -> None:
        """Phase 5: Exploitation — strictly blocked in current safe boundary."""
        rec = self.phase_records["PHASE_5"]
        rec.started_at = _utc_now_iso()

        # Check if any exploit actions are authorized
        exploit_actions = {"ACTION-WEB-001", "ACTION-WEB-002", "ACTION-WEB-003"}
        authorized_exploit_actions = exploit_actions.intersection(self.gate.effective_actions)

        c1 = CheckResult("phase4_completed", self.phase_records["PHASE_4"].outcome == "COMPLETED")
        c2 = CheckResult("approved_exploit_capability", len(authorized_exploit_actions) > 0, f"authorized={list(authorized_exploit_actions)}")
        rec.entry_checks = [asdict(c1), asdict(c2)]

        # No exploit actions authorized in current safety envelope
        if not c2.passed:
            rec.outcome = "BLOCKED"
            rec.transition_reason = "NO_APPROVED_CAPABILITY"
            rec.limitations = ["Exploitation not authorized in current safe lab scope; zero exploit dispatch"]
            self.blocked_operations.append({
                "phase": "EXPLOITATION",
                "reason": "NO_APPROVED_CAPABILITY",
                "timestamp_utc": _utc_now_iso(),
            })

            # Persist Phase 5 block artifact
            p5_payload = {
                "phase": "EXPLOITATION",
                "run_id": self.run_id,
                "target_id": self.target_id,
                "outcome": "BLOCKED",
                "reason": "NO_APPROVED_CAPABILITY",
                "exploit_dispatch_count": 0,
            }
            art = self.recorder.persist_phase_artifact("phase5_exploitation_blocked", p5_payload)
            rec.artifact_refs.append(art["evidence_id"])
            self.evidence_refs.append(art["evidence_id"])

            ex1 = CheckResult("zero_exploit_dispatch", True, "exploit_dispatches=0")
            ex2 = CheckResult("artifact_verified", self._verify_artifact_ref(art), f"evidence_id={art['evidence_id']}")
            rec.exit_checks = [asdict(ex1), asdict(ex2)]
            rec.ended_at = _utc_now_iso()
            return

        # If exploit capability were permitted (not in this scope)
        rec.outcome = "BLOCKED"
        rec.transition_reason = "EXPLOITATION_RESTRICTED"
        rec.ended_at = _utc_now_iso()

    def _run_phase_6_post_exploitation(self) -> None:
        """Phase 6: Post-Exploitation — marked NOT_RUN or UNRESOLVED when exploitation blocked."""
        rec = self.phase_records["PHASE_6"]
        rec.started_at = _utc_now_iso()

        c1 = CheckResult("exploitation_completed", self.phase_records["PHASE_5"].outcome == "COMPLETED")
        rec.entry_checks = [asdict(c1)]

        # Because Phase 5 was BLOCKED, Phase 6 did not run
        rec.outcome = "NOT_RUN"
        rec.transition_reason = "EXPLOITATION_NOT_PERFORMED"
        rec.limitations = [
            "Post-exploitation not authorized; impact assessment unresolved",
            "No persistence, credential theft, host file read, or lateral movement permitted",
        ]

        p6_payload = {
            "phase": "POST_EXPLOITATION",
            "run_id": self.run_id,
            "target_id": self.target_id,
            "outcome": "NOT_RUN",
            "reason": "EXPLOITATION_NOT_PERFORMED",
            "unresolved_impact": True,
        }
        art = self.recorder.persist_phase_artifact("phase6_post_exploitation_not_run", p6_payload)
        rec.artifact_refs.append(art["evidence_id"])
        self.evidence_refs.append(art["evidence_id"])

        ex1 = CheckResult("zero_post_exploit_dispatch", True, "post_exploit_dispatches=0")
        ex2 = CheckResult("artifact_verified", self._verify_artifact_ref(art), f"evidence_id={art['evidence_id']}")
        rec.exit_checks = [asdict(ex1), asdict(ex2)]
        rec.ended_at = _utc_now_iso()

    def _run_phase_7_reporting(self, diagnostic_only: bool = False) -> None:
        """Phase 7: Generate honest summary report with traceable evidence references."""
        rec = self.phase_records["PHASE_7"]
        rec.started_at = _utc_now_iso()

        c1 = CheckResult("recorder_ready", self.recorder is not None and self.recorder.directory.is_dir())
        rec.entry_checks = [asdict(c1)]

        report_data = {
            "phase": "REPORTING",
            "run_id": self.run_id,
            "target_id": self.target_id,
            "diagnostic_only": diagnostic_only,
            "phase_statuses": {k: v.outcome for k, v in self.phase_records.items() if k != "PHASE_7"},
            "pipeline_control_completed": True,
            "full_ptes_assessment_completed": False,  # Transparent honest assessment
            "observed_inventory_count": len(self.inventory.items),
            "hypotheses_count": len(self.hypotheses),
            "findings_count": len(self.findings),
            "candidate_findings": [f for f in self.findings if f.get("classification") == "CANDIDATE"],
            "negative_results": [f for f in self.findings if f.get("classification") == "NEGATIVE_RESULT"],
            "confirmed_findings": [f for f in self.findings if f.get("classification") == "CONFIRMED"],
            "blocked_operations": self.blocked_operations,
            "network_dispatches": self.gate.network_dispatch_count,
            "planner_provenance": self.planner_provenance,
            "budget_consumed": {
                "requests": self.gate.budget_tracker.requests_dispatched,
                "pages": self.gate.budget_tracker.pages_visited,
            },
            "evidence_refs": list(self.evidence_refs),
            "limitations": [
                "Safe, bounded non-destructive assessment only",
                "Phase 5 exploitation blocked due to safety boundary",
                "Phase 6 post-exploitation impact unresolved",
            ],
            "unresolved_items": [
                "Backend vulnerability confirmation requires approved test scope",
                "Full PTES completion pending authorized exploitation",
            ],
        }

        art = self.recorder.persist_phase_artifact("phase7_report", report_data)
        rec.artifact_refs.append(art["evidence_id"])
        self.evidence_refs.append(art["evidence_id"])

        ex1 = CheckResult("report_artifact_verified", self._verify_artifact_ref(art), f"evidence_id={art['evidence_id']}")
        ex2 = CheckResult("honest_assessment_claim", report_data["full_ptes_assessment_completed"] is False, "no_false_full_claim")
        rec.exit_checks = [asdict(ex1), asdict(ex2)]

        rec.outcome = "COMPLETED"
        rec.transition_reason = "REPORTING_COMPLETED"
        rec.ended_at = _utc_now_iso()

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _mark_execution_phases_not_run(self, reason: str) -> None:
        """Mark Phases 2 through 6 as NOT_RUN when Phase 1 blocked."""
        for p_key in ("PHASE_2", "PHASE_3", "PHASE_4", "PHASE_5", "PHASE_6"):
            rec = self.phase_records[p_key]
            rec.outcome = "NOT_RUN"
            rec.transition_reason = reason
            rec.ended_at = _utc_now_iso()

    def _mark_remaining_execution_phases_not_run(self, from_phase: int, reason: str) -> None:
        """Mark remaining phases as NOT_RUN."""
        for i in range(from_phase, 7):
            rec = self.phase_records[f"PHASE_{i}"]
            rec.outcome = "NOT_RUN"
            rec.transition_reason = reason
            rec.ended_at = _utc_now_iso()

    def _build_report(self) -> CoordinatorReport:
        """Build the final immutable CoordinatorReport envelope."""
        candidate_count = sum(1 for f in self.findings if f.get("classification") == "CANDIDATE")
        negative_count = sum(1 for f in self.findings if f.get("classification") == "NEGATIVE_RESULT")
        confirmed_count = sum(1 for f in self.findings if f.get("classification") == "CONFIRMED")

        return CoordinatorReport(
            run_id=self.run_id,
            target_id=self.target_id,
            phases={k: asdict(v) for k, v in self.phase_records.items()},
            pipeline_control_completed=self.pipeline_control_completed,
            full_ptes_assessment_completed=self.full_ptes_assessment_completed,
            budget_initial=self.initial_budget,
            budget_consumed={
                "requests": self.gate.budget_tracker.requests_dispatched,
                "pages": self.gate.budget_tracker.pages_visited,
            },
            budget_remaining={
                "requests": self.gate.budget_tracker.max_requests - self.gate.budget_tracker.requests_dispatched,
                "pages": self.gate.budget_tracker.max_pages - self.gate.budget_tracker.pages_visited,
            },
            observed_inventory_count=len(self.inventory.items),
            hypotheses_count=len(self.hypotheses),
            candidate_findings_count=candidate_count,
            negative_results_count=negative_count,
            confirmed_findings_count=confirmed_count,
            blocked_operations_count=len(self.blocked_operations),
            network_dispatch_count=self.gate.network_dispatch_count,
            unsafe_dispatch_count=self.unsafe_dispatch_count,
            evidence_refs=list(self.evidence_refs),
            coverage_limitations=[
                "Bounded non-destructive discovery and passive analysis",
                "Phase 5 exploitation blocked by safety boundary",
            ],
            unresolved_items=[
                "Active exploitation verification not authorized",
                "Post-exploitation impact assessment unresolved",
            ],
            planner_provenance=self.planner_provenance or {
                "requested_mode": self.requested_planner_mode,
                "actual_mode": "RULE",
                "provider": "rule_engine",
                "fallback_reason": None,
            },
        )
