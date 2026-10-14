"""Synthetic TASK-025 learning, mathematical updates and replay boundaries."""
import socket
import subprocess
import unittest
from unittest.mock import patch

import numpy as np

from runtime.evaluation.q_learning import (
    QLearningAgent, QLearningConfig, ReplayState, run_replay_episode, train_replay,
)
from runtime.evaluation.reward_model import score_replay_reward
from runtime.evaluation.rl_environment import OPERATIONS, ReplayAsset, ReplayAssessmentEnv


def make_env(**kwargs):
    options = dict(approved_targets=["lab-fixture"], approved_operations=OPERATIONS,
                   max_steps=6)
    options.update(kwargs)
    return ReplayAssessmentEnv([ReplayAsset("lab-fixture", 3, True)], **options)


def state(mask=(1, 1, 1), budget=1.0, age=-1):
    return ReplayState(((1, 0, 0, 0),), (3,), budget, mask, age)


class QLearningTests(unittest.TestCase):
    def test_sparse_zero_initialization_and_detached_values(self):
        agent = QLearningAgent(3)
        row = agent.values(state())
        self.assertEqual(row.tolist(), [0, 0, 0])
        row[:] = 99
        self.assertEqual(agent.values(state()).tolist(), [0, 0, 0])
        self.assertEqual(agent.q_table(), {})

    def test_bellman_numeric_update(self):
        agent = QLearningAgent(3, config=QLearningConfig(alpha=0.5, gamma=0.5))
        successor = state(budget=0.5)
        agent.update(successor, 1, 4.0, successor, episode_ended=True)
        error = agent.update(state(), 0, 0.2, successor, episode_ended=False)
        self.assertAlmostEqual(error, 1.2)
        self.assertAlmostEqual(agent.values(state())[0], 0.6)
        agent.update(state(), 0, 0.2, successor, episode_ended=False)
        self.assertAlmostEqual(agent.values(state())[0], 0.9)

    def test_bootstrap_excludes_masked_zero_values(self):
        agent = QLearningAgent(3, config=QLearningConfig(alpha=1.0, gamma=0.5))
        successor = state(mask=(1, 0, 0), budget=0.5)
        agent.update(successor, 0, -2.0, successor, episode_ended=True)
        agent.update(state(), 0, -1.0, successor, episode_ended=False)
        self.assertAlmostEqual(agent.values(state())[0], -2.0)

    def test_terminal_and_empty_mask_have_no_bootstrap(self):
        agent = QLearningAgent(3, config=QLearningConfig(alpha=1))
        successor = state(budget=0.5)
        agent.update(successor, 0, 5.0, successor, episode_ended=True)
        agent.update(state(), 1, -0.51, successor, episode_ended=True)
        self.assertAlmostEqual(agent.values(state())[1], -0.51)
        agent.update(state(), 2, -0.1, state(mask=(0, 0, 0)), episode_ended=False)
        self.assertAlmostEqual(agent.values(state())[2], -0.1)

    def test_selection_always_respects_mask_and_stops_when_empty(self):
        agent = QLearningAgent(3)
        for epsilon in (0, 1, 0.3):
            for _ in range(30):
                self.assertEqual(agent.select_action(state(mask=(0, 1, 0)), epsilon=epsilon), 1)
        self.assertIsNone(agent.select_action(state(mask=(0, 0, 0))))

    def test_seeded_ties_do_not_always_choose_first_index(self):
        agent = QLearningAgent(3)
        choices = {agent.select_action(state()) for _ in range(30)}
        self.assertEqual(choices, {0, 1, 2})

    def test_state_keeps_budget_mask_and_visible_rate_history(self):
        env = make_env(min_interval_ticks=4)
        obs, info = env.reset()
        first = ReplayState.from_observation(obs, info["action_mask"])
        obs, _, _, _, info = env.step(0)
        after = ReplayState.from_observation(obs, info["action_mask"], read_age=0)
        self.assertNotEqual(first, after)
        self.assertNotEqual(after, ReplayState.from_observation(obs, info["action_mask"], read_age=1))
        self.assertNotEqual(state(budget=0.5), state(budget=1.0))

    def test_negative_repeat_lowers_q_and_changes_greedy_proposal(self):
        env = make_env()
        env.reset()
        obs, _, _, _, info = env.step(0)
        before = ReplayState.from_observation(obs, info["action_mask"], read_age=0)
        obs, _, ended, truncated, info = env.step(0)
        after = ReplayState.from_observation(obs, info["action_mask"], read_age=0)
        agent = QLearningAgent(3)
        agent.update(before, 0, score_replay_reward(info["outcome"]).total,
                     after, episode_ended=ended or truncated)
        self.assertEqual(info["outcome"], "NO_PROGRESS")
        self.assertLess(agent.values(before)[0], 0)
        self.assertNotEqual(agent.select_action(before), 0)

    def test_training_reproducibility(self):
        first, traces_a = train_replay(make_env(), episodes=100)
        second, traces_b = train_replay(make_env(), episodes=100)
        self.assertEqual(traces_a, traces_b)
        self.assertEqual(first.q_table(), second.q_table())

    def test_tiny_fixture_learns_three_step_review(self):
        env = make_env()
        agent, _ = train_replay(env, episodes=500)
        before = agent.q_table()
        result = run_replay_episode(env, agent, seed=25)
        self.assertEqual([step.action for step in result.steps], [0, 1, 2])
        self.assertEqual(result.stop_reason, "REVIEW_COMPLETE")
        self.assertAlmostEqual(result.total_reward, 1.27)
        self.assertEqual(agent.q_table(), before)

    def test_missing_approval_and_lab_refusal_stop_without_step(self):
        for options in (dict(approved_operations=()), dict(lab_mode=False)):
            with self.subTest(options=options):
                env = make_env(**options)
                with patch.object(env, "step", wraps=env.step) as step:
                    agent, traces = train_replay(env, episodes=2)
                step.assert_not_called()
                self.assertEqual(agent.q_table(), {})
                self.assertTrue(all(t.stop_reason == "NO_ADMISSIBLE_ACTION" for t in traces))

    def test_task24_scored_once_per_committed_step_and_not_reset(self):
        env = make_env(approved_operations=("READ_INVENTORY",), max_steps=2)
        with patch("runtime.evaluation.q_learning.score_replay_reward", wraps=score_replay_reward) as scorer:
            agent, traces = train_replay(env, episodes=1)
        self.assertEqual(scorer.call_count, 2)
        np.testing.assert_allclose([s.reward for s in traces[0].steps], [0.09, -0.11])
        self.assertEqual(traces[0].stop_reason, "BUDGET_EXHAUSTED")
        self.assertTrue(traces[0].steps[-1].truncated)
        self.assertFalse(traces[0].steps[-1].terminated)
        self.assertTrue(any(row[0] < 0 for row in agent.q_table().values()))

    def test_audit_failure_propagates_without_q_update_or_reward(self):
        env = make_env(approved_operations=("READ_INVENTORY",))
        agent = QLearningAgent(3)
        record = env._record

        def fail_step(operation, *args, **kwargs):
            if operation != "RESET":
                raise OSError("audit unavailable")
            return record(operation, *args, **kwargs)

        with patch.object(env, "_record", side_effect=fail_step), \
                patch("runtime.evaluation.q_learning.score_replay_reward") as scorer:
            with self.assertRaises(OSError):
                run_replay_episode(env, agent, seed=25, learn=True)
        self.assertEqual(agent.q_table(), {})
        scorer.assert_not_called()

    def test_training_preserves_audit_and_has_no_network_or_process_calls(self):
        env = make_env()
        env.reset()
        baseline = env.audit_records()
        with patch.object(socket, "socket", side_effect=AssertionError("network")) as sock, \
                patch.object(socket, "create_connection", side_effect=AssertionError("network")) as conn, \
                patch.object(subprocess, "Popen", side_effect=AssertionError("process")) as proc:
            _, traces = train_replay(env, episodes=10)
        sock.assert_not_called()
        conn.assert_not_called()
        proc.assert_not_called()
        self.assertEqual(env.audit_records()[:len(baseline)], baseline)
        self.assertEqual(sum(len(t.steps) for t in traces),
                         sum(r["operation"] != "RESET" for r in env.audit_records()))

    def test_invalid_configuration_and_episode_bounds(self):
        for options in (dict(alpha=0), dict(gamma=float("nan")), dict(alpha=True),
                        dict(epsilon_decay=0), dict(epsilon_min=0.9, epsilon_start=0.1),
                        dict(seed=-1), dict(max_states=True)):
            with self.subTest(options=options), self.assertRaises(ValueError):
                QLearningConfig(**options)
        for episodes in (0, -1, True, 1.0, 10_001):
            with self.subTest(episodes=episodes), self.assertRaises(ValueError):
                train_replay(make_env(), episodes=episodes)

    def test_malformed_observations_and_states_rejected(self):
        env = make_env()
        obs, info = env.reset()
        for name, value in (("remaining_budget", np.array([np.nan], dtype=np.float32)),
                            ("assets", np.ones((1, 4), dtype=np.float64)),
                            ("inventory_counts", np.array([-1], dtype=np.int32))):
            malformed = dict(obs, **{name: value})
            with self.subTest(name=name), self.assertRaises(ValueError):
                ReplayState.from_observation(malformed, info["action_mask"])
        with self.assertRaises(ValueError):
            ReplayState.from_observation(dict(obs, secret="unexpected"), info["action_mask"])
        with self.assertRaises(ValueError):
            state(mask=(1, 2, 0))
        with self.assertRaises(ValueError):
            state(age=True)

    def test_invalid_update_does_not_modify_q_table(self):
        agent = QLearningAgent(3)
        for options in (dict(action=True), dict(reward=float("inf")),
                        dict(episode_ended=1), dict(action=3)):
            args = dict(action=0, reward=0.1, episode_ended=False)
            args.update(options)
            with self.subTest(options=options), self.assertRaises(ValueError):
                agent.update(state(), next_state=state(), **args)
        with self.assertRaises(ValueError):
            agent.update(state(mask=(0, 1, 0)), 0, 0.1, state(), episode_ended=False)
        self.assertEqual(agent.q_table(), {})

    def test_capacity_rejection_preserves_existing_values(self):
        agent = QLearningAgent(3, config=QLearningConfig(max_states=1))
        agent.update(state(), 0, 0.1, state(), episode_ended=True)
        before = agent.q_table()
        with self.assertRaises(RuntimeError):
            agent.update(state(budget=0.5), 0, 0.1, state(), episode_ended=True)
        self.assertEqual(agent.q_table(), before)

    def test_scope_binding_and_greedy_evaluation_validation(self):
        env = make_env()
        agent, _ = train_replay(env, episodes=1)
        with self.assertRaises(ValueError):
            run_replay_episode(make_env(), agent, seed=25)
        with self.assertRaises(ValueError):
            run_replay_episode(env, agent, seed=25, epsilon=0.1)
        with self.assertRaises(ValueError):
            train_replay(object(), episodes=1)


if __name__ == "__main__":
    unittest.main()
