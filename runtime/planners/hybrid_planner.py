"""Hybrid Belief-State Planner for Enterprise Red Team Operations (RT-05C).

Implements the proposed research method:
  1. Safe planner-visible context serialization (strict Zero-Knowledge allowlist).
  2. LLM semantic ranking over current eligible candidate universe.
  3. Server-side candidate membership validation (rejecting unknown/invented candidates).
  4. Deterministic linear semantic rank score transformation.
  5. Deterministic symbolic scoring (progression heuristic, step/noise costs, repetition & failure penalties).
  6. Transparent, versioned, ablation-ready score fusion.
  7. Deterministic tie-breaking.
  8. Graceful fail-closed degradation to SYMBOLIC_ONLY fallback (never calling RuleBasedPlanner).
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from actions.catalog.action_registry import get_canonical_action_id, get_legacy_action_id
from runtime.evaluation.usage_costs import MeteredReviewResponse, TokenUsage
from runtime.planners.candidate_generator import compute_candidate_key, compute_candidate_signature
from runtime.planners.llm_planner import (
    LLMProvider,
    _scan_for_forbidden_llm_data,
    parse_llm_decision_json,
    serialize_llm_context,
)
from runtime.planners.planner_context import PlannerDecision, PlannerDecisionContext
from runtime.planners.planner_interface import Mode, Planner, PlanningDecision, PlanningInput
from runtime.planners.symbolic_scorer import (
    CandidateScoreBreakdown,
    HybridScoringConfig,
    SymbolicScorer,
)

HYBRID_PLANNER_PROMPT_V1 = "HYBRID_ATTACK_PLANNER_V1"
HYBRID_OUTPUT_SCHEMA_VERSION = "HYBRID_OUTPUT_SCHEMA_V1"

HYBRID_PLANNER_SYSTEM_PROMPT = """You are an advanced AI Attack Planning Assistant operating under strict Fog-of-War rules.
Your task is to rank the available eligible attack candidate proposals by strategic and operational priority from best to worst.

