from __future__ import annotations

import unittest

from agent.planner.rl.environment import ALLOWED_ACTIONS, BoundedRLEnvironment
from agent.planner.rl.q_learning import QLearningAgent
from agent.planner.rl.trainer import QLearningTrainer


def state_key(state: dict) -> tuple:
    return (
        state["phase"],
        state["remaining_budget"]["actions"],
    )


def reward_fn(state, action, next_state, info) -> float:
    return 1.0 if info["outcome"] == "SUCCESS" else 0.0


class TestQLearningTrainer(unittest.TestCase):
    def _build(self, seed: int):
        environment = BoundedRLEnvironment()
        agent = QLearningAgent(
            actions=ALLOWED_ACTIONS,
            alpha=0.5,
            gamma=0.9,
            epsilon=0.1,
            seed=seed,
        )

        trainer = QLearningTrainer(
            environment=environment,
            agent=agent,
            state_key=state_key,
            reward_fn=reward_fn,
        )

        return trainer, agent

    def _run(self, seed: int):
        trainer, agent = self._build(seed)
        history = trainer.train(episodes=3)
        return history, agent.q_table

    def test_seeded_training_is_reproducible(self):
        history_a, _ = self._run(0)
        history_b, _ = self._run(0)

        self.assertEqual(history_a, history_b)

    def test_seeded_q_table_is_reproducible(self):
        _, q_table_a = self._run(0)
        _, q_table_b = self._run(0)

        self.assertEqual(
            dict(q_table_a),
            dict(q_table_b),
        )


if __name__ == "__main__":
    unittest.main()
