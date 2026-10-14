"""TASK-023: synthetic replay boundaries and read-only state-store integration."""
import hashlib
import json
import socket
import subprocess
import unittest
from unittest.mock import patch

import numpy as np
from gymnasium.utils.env_checker import check_env

from runtime.state.knowledge_state_store import KnowledgeStateStore, StoreContext
from runtime.planners.planner_interface import StateSnapshot
from runtime.evaluation.rl_environment import OPERATIONS, ReplayAsset, ReplayAssessmentEnv


TARGET = "lab-fixture"


def make_env(rows=None, **kwargs):
    rows = [ReplayAsset(TARGET, 3, True)] if rows is None else rows
    options = dict(approved_targets=[a.target_id for a in rows],
                   approved_operations=OPERATIONS)
    options.update(kwargs)
    return ReplayAssessmentEnv(rows, **options)


class ReplayTests(unittest.TestCase):
    def test_gymnasium_checker(self):
        env = make_env()
        check_env(env, skip_render_check=True)
        env.close()

    def test_spaces_and_visibility(self):
        env = make_env()
        obs, info = env.reset(seed=23)
        self.assertTrue(env.observation_space.contains(obs))
        self.assertEqual(env.action_space.n, 3)
        self.assertEqual(obs["assets"].tolist(), [[0, 0, 0, 0]])
        self.assertEqual(info["action_mask"].tolist(), [1, 0, 1])
        obs, _, _, _, _ = env.step(0)
        self.assertEqual(obs["inventory_counts"].tolist(), [3])
        self.assertEqual(obs["assets"].tolist(), [[1, 0, 0, 0]])
        obs, reward, _, _, info = env.step(1)
        self.assertTrue(env.observation_space.contains(obs))
        self.assertAlmostEqual(reward, 0.19)
        self.assertEqual(obs["assets"].tolist(), [[1, 1, 1, 1]])
        self.assertEqual(info["network_dispatches"], 0)

    def test_refusal_rechecks_order_even_when_mask_ignored(self):
        env = make_env()
        env.reset()
        obs, reward, ended, truncated, info = env.step(1)
        self.assertEqual(info["outcome"], "DENIED_ORDER")
        self.assertLess(reward, 0)
        self.assertFalse(ended or truncated)
        self.assertFalse(obs["assets"].any())
        self.assertAlmostEqual(float(obs["remaining_budget"][0]), 0.95)

    def test_missing_approval_defaults_to_denial(self):
        env = ReplayAssessmentEnv([ReplayAsset(TARGET)])
        _, info = env.reset()
        self.assertFalse(info["action_mask"].any())
        self.assertEqual(env.step(0)[4]["outcome"], "DENIED_APPROVAL")

    def test_target_and_operation_approval_are_independent(self):
        for options, outcome in [
            (dict(approved_targets=()), "DENIED_TARGET"),
            (dict(approved_operations=("FINISH",)), "DENIED_APPROVAL"),
            (dict(lab_mode=False), "DENIED_LAB_MODE"),
        ]:
            with self.subTest(options=options):
                env = make_env(**options)
                env.reset()
                obs, _, _, _, info = env.step(0)
                self.assertEqual(info["outcome"], outcome)
                self.assertFalse(obs["assets"].any())

    def test_rate_is_simulated_ticks_and_denials_consume_budget(self):
        env = make_env(min_interval_ticks=2)
        env.reset()
        env.step(0)
        obs, _, _, _, info = env.step(1)
        self.assertEqual(info["outcome"], "DENIED_RATE")
        self.assertEqual(obs["assets"].tolist(), [[1, 0, 0, 0]])
        self.assertEqual(env.step(1)[4]["outcome"], "REPORT_REVIEWED")

    def test_repetition_does_not_mint_reward(self):
        env = make_env()
        env.reset()
        self.assertGreater(env.step(0)[1], 0)
        self.assertEqual(env.step(0)[1], -0.01)
        self.assertGreater(env.step(1)[1], 0)
        self.assertEqual(env.step(1)[1], -0.01)

    def test_candidate_count_does_not_change_reward(self):
        rewards = []
        for report in (True, False, None):
            env = make_env([ReplayAsset(TARGET, 3, report)])
            env.reset()
            env.step(0)
            rewards.append(env.step(1)[1])
        self.assertEqual(len(set(rewards)), 1)

    def test_missing_and_negative_report_remain_distinguishable(self):
        for report, expected, outcome in [
            (None, [1, 1, 0, 0], "REPORT_UNAVAILABLE"),
            (False, [1, 1, 1, 0], "REPORT_REVIEWED"),
        ]:
            env = make_env([ReplayAsset(TARGET, 0, report)])
            env.reset()
            env.step(0)
            obs, _, _, _, info = env.step(1)
            self.assertEqual(obs["assets"].tolist(), [expected])
            self.assertEqual(info["outcome"], outcome)

    def test_termination_and_early_stop(self):
        env = make_env()
        env.reset()
        _, reward, ended, truncated, info = env.step(env.finish_action)
        self.assertTrue(ended)
        self.assertFalse(truncated)
        self.assertLess(reward, 0)
        self.assertEqual(info["outcome"], "STOPPED_EARLY")
        env.reset()
        env.step(0)
        env.step(1)
        _, reward, ended, truncated, info = env.step(env.finish_action)
        self.assertTrue(ended)
        self.assertFalse(truncated)
        self.assertGreater(reward, 0)
        self.assertEqual(info["outcome"], "REVIEW_COMPLETE")
        self.assertFalse(info["action_mask"].any())
        with self.assertRaises(RuntimeError):
            env.step(0)

    def test_budget_truncation_and_terminal_precedence(self):
        env = make_env(max_steps=1)
        env.reset()
        obs, _, ended, truncated, _ = env.step(0)
        self.assertFalse(ended)
        self.assertTrue(truncated)
        self.assertEqual(float(obs["remaining_budget"][0]), 0)
        with self.assertRaises(RuntimeError):
            env.step(0)
        env.reset()
        self.assertEqual(env.step(env.finish_action)[2:4], (True, False))

    def test_invalid_actions_stop_without_observation_change(self):
        for action in (True, np.bool_(False), -1, 3, 1.0, "0", None,
                       np.array(0), np.array([0]), {"action": 0}):
            with self.subTest(action=action):
                env = make_env()
                env.reset()
                with self.assertRaises(ValueError):
                    env.step(action)
                self.assertFalse(env._assets.any())
                self.assertEqual(env._steps, 0)
                self.assertEqual(env.audit_records()[-1]["outcome"], "DENIED_MALFORMED")
                with self.assertRaises(RuntimeError):
                    env.step(0)
        env = make_env()
        env.reset()
        self.assertEqual(env.step(np.int64(0))[4]["outcome"], "INVENTORY_OBSERVED")

    def test_reset_restores_state_and_preserves_audit(self):
        env = make_env()
        env.reset(seed=23)
        env.step(0)
        before = env.audit_records()
        obs, _ = env.reset(seed=23)
        self.assertFalse(obs["assets"].any())
        self.assertFalse(obs["inventory_counts"].any())
        self.assertEqual(float(obs["remaining_budget"][0]), 1)
        self.assertEqual(env.audit_records()[:len(before)], before)
        self.assertEqual(env.audit_records()[0]["episode_id"], "EPISODE-1")
        self.assertEqual(env.audit_records()[-1]["episode_id"], "EPISODE-2")

    def test_reset_audit_failure_stops_without_erasing_prior_state(self):
        env = make_env()
        env.reset()
        env.step(0)
        before = env.audit_records()
        with patch.object(env, "_record", side_effect=OSError("audit unavailable")):
            with self.assertRaises(OSError):
                env.reset()
        self.assertEqual(env._assets.tolist(), [[1, 0, 0, 0]])
        self.assertEqual(env.audit_records(), before)
        with self.assertRaises(RuntimeError):
            env.step(0)

    def test_outputs_and_input_collection_are_detached(self):
        rows = [ReplayAsset(TARGET, 3, True)]
        env = make_env(rows)
        rows.clear()
        obs, info = env.reset()
        obs["assets"][:] = 1
        info["action_mask"][:] = 0
        self.assertEqual(env.step(1)[4]["outcome"], "DENIED_ORDER")
        audit = env.audit_records()
        audit[0]["outcome"] = "changed"
        self.assertEqual(env.audit_records()[0]["outcome"], "RESTORE")

    def test_audit_hash_and_minimized_info(self):
        env = make_env()
        _, info = env.reset()
        env.step(0)
        for record in env.audit_records():
            sha = record.pop("sha256")
            text = json.dumps(record, sort_keys=True, separators=(",", ":"))
            self.assertEqual(sha, hashlib.sha256(text.encode()).hexdigest())
            self.assertTrue(record["timestamp_utc"].endswith("Z"))
            self.assertEqual(record["source"], "SIMULATED_FIXTURE")
            self.assertEqual(record["redaction"], "METADATA_ONLY")
        self.assertEqual(set(info), {"action_mask", "outcome", "provenance", "network_dispatches"})

    def test_audit_failure_blocks_state_commit(self):
        env = make_env()
        env.reset()
        with patch.object(env, "_record", side_effect=OSError("audit unavailable")):
            with self.assertRaises(OSError):
                env.step(0)
        self.assertFalse(env._assets.any())
        self.assertEqual(env._steps, 0)
        with self.assertRaises(RuntimeError):
            env.step(0)

    def test_invalid_configuration(self):
        for rows in ([], [object()], [ReplayAsset(TARGET)] * 2,
                     [ReplayAsset(f"lab-{i}") for i in range(65)]):
            with self.subTest(rows=rows):
                with self.assertRaises(ValueError):
                    ReplayAssessmentEnv(rows)
        for options in (dict(max_steps=True), dict(max_steps=0), dict(max_steps=10001),
                        dict(min_interval_ticks=0), dict(lab_mode=1),
                        dict(approved_targets=["lab-other"]),
                        dict(approved_targets="lab-fixture"),
                        dict(approved_operations=["RUN_SCANNER"])):
            with self.subTest(options=options):
                with self.assertRaises(ValueError):
                    make_env(**options)
        for args in (("https://example.com",), (TARGET, -1), (TARGET, True),
                     (TARGET, 10001), (TARGET, 0, 1)):
            with self.assertRaises(ValueError):
                ReplayAsset(*args)

    def test_reset_input_close_and_pre_reset_step(self):
        env = make_env()
        with self.assertRaises(RuntimeError):
            env.step(0)
        for options in ([], {"target": "lab-other"}):
            with self.assertRaises(ValueError):
                env.reset(options=options)
        for seed in (True, -1, "23", 1.5):
            with self.assertRaises(ValueError):
                env.reset(seed=seed)
        env.reset()
        env.close()
        with self.assertRaises(RuntimeError):
            env.reset()

    def test_multiple_assets_use_fixed_slots(self):
        env = make_env([ReplayAsset(TARGET, 3, True), ReplayAsset("lab-other", 1, False)])
        env.reset()
        env.step(1)
        obs = env.step(3)[0]
        self.assertEqual(obs["assets"].tolist(), [[0, 0, 0, 0], [1, 1, 1, 0]])
        self.assertEqual(env.target_ids, (TARGET, "lab-other"))

    def test_no_transport_or_process_launch(self):
        with patch.object(socket, "socket", side_effect=AssertionError("network")), \
             patch.object(socket, "create_connection", side_effect=AssertionError("network")), \
             patch.object(subprocess, "Popen", side_effect=AssertionError("process")):
            env = make_env()
            env.reset(seed=23)
            env.step(0)
            env.step(1)
            env.step(2)


