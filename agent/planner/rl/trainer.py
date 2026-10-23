from __future__ import annotations

from collections.abc import Callable
from typing import Any, Hashable

from agent.planner.rl.environment import BoundedRLEnvironment
from agent.planner.rl.q_learning import QLearningAgent


RewardFunction = Callable[
    [dict[str, Any], str, dict[str, Any], dict[str, Any]],
    float,
]


class QLearningTrainer:
    """Reproducible trainer for the bounded local RL environment."""

    def __init__(
        self,
        environment: BoundedRLEnvironment,
        agent: QLearningAgent,
        state_key: Callable[[dict[str, Any]], Hashable],
        reward_fn: RewardFunction,
    ) -> None:
        self.environment = environment
        self.agent = agent
        self.state_key = state_key
        self.reward_fn = reward_fn

    def train(self, episodes: int) -> list[dict[str, Any]]:
        if episodes <= 0:
            raise ValueError("episodes must be greater than zero")

        history: list[dict[str, Any]] = []

        for episode in range(episodes):
            state = self.environment.reset()
            state_key = self.state_key(state)
            total_reward = 0.0
            steps = 0
            terminated = False

            while not terminated:
                action = self.agent.select_action(state_key)

                next_state, _, terminated, info = self.environment.step(action)

                reward = self.reward_fn(
                    state,
                    action,
                    next_state,
                    info,
                )

                next_state_key = self.state_key(next_state)

                self.agent.update(
                    state_key=state_key,
                    action=action,
                    reward=reward,
                    next_state_key=next_state_key,
                    terminated=terminated,
                )

                total_reward += reward
                steps += 1

                state = next_state
                state_key = next_state_key

            history.append(
                {
                    "episode": episode,
                    "steps": steps,
                    "total_reward": total_reward,
                }
            )

        return history
