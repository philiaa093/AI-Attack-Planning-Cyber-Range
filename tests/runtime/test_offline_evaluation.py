"""Offline evaluation protocol acceptance; synthetic selectors, not DQN/PPO."""
import socket
import subprocess
import unittest
from dataclasses import replace
from unittest.mock import patch

import numpy as np

from runtime.evaluation.offline_evaluation import (
    OfflineEvaluationProtocol, ReplayFixture, evaluate_offline,
)
from runtime.evaluation.rl_environment import ReplayAsset, ReplayAssessmentEnv


def fixture(name, count, candidate=True, **kwargs):
    return ReplayFixture(name, name, (ReplayAsset("lab-fixture", count, candidate),),
                         ("lab-fixture",), **kwargs)


def protocol(**kwargs):
    options = dict(train=(fixture("train", 3),),
                   validation=(fixture("validation", 5, False),),
                   test=(fixture("test", 7, None),), episode_seeds=(101, 102))
    options.update(kwargs)
    return OfflineEvaluationProtocol(**options)


def review_selector(observation, mask, rng):
    flags = observation["assets"]
    n = len(flags)
    for slot in range(n):
        if not flags[slot, 0] and mask[slot]:
            return slot
        if not flags[slot, 1] and mask[n + slot]:
            return n + slot
    return 2 * n


