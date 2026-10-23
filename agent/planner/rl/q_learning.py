from __future__ import annotations

import random
from collections import defaultdict
from typing import Callable, Hashable, Sequence


class QLearningAgent:
    """Minimal tabular Q-learning baseline for the bounded RL environment."""

    def __init__(
        self,
        actions: Sequence[str],
        alpha: float,
        gamma: float,
        epsilon: float,
        seed: int = 0,
    ) -> None:
        if not actions:
            raise ValueError("actions must not be empty")
        if not 0.0 < alpha <= 1.0:
            raise ValueError("alpha must be in (0, 1]")
        if not 0.0 <= gamma <= 1.0:
            raise ValueError("gamma must be in [0, 1]")
        if not 0.0 <= epsilon <= 1.0:
            raise ValueError("epsilon must be in [0, 1]")

        self.actions = tuple(actions)
        self.alpha = alpha
        self.gamma = gamma
        self.epsilon = epsilon
        self.seed = seed
        self.rng = random.Random(seed)
        self.q_table: dict[Hashable, dict[str, float]] = defaultdict(
            lambda: {action: 0.0 for action in self.actions}
        )

    def select_action(self, state_key: Hashable) -> str:
        if self.rng.random() < self.epsilon:
            return self.rng.choice(self.actions)

        values = self.q_table[state_key]
        max_value = max(values.values())
        candidates = [
            action for action, value in values.items()
            if value == max_value
        ]
        return candidates[0]

    def update(
        self,
        state_key: Hashable,
        action: str,
        reward: float,
        next_state_key: Hashable,
        terminated: bool,
    ) -> float:
        if action not in self.actions:
            raise ValueError(f"Action is not allowlisted: {action}")

        current = self.q_table[state_key][action]

        if terminated:
            target = reward
        else:
            next_max = max(self.q_table[next_state_key].values())
            target = reward + self.gamma * next_max

        updated = current + self.alpha * (target - current)
        self.q_table[state_key][action] = updated

        return updated
