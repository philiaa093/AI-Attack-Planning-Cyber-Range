import unittest

from agent.planner.rl.q_learning import QLearningAgent


class TestQLearningAgent(unittest.TestCase):

    def test_update_matches_q_learning_formula(self):
        agent = QLearningAgent(
            actions=["ACTION-RECON-001", "ACTION-END-001"],
            alpha=0.5,
            gamma=0.9,
            epsilon=0.0,
            seed=0,
        )

        state = ("DISCOVERY", 10)
        next_state = ("DISCOVERY", 9)

        updated = agent.update(
            state_key=state,
            action="ACTION-RECON-001",
            reward=1.0,
            next_state_key=next_state,
            terminated=False,
        )

        self.assertEqual(updated, 0.5)
        self.assertEqual(
            agent.q_table[state]["ACTION-RECON-001"],
            0.5,
        )

    def test_unknown_action_is_rejected(self):
        agent = QLearningAgent(
            actions=["ACTION-RECON-001"],
            alpha=0.5,
            gamma=0.9,
            epsilon=0.0,
            seed=0,
        )

        with self.assertRaises(ValueError):
            agent.update(
                state_key=("DISCOVERY", 10),
                action="ACTION-UNKNOWN-999",
                reward=0.0,
                next_state_key=("DISCOVERY", 9),
                terminated=False,
            )

    def test_seeded_agent_is_reproducible(self):
        actions = [
            "ACTION-RECON-001",
            "ACTION-END-001",
        ]

        agent_a = QLearningAgent(
            actions=actions,
            alpha=0.5,
            gamma=0.9,
            epsilon=1.0,
            seed=0,
        )
        agent_b = QLearningAgent(
            actions=actions,
            alpha=0.5,
            gamma=0.9,
            epsilon=1.0,
            seed=0,
        )

        selected_a = [
            agent_a.select_action(("DISCOVERY", index))
            for index in range(10)
        ]
        selected_b = [
            agent_b.select_action(("DISCOVERY", index))
            for index in range(10)
        ]

        self.assertEqual(selected_a, selected_b)


if __name__ == "__main__":
    unittest.main()
