from __future__ import annotations

import unittest

from agent.planner.rl.reward import RewardCoefficients, RewardModel


class TestRewardModel(unittest.TestCase):
    def setUp(self) -> None:
        self.model = RewardModel(RewardCoefficients())

        self.state = {
            "phase": "DISCOVERY",
            "remaining_budget": {
                "actions": 10,
                "requests": 20,
                "seconds": 60.0,
            },
        }

        self.next_state = {
            "phase": "DISCOVERY",
            "remaining_budget": {
                "actions": 9,
                "requests": 20,
                "seconds": 60.0,
            },
        }

        self.info = {
            "outcome": "SUCCESS",
        }

    def test_unresolved_coefficients_are_rejected(self):
        with self.assertRaisesRegex(
            ValueError,
            "Reward coefficients are unresolved",
        ):
            self.model.calculate(
                self.state,
                "ACTION-RECON-001",
                self.next_state,
                self.info,
            )

    def test_invalid_state_is_rejected(self):
        with self.assertRaises(TypeError):
            self.model.calculate(
                [],
                "ACTION-RECON-001",
                self.next_state,
                self.info,
            )

    def test_invalid_next_state_is_rejected(self):
        with self.assertRaises(TypeError):
            self.model.calculate(
                self.state,
                "ACTION-RECON-001",
                [],
                self.info,
            )

    def test_invalid_info_is_rejected(self):
        with self.assertRaises(TypeError):
            self.model.calculate(
                self.state,
                "ACTION-RECON-001",
                self.next_state,
                [],
            )

    def test_empty_action_is_rejected(self):
        with self.assertRaises(ValueError):
            self.model.calculate(
                self.state,
                "",
                self.next_state,
                self.info,
            )


if __name__ == "__main__":
    unittest.main()