class SnapshotTests(unittest.TestCase):
    def test_store_snapshot_read_only_unknown_and_minimized_projection(self):
        context = StoreContext("RUN-023", "SESSION-1", "EPISODE-1")
        with KnowledgeStateStore(":memory:") as store:
            store.create_context(context, scenario_id="SCN-001", objective_id="OBJ-023",
                                 budget=dict(actions=20, requests=10, seconds=60.0),
                                 allowed_subjects={TARGET, "lab-other"},
                                 allowed_actions={"ACTION-RECON-001"})
            observation = dict(
                observation_id="OBS-023", run_id=context.run_id,
                action_id="ACTION-RECON-001", timestamp_utc="2026-10-12T00:00:00Z",
                outcome="PARTIAL", evidence_refs=[], new_facts=[
                    dict(fact_id="F-1", fact_type="ENDPOINT", subject=TARGET,
                         value="/private-fixture-route", confidence=0.7),
                    dict(fact_id="F-2", fact_type="CANDIDATE_FINDING", subject=TARGET,
                         value="candidate_metadata", confidence=0.0),
                ])
            store.ingest(context, observation, source="SIMULATED_FIXTURE",
                         source_sha256=hashlib.sha256(b"fixture").hexdigest())
            before = store.get_state(context)
            snapshot = StateSnapshot.from_store(store, context=context)
            env = ReplayAssessmentEnv.from_snapshot(
                snapshot, targets=[TARGET, "lab-other"],
                approved_targets=[TARGET, "lab-other"], approved_operations=OPERATIONS)
            env.reset()
            env.step(0)
            obs, _, _, _, info = env.step(2)
            self.assertEqual(obs["inventory_counts"].tolist(), [1, 0])
            self.assertEqual(obs["assets"].tolist(), [[1, 1, 1, 1], [0, 0, 0, 0]])
            self.assertEqual(info["provenance"], "OFFLINE_STATE_SNAPSHOT")
            env.step(1)
            self.assertEqual(env.step(3)[4]["outcome"], "REPORT_UNAVAILABLE")
            env.reset()
            self.assertEqual(store.get_state(context), before)
            self.assertEqual(store.reconstruct(context), before)
            self.assertNotIn("/private-fixture-route", json.dumps(env.audit_records()))
            self.assertEqual(env.audit_records()[0]["source_sha256"], snapshot.revision)

    def test_snapshot_adapter_rejects_untyped_input(self):
        with self.assertRaises(ValueError):
            ReplayAssessmentEnv.from_snapshot({}, targets=[TARGET])


if __name__ == "__main__":
    unittest.main()
