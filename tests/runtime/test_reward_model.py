"""TASK-024: mathematical scoring checks over offline TASK-023 traces only."""
import socket
import subprocess
import unittest
from unittest.mock import patch

from runtime.evaluation.reward_model import score_replay_reward
from runtime.evaluation.rl_environment import OPERATIONS, ReplayAsset, ReplayAssessmentEnv


class RewardModelTests(unittest.TestCase):
    def test_unknown_and_malformed_outcomes_fail_closed(self):
        for value in (None, True, 1, [], {}, "RESET", "", "report_reviewed",
                      "REPORT_REVIEWED ", "EXPLOIT_SUCCESS"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                score_replay_reward(value)

    def test_refusals_cannot_gain_positive_reward(self):
        for label in ("DENIED_RATE", "DENIED_ORDER", "DENIED_LAB_MODE",
                      "DENIED_TARGET", "DENIED_APPROVAL", "DENIED_MALFORMED"):
            with self.subTest(label=label):
                result = score_replay_reward(label)
                self.assertLess(result.total, 0)
                self.assertEqual(result.progress, 0)
                self.assertEqual(result.completion, 0)

    def test_unknown_report_has_no_clean_or_candidate_bonus(self):
        self.assertEqual(score_replay_reward("REPORT_UNAVAILABLE").total,
                         score_replay_reward("REPORT_REVIEWED").total)

    def trace(self, actions, *, candidate=True, **options):
        # Guard the entire replay and scoring, including construction and reset.
        with patch.object(socket, "socket", side_effect=AssertionError("network")), \
                patch.object(subprocess, "Popen", side_effect=AssertionError("process")):
            env = ReplayAssessmentEnv(
                [ReplayAsset("lab-reward-fixture", 3, candidate)],
                approved_targets=["lab-reward-fixture"],
                approved_operations=OPERATIONS, **options)
            try:
                env.reset(seed=24)
                results = []
                for action in actions:
                    _, _, terminated, truncated, info = env.step(action)
                    self.assertEqual(info["network_dispatches"], 0)
                    results.append((score_replay_reward(info["outcome"]),
                                    terminated, truncated))
                return results
            finally:
                env.close()

    def test_report_content_does_not_change_episode_return(self):
        traces = [self.trace([0, 1, 2], candidate=value)
                  for value in (True, False, None)]
        totals = [sum(row[0].total for row in trace) for trace in traces]
        self.assertTrue(all(abs(total - 1.27) < 1e-12 for total in totals))

    def test_duplicate_reads_reduce_return(self):
        efficient = sum(row[0].total for row in self.trace([0, 1, 2]))
        repeated = self.trace([0, 0, 1, 1, 2])
        self.assertEqual([row[0].outcome for row in repeated],
                         ["INVENTORY_OBSERVED", "NO_PROGRESS", "REPORT_REVIEWED",
                          "NO_PROGRESS", "REVIEW_COMPLETE"])
        self.assertAlmostEqual(efficient - sum(row[0].total for row in repeated), 0.22)

    def test_recovery_after_refusal_earns_only_normal_progress(self):
        trace = self.trace([1, 0, 1, 2])
        self.assertEqual(trace[0][0].outcome, "DENIED_ORDER")
        self.assertAlmostEqual(trace[0][0].total, -0.51)
        self.assertAlmostEqual(sum(row[0].total for row in trace), 0.76)
        self.assertTrue(trace[-1][1])

    def test_simulated_rate_noise_is_penalized(self):
        trace = self.trace([0, 1, 1, 2], min_interval_ticks=2)
        self.assertEqual(trace[1][0].outcome, "DENIED_RATE")
        self.assertAlmostEqual(trace[1][0].total, -0.51)

    def test_hard_boundary_does_not_change_environment_stop_semantics(self):
        trace = self.trace([0], lab_mode=False)
        self.assertEqual(trace[0][0].outcome, "DENIED_LAB_MODE")
        self.assertAlmostEqual(trace[0][0].total, -2.01)
        self.assertFalse(trace[0][1])

    def test_early_finish_is_negative_and_terminal(self):
        result, terminated, truncated = self.trace([2])[0]
        self.assertAlmostEqual(result.total, -0.51)
        self.assertTrue(terminated)
        self.assertFalse(truncated)

    def test_budget_cutoff_does_not_mint_completion_reward(self):
        result, terminated, truncated = self.trace([0], max_steps=1)[0]
        self.assertEqual(result.completion, 0)
        self.assertFalse(terminated)
        self.assertTrue(truncated)

    def test_malformed_action_remains_an_exception(self):
        with self.assertRaises(ValueError):
            self.trace([True])


if __name__ == "__main__":
    unittest.main()
