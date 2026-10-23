"""Tests for Canonical Candidate Generator (RT-05A).

Verifies invariants:
- Test D: Candidate generation derives exclusively from visible targets.
- Test F: Candidate generator does not read Safety Gate full allowlist.
- Test I: ActionConstraintEvaluator determines logical eligibility (eligible vs reasoned rejected).
- Determinism: Stable sorted proposals for identical input.
"""
from __future__ import annotations

import pytest

from actions.catalog.action_registry import ActionRegistry
from agent.memory.state.belief_state import BeliefState
from runtime.evaluators.action_evaluator import ActionConstraintEvaluator
from runtime.planners.candidate_generator import CandidateGenerator
from runtime.safety.discovery_gate import CentralizedSafetyGate, KillSwitch


class TestCandidateGeneratorInvariants:
    """Validate canonical candidate generation invariants under partial observability."""

    def test_d_candidate_generation_uses_visible_targets_only(self) -> None:
        """Test D: Candidate generator derives target-bound proposals exclusively from visible targets."""
        # Belief state where only lab-dmz-entry is visible, but the lab has other nodes
        belief = BeliefState.from_facts([
            {
                "fact_id": "FACT-TGT-001",
                "fact_type": "TARGET",
                "subject": "lab-dmz-entry",
                "value": {"target_id": "lab-dmz-entry", "status": "REACHABLE"},
                "confidence": 1.0,
            },
            {
                "fact_id": "FACT-001",
                "fact_type": "SERVICE",
                "subject": "lab-dmz-entry:80",
                "value": {"port": 80, "protocol": "HTTP", "service_type": "HTTP"},
                "confidence": 1.0,
            },
        ])

        assert belief.visible_target_ids == frozenset({"lab-dmz-entry"})

        gen = CandidateGenerator()
        res = gen.generate(belief_state=belief)

        # Check all proposals
        target_ids_in_proposals = {
            p["target_id"] for p in res.all_proposals if p.get("target_id") is not None
        }

        # Target IDs in proposals MUST be a subset of belief.visible_target_ids
        for tid in target_ids_in_proposals:
            host = tid.split(":")[0]
            assert host in belief.visible_target_ids, (
                f"Candidate proposal targets {tid} which is NOT in visible_target_ids: {belief.visible_target_ids}"
            )

        # Hidden targets (e.g. lab-db-crown, lab-internal-app) must NOT appear anywhere in proposals
        forbidden_hidden = {"lab-internal-app", "lab-db-crown", "lab-jump-box", "lab-decoy-honeypot"}
        for p in res.all_proposals:
            tgt = p.get("target_id", "")
            for h in forbidden_hidden:
                assert h not in str(tgt), f"Hidden target {h} leaked into proposal: {p}"

    def test_f_candidate_generator_does_not_read_safety_gate_allowlist(self) -> None:
        """Test F: Candidate generator does NOT consult Safety Gate target allowlist."""
        # Create a Safety Gate with full envelope (including hidden targets)
        full_envelope = frozenset({"lab-dmz-entry", "lab-internal-app", "lab-db-crown", "lab-decoy-honeypot"})
        gate = CentralizedSafetyGate(
            base_origin="http://127.0.0.1:18088",
            canonical_target_allowlist=full_envelope,
            canonical_action_allowlist=frozenset({"ACTION-RECON-001", "ACTION-SCAN-001", "ACTION-STOP-001"}),
            target_allowlist=full_envelope,
            action_allowlist=frozenset({"ACTION-RECON-001", "ACTION-SCAN-001", "ACTION-STOP-001"}),
            kill_switch=KillSwitch(),
            lab_mode=True,
        )

        # Attacker belief only knows lab-dmz-entry
        belief = BeliefState.from_facts([
            {
                "fact_id": "FACT-TGT-001",
                "fact_type": "TARGET",
                "subject": "lab-dmz-entry",
                "value": {"target_id": "lab-dmz-entry", "status": "REACHABLE"},
                "confidence": 1.0,
            },
            {
                "fact_id": "FACT-001",
                "fact_type": "SERVICE",
                "subject": "lab-dmz-entry:80",
                "value": {"port": 80, "protocol": "HTTP", "service_type": "HTTP"},
                "confidence": 1.0,
            },
        ])

        # Candidate generator takes BeliefState, not the Safety Gate
        gen = CandidateGenerator()
        res = gen.generate(belief_state=belief)

        # Verify that candidate generator did not produce candidates for the other targets in gate.target_allowlist
        all_targets = {p.get("target_id") for p in res.all_proposals if p.get("target_id")}
        assert all_targets == {"lab-dmz-entry"}
        assert not any("lab-db-crown" in str(p) for p in res.all_proposals)
        assert not any("lab-internal-app" in str(p) for p in res.all_proposals)

    def test_i_constraint_evaluator_partitions_eligible_and_rejected(self) -> None:
        """Test I: ConstraintEvaluator determines logical eligibility and enriches with reasons and costs."""
        # Belief state with visible target and service observed, but NO active session and NO valid creds
        belief = BeliefState.from_facts([
            {
                "fact_id": "FACT-TGT-001",
                "fact_type": "TARGET",
                "subject": "lab-dmz-entry",
                "value": {"target_id": "lab-dmz-entry", "status": "REACHABLE"},
                "confidence": 1.0,
            },
            {
                "fact_id": "FACT-001",
                "fact_type": "SERVICE",
                "subject": "lab-dmz-entry:80",
                "value": {"port": 80, "protocol": "HTTP", "service_type": "HTTP"},
                "confidence": 1.0,
            },
        ])

        gen = CandidateGenerator()
        res = gen.generate(belief_state=belief)

        # ACTION-STOP-001 is target-neutral and always eligible
        eligible_act_ids = {p["action_id"] for p in res.eligible_proposals}
        assert "ACTION-STOP-001" in eligible_act_ids

        # ACTION-DISCOVERY-001, ACTION-SCAN-001, ACTION-FOOTHOLD-001 should be eligible on lab-dmz-entry
        assert "ACTION-DISCOVERY-001" in eligible_act_ids
        assert "ACTION-SCAN-001" in eligible_act_ids
        assert "ACTION-FOOTHOLD-001" in eligible_act_ids
        rejected_act_ids = {p["action_id"] for p in res.rejected_proposals}
        # Invariant: legacy aliases are normalized and not duplicated
        assert "ACTION-RECON-001" not in eligible_act_ids
        assert "ACTION-WEB-001" not in eligible_act_ids
        assert "ACTION-RECON-001" not in rejected_act_ids
        assert "ACTION-WEB-001" not in rejected_act_ids

        # Each proposal in eligible_proposals must have step_cost and noise_cost
        for p in res.eligible_proposals:
            assert "step_cost" in p
            assert "noise_cost" in p
            assert p["step_cost"] >= 0
            assert p["noise_cost"] >= 0.0

        # Each rejected proposal must contain reason_codes
        for p in res.rejected_proposals:
            assert "reason_codes" in p
            assert len(p["reason_codes"]) > 0

    def test_determinism_identical_candidates_and_ordering(self) -> None:
        """Generated candidates and their sorting are bit-for-bit deterministic."""
        belief = BeliefState.from_facts([
            {
                "fact_id": "FACT-001",
                "fact_type": "SERVICE",
                "subject": "lab-dmz-entry:80",
                "value": {"port": 80, "protocol": "HTTP", "service_type": "HTTP"},
                "confidence": 1.0,
            },
            {
                "fact_id": "FACT-002",
                "fact_type": "ACCESS",
                "subject": "lab-dmz-entry",
                "value": {"access_level": "FOOTHOLD"},
                "confidence": 1.0,
            },
            {
                "fact_id": "FACT-003",
                "fact_type": "SESSION",
                "subject": "sess-dmz-01",
                "value": {"node_id": "lab-dmz-entry", "session_state": "ACTIVE"},
                "confidence": 1.0,
            },
        ])

        gen = CandidateGenerator()
        res1 = gen.generate(belief_state=belief)
        res2 = gen.generate(belief_state=belief)

        assert res1.all_proposals == res2.all_proposals
        assert res1.eligible_proposals == res2.eligible_proposals
        assert res1.rejected_proposals == res2.rejected_proposals
        assert res1.candidate_action_ids == res2.candidate_action_ids
