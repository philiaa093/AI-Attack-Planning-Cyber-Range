import unittest

from agent.planner.rl.environment import BoundedRLEnvironment


class TestBoundedRLEnvironment(unittest.TestCase):

    def test_reset_returns_expected_state(self):
        env = BoundedRLEnvironment()

        state = env.reset()

        self.assertEqual(state["schema_version"], "1.0")
        self.assertEqual(state["scenario_id"], "SCN-001")
        self.assertEqual(state["objective_id"], "OBJ-001")
        self.assertEqual(state["phase"], "DISCOVERY")
        self.assertEqual(state["remaining_budget"]["actions"], 10)
        self.assertEqual(state["remaining_budget"]["requests"], 20)
        self.assertEqual(state["remaining_budget"]["seconds"], 60.0)
        self.assertEqual(state["observed_facts"], [])
        self.assertEqual(state["previous_actions"], [])

    def test_allowed_action_updates_state(self):
        env = BoundedRLEnvironment()

        env.reset()
        state, reward, terminated, info = env.step("ACTION-RECON-001")

        self.assertEqual(state["remaining_budget"]["actions"], 9)
        self.assertEqual(
            state["previous_actions"],
            ["ACTION-RECON-001"],
        )
        self.assertEqual(reward, 0.0)
        self.assertFalse(terminated)
        self.assertEqual(info["outcome"], "SUCCESS")

    def test_unknown_action_is_rejected(self):
        env = BoundedRLEnvironment()

        env.reset()

        with self.assertRaises(ValueError):
            env.step("ACTION-UNKNOWN-999")


if __name__ == "__main__":
    unittest.main()