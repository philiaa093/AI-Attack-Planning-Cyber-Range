"""Offline reward/mask adapter; does not enable TASK-026 training or dispatch."""
from __future__ import annotations

import math

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from runtime.evaluation.reward_model import score_replay_reward
from runtime.evaluation.rl_environment import ReplayAssessmentEnv


OBSERVATION_VERSION = "replay-normalized-v1"
REWARD_VERSION = "task024-fixed-v1"


class ReplayRewardMaskWrapper(gym.Wrapper):
    """Fixed normalization, detached masks, one score per committed transition.

    Only the exact metadata simulator is accepted. This is not a sandbox for
    caller code. The simulator still checks policy even when masks are ignored.
    Intrinsic budget exhaustion is terminal for this finite-horizon adapter;
    base termination flags are retained in info, without changing TASK-023.
    """

    def __init__(self, env):
        if type(env) is not ReplayAssessmentEnv:
            raise ValueError("exact offline ReplayAssessmentEnv required")
        super().__init__(env)
        n = env.observation_space["inventory_counts"].shape[0]
        self.observation_space = spaces.Dict({
            "assets": spaces.MultiBinary((n, 4)),
            "inventory_counts": spaces.Box(0, 1, (n,), dtype=np.float32),
            "remaining_budget": spaces.Box(0, 1, (1,), dtype=np.float32),
            "action_mask": spaces.MultiBinary(int(env.action_space.n)),
            "read_age": spaces.Box(-1, 1, (1,), dtype=np.float32),
        })
        self._ready = False
        self._closed = False
        self._mask = None
        self._read_age = -1
        self._last_read = None
        self._tick = 0

    def _invalidate(self):
        self._ready = False
        self._mask = None

    def _project(self, observation, info, *, ended):
        if type(info) is not dict or set(info) != {
            "action_mask", "outcome", "provenance", "network_dispatches"
        }:
            raise ValueError("closed simulator info required")
        if info["provenance"] not in ("SIMULATED_FIXTURE", "OFFLINE_STATE_SNAPSHOT"):
            raise ValueError("offline provenance required")
        if type(info["network_dispatches"]) is not int or info["network_dispatches"] != 0:
            raise ValueError("zero simulator dispatches required")
        if type(observation) is not dict or set(observation) != {
            "assets", "inventory_counts", "remaining_budget"
        }:
            raise ValueError("closed simulator observation required")
        arrays = ((observation["assets"], np.int8),
                  (observation["inventory_counts"], np.int32),
                  (observation["remaining_budget"], np.float32),
                  (info["action_mask"], np.int8))
        if any(type(a) is not np.ndarray or a.dtype != dtype for a, dtype in arrays):
            raise ValueError("typed simulator arrays required")
        mask = info["action_mask"]
        if (not self.env.observation_space.contains(observation)
                or mask.shape != (self.action_space.n,)
                or not np.isin(mask, (0, 1)).all()):
            raise ValueError("simulator observation/mask outside declared space")
        if ended and mask.any():
            raise ValueError("ended simulator must have an empty mask")
        projected = {
            "assets": observation["assets"].copy(),
            "inventory_counts": (
                np.log1p(observation["inventory_counts"].astype(np.float64))
                / math.log1p(10_000)
            ).astype(np.float32),
            "remaining_budget": observation["remaining_budget"].copy(),
            "action_mask": info["action_mask"].copy(),
            "read_age": np.array([
                -1 if self._read_age == -1 else self._read_age / 10_000
            ], dtype=np.float32),
        }
        if not self.observation_space.contains(projected):
            raise ValueError("normalized observation outside declared space")
        detached_info = dict(info, action_mask=info["action_mask"].copy(),
                             observation_version=OBSERVATION_VERSION,
                             reward_version=REWARD_VERSION)
        self._mask = info["action_mask"].astype(bool, copy=True)
        self._ready = not ended
        return projected, detached_info

    def reset(self, *, seed=None, options=None):
        self._invalidate()
        if self._closed:
            raise RuntimeError("wrapper closed")
        try:
            observation, info = self.env.reset(seed=seed, options=options)
            if info.get("outcome") != "RESET":
                raise ValueError("simulator reset outcome required")
            self._read_age, self._last_read, self._tick = -1, None, 0
            return self._project(observation, info, ended=False)
        except Exception:
            self._invalidate()
            raise

    def action_masks(self):
        """SB3-contrib convention: True means admissible, not authorized dispatch."""
        if not self._ready or self._closed:
            raise RuntimeError("active reset episode required")
        return self._mask.copy()

    def step(self, action):
        if not self._ready or self._closed:
            raise RuntimeError("active reset episode required")
        self._invalidate()
        try:
            observation, _, base_terminated, base_truncated, info = self.env.step(action)
            if type(base_terminated) is not bool or type(base_truncated) is not bool:
                raise ValueError("boolean simulator episode flags required")
            self._tick += 1
            outcome = info.get("outcome")
            if int(action) < self.env.finish_action and outcome in (
                "INVENTORY_OBSERVED", "REPORT_REVIEWED", "REPORT_UNAVAILABLE", "NO_PROGRESS"
            ):
                self._last_read = self._tick
            self._read_age = (-1 if self._last_read is None
                              else self._tick - self._last_read)
            ended = base_terminated or base_truncated
            if base_truncated and float(observation["remaining_budget"][0]) != 0:
                raise ValueError("only intrinsic budget truncation is supported")
            projected, detached_info = self._project(observation, info, ended=ended)
            # Called once, only after the base audit/state commit succeeded.
            breakdown = score_replay_reward(outcome)
            detached_info.update(
                base_terminated=base_terminated, base_truncated=base_truncated,
                budget_exhausted=base_truncated,
                reward_terms=dict(step_cost=breakdown.step_cost,
                                  progress=breakdown.progress,
                                  penalty=breakdown.penalty,
                                  completion=breakdown.completion),
            )
            return projected, breakdown.total, ended, False, detached_info
        except Exception:
            # Base may already have committed. Never retry/rescore that transition.
            self._invalidate()
            raise

    def close(self):
        self._closed = True
        self._invalidate()
        self.env.close()
