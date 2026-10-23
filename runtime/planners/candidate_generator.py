"""Canonical Candidate Proposal Generator for AI Attack Planning (RT-05A).

Reused by all Planners (Rule baseline, LLM planner, Hybrid router) and
SimulationGymEnv to maintain a single authoritative candidate-generation path.

HARD INVARIANTS:
1. Fog-of-War: Candidate targets derive EXCLUSIVELY from belief_state.visible_target_ids.
   Scenario node inventory is NEVER enumerated.
2. Safety Gate Separation: Candidate generator does NOT read Safety Gate full allowlist.
   Safety Gate retains separate authoritative evaluation at execution time.
3. Logical Eligibility: ActionConstraintEvaluator determines whether a candidate is
   logically eligible under current belief. Evaluator does NOT rank or select actions.
4. Determinism: Generated candidates are deterministically sorted for identical input.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from actions.catalog.action_registry import (
    ActionDefinition,
    ActionRegistry,
    CANONICAL_BENCHMARK_ACTION_IDS,
    get_action_family,
    get_action_registry,
    get_canonical_action_id,
)
from agent.memory.state.belief_state import BeliefState
from runtime.evaluators.action_evaluator import ActionConstraintEvaluator, EvaluationResult

# Canonical 9 benchmark actions for planner-facing candidate space (RT-05A1)
CANONICAL_ACTION_IDS = CANONICAL_BENCHMARK_ACTION_IDS


def compute_candidate_key(proposal: Mapping[str, Any], index: int | None = None) -> str:
    """Generate a deterministic stable candidate key for a proposal.

    If an index in sorted eligible candidates is given, returns 'CAND-NNN'.
    Otherwise derives a stable identity digest from canonical parameters.
    """
    if index is not None and index >= 0:
        return f"CAND-{index + 1:03d}"
    can_act = get_canonical_action_id(str(proposal.get("action_id") or ""))
    tgt = str(proposal.get("target_id") or "")
    src = str(proposal.get("from_node_id") or proposal.get("from_host") or "")
    cid = str(proposal.get("credential_id") or "")
    payload = f"{can_act}:{tgt}:{src}:{cid}"
    return "CAND-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]


def compute_candidate_signature(proposal: Mapping[str, Any]) -> str:
    """Generate a stable semantic identity signature for a proposal.

    Independent of ordinal list position; depends strictly on canonical capability,
    target, from_node, and credential parameters. Contains zero hidden state.
    """
    can_act = get_canonical_action_id(str(proposal.get("action_id") or ""))
    tgt = str(proposal.get("target_id") or "")
    src = str(proposal.get("from_node_id") or proposal.get("from_host") or "")
    cid = str(proposal.get("credential_id") or "")
    payload = f"{can_act}:{tgt}:{src}:{cid}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()



@dataclass(frozen=True)
class CandidateGenerationResult:
    """Structured result of candidate proposal generation."""

    all_proposals: tuple[dict[str, Any], ...]
    eligible_proposals: tuple[dict[str, Any], ...]
    rejected_proposals: tuple[dict[str, Any], ...]
    candidate_action_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "all_count": len(self.all_proposals),
            "eligible_count": len(self.eligible_proposals),
            "rejected_count": len(self.rejected_proposals),
            "candidate_action_ids": list(self.candidate_action_ids),
            "eligible_proposals": [copy.deepcopy(p) for p in self.eligible_proposals],
            "rejected_proposals": [copy.deepcopy(p) for p in self.rejected_proposals],
        }


class CandidateGenerator:
    """Canonical generator producing eligible proposals from BeliefState and Action Catalog."""

    def __init__(
        self,
        action_registry: ActionRegistry | None = None,
        evaluator: ActionConstraintEvaluator | None = None,
        candidate_action_ids: Sequence[str] | None = None,
    ) -> None:
        self.action_registry = action_registry or get_action_registry()
        self.evaluator = evaluator or ActionConstraintEvaluator()
        self.action_ids = tuple(candidate_action_ids or CANONICAL_ACTION_IDS)

    def generate(
        self,
        belief_state: BeliefState,
        visible_target_ids: frozenset[str] | Sequence[str] | None = None,
        current_phase: str | None = None,
    ) -> CandidateGenerationResult:
        """Generate eligible and reasoned rejected action proposals from current belief.

        Args:
            belief_state: Attacker belief state snapshot.
            visible_target_ids: Optional override for visible target scope (defaults to belief_state.visible_target_ids).
            current_phase: Optional current phase (e.g. 'ENGAGEMENT', 'ANALYSIS').

        Returns:
            CandidateGenerationResult with deterministically sorted proposals.
        """
        if visible_target_ids is not None:
            vis_targets = sorted(visible_target_ids)
        else:
            vis_targets = sorted(belief_state.visible_target_ids)

        vis_targets_set = frozenset(vis_targets)

        raw_proposals: list[dict[str, Any]] = []

        # 1. Generate target-neutral proposals (e.g. ACTION-STOP-001)
        for act_id in self.action_ids:
            can_id = get_canonical_action_id(act_id)
            act_def = self.action_registry.get_action(can_id) or self.action_registry.get_action(act_id)
            if not act_def:
                continue
            if act_def.target_kind == "ENVIRONMENT" or act_def.action_class == "STOP":
                raw_proposals.append({"action_id": can_id})

        # 2. Generate target-bound proposals
        active_session_hosts = {
            s.get("target_id") if isinstance(s, Mapping) else getattr(s, "target_id", None)
            for s in belief_state.active_sessions
        }
        valid_creds = belief_state.get_valid_credentials()
        reachability_edges = belief_state.observed_reachability

        for act_id in self.action_ids:
            can_id = get_canonical_action_id(act_id)
            act_def = self.action_registry.get_action(can_id) or self.action_registry.get_action(act_id)
            if not act_def or act_def.target_kind == "ENVIRONMENT" or act_def.action_class == "STOP":
                continue

            for tgt in vis_targets:
                # Specialized lateral movement / pivot proposals
                if can_id == "ACTION-PIVOT-001":
                    inbound_edges = [
                        e for e in reachability_edges
                        if (e.get("to_host") if isinstance(e, Mapping) else getattr(e, "to_host", None)) in (tgt, tgt.split(":")[0])
                        or (e.get("target") if isinstance(e, Mapping) else getattr(e, "target", None)) in (tgt, tgt.split(":")[0])
                    ]
                    for edge in inbound_edges:
                        src = edge.get("from_host") if isinstance(edge, Mapping) else getattr(edge, "from_host", None)
                        if not src and isinstance(edge, Mapping):
                            src = edge.get("source")
                        if not src or src not in active_session_hosts:
                            continue
                        matched_creds = [
                            c for c in valid_creds
                            if (c.get("observed_scope") if isinstance(c, Mapping) else getattr(c, "observed_scope", None)) in (tgt, tgt.split(":")[0], "*", "domain")
                        ]
                        for cred in matched_creds:
                            cid = cred.get("credential_id") if isinstance(cred, Mapping) else getattr(cred, "credential_id", None)
                            raw_proposals.append({
                                "action_id": can_id,
                                "target_id": tgt,
                                "from_node_id": src,
                                "from_host": src,
                                "credential_id": cid,
                            })
                        if not matched_creds:
                            raw_proposals.append({
                                "action_id": can_id,
                                "target_id": tgt,
                                "from_node_id": src,
                                "from_host": src,
                            })

                # Specialized objective access proposals
                elif can_id == "ACTION-OBJECTIVE-001":
                    inbound_edges = [
                        e for e in reachability_edges
                        if (e.get("to_host") if isinstance(e, Mapping) else getattr(e, "to_host", None)) in (tgt, tgt.split(":")[0])
                        or (e.get("target") if isinstance(e, Mapping) else getattr(e, "target", None)) in (tgt, tgt.split(":")[0])
                    ]
                    for edge in inbound_edges:
                        src = edge.get("from_host") if isinstance(edge, Mapping) else getattr(edge, "from_host", None)
                        if not src and isinstance(edge, Mapping):
                            src = edge.get("source")
                        if not src or src not in active_session_hosts:
                            continue
                        matched_creds = [
                            c for c in valid_creds
                            if (c.get("observed_scope") if isinstance(c, Mapping) else getattr(c, "observed_scope", None)) in (tgt, tgt.split(":")[0], "*", "domain")
                        ]
                        for cred in matched_creds:
                            cid = cred.get("credential_id") if isinstance(cred, Mapping) else getattr(cred, "credential_id", None)
                            raw_proposals.append({
                                "action_id": can_id,
                                "target_id": tgt,
                                "from_node_id": src,
                                "from_host": src,
                                "credential_id": cid,
                            })
                        if not matched_creds:
                            raw_proposals.append({
                                "action_id": can_id,
                                "target_id": tgt,
                                "from_node_id": src,
                                "from_host": src,
                            })
                    # Direct local objective access if session already active on target
                    if tgt in active_session_hosts or tgt.split(":")[0] in active_session_hosts:
                        raw_proposals.append({
                            "action_id": can_id,
                            "target_id": tgt,
                        })

                else:
                    raw_proposals.append({"action_id": can_id, "target_id": tgt})

        # 3. Deduplicate raw proposals deterministically by canonical capability key
        unique_proposals: list[dict[str, Any]] = []
        seen_keys: set[tuple[str, str, str, str]] = set()
        for p in raw_proposals:
            act_id = get_canonical_action_id(p.get("action_id", ""))
            tgt_id = str(p.get("target_id") or "")
            from_id = str(p.get("from_node_id") or p.get("from_host") or "")
            cred_id = str(p.get("credential_id") or "")
            dedup_key = (act_id, tgt_id, from_id, cred_id)
            if dedup_key not in seen_keys:
                seen_keys.add(dedup_key)
                norm_p = dict(p)
                norm_p["action_id"] = act_id
                unique_proposals.append(norm_p)

        # 4. Evaluate each proposal using ActionConstraintEvaluator
        eligible_proposals: list[dict[str, Any]] = []
        rejected_proposals: list[dict[str, Any]] = []

        for prop in unique_proposals:
            act_id = prop["action_id"]
            tgt_id = prop.get("target_id")
            act_def = self.action_registry.get_action(act_id)
            if not act_def:
                continue

            eval_res: EvaluationResult = self.evaluator.evaluate(
                action=act_def,
                target_id=tgt_id,
                belief_state=belief_state,
                visible_target_ids=vis_targets_set,
                proposal_parameters=prop,
                current_phase=current_phase,
            )

            enriched_prop = copy.deepcopy(prop)
            enriched_prop["step_cost"] = eval_res.step_cost
            enriched_prop["noise_cost"] = eval_res.noise_cost

            if eval_res.eligible:
                eligible_proposals.append(enriched_prop)
            else:
                enriched_prop["reasons"] = list(eval_res.reasons)
                enriched_prop["reason_codes"] = list(eval_res.reason_codes)
                rejected_proposals.append(enriched_prop)

        # 5. Deterministic stable sorting
        def _sort_key(p: dict[str, Any]) -> tuple:
            return (
                p.get("action_id", ""),
                p.get("target_id") or "",
                p.get("from_node_id") or "",
                p.get("credential_id") or "",
            )

        unique_proposals.sort(key=_sort_key)
        eligible_proposals.sort(key=_sort_key)
        rejected_proposals.sort(key=_sort_key)

        for idx, p in enumerate(eligible_proposals):
            p["candidate_key"] = f"CAND-{idx + 1:03d}"
            p["candidate_signature"] = compute_candidate_signature(p)

        return CandidateGenerationResult(
            all_proposals=tuple(unique_proposals),
            eligible_proposals=tuple(eligible_proposals),
            rejected_proposals=tuple(rejected_proposals),
            candidate_action_ids=tuple(sorted({p["action_id"] for p in unique_proposals})),
        )