CONSTRAINTS:
1. Ground Truth and hidden defender states are strictly isolated; operate only on visible evidence and belief facts.
2. Rank only candidates present in the 'eligible_candidates' list using their stable 'candidate_key' (e.g. CAND-001, CAND-002).
3. Do not invent candidates, targets, action IDs, credentials, or exploit payloads.
4. Respond strictly with a single valid JSON object in the format:
```json
{
  "ranked_candidate_keys": [
    "CAND-001",
    "CAND-002"
  ],
  "reason_code": "STRATEGIC_PRIORITY",
  "brief_justification": "Prioritizing foothold on web entry..."
}
```
Do not include any prose, markdown explanation, or text outside the JSON object.
"""


def parse_hybrid_ranking_json(text: str) -> dict[str, Any] | None:
    """Extract and parse structured hybrid ranking JSON."""
    if not isinstance(text, str):
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        match = re.search(r"\{[^{}]*\}", cleaned, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
    return None


class FakeHybridRankingProvider:
    """Deterministic scripted mock provider for testing Hybrid planner baseline.

    Supports:
    - Sequence of ranked candidate key lists (e.g. [['CAND-001', 'CAND-002']])
    - Sequence of ranking response dicts
    - Raw strings for malformed JSON testing
    - Callable generator
    - Exceptions (TimeoutError, ValueError)
    - Metered token usage injection
    """

    def __init__(
        self,
        script: Sequence[Any] | Callable[[str], Any] | None = None,
        model_name: str = "fake-hybrid-model",
        default_reason: str = "SCRIPTED_HYBRID_RANKING",
        token_usage: TokenUsage | None = None,
    ):
        self.script = list(script) if isinstance(script, (list, tuple)) else script
        self.model_name = model_name
        self.default_reason = default_reason
        self.token_usage = token_usage
        self.call_history: list[str] = []
        self._index = 0

    def complete(self, prompt: str) -> str | MeteredReviewResponse:
        self.call_history.append(prompt)

        if callable(self.script):
            res = self.script(prompt)
        elif self.script is not None and self._index < len(self.script):
            res = self.script[self._index]
            self._index += 1
        else:
            res = self._auto_rank_from_prompt(prompt)

        if isinstance(res, Exception):
            raise res

        if isinstance(res, MeteredReviewResponse):
            return res

        # List of candidate keys or actions -> wrap in valid JSON
        if isinstance(res, list):
            res = {
                "ranked_candidate_keys": [
                    item if isinstance(item, str) and item.startswith("CAND-")
                    else self._map_item_to_candidate_key(item, prompt)
                    for item in res
                ],
                "reason_code": self.default_reason,
                "brief_justification": "Scripted candidate ranking",
            }

        if isinstance(res, dict):
            out_str = json.dumps(res)
        elif isinstance(res, str):
            out_str = res
        else:
            out_str = str(res)

        if self.token_usage is not None:
            return MeteredReviewResponse(review_json=out_str, usage=self.token_usage)
        return out_str

    def _extract_candidates_from_prompt(self, prompt: str) -> list[dict[str, Any]]:
        match = re.search(r"### CURRENT OPERATIONAL CONTEXT:\s*```json\s*(\{.*?\})\s*```", prompt, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                return data.get("eligible_candidates", [])
            except Exception:
                pass
        return []

    def _map_item_to_candidate_key(self, item: Any, prompt: str) -> str:
        candidates = self._extract_candidates_from_prompt(prompt)
        if isinstance(item, str):
            act_id = item
            tgt_id = None
            from_node = None
        elif isinstance(item, (tuple, list)):
            act_id = item[0] if len(item) >= 1 else ""
            tgt_id = item[1] if len(item) >= 2 else None
            from_node = item[2] if len(item) >= 3 else None
        else:
            return "CAND-001"

        for c in candidates:
            if c.get("action_id") == act_id:
                if tgt_id is None or c.get("target_id") == tgt_id or (c.get("target_id") and c.get("target_id").startswith(tgt_id)):
                    if from_node is not None:
                        c_from = c.get("from_node_id") or c.get("from_host")
                        if c_from != from_node:
                            continue
                    return c.get("candidate_key", "CAND-001")
        return candidates[0].get("candidate_key", "CAND-001") if candidates else "CAND-001"

    def _auto_rank_from_prompt(self, prompt: str) -> dict[str, Any]:
        candidates = self._extract_candidates_from_prompt(prompt)
        keys = [c.get("candidate_key") for c in candidates if c.get("candidate_key")]
        return {
            "ranked_candidate_keys": keys,
            "reason_code": "AUTO_ORDER_RANKING",
            "brief_justification": "Default candidate order",
        }


class HybridPlanner(Planner):
    """Hybrid Belief-State Planner combining LLM semantic ranking and deterministic symbolic scoring.

    HARD INVARIANTS:
    1. Uniform Information Surface: Receives the exact same PlannerDecisionContext as Rule and LLM.
    2. Server-Side Candidate Membership: Never trusts model-supplied action or target parameters.
    3. Symbolic-Only Fallback: If LLM semantic component fails, degrades explicitly to SYMBOLIC_ONLY.
       NEVER calls RuleBasedPlanner.
    4. Determinism: Bit-for-bit reproducible ranking given identical semantic output and context.
    5. Modular Ablations: All scoring weights are versioned and can be independently disabled.
    """

    def __init__(
        self,
        provider: LLMProvider | None = None,
        scoring_config: HybridScoringConfig | None = None,
        model_name: str = "hybrid-attack-model",
        prompt_version: str = HYBRID_PLANNER_PROMPT_V1,
        count_tokens: Callable[[str], int] | None = None,
    ):
        self.provider = provider
        self.scoring_config = scoring_config or HybridScoringConfig.full()
        self.scorer = SymbolicScorer(self.scoring_config)
        self.model_name = model_name
        self.prompt_version = prompt_version
        self.count_tokens = count_tokens or len
        self._metrics: dict[str, int] = {
            "total_decisions": 0,
            "semantic_calls": 0,
            "semantic_skipped_single_candidate": 0,
            "valid_semantic_rankings": 0,
            "invalid_semantic_rankings": 0,
            "malformed_semantic_responses": 0,
            "unknown_candidate_keys": 0,
            "duplicate_candidate_keys": 0,
            "provider_errors": 0,
            "symbolic_fallback_count": 0,
        }

    @property
    def mode(self) -> Mode:
        return "HYBRID"

    @property
    def metrics(self) -> dict[str, int]:
        return dict(self._metrics)

    def _plan(self, request: PlanningInput) -> PlanningDecision:
        """Backwards compatibility for legacy PlanningInput."""
        return PlanningDecision(
            request.state.context,
            request.state.revision,
            self.mode,
            self.mode,
            stop_reason="NO_VALID_CANDIDATE",
        )

    def _plan_context(self, context: PlannerDecisionContext) -> PlannerDecision:
        """Core episode runner entry point using PlannerDecisionContext."""
        self._metrics["total_decisions"] += 1
        t_start = time.perf_counter()

        # Handle empty eligible proposals
        if not context.eligible_proposals:
            stop_proposal = {"action_id": "ACTION-STOP-001"}
            return PlannerDecision(
                proposal=stop_proposal,
                rationale="No eligible candidates available under current belief state",
                reason_code="NO_VALID_CANDIDATE",
                confidence=1.0,
                metadata={
                    "planner_type": "HYBRID",
                    "scoring_version": self.scoring_config.version,
                    "reason_code": "NO_VALID_CANDIDATE",
                    "valid": True,
                },
            )

        # 1. Prepare candidate map & prompt
        prompt_text, prompt_hash, context_hash, candidate_map = serialize_llm_context(
            context, system_prompt=HYBRID_PLANNER_SYSTEM_PROMPT
        )
        total_candidates = len(context.eligible_proposals)

        semantic_valid = False
        fallback_mode = "NONE"
        skipped_reason = None
        fallback_used = False
        ranked_keys: list[str] = []
        semantic_rank_map: dict[str, tuple[int, float]] = {}
        reason_code = "HYBRID_FUSED_DECISION"
        justification = "Decision derived from hybrid semantic-symbolic fusion"
        tokens_used: dict[str, int] = {}
        response_hash = ""

        # 2. Check for single candidate short-circuit (Section 6)
        if total_candidates == 1:
            self._metrics["semantic_skipped_single_candidate"] += 1
            skipped_reason = "SINGLE_CANDIDATE"
            semantic_valid = True
            only_key = list(candidate_map.keys())[0]
            ranked_keys = [only_key]
            semantic_rank_map[only_key] = (0, 1.0)
            justification = f"Single eligible candidate {only_key}; semantic ranking short-circuited."

        # 3. Call LLM Provider for semantic ranking if multiple candidates
        elif self.provider is not None:
            self._metrics["semantic_calls"] += 1
            try:
                raw_response = self.provider.complete(prompt_text)

                if isinstance(raw_response, MeteredReviewResponse):
                    response_text = raw_response.review_json
                    if raw_response.usage:
                        tokens_used = {
                            "input_tokens": raw_response.usage.input_uncached,
                            "output_tokens": raw_response.usage.output_tokens,
                            "total_tokens": raw_response.usage.total_tokens,
                        }
                else:
                    response_text = str(raw_response)
                    tokens_used = {
                        "input_tokens": self.count_tokens(prompt_text),
                        "output_tokens": self.count_tokens(response_text),
                    }

                response_hash = hashlib.sha256(response_text.encode("utf-8")).hexdigest()

                # Parse JSON
                parsed_json = parse_hybrid_ranking_json(response_text)
                if not parsed_json or not isinstance(parsed_json, dict):
                    self._metrics["invalid_semantic_rankings"] += 1
                    self._metrics["malformed_semantic_responses"] += 1
                    fallback_mode = "SYMBOLIC_ONLY"
                    fallback_used = True
                    justification = "LLM response malformed JSON; falling back to SYMBOLIC_ONLY"

                else:
                    raw_keys = parsed_json.get("ranked_candidate_keys")
                    if not isinstance(raw_keys, list):
                        self._metrics["invalid_semantic_rankings"] += 1
                        self._metrics["malformed_semantic_responses"] += 1
                        fallback_mode = "SYMBOLIC_ONLY"
                        fallback_used = True
                        justification = "LLM response missing ranked_candidate_keys list; falling back to SYMBOLIC_ONLY"

                    else:
                        # Server-side candidate membership & uniqueness validation
                        has_unknown = any(k not in candidate_map for k in raw_keys)
                        has_duplicates = len(set(raw_keys)) != len(raw_keys)

                        if has_unknown:
                            self._metrics["invalid_semantic_rankings"] += 1
                            self._metrics["unknown_candidate_keys"] += 1
                            fallback_mode = "SYMBOLIC_ONLY"
                            fallback_used = True
                            justification = "LLM returned unknown candidate key(s); falling back to SYMBOLIC_ONLY"

                        elif has_duplicates:
                            self._metrics["invalid_semantic_rankings"] += 1
                            self._metrics["duplicate_candidate_keys"] += 1
                            fallback_mode = "SYMBOLIC_ONLY"
                            fallback_used = True
                            justification = "LLM returned duplicate candidate keys; falling back to SYMBOLIC_ONLY"

                        else:
                            # Valid semantic ranking!
                            self._metrics["valid_semantic_rankings"] += 1
                            semantic_valid = True
                            ranked_keys = [str(k) for k in raw_keys]
                            if parsed_json.get("reason_code"):
                                reason_code = str(parsed_json["reason_code"])
                            if parsed_json.get("brief_justification"):
                                justification = str(parsed_json["brief_justification"])

            except Exception as e:
                self._metrics["invalid_semantic_rankings"] += 1
                self._metrics["provider_errors"] += 1
                fallback_mode = "SYMBOLIC_ONLY"
                fallback_used = True
                justification = f"LLM provider error: {type(e).__name__}; falling back to SYMBOLIC_ONLY"

        else:
            # No provider supplied -> SYMBOLIC_ONLY
            fallback_mode = "SYMBOLIC_ONLY"
            fallback_used = True
            justification = "No LLM provider configured; operating in SYMBOLIC_ONLY mode"

        # 4. Convert validated ranking into linear semantic scores (Section 6)
        if semantic_valid and total_candidates > 1:
            for rank_idx, k in enumerate(ranked_keys):
                score = 1.0 - (rank_idx / (total_candidates - 1))
                semantic_rank_map[k] = (rank_idx, score)

        # 5. Determine active scoring configuration (SYMBOLIC_ONLY zeroes semantic weight)
        if fallback_mode == "SYMBOLIC_ONLY":
            self._metrics["symbolic_fallback_count"] += 1
            active_scorer = SymbolicScorer(self.scoring_config.symbolic_only())
        else:
            active_scorer = self.scorer

        # 6. Score and deterministically rank all eligible proposals
        breakdowns = active_scorer.score_all(
            proposals=context.eligible_proposals,
            semantic_rank_map=semantic_rank_map,
            context=context,
        )

        # 7. Select top candidate
        winner = breakdowns[0]
        chosen_proposal = copy.deepcopy(winner.proposal)
        latency_ms = (time.perf_counter() - t_start) * 1000.0

        # Construct comprehensive trace metadata
        metadata = {
            "planner_type": "HYBRID",
            "scoring_version": active_scorer.config.version,
            "scoring_weights": active_scorer.config.to_dict(),
            "weights_hash": active_scorer.config.weights_hash(),
            "candidate_key": winner.candidate_key,
            "candidate_signature": winner.candidate_signature,
            "canonical_action_id": winner.canonical_action_id,
            "execution_alias_id": chosen_proposal.get("execution_alias_id") or get_legacy_action_id(winner.canonical_action_id),
            "target_id": winner.target_id,
            "from_node_id": winner.from_node_id,
            "credential_id": winner.credential_id,
            "semantic_rank": winner.semantic_rank,
            "normalized_semantic_score": round(winner.semantic_score, 4),
            "progress_score": round(winner.progress_score, 4),
            "normalized_noise_cost": round(winner.noise_cost_norm, 4),
            "normalized_step_cost": round(winner.step_cost_norm, 4),
            "repeat_penalty": round(winner.repeat_penalty, 4),
            "failure_penalty": round(winner.failure_penalty, 4),
            "final_fused_score": round(winner.fused_score, 4),
            "final_rank": 1,
            "selected_candidate": winner.candidate_key,
            "semantic_component_valid": semantic_valid,
            "semantic_fallback_mode": fallback_mode,
            "semantic_call_skipped_reason": skipped_reason,
            "fallback_used": fallback_used,
            "model": getattr(self.provider, "model_name", self.model_name),
            "prompt_version": self.prompt_version,
            "prompt_hash": prompt_hash,
            "context_hash": context_hash,
            "response_hash": response_hash,
            "tokens_used": tokens_used,
            "latency_ms": round(latency_ms, 2),
            "valid": True,
            "all_candidate_scores": [b.to_dict() for b in breakdowns],
        }

        # STOP action rationale adjustment if STOP won
        if winner.canonical_action_id in ("ACTION-STOP-001", "ACTION-END-001"):
            if context.belief_state.is_objective_achieved():
                reason_code = "OBJECTIVE_ACHIEVED"
                justification = "Mission objective achieved in belief state; stopping cleanly."
            else:
                reason_code = "STOP_ACTION"
                justification = "STOP chosen as optimal action under fused symbolic scoring."

        return PlannerDecision(
            proposal=chosen_proposal,
            rationale=justification,
            reason_code=reason_code,
            confidence=round(max(0.0, min(1.0, winner.fused_score)), 4),
            metadata=metadata,
        )

    def plan_decision(self, context: PlannerDecisionContext) -> PlannerDecision:
        """Alias matching RuleBasedPlanner and LLMPlanner."""
        return self._plan_context(context)
