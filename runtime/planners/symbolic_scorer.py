"""Deterministic Symbolic and Fusion Scorer for Hybrid Belief-State Planner (RT-05C).

Implements the proposed research method:
  Eligible Candidates -> LLM Semantic Ranking + Deterministic Symbolic Scoring -> Fusion -> Decision.

HARD INVARIANTS:
1. Zero-Knowledge: Scorer operates STRICTLY on planner-visible/public features:
   - public step_cost and operational noise_cost
   - Belief State (access levels, sessions, valid credentials, reachability)
   - visible target IDs
   - observable action history and previous observable outcome
2. Strict Isolation: Scorer NEVER reads:
   - TrueState / HiddenScenario
   - ScenarioEvaluationView
   - hidden topology
   - hidden defender state / detection thresholds
   - hidden transition success probabilities
   - scenario identifiers (S1/S2/S3/S4)
   - decoy labels / oracles
3. Determinism: Bit-for-bit reproducible scoring for identical inputs.
4. Scale Normalization: All individual score terms are normalized to [0.0, 1.0].
5. Modular Ablations: All weights can be independently configured or zeroed.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from actions.catalog.action_registry import get_action_family, get_canonical_action_id
from agent.memory.state.belief_state import BeliefState
from runtime.planners.candidate_generator import compute_candidate_signature
from runtime.planners.planner_context import PlannerDecisionContext


@dataclass(frozen=True)
class HybridScoringConfig:
    """Versioned scoring configuration for Hybrid fusion."""

    version: str = "HYBRID_SCORING_V1"
    w_semantic: float = 0.40
    w_progress: float = 0.30
    w_noise: float = 0.10
    w_step: float = 0.05
    w_repeat: float = 0.15
    w_failure: float = 0.20
    max_step_cost: float = 5.0
    max_noise_cost: float = 10.0
    repeat_scale: float = 0.40
    failure_scale: float = 0.50

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "w_semantic": self.w_semantic,
            "w_progress": self.w_progress,
            "w_noise": self.w_noise,
            "w_step": self.w_step,
            "w_repeat": self.w_repeat,
            "w_failure": self.w_failure,
            "max_step_cost": self.max_step_cost,
            "max_noise_cost": self.max_noise_cost,
            "repeat_scale": self.repeat_scale,
            "failure_scale": self.failure_scale,
        }

    def weights_hash(self) -> str:
        data = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    @classmethod
    def full(cls) -> HybridScoringConfig:
        """Full hybrid fusion with all semantic and symbolic terms active."""
        return cls()

    @classmethod
    def without_noise(cls) -> HybridScoringConfig:
        """Ablation: Disable noise cost penalty term."""
        return cls(w_noise=0.0)

    @classmethod
    def without_penalties(cls) -> HybridScoringConfig:
        """Ablation: Disable repetition and failure penalty terms."""
        return cls(w_repeat=0.0, w_failure=0.0)

    @classmethod
    def semantic_only(cls) -> HybridScoringConfig:
        """Ablation: Use semantic ranking alone (symbolic terms zeroed)."""
        return cls(
            w_semantic=1.0,
            w_progress=0.0,
            w_noise=0.0,
            w_step=0.0,
            w_repeat=0.0,
            w_failure=0.0,
        )

    @classmethod
    def symbolic_only(cls) -> HybridScoringConfig:
        """Ablation / Fallback: Use symbolic scoring alone (semantic term zeroed)."""
        return cls(w_semantic=0.0)

    @classmethod
    def frozen(cls) -> HybridScoringConfig:
        """Frozen benchmark configuration identifier for RT-05D / RT-07 evaluation."""
        return cls(version="HYBRID_SCORING_V1_FROZEN")


HYBRID_SCORING_V1_FROZEN = HybridScoringConfig(version="HYBRID_SCORING_V1_FROZEN")
FROZEN_WEIGHTS_HASH = HYBRID_SCORING_V1_FROZEN.weights_hash()
V1_WEIGHTS_HASH = HybridScoringConfig().weights_hash()


@dataclass(frozen=True)
class CandidateScoreBreakdown:
    """Detailed score breakdown for a single candidate proposal."""

    candidate_key: str
    candidate_signature: str
    action_id: str
    canonical_action_id: str
    target_id: str | None
    from_node_id: str | None
    credential_id: str | None
    semantic_rank: int | None
    semantic_score: float
    progress_score: float
    noise_cost: float
    noise_cost_norm: float
    step_cost: float
    step_cost_norm: float
    repeat_count: int
    repeat_penalty: float
    failure_count: int
    failure_penalty: float
    fused_score: float
    proposal: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_key": self.candidate_key,
            "candidate_signature": self.candidate_signature,
            "action_id": self.action_id,
            "canonical_action_id": self.canonical_action_id,
            "target_id": self.target_id,
            "from_node_id": self.from_node_id,
            "credential_id": self.credential_id,
            "semantic_rank": self.semantic_rank,
            "semantic_score": round(self.semantic_score, 4),
            "progress_score": round(self.progress_score, 4),
            "noise_cost": self.noise_cost,
            "noise_cost_norm": round(self.noise_cost_norm, 4),
            "step_cost": self.step_cost,
            "step_cost_norm": round(self.step_cost_norm, 4),
            "repeat_count": self.repeat_count,
            "repeat_penalty": round(self.repeat_penalty, 4),
            "failure_count": self.failure_count,
            "failure_penalty": round(self.failure_penalty, 4),
            "fused_score": round(self.fused_score, 4),
        }


class SymbolicScorer:
    """Canonical deterministic symbolic scorer for planner candidates."""

    def __init__(self, config: HybridScoringConfig | None = None):
        self.config = config or HybridScoringConfig()

    def compute_progress_score(
        self,
        proposal: Mapping[str, Any],
        belief: BeliefState,
    ) -> float:
        """Compute generic progression heuristic based on current Belief State.

        Derived solely from belief facts and canonical action family.
        Zero knowledge of ground truth, scenario names, or hidden topology.
        Scale: [0.0, 1.0].
        """
        act_id = str(proposal.get("action_id") or "")
        can_id = get_canonical_action_id(act_id)
        family = get_action_family(act_id) or get_action_family(can_id)
        target = str(proposal.get("target_id") or "")
        target_base = target.split(":")[0] if target else ""

        # STOP action
        if can_id in ("ACTION-STOP-001", "ACTION-END-001") or family == "STOP":
            if belief.is_objective_achieved():
                return 1.0
            return 0.10

        # Mission objective access
        if can_id in ("ACTION-OBJECTIVE-001", "ACTION-FLOW-002") or family == "OBJECTIVE_ACCESS":
            if not belief.is_objective_achieved():
                return 0.95
            return 0.05

        # Initial network discovery
        if can_id in ("ACTION-DISCOVERY-001", "ACTION-RECON-001") or family == "NETWORK_DISCOVERY":
            services_for_target = [
                s for s in belief.known_services
                if (s.get("target_id") if isinstance(s, Mapping) else getattr(s, "target_id", None)) in (target, target_base)
            ]
            if not services_for_target:
                return 0.85
            return 0.25

        # Service / vulnerability scanning
        if can_id == "ACTION-SCAN-001" or family in ("SERVICE_SCAN", "ACTIVE_SCAN"):
            all_findings = belief.candidate_findings + belief.confirmed_findings
            findings_for_target = [
                f for f in all_findings
                if (f.get("target") if isinstance(f, Mapping) else getattr(f, "target", None)) in (target, target_base)
                or (f.get("subject") if isinstance(f, Mapping) else getattr(f, "subject", None)) in (target, target_base)
            ]
            if not findings_for_target:
                return 0.80
            return 0.25

        # Initial foothold / exploitation
        if can_id in ("ACTION-FOOTHOLD-001", "ACTION-WEB-001") or family == "INITIAL_FOOTHOLD":
            sessions = [
                s for s in belief.active_sessions
                if (s.get("target_id") if isinstance(s, Mapping) else getattr(s, "target_id", None)) in (target, target_base)
            ]
            if not sessions:
                return 0.85
            return 0.20

        # Host recon
        if can_id == "ACTION-HOSTRECON-001" or family == "HOST_RECON":
            host_info = belief.known_hosts.get(target) or belief.known_hosts.get(target_base)
            if not host_info or not (isinstance(host_info, Mapping) and host_info.get("os")):
                return 0.70
            return 0.25

        # Credential discovery
        if can_id in ("ACTION-CREDS-001", "ACTION-AUTH-001") or family == "CREDENTIAL_DISCOVERY":
            creds = [
                c for c in belief.get_valid_credentials()
                if (c.get("host") if isinstance(c, Mapping) else getattr(c, "host", None)) in (target, target_base)
            ]
            if not creds:
                return 0.80
            return 0.25

        # Lateral movement / pivot
        if can_id in ("ACTION-PIVOT-001", "ACTION-FLOW-001") or family == "LATERAL_PIVOT":
            sessions = [
                s for s in belief.active_sessions
                if (s.get("target_id") if isinstance(s, Mapping) else getattr(s, "target_id", None)) in (target, target_base)
            ]
            if not sessions:
                return 0.85
            return 0.20

        # Privilege escalation
        if can_id == "ACTION-PRIVESC-001" or family == "PRIVILEGE_ESCALATION":
            sessions = [
                s for s in belief.active_sessions
                if (s.get("target_id") if isinstance(s, Mapping) else getattr(s, "target_id", None)) in (target, target_base)
            ]
            for s in sessions:
                lvl = s.get("access_level") if isinstance(s, Mapping) else getattr(s, "access_level", "NONE")
                if lvl not in ("PRIVILEGED", "SYSTEM"):
                    return 0.80
            return 0.20

        # Default fallback progression
        return 0.30

    def compute_repeat_penalty(
        self,
        proposal: Mapping[str, Any],
        context: PlannerDecisionContext,
    ) -> tuple[int, float]:
        """Compute repetition penalty from observable action history.

        Scale: [0.0, 1.0].
        """
        can_act = get_canonical_action_id(str(proposal.get("action_id") or ""))
        tgt = str(proposal.get("target_id") or "")
        from_n = str(proposal.get("from_node_id") or proposal.get("from_host") or "")
        sig = proposal.get("candidate_signature") or compute_candidate_signature(proposal)

        count = 0
        for item in context.action_history:
            if not isinstance(item, Mapping):
                continue
            item_act = get_canonical_action_id(str(item.get("action_id") or ""))
            item_tgt = str(item.get("target_id") or "")
            item_from = str(item.get("from_node_id") or item.get("from_host") or "")
            item_sig = item.get("candidate_signature")

            if item_sig and item_sig == sig:
                count += 1
            elif item_act == can_act and item_tgt == tgt and (not from_n or item_from == from_n):
                count += 1

        penalty = min(1.0, count * self.config.repeat_scale)
        return count, penalty

    def compute_failure_penalty(
        self,
        proposal: Mapping[str, Any],
        context: PlannerDecisionContext,
    ) -> tuple[int, float]:
        """Compute observable failure penalty from action history and prior outcome.

        Derived STRICTLY from observed failure outcomes; never accesses hidden failure causes.
        Scale: [0.0, 1.0].
        """
        can_act = get_canonical_action_id(str(proposal.get("action_id") or ""))
        tgt = str(proposal.get("target_id") or "")
        from_n = str(proposal.get("from_node_id") or proposal.get("from_host") or "")

        count = 0

        # Check prior step outcome
        if context.previous_outcome and context.previous_outcome.get("success") is False:
            prev = context.previous_outcome
            prev_act = get_canonical_action_id(str(prev.get("action_id") or ""))
            prev_tgt = str(prev.get("target_id") or "")
            prev_from = str(prev.get("from_node_id") or prev.get("from_host") or "")
            if prev_act == can_act and prev_tgt == tgt and (not from_n or prev_from == from_n):
                count += 1

        # Check action history records
        for item in context.action_history:
            if not isinstance(item, Mapping):
                continue
            if item.get("success") is False:
                item_act = get_canonical_action_id(str(item.get("action_id") or ""))
                item_tgt = str(item.get("target_id") or "")
                item_from = str(item.get("from_node_id") or item.get("from_host") or "")
                if item_act == can_act and item_tgt == tgt and (not from_n or item_from == from_n):
                    count += 1

        penalty = min(1.0, count * self.config.failure_scale)
        return count, penalty

    def score_candidate(
        self,
        proposal: Mapping[str, Any],
        semantic_rank: int | None,
        semantic_score: float,
        context: PlannerDecisionContext,
    ) -> CandidateScoreBreakdown:
        """Score a single candidate proposal and compute fused score."""
        p_dict = dict(proposal)
        can_act = get_canonical_action_id(str(p_dict.get("action_id") or ""))
        tgt = p_dict.get("target_id")
        from_n = p_dict.get("from_node_id") or p_dict.get("from_host")
        cid = p_dict.get("credential_id")
        key = p_dict.get("candidate_key") or ""
        sig = p_dict.get("candidate_signature") or compute_candidate_signature(p_dict)

        # 1. Progress score
        progress = self.compute_progress_score(p_dict, context.belief_state)

        # 2. Costs normalized
        step_cost = float(p_dict.get("step_cost", 1))
        noise_cost = float(p_dict.get("noise_cost", 0))
        step_norm = min(1.0, max(0.0, step_cost / max(1.0, self.config.max_step_cost)))
        noise_norm = min(1.0, max(0.0, noise_cost / max(1.0, self.config.max_noise_cost)))

        # 3. Penalties
        repeat_count, repeat_penalty = self.compute_repeat_penalty(p_dict, context)
        failure_count, failure_penalty = self.compute_failure_penalty(p_dict, context)

        # 4. Fused score calculation
        cfg = self.config
        fused = (
            cfg.w_semantic * semantic_score
            + cfg.w_progress * progress
            - cfg.w_noise * noise_norm
            - cfg.w_step * step_norm
            - cfg.w_repeat * repeat_penalty
            - cfg.w_failure * failure_penalty
        )

        return CandidateScoreBreakdown(
            candidate_key=key,
            candidate_signature=sig,
            action_id=str(p_dict.get("action_id") or ""),
            canonical_action_id=can_act,
            target_id=tgt,
            from_node_id=from_n,
            credential_id=cid,
            semantic_rank=semantic_rank,
            semantic_score=semantic_score,
            progress_score=progress,
            noise_cost=noise_cost,
            noise_cost_norm=noise_norm,
            step_cost=step_cost,
            step_cost_norm=step_norm,
            repeat_count=repeat_count,
            repeat_penalty=repeat_penalty,
            failure_count=failure_count,
            failure_penalty=failure_penalty,
            fused_score=fused,
            proposal=p_dict,
        )

    def score_all(
        self,
        proposals: Sequence[Mapping[str, Any]],
        semantic_rank_map: Mapping[str, tuple[int, float]],
        context: PlannerDecisionContext,
    ) -> list[CandidateScoreBreakdown]:
        """Score and deterministically rank all candidate proposals.

        semantic_rank_map: dict mapping candidate_key -> (semantic_rank, semantic_score)
        """
        breakdowns: list[CandidateScoreBreakdown] = []
        for prop in proposals:
            key = prop.get("candidate_key") or ""
            rank, score = semantic_rank_map.get(key, (None, 0.0))
            b = self.score_candidate(prop, rank, score, context)
            breakdowns.append(b)

        # Deterministic stable tie-breaking:
        # Highest fused score first, then canonical action ID, target, from_node, credential, signature
        def _sort_key(item: CandidateScoreBreakdown) -> tuple:
            return (
                -item.fused_score,
                item.canonical_action_id,
                item.target_id or "",
                item.from_node_id or "",
                item.credential_id or "",
                item.candidate_signature,
            )

        breakdowns.sort(key=_sort_key)
        return breakdowns
