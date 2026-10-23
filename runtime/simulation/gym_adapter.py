"""Farama Gymnasium Adapter for Enterprise Attack Simulation (RT-04C).

Wraps the canonical EpisodeEnvironment into a standard Gymnasium Environment
satisfying the Farama Gymnasium 1.4+ Env API and env_checker.

HARD INVARIANTS:
1. One Canonical World Model: This adapter delegates 100% of simulator logic,
   transitions, and truth to EpisodeEnvironment. It has NO private world model.
2. Partial Observability: Observations and info dicts are derived EXCLUSIVELY
   from Planner-visible BeliefState. TrueState and hidden scenario models are NEVER leaked.
3. Policy Enforcement: Actions pass through ActionConstraintEvaluator and CentralizedSafetyGate.
4. Provisional Reward: Mechanical baseline reward without research optimality claims.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Mapping, Sequence

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from actions.catalog.action_registry import get_action_registry
from agent.memory.state.belief_state import BeliefState
from runtime.evaluators.action_evaluator import ActionConstraintEvaluator
from runtime.simulation.environment import EpisodeEnvironment
from runtime.simulation.models.evaluator_view import ScenarioEvaluationView
from runtime.simulation.models.scenario import HiddenScenario
from runtime.simulation.models.step_result import EpisodeStepResult, TerminationReason

logger = logging.getLogger(__name__)

_ACCESS_RANK = {
    "NONE": 0.0,
    "FOOTHOLD": 1.0,
    "USER": 2.0,
    "PRIVILEGED": 3.0,
    "SYSTEM": 4.0,
}


def encode_belief_state_features(
    belief_state: BeliefState,
    max_steps: int = 50,
    max_budget: int = 20,
    current_step: int = 0,
    remaining_budget: int = 20,
    last_success: bool = True,
    last_step_cost: int = 0,
) -> np.ndarray:
    """Encode Planner-visible BeliefState into a deterministic numeric float32 vector.

    Derived STRICTLY from BeliefState. Contains ZERO ground truth data.
    """
    access_levels = [
        _ACCESS_RANK.get(lvl, 0.0)
        for lvl in belief_state.access_state.values()
    ]
    max_access = max(access_levels) if access_levels else 0.0

    obj_status = 0.0
    for obj_info in belief_state.objective_status.values():
        st = obj_info.get("status") if isinstance(obj_info, dict) else str(obj_info)
        if st == "ACHIEVED":
            obj_status = max(obj_status, 2.0)
        elif st == "DISCOVERED":
            obj_status = max(obj_status, 1.0)

    budget_fraction = max(0.0, min(1.0, float(remaining_budget) / max(1.0, float(max_budget))))
    step_fraction = max(0.0, min(1.0, float(current_step) / max(1.0, float(max_steps))))

    features = np.array(
        [
            float(len(belief_state.known_hosts)),
            float(len(belief_state.known_services)),
            float(len(belief_state.known_endpoints)),
            float(len(belief_state.candidate_findings)),
            float(len(belief_state.confirmed_findings)),
            float(len(belief_state.known_credentials)),
            float(len(belief_state.get_valid_credentials())),
            float(len(belief_state.active_sessions)),
            float(len(belief_state.observed_reachability)),
            float(len(belief_state.detection_signals)),
            float(max_access),
            float(obj_status),
            float(budget_fraction),
            float(step_fraction),
            1.0 if last_success else 0.0,
            float(last_step_cost),
        ],
        dtype=np.float32,
    )
    return features


class SimulationGymEnv(gym.Env):
    """Farama Gymnasium environment wrapping the canonical EpisodeEnvironment."""

    metadata = {"render_modes": []}

    def __init__(
        self,
        scenario: HiddenScenario | Path | str,
        max_actions: int = 64,
        max_steps: int = 50,
        max_budget: int = 20,
        random_seed: int = 42,
    ) -> None:
        super().__init__()
        self.max_actions = int(max_actions)
        self.max_steps = int(max_steps)
        self.max_budget = int(max_budget)
        self.random_seed = int(random_seed)

        # Underlying canonical episode environment
        self.episode_env = EpisodeEnvironment(
            scenario=scenario,
            random_seed=self.random_seed,
            max_steps=self.max_steps,
            max_budget=self.max_budget,
        )

        self.action_registry = get_action_registry()
        self.evaluator = ActionConstraintEvaluator()

        # Gymnasium spaces
        self.action_space = spaces.Discrete(self.max_actions)
        self.observation_space = spaces.Box(
            low=0.0,
            high=1000.0,
            shape=(16,),
            dtype=np.float32,
        )

        self._current_admissible_proposals: list[dict[str, Any]] = []
        self._last_step_cost: int = 0
        self._last_success: bool = True

    def _generate_admissible_proposals(
        self, belief_state: BeliefState
    ) -> list[dict[str, Any]]:
        """Generate candidate proposals using canonical CandidateGenerator (RT-05A)."""
        from runtime.planners.candidate_generator import CandidateGenerator

        generator = CandidateGenerator(
            action_registry=self.action_registry,
            evaluator=self.evaluator,
        )
        cand_result = generator.generate(
            belief_state=belief_state,
            visible_target_ids=belief_state.visible_target_ids,
        )
        proposals = list(cand_result.eligible_proposals)
        return proposals[: self.max_actions]

    def _get_action_mask(self) -> np.ndarray:
        """Return binary action mask of shape (max_actions,) for valid discrete actions."""
        mask = np.zeros(self.max_actions, dtype=np.int8)
        num_valid = min(len(self._current_admissible_proposals), self.max_actions)
        mask[:num_valid] = 1
        return mask

    def _encode_obs(
        self,
        belief_state: BeliefState,
        step_cost: int = 0,
        success: bool = True,
    ) -> np.ndarray:
        rem_budget = self.episode_env.state_manager._budget.get("actions", self.max_budget)
        return encode_belief_state_features(
            belief_state=belief_state,
            max_steps=self.max_steps,
            max_budget=self.max_budget,
            current_step=self.episode_env.step_count,
            remaining_budget=rem_budget,
            last_success=success,
            last_step_cost=step_cost,
        )

    def reset(
        self,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        """Reset Gym environment conforming to Farama Gym Env API."""
        super().reset(seed=seed)
        eff_seed = seed if seed is not None else self.random_seed
        bootstrap_obs, initial_belief = self.episode_env.reset(seed=eff_seed)

        self._last_step_cost = 0
        self._last_success = True
        self._current_admissible_proposals = self._generate_admissible_proposals(
            initial_belief
        )

        obs = self._encode_obs(initial_belief, step_cost=0, success=True)
        info = {
            "step_index": 0,
            "action_mask": self._get_action_mask(),
            "visible_targets": sorted(initial_belief.visible_target_ids),
            "admissible_actions_count": len(self._current_admissible_proposals),
            "bootstrap_observation_id": bootstrap_obs.get("observation_id"),
        }
        return obs, info

    def step(
        self, action: int | np.integer | Mapping[str, Any]
    ) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        """Execute action via Gym API.

        Accepts:
            - int: discrete action index mapped to dynamic admissible proposals.
            - dict/Mapping: structured action proposal.
        """
        # Resolve discrete index or structured proposal
        if isinstance(action, (int, np.integer)):
            act_idx = int(action)
            if 0 <= act_idx < len(self._current_admissible_proposals):
                proposal = self._current_admissible_proposals[act_idx]
            else:
                # Invalid action index outside admissible mask
                belief = self.episode_env.get_belief_state()
                obs = self._encode_obs(belief, step_cost=0, success=False)
                info = {
                    "step_index": self.episode_env.step_count,
                    "action_mask": self._get_action_mask(),
                    "rejection_reason": "ACTION_INDEX_OUT_OF_BOUNDS_OR_MASKED",
                }
                return obs, -0.5, False, False, info
        elif isinstance(action, Mapping):
            proposal = dict(action)
        else:
            raise ValueError(f"action must be int or Mapping, got {type(action)}")

        # Execute on underlying canonical EpisodeEnvironment
        step_res: EpisodeStepResult = self.episode_env.step(proposal)

        self._last_step_cost = step_res.step_cost
        self._last_success = step_res.success
        self._current_admissible_proposals = self._generate_admissible_proposals(
            step_res.belief_state
        )

        if step_res.termination_reason == TerminationReason.PLANNER_STOP:
            reward = 0.0
        else:
            reward = -0.05 * float(step_res.step_cost)
            if step_res.termination_reason == TerminationReason.OBJECTIVE_ACHIEVED:
                reward += 10.0
            elif step_res.termination_reason == TerminationReason.CONTAINED:
                reward -= 2.0
            elif step_res.termination_reason == TerminationReason.SAFETY_KILL_SWITCH:
                reward -= 5.0
            elif step_res.truncated:
                reward -= 1.0
            elif not step_res.success:
                reward -= 0.1

        obs = self._encode_obs(
            step_res.belief_state,
            step_cost=step_res.step_cost,
            success=step_res.success,
        )

        # Planner-safe info dict
        info: dict[str, Any] = {
            "step_index": step_res.step_index,
            "action_id": step_res.action_id,
            "target_id": step_res.target_id,
            "success": step_res.success,
            "termination_reason": (
                step_res.termination_reason.value
                if step_res.termination_reason
                else None
            ),
            "action_mask": self._get_action_mask(),
            "admissible_actions_count": len(self._current_admissible_proposals),
            "step_cost": step_res.step_cost,
            "noise_estimate": step_res.noise_estimate,
        }

        return obs, float(reward), step_res.terminated, step_res.truncated, info

    def get_evaluator_view(self) -> ScenarioEvaluationView:
        """Access read-only evaluator scoring view. Separate from Gym observation/info."""
        return self.episode_env.get_evaluator_view()
