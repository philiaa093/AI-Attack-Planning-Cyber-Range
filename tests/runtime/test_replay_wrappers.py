"""Synthetic reward/mask/finite-horizon acceptance checks; no learned models."""
import math
import unittest
from unittest.mock import patch

import numpy as np
from gymnasium.utils.env_checker import check_env

from runtime.evaluation.replay_wrappers import ReplayRewardMaskWrapper
from runtime.evaluation.reward_model import score_replay_reward
from runtime.evaluation.rl_environment import OPERATIONS, ReplayAsset, ReplayAssessmentEnv


def make_wrapper(*, count=3, candidate=True, **kwargs):
    options = dict(approved_targets=("lab-fixture",), approved_operations=OPERATIONS)
    options.update(kwargs)
    base = ReplayAssessmentEnv([ReplayAsset("lab-fixture", count, candidate)], **options)
    return ReplayRewardMaskWrapper(base)


class WrapperTests(unittest.TestCase):
    def test_gymnasium_api(self):
        env = make_wrapper()
        with self.assertWarns(UserWarning):
            check_env(env, skip_render_check=True)
        env.close()

    def test_normalization_schema_and_detached_arrays(self):
        env = make_wrapper(count=10_000)
        obs, info = env.reset(seed=26)
        self.assertTrue(env.observation_space.contains(obs))
        self.assertEqual(set(obs), {"assets", "inventory_counts", "remaining_budget",
                                    "action_mask", "read_age"})
        self.assertEqual(obs["read_age"].tolist(), [-1])
        self.assertEqual(env.action_masks().dtype, np.bool_)
        mask = env.action_masks()
        mask[:] = False
        obs["action_mask"][:] = 0
        info["action_mask"][:] = 0
        self.assertEqual(env.action_masks().tolist(), [True, False, True])
        obs, _, _, _, _ = env.step(0)
        self.assertEqual(obs["inventory_counts"].tolist(), [1])
        self.assertEqual(obs["read_age"].tolist(), [0])
        self.assertTrue(env.observation_space.contains(obs))
        env.close()

    def test_log_normalization_and_zero_count(self):
        for count in (0, 3, 9999):
            env = make_wrapper(count=count)
            env.reset()
            obs = env.step(0)[0]
            self.assertAlmostEqual(float(obs["inventory_counts"][0]),
                                   math.log1p(count) / math.log1p(10_000), places=6)
            env.close()

    def test_task024_scored_once_and_not_on_reset_or_mask_query(self):
        env = make_wrapper()
        with patch("runtime.evaluation.replay_wrappers.score_replay_reward",
                   wraps=score_replay_reward) as scorer:
            env.reset()
            env.action_masks()
            env.action_masks()
            self.assertEqual(scorer.call_count, 0)
            self.assertAlmostEqual(env.step(0)[1], 0.09)
            self.assertAlmostEqual(env.step(0)[1], -0.11)
            self.assertAlmostEqual(env.step(1)[1], 0.19)
            self.assertAlmostEqual(env.step(2)[1], 0.99)
            self.assertEqual(scorer.call_count, 4)
            with self.assertRaises(RuntimeError):
                env.step(2)
            self.assertEqual(scorer.call_count, 4)
        env.close()

    def test_candidates_do_not_change_reward_and_unknown_is_preserved(self):
        returns, flags = [], []
        for candidate in (True, False, None):
            env = make_wrapper(candidate=candidate)
            env.reset()
            first = env.step(0)
            second = env.step(1)
            third = env.step(2)
            returns.append(first[1] + second[1] + third[1])
            flags.append(second[0]["assets"].tolist()[0])
            env.close()
        self.assertEqual(len(set(returns)), 1)
        self.assertEqual(flags, [[1, 1, 1, 1], [1, 1, 1, 0], [1, 1, 0, 0]])

    def test_ignored_mask_still_gets_policy_refusal(self):
        cases = [({}, "DENIED_ORDER", -0.51, 1),
                 ({"lab_mode": False}, "DENIED_LAB_MODE", -2.01, 0),
                 ({"approved_targets": ()}, "DENIED_TARGET", -2.01, 0),
                 ({"approved_operations": ()}, "DENIED_APPROVAL", -2.01, 0)]
        for options, outcome, reward, action in cases:
            with self.subTest(options=options):
                env = make_wrapper(**options)
                env.reset()
                obs, actual, _, _, info = env.step(action)
                self.assertEqual(info["outcome"], outcome)
                self.assertAlmostEqual(actual, reward)
                self.assertFalse(obs["assets"].any())
                env.close()

    def test_rate_mask_and_read_age_use_committed_reads(self):
        env = make_wrapper(min_interval_ticks=3)
        env.reset()
        env.step(0)
        self.assertEqual(env.action_masks().tolist(), [False, False, True])
        obs, _, _, _, info = env.step(1)
        self.assertEqual(info["outcome"], "DENIED_RATE")
        self.assertAlmostEqual(float(obs["read_age"][0]), 0.0001)
        env.step(1)
        self.assertEqual(env.action_masks().tolist(), [True, True, True])
        obs = env.step(1)[0]
        self.assertEqual(obs["read_age"].tolist(), [0])
        env.close()

    def test_budget_is_intrinsic_terminal_with_base_flags_preserved(self):
        env = make_wrapper(max_steps=1)
        env.reset()
        _, _, terminated, truncated, info = env.step(0)
        self.assertTrue(terminated)
        self.assertFalse(truncated)
        self.assertFalse(info["base_terminated"])
        self.assertTrue(info["base_truncated"])
        self.assertTrue(info["budget_exhausted"])
        self.assertFalse(info["action_mask"].any())
        with self.assertRaises(RuntimeError):
            env.action_masks()
        env.close()

    def test_finish_on_last_step_retains_terminal_precedence(self):
        env = make_wrapper(max_steps=3)
        env.reset()
        env.step(0)
        env.step(1)
        _, _, terminated, truncated, info = env.step(2)
        self.assertTrue(terminated)
        self.assertFalse(truncated or info["budget_exhausted"])
        self.assertEqual(info["outcome"], "REVIEW_COMPLETE")
        env.close()

    def test_malformed_actions_stop_without_scoring(self):
        for action in (True, -1, 3, 0.0, np.array([0]), "READ_INVENTORY"):
            with self.subTest(action=action):
                env = make_wrapper()
                env.reset()
                with patch("runtime.evaluation.replay_wrappers.score_replay_reward") as scorer:
                    with self.assertRaises(ValueError):
                        env.step(action)
                    scorer.assert_not_called()
                with self.assertRaises(RuntimeError):
                    env.action_masks()
                self.assertEqual(env.env.audit_records()[-1]["outcome"], "DENIED_MALFORMED")
                env.close()

    def test_audit_failure_stops_before_reward_and_state_commit(self):
        env = make_wrapper()
        env.reset()
        with patch.object(env.env, "_record", side_effect=OSError("synthetic failure")):
            with patch("runtime.evaluation.replay_wrappers.score_replay_reward") as scorer:
                with self.assertRaises(OSError):
                    env.step(0)
                scorer.assert_not_called()
        self.assertFalse(env.env._assets.any())
        with self.assertRaises(RuntimeError):
            env.step(0)
        env.close()

    def test_scorer_failure_after_commit_cannot_be_retried(self):
        env = make_wrapper()
        env.reset()
        with patch("runtime.evaluation.replay_wrappers.score_replay_reward",
                   side_effect=ValueError("synthetic failure")) as scorer:
            with self.assertRaises(ValueError):
                env.step(0)
            with self.assertRaises(RuntimeError):
                env.step(0)
            self.assertEqual(scorer.call_count, 1)
        self.assertTrue(env.env._assets[0, 0])
        env.close()

    def test_failed_reset_invalidates_previous_mask(self):
        env = make_wrapper()
        env.reset()
        with self.assertRaises(ValueError):
            env.reset(options={"unexpected": True})
        with self.assertRaises(RuntimeError):
            env.action_masks()
        env.close()

    def test_no_silent_repair_of_bad_observation_or_mask(self):
        for field, value in (("remaining_budget", np.array([np.nan], dtype=np.float32)),
                             ("inventory_counts", np.array([10001], dtype=np.int32)),
                             ("inventory_counts", np.array([3.0], dtype=np.float32))):
            env = make_wrapper()
            original = env.env._observation
            def invalid_observation():
                observation = original()
                observation[field] = value
                return observation
            with patch.object(env.env, "_observation", side_effect=invalid_observation):
                with self.assertRaises(ValueError):
                    env.reset()
            with self.assertRaises(RuntimeError):
                env.action_masks()
            env.close()
        env = make_wrapper()
        original = env.env._info
        def invalid_info(outcome):
            info = original(outcome)
            info["action_mask"][0] = 2
            return info
        with patch.object(env.env, "_info", side_effect=invalid_info):
            with self.assertRaises(ValueError):
                env.reset()
        env.close()

    def test_exact_simulator_only_and_audit_preserved_across_reset(self):
        with self.assertRaises(ValueError):
            ReplayRewardMaskWrapper(object())
        env = make_wrapper()
        env.reset()
        env.step(0)
        before = env.env.audit_records()
        obs, _ = env.reset()
        self.assertEqual(env.env.audit_records()[:len(before)], before)
        self.assertFalse(obs["assets"].any())
        env.close()
        with self.assertRaises(RuntimeError):
            env.reset()


if __name__ == "__main__":
    unittest.main()