class EvaluationTests(unittest.TestCase):
    def test_review_completion_and_metadata_only_metrics(self):
        result = evaluate_offline(protocol(), review_selector, candidate_id="synthetic-rule")
        metrics = result.metrics()
        self.assertEqual(metrics["episodes"], 2)
        self.assertEqual(metrics["completion_rate"], 1)
        self.assertEqual(metrics["mean_decisions_completed"], 3)
        self.assertAlmostEqual(metrics["mean_return"], 1.27)
        self.assertEqual(metrics["refusals"], 0)
        self.assertEqual(result.episodes[0].outcomes,
                         ("INVENTORY_OBSERVED", "REPORT_REVIEWED", "REVIEW_COMPLETE"))
        heldout = evaluate_offline(protocol(), review_selector, candidate_id="synthetic-rule", split="test")
        self.assertIn("REPORT_UNAVAILABLE", heldout.episodes[0].outcomes)
        self.assertTrue(heldout.episodes[0].complete)

    def test_seeded_repeatability(self):
        def random_selector(observation, mask, rng):
            return int(rng.choice(np.flatnonzero(mask)))
        first = evaluate_offline(protocol(), random_selector, candidate_id="synthetic-random")
        second = evaluate_offline(protocol(), random_selector, candidate_id="synthetic-random")
        self.assertEqual(first, second)

    def test_no_valid_action_stops_without_step_or_success(self):
        p = protocol(validation=(replace(fixture("validation", 5), approved_operations=()),))
        with patch.object(ReplayAssessmentEnv, "step", side_effect=AssertionError("unexpected step")):
            result = evaluate_offline(p, review_selector, candidate_id="synthetic-rule")
        self.assertEqual(result.metrics()["empty_masks"], 2)
        self.assertEqual(result.metrics()["completion_rate"], 0)
        self.assertEqual(result.metrics()["mean_decisions_completed"], None)
        self.assertTrue(all(e.decisions == 0 for e in result.episodes))

    def test_masked_proposal_violation_is_not_silently_replaced(self):
        result = evaluate_offline(protocol(), lambda *args: 1, candidate_id="invalid-rule")
        self.assertTrue(all(e.stop_reason == "MASK_VIOLATION" for e in result.episodes))
        self.assertEqual(result.metrics()["invalid_proposals"], 2)
        self.assertEqual(result.metrics()["refusals"], 0)
        self.assertTrue(all(e.decisions == 0 for e in result.episodes))

    def test_unmasked_track_keeps_refusals_in_budget_and_denominator(self):
        result = evaluate_offline(protocol(masking=False), lambda *args: 1,
                                  candidate_id="unmasked-rule")
        self.assertEqual(result.metrics()["completion_rate"], 0)
        self.assertEqual(result.metrics()["refusals"], 40)
        self.assertEqual(result.metrics()["budget_exhaustions"], 2)
        self.assertTrue(all(e.decisions == 20 for e in result.episodes))

    def test_repetition_and_early_finish_are_not_completion(self):
        repeated = evaluate_offline(protocol(), lambda *args: 0, candidate_id="repeat-rule")
        self.assertEqual(repeated.metrics()["repeated_reads"], 38)
        self.assertEqual(repeated.metrics()["budget_exhaustions"], 2)
        early = evaluate_offline(protocol(), lambda *args: 2, candidate_id="early-rule")
        self.assertEqual(early.metrics()["completion_rate"], 0)
        self.assertTrue(all(e.stop_reason == "STOPPED_EARLY" for e in early.episodes))

    def test_malformed_and_policy_error_rows_remain_in_denominator(self):
        for action in (True, -1, 3, 0.0, np.array([0]), "command"):
            with self.subTest(action=action):
                result = evaluate_offline(protocol(), lambda *args: action, candidate_id="bad-rule")
                self.assertEqual(result.metrics()["invalid_proposals"], 2)
                self.assertEqual(result.metrics()["completion_rate"], 0)
                self.assertTrue(all(e.stop_reason == "MALFORMED_PROPOSAL" for e in result.episodes))
        def failing_selector(*args):
            raise RuntimeError("synthetic failure")
        result = evaluate_offline(protocol(), failing_selector, candidate_id="error-rule")
        self.assertEqual(result.metrics()["policy_errors"], 2)

    def test_selector_gets_only_detached_observation_and_mask(self):
        calls = []
        def mutating_selector(observation, mask, rng):
            self.assertEqual(set(observation), {"assets", "inventory_counts", "remaining_budget",
                                                "action_mask", "read_age"})
            action = review_selector(observation, mask, rng)
            calls.append(observation["assets"].copy())
            for value in observation.values():
                value[:] = 0
            mask[:] = False
            return action
        result = evaluate_offline(protocol(), mutating_selector, candidate_id="mutating-rule")
        self.assertEqual(result.metrics()["completion_rate"], 1)
        self.assertEqual(len(calls), 6)

    def test_audit_failure_aborts_evaluation_without_manufacturing_rows(self):
        with patch.object(ReplayAssessmentEnv, "_record", side_effect=OSError("synthetic failure")):
            with self.assertRaises(OSError):
                evaluate_offline(protocol(), review_selector, candidate_id="synthetic-rule")

    def test_disjoint_ids_families_and_semantic_content(self):
        p = protocol()
        bad_validation = (
            replace(p.validation[0], fixture_id="train"),
            replace(p.validation[0], family_id="train"),
            replace(p.train[0], fixture_id="renamed", family_id="renamed",
                    assets=(ReplayAsset("lab-renamed", 3, True),),
                    approved_targets=("lab-renamed",)),
        )
        for bad in bad_validation:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    replace(p, validation=(bad,))
        left = ReplayFixture("left", "left", (ReplayAsset("lab-a", 3), ReplayAsset("lab-b", 4)),
                             ("lab-a", "lab-b"))
        right = replace(left, fixture_id="right", family_id="right", assets=tuple(reversed(left.assets)))
        self.assertEqual(left.content_hash(), right.content_hash())
        self.assertNotEqual(left.identity_record(), right.identity_record())

    def test_matched_spaces_budget_rate_and_fingerprint(self):
        p = protocol()
        for bad in (replace(p.validation[0], max_steps=19),
                    replace(p.validation[0], min_interval_ticks=2),
                    replace(p.validation[0], assets=(ReplayAsset("lab-fixture", 5), ReplayAsset("lab-b", 4)))):
            with self.assertRaises(ValueError):
                replace(p, validation=(bad,))
        self.assertEqual(len(p.fingerprint()), 64)
        self.assertNotEqual(p.fingerprint(), replace(p, masking=False).fingerprint())
        self.assertNotEqual(p.fingerprint(), replace(p, episode_seeds=(103,)).fingerprint())

    def test_protocol_input_validation(self):
        p = protocol()
        for kwargs in (dict(episode_seeds=()), dict(episode_seeds=(1, 1)),
                       dict(episode_seeds=(True,)), dict(episode_seeds=(-1,)),
                       dict(masking=1), dict(train=[]), dict(test=()), dict(validation=(object(),))):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    replace(p, **kwargs)
        for split in ("train", "unknown", None):
            with self.assertRaises(ValueError):
                evaluate_offline(p, review_selector, candidate_id="rule", split=split)
        with self.assertRaises(ValueError):
            evaluate_offline(p, None, candidate_id="rule")
        with self.assertRaises(ValueError):
            evaluate_offline(p, review_selector, candidate_id="not a bounded identifier")

    def test_fixture_input_validation(self):
        f = fixture("fixture", 3)
        for kwargs in (dict(fixture_id="bad id"), dict(family_id="../bad"),
                       dict(assets=[]), dict(approved_targets=("lab-public",)),
                       dict(approved_operations=("dynamic",)), dict(lab_mode=1),
                       dict(max_steps=0), dict(min_interval_ticks=0),
                       dict(approved_targets=("lab-fixture", "lab-fixture"))):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    replace(f, **kwargs)

    def test_offline_sentinels_observe_zero_network_and_process_calls(self):
        with patch.object(socket, "create_connection", side_effect=AssertionError("network")) as connect:
            with patch.object(socket.socket, "connect", side_effect=AssertionError("network")) as raw_connect:
                with patch.object(subprocess, "Popen", side_effect=AssertionError("process")) as process:
                    result = evaluate_offline(protocol(), review_selector, candidate_id="synthetic-rule")
                    self.assertEqual(result.metrics()["completion_rate"], 1)
                    connect.assert_not_called()
                    raw_connect.assert_not_called()
                    process.assert_not_called()


if __name__ == "__main__":
    unittest.main()
