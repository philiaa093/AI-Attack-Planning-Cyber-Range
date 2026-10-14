"""TASK-025: tabular learning for TASK-023 offline metadata replay only.

Replay indices are proposals, never execution authority. TASK-024 scores each
committed simulator outcome once. No scanner, provider or transport integration.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from runtime.evaluation.reward_model import score_replay_reward
from runtime.evaluation.rl_environment import ReplayAssessmentEnv


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("integer outside supported bounds")
    return value


def _number(value, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError("finite number outside supported bounds")
    return float(value)


@dataclass(frozen=True)
class QLearningConfig:
    alpha: float = 0.2
    gamma: float = 0.95
    epsilon_start: float = 1.0
    epsilon_min: float = 0.05
    epsilon_decay: float = 0.99
    seed: int = 25
    max_states: int = 100_000

    def __post_init__(self):
        for name in ("alpha", "gamma", "epsilon_start", "epsilon_min", "epsilon_decay"):
            _number(getattr(self, name), 0, 1)
        if self.alpha == 0 or self.epsilon_decay == 0 or self.epsilon_min > self.epsilon_start:
            raise ValueError("positive alpha/decay and ordered epsilon bounds required")
        _integer(self.seed, 0, 2**32 - 1)
        _integer(self.max_states, 1, 1_000_000)

    def epsilon(self, episode):
        _integer(episode, 0, 10_000)
        return max(self.epsilon_min, self.epsilon_start * self.epsilon_decay**episode)


@dataclass(frozen=True)
class ReplayState:
    """Hashable public observation plus read age derived from committed outcomes.

    Read age -1 means no successful read yet. This accounts for tick-based rate
    history without reading simulator internals or unrevealed fixture metadata.
    """

    assets: tuple
    inventory_counts: tuple
    remaining_budget: float
    action_mask: tuple
    read_age: int = -1

    def __post_init__(self):
        if type(self.assets) is not tuple or not 1 <= len(self.assets) <= 64:
            raise ValueError("bounded immutable asset rows required")
        for row in self.assets:
            if type(row) is not tuple or len(row) != 4:
                raise ValueError("four binary columns required")
            for bit in row:
                _integer(bit, 0, 1)
        if type(self.inventory_counts) is not tuple or len(self.inventory_counts) != len(self.assets):
            raise ValueError("inventory counts must match asset slots")
        for count in self.inventory_counts:
            _integer(count, 0, 10_000)
        _number(self.remaining_budget, 0, 1)
        if type(self.action_mask) is not tuple or len(self.action_mask) != 2 * len(self.assets) + 1:
            raise ValueError("fixed replay mask shape required")
        for bit in self.action_mask:
            _integer(bit, 0, 1)
        _integer(self.read_age, -1, 10_000)

    @classmethod
    def from_observation(cls, observation, action_mask, *, read_age=-1):
        if type(observation) is not dict or set(observation) != {
            "assets", "inventory_counts", "remaining_budget"
        }:
            raise ValueError("closed replay observation required")
        assets = observation["assets"]
        counts = observation["inventory_counts"]
        budget = observation["remaining_budget"]
        arrays = ((assets, np.int8), (counts, np.int32), (budget, np.float32),
                  (action_mask, np.int8))
        if any(type(array) is not np.ndarray or array.dtype != dtype for array, dtype in arrays):
            raise ValueError("typed replay observation arrays required")
        if assets.ndim != 2 or assets.shape[1] != 4 or counts.shape != (assets.shape[0],):
            raise ValueError("invalid replay observation shape")
        if budget.shape != (1,) or action_mask.shape != (2 * assets.shape[0] + 1,):
            raise ValueError("invalid replay budget or mask shape")
        return cls(tuple(tuple(int(b) for b in row) for row in assets),
                   tuple(int(c) for c in counts), float(budget[0]),
                   tuple(int(b) for b in action_mask), read_age)


class QLearningAgent:
    """Sparse Q rows, zero initialization, masked epsilon-greedy and Bellman TD."""

    def __init__(self, n_actions, *, config=None):
        _integer(n_actions, 3, 129)
        if n_actions % 2 != 1:
            raise ValueError("fixed replay action count required")
        config = QLearningConfig() if config is None else config
        if type(config) is not QLearningConfig:
            raise ValueError("QLearningConfig required")
        self.n_actions = n_actions
        self.config = config
        self._rng = np.random.default_rng(config.seed)
        self._q = {}
        self._replay_env = None

    def _check_state(self, state):
        if type(state) is not ReplayState or len(state.action_mask) != self.n_actions:
            raise ValueError("matching validated ReplayState required")

    def values(self, state):
        """Detached values; unseen states read as zero without growing the table."""
        self._check_state(state)
        row = self._q.get(state)
        return np.zeros(self.n_actions, dtype=np.float64) if row is None else row.copy()

    def q_table(self):
        return {state: tuple(float(q) for q in row) for state, row in self._q.items()}

    def select_action(self, state, *, epsilon=0.0):
        self._check_state(state)
        epsilon = _number(epsilon, 0, 1)
        allowed = np.flatnonzero(state.action_mask)
        if not allowed.size:
            return None
        if epsilon > 0 and self._rng.random() < epsilon:
            return int(self._rng.choice(allowed))
        row = self.values(state)
        best = allowed[row[allowed] == row[allowed].max()]
        return int(self._rng.choice(best))  # Seeded tie-breaking avoids index bias.

    def update(self, state, action, reward, next_state, *, episode_ended):
        """Q <- Q + alpha * (r + gamma * max_allowed Q(next) - Q).

        episode_ended includes exhausted intrinsic replay budget. This is not
        generic Gymnasium time-limit handling for continuing environments.
        """
        self._check_state(state)
        self._check_state(next_state)
        _integer(action, 0, self.n_actions - 1)
        reward = _number(reward, -10, 10)
        if type(episode_ended) is not bool:
            raise ValueError("boolean episode boundary required")
        if not state.action_mask[action]:
            raise ValueError("masked action cannot be learned as an admissible decision")
        allowed = np.flatnonzero(next_state.action_mask)
        future = 0.0
        if not episode_ended and allowed.size:
            future = float(self.values(next_state)[allowed].max())
        row = self.values(state)
        td_error = reward + self.config.gamma * future - row[action]
        updated = row[action] + self.config.alpha * td_error
        if not math.isfinite(updated):
            raise ValueError("nonfinite Q update")
        if state not in self._q and len(self._q) >= self.config.max_states:
            raise RuntimeError("Q-table capacity exhausted")
        row[action] = updated
        self._q[state] = row
        return float(td_error)


@dataclass(frozen=True)
class ReplayStep:
    action: int
    outcome: str
    reward: float
    terminated: bool
    truncated: bool


@dataclass(frozen=True)
class EpisodeResult:
    steps: tuple[ReplayStep, ...]
    stop_reason: str

    @property
    def total_reward(self):
        return sum(step.reward for step in self.steps)


def run_replay_episode(env, agent, *, seed, epsilon=0.0, learn=False):
    """Replan from each new observation; evaluator and learner share replay policy.

    Refusal, audit and malformed-input exceptions propagate; no synthetic success.
    No permitted operation means stop without calling step or granting approval.
    """
    if type(env) is not ReplayAssessmentEnv or type(agent) is not QLearningAgent:
        raise ValueError("exact offline replay environment and tabular agent required")
    if env.action_space.n != agent.n_actions:
        raise ValueError("environment action space mismatch")
    _integer(seed, 0, 2**32 - 1)
    _number(epsilon, 0, 1)
    if type(learn) is not bool or (not learn and epsilon != 0):
        raise ValueError("evaluation must be greedy; explicit boolean learn required")
    if agent._replay_env is not None and agent._replay_env is not env:
        raise ValueError("Q-table is bound to one fixed replay environment")
    agent._replay_env = env
    observation, info = env.reset(seed=seed)
    read_age = -1
    state = ReplayState.from_observation(observation, info["action_mask"], read_age=read_age)
    steps = []
    while True:
        action = agent.select_action(state, epsilon=epsilon)
        if action is None:
            return EpisodeResult(tuple(steps), "NO_ADMISSIBLE_ACTION")
        observation, _, terminated, truncated, info = env.step(action)
        # Task 23 commits its audit/state before returning this trusted outcome.
        reward = score_replay_reward(info["outcome"]).total
        if info["outcome"] in {
            "INVENTORY_OBSERVED", "REPORT_REVIEWED", "REPORT_UNAVAILABLE", "NO_PROGRESS"
        }:
            read_age = 0
        elif read_age >= 0:
            read_age += 1
        next_state = ReplayState.from_observation(observation, info["action_mask"], read_age=read_age)
        ended = terminated or truncated
        if learn:
            agent.update(state, action, reward, next_state, episode_ended=ended)
        steps.append(ReplayStep(action, info["outcome"], reward, terminated, truncated))
        if ended:
            return EpisodeResult(tuple(steps), "BUDGET_EXHAUSTED" if truncated else info["outcome"])
        state = next_state


def train_replay(env, *, episodes=500, config=None):
    """Bounded reproducible training on one fixed replay scope; return agent/traces.

    Caller supplies already-approved simulator. No file writing, new approvals or
    durable-evidence claim. A different environment requires a fresh agent.
    """
    if type(env) is not ReplayAssessmentEnv:
        raise ValueError("exact offline replay environment required")
    _integer(episodes, 1, 10_000)
    agent = QLearningAgent(int(env.action_space.n), config=config)
    traces = tuple(run_replay_episode(
        env, agent, seed=(agent.config.seed + episode) % (2**32),
        epsilon=agent.config.epsilon(episode), learn=True,
    ) for episode in range(episodes))
    return agent, traces
