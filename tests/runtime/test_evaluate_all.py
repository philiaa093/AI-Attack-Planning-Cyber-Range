"""Offline pipeline, integrity and paired inference acceptance checks."""
import hashlib
import json
import socket
import subprocess
import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scipy import stats

from runtime.evaluation.evaluate_all import (
    ArtifactRef, ArtifactStore, CANDIDATES, EpisodeKPI, ExperimentRunner,
    MetricsEngine, StatisticalAnalysis, demo_protocol, evaluate_all,
)
from runtime.evaluation.offline_evaluation import evaluate_offline


class EvaluationPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.protocol = demo_protocol()

    def log(self, store, result, *, split="validation"):
        return store.write("fixture.log.json", store.envelope(
            dict(candidate_id=CANDIDATES[0], split=split,
                 protocol_sha256=self.protocol.fingerprint(), terminal="REVIEW_COMPLETE"),
            result,
        ))

    def result(self, selector):
        return json.loads(json.dumps(asdict(evaluate_offline(
            self.protocol, selector, candidate_id=CANDIDATES[0]))))

    def test_end_to_end_artifacts_and_zero_transport(self):
        with patch.object(socket, "create_connection", side_effect=AssertionError("network")) as connect, \
             patch.object(socket.socket, "connect", side_effect=AssertionError("raw network")) as raw, \
             patch.object(subprocess, "Popen", side_effect=AssertionError("process")) as process:
            root = evaluate_all(self.protocol, self.parent, cost_per_step=2)
        for sentinel in (connect, raw, process):
            sentinel.assert_not_called()
        manifest = json.loads((root / "manifest.json").read_text())
        configuration = json.loads((root / "configuration.json").read_text())
        source_hashes = configuration["observed_state"]["source_sha256"]
        repository = Path(__file__).resolve().parents[2]
        self.assertIn("runtime/planners/planner_interface.py", source_hashes)
        self.assertIn("runtime/audit/audit_support.py", source_hashes)
        for name, digest in source_hashes.items():
            self.assertEqual(hashlib.sha256((repository / name).read_bytes()).hexdigest(), digest)
        observed = manifest["observed_state"]
        self.assertEqual(observed["pipeline"], "COMPLETED_OFFLINE")
        self.assertEqual(observed["live_evaluation"], "UNRESOLVED")
        self.assertEqual(len(observed["artifacts"]), 11)
        for ref in observed["artifacts"]:
            self.assertEqual(hashlib.sha256((root / ref["name"]).read_bytes()).hexdigest(), ref["sha256"])
        metrics = json.loads((root / "validation-synthetic-review.metrics.json").read_text())["observed_state"]
        self.assertEqual(metrics["successes"], 5)
        self.assertEqual(metrics["denominator"], 5)
        self.assertEqual(metrics["success_rate"], 1)
        self.assertTrue(all(r["steps"] == 3 and r["cost_credits"] == 6 for r in metrics["episodes"]))
        analysis = json.loads((root / "analysis.json").read_text())["observed_state"]
        self.assertEqual(len(analysis["tests"]), 6)
        self.assertTrue(all(t["n"] == 5 for t in analysis["tests"]))
        self.assertEqual(len(analysis["generalization_gaps"]), 2)
        self.assertIn("monetary/provider cost is unmeasured", (root / "report.md").read_text())

    def test_sequential_data_flow_and_heldout_order(self):
        calls = []
        original_run, original_compute = ExperimentRunner.run, MetricsEngine.compute
        def run(runner, protocol, candidate, split, store):
            calls.append(("runner", split, candidate))
            return original_run(runner, protocol, candidate, split, store)
        def compute(engine, store, ref, protocol, candidate, split, cost):
            self.assertTrue((store.root / ref.name).is_file())
            calls.append(("metrics", split, candidate))
            return original_compute(engine, store, ref, protocol, candidate, split, cost)
        with patch.object(ExperimentRunner, "run", run), patch.object(MetricsEngine, "compute", compute):
            evaluate_all(self.protocol, self.parent)
        expected = [(stage, split, candidate) for split in ("validation", "test")
                    for candidate in CANDIDATES for stage in ("runner", "metrics")]
        self.assertEqual(calls, expected)

    def test_early_stop_and_policy_errors_remain_unsuccessful(self):
        for selector in (lambda o, m, r: 2, lambda *args: (_ for _ in ()).throw(RuntimeError("policy"))):
            with self.subTest(selector=selector):
                store = ArtifactStore(self.parent)
                ref = self.log(store, self.result(selector))
                rows, metric_ref = MetricsEngine().compute(store, ref, self.protocol, CANDIDATES[0], "validation", 1)
                result = store.read_json(metric_ref)["observed_state"]
                self.assertEqual(result["denominator"], 5)
                self.assertEqual(result["exclusions"], 0)
                self.assertEqual(result["success_rate"], 0)
                self.assertTrue(all(not r.success for r in rows))

    def test_budget_exhaustion_remains_in_denominator(self):
        protocol = replace(self.protocol, **{
            split: tuple(replace(f, max_steps=2) for f in getattr(self.protocol, split))
            for split in ("train", "validation", "test")})
        root = evaluate_all(protocol, self.parent)
        metric = json.loads((root / "test-synthetic-review.metrics.json").read_text())["observed_state"]
        self.assertEqual(metric["success_rate"], 0)
        self.assertEqual(metric["stop_reasons"], {"BUDGET_EXHAUSTED": 5})

    def test_hash_tamper_and_unregistered_reference_rejected(self):
        store = ArtifactStore(self.parent)
        ref = ExperimentRunner().run(self.protocol, CANDIDATES[0], "validation", store)
        with (store.root / ref.name).open("ab") as stream:
            stream.write(b" ")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            MetricsEngine().compute(store, ref, self.protocol, CANDIDATES[0], "validation", 1)
        with self.assertRaisesRegex(ValueError, "reference"):
            store.read_json(ArtifactRef(ref.name, "0" * 64))

    def test_duplicate_missing_and_unsupported_success_rejected(self):
        for change in ("duplicate", "missing", "success", "counter", "bool_seed", "extra"):
            with self.subTest(change=change):
                result = self.result(lambda o, m, r: 2)
                episodes = result["episodes"]
                if change == "duplicate":
                    episodes[1] = episodes[0]
                elif change == "missing":
                    result["episodes"] = episodes[:-1]
                elif change == "success":
                    episodes[0]["complete"] = True
                elif change == "counter":
                    episodes[0]["refusals"] = 1
                elif change == "bool_seed":
                    episodes[0]["episode_seed"] = True
                else:
                    episodes[0]["credential"] = "synthetic-placeholder"
                store = ArtifactStore(self.parent)
                ref = self.log(store, result)
                with self.assertRaises(ValueError):
                    MetricsEngine().compute(store, ref, self.protocol, CANDIDATES[0], "validation", 1)

    def test_unknown_candidate_and_cross_split_log_rejected(self):
        store = ArtifactStore(self.parent)
        with self.assertRaises(ValueError):
            ExperimentRunner().run(self.protocol, "live-runner", "validation", store)
        ref = ExperimentRunner().run(self.protocol, CANDIDATES[0], "validation", store)
        with self.assertRaises(ValueError):
            MetricsEngine().compute(store, ref, self.protocol, CANDIDATES[0], "test", 1)

    def test_append_only_runs_and_path_validation(self):
        store = ArtifactStore(self.parent)
        ref = store.write("one.json", {"value": 1})
        original = (store.root / ref.name).read_bytes()
        with self.assertRaises(FileExistsError):
            store.write("one.json", {"value": 2})
        self.assertEqual((store.root / ref.name).read_bytes(), original)
        self.assertNotEqual(store.root, ArtifactStore(self.parent).root)
        for name in ("../escape.json", "C:\\escape.json", "nested/file.json", "..json"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                store.write(name, {})

    def test_write_failure_stops_before_runner_and_preserves_partial_run(self):
        original = ArtifactStore.write
        def fail(store, name, value, **kwargs):
            if name.endswith(".metrics.json"):
                raise OSError("simulated publication failure")
            return original(store, name, value, **kwargs)
        with patch.object(ArtifactStore, "write", fail), \
             patch.object(ExperimentRunner, "run", autospec=True, wraps=None) as run:
            run.side_effect = self.real_runner
            with self.assertRaisesRegex(OSError, "publication failure"):
                evaluate_all(self.protocol, self.parent)
            self.assertEqual(run.call_count, 1)
        root = next(self.parent.iterdir())
        self.assertTrue((root / "configuration.json").exists())
        self.assertTrue((root / "validation-synthetic-review.log.json").exists())
        self.assertFalse((root / "manifest.json").exists())

    real_runner = staticmethod(ExperimentRunner.run)

    def rows(self, seeds=(101, 102, 103, 104, 105)):
        rows = []
        for split in ("validation", "test"):
            fixture = getattr(self.protocol, split)[0].fixture_id
            for candidate in CANDIDATES:
                for index, seed in enumerate(seeds):
                    steps = 3 if candidate == CANDIDATES[0] else [3, 4, 6, 4, 8][index]
                    rows.append(EpisodeKPI(candidate, split, fixture, seed, True, steps, 2 * steps, "REVIEW_COMPLETE"))
        return tuple(rows)

    def test_paired_t_matches_scipy_and_holm_accounts_for_six_tests(self):
        result = StatisticalAnalysis().analyze(self.rows(), self.protocol)
        test = next(t for t in result["tests"] if t["split"] == "test" and t["metric"] == "mean_steps")
        expected = stats.ttest_rel([3, 4, 6, 4, 8], [3] * 5)
        self.assertAlmostEqual(test["statistic"], float(expected.statistic))
        self.assertAlmostEqual(test["pvalue"], float(expected.pvalue))
        self.assertEqual(test["df"], 4)
        self.assertTrue(np.allclose(test["difference"]["ci"], expected.confidence_interval()))
        # Four tied testable p-values, plus two zero-variance comparisons.
        self.assertAlmostEqual(test["pvalue_holm"], min(1, 6 * float(expected.pvalue)))
        self.assertTrue(all(t["pvalue"] is None for t in result["tests"] if t["metric"] == "success_rate"))

    def test_single_seed_and_constant_delta_have_no_inference(self):
        protocol = replace(self.protocol, episode_seeds=(101,))
        result = StatisticalAnalysis().analyze(self.rows((101,)), protocol)
        self.assertTrue(all(t["inference_state"] == "INSUFFICIENT_SEEDS" and t["pvalue"] is None for t in result["tests"]))
        rows = tuple(replace(r, steps=4, cost_credits=8) for r in self.rows())
        result = StatisticalAnalysis().analyze(rows, self.protocol)
        self.assertTrue(all(t["inference_state"] == "ZERO_VARIANCE" and t["reject_h0"] is None for t in result["tests"]))
        json.dumps(result, allow_nan=False)

    def test_stats_rejects_incomplete_pairs_and_nonfinite_configuration(self):
        with self.assertRaisesRegex(ValueError, "matched"):
            StatisticalAnalysis().analyze(self.rows()[:-1], self.protocol)
        for kwargs in ({"cost_per_step": float("nan")}, {"cost_per_step": -1}, {"alpha": True}, {"alpha": 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                evaluate_all(self.protocol, self.parent, **kwargs)
        self.assertEqual(list(self.parent.iterdir()), [])

    def test_multiple_scenarios_aggregate_to_five_seed_units(self):
        protocol = replace(self.protocol, validation=(
            self.protocol.validation[0],
            replace(self.protocol.validation[0], fixture_id="second-standard", family_id="second-standard"),
        ))
        rows = list(self.rows())
        rows.extend(replace(row, fixture_id="second-standard", steps=row.steps + 2,
                            cost_credits=row.cost_credits + 4)
                    for row in self.rows() if row.split == "validation")
        result = StatisticalAnalysis().analyze(tuple(rows), protocol)
        summary = next(s for s in result["summaries"]
                       if s["split"] == "validation" and s["candidate_id"] == CANDIDATES[0])
        self.assertEqual(summary["episodes"], 10)
        self.assertEqual(summary["metrics"]["mean_steps"]["mean"], 4)
        self.assertTrue(all(t["n"] == 5 for t in result["tests"]))


if __name__ == "__main__":
    unittest.main()
