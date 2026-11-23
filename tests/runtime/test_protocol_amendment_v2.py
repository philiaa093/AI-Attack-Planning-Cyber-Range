"""Development-only V1/V2 contract, exact request and provenance regressions."""
from __future__ import annotations

import dataclasses
import hashlib
import http.client
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from evaluation.experiments import benchmark_preflight, run_benchmark
from evaluation.experiments.source_snapshot import (
    FROZEN_PROTOCOL_ID, PROPOSED_PROTOCOL_ID_V2, RELEVANT_SOURCE_FILES,
    build_source_snapshot, get_git_status,
)
from runtime.planners.candidate_generator import CandidateGenerator
from runtime.planners.hybrid_planner import (
    HYBRID_PLANNER_PROMPT_V1, HYBRID_PLANNER_PROMPT_V2,
    HYBRID_PLANNER_SYSTEM_PROMPT, HYBRID_RANKING_FOOTER_V2,
    HybridPlanner, parse_hybrid_ranking_json_v2,
)
from runtime.planners.llm_planner import (
    ATTACK_PLANNER_SYSTEM_PROMPT, LLM_SELECTION_FOOTER_V1,
    LLMPlanner, serialize_llm_context,
)
from runtime.planners.planner_context import PlannerDecisionContext
from runtime.planners.real_provider_adapter import RealLLMProviderAdapter, RealLLMProviderConfig
from runtime.planners.symbolic_scorer import HybridScoringConfig
from runtime.simulation.environment import EpisodeEnvironment
from shared.schema_validation import validate_shape

ROOT = Path(__file__).resolve().parents[2]
AMENDMENT = json.loads((ROOT / "evaluation/experiments/protocol_amendment_v2.json").read_text(encoding="utf-8"))
FIXTURE = AMENDMENT["effective_request_fixture"]
S1 = ROOT / FIXTURE["scenario"]


def sha(data: bytes | str) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


class MockConnection:
    """Injected transport only; never creates a socket."""

    def __init__(self, response: str):
        self.response = response
        self.requests = []

    def request(self, method, path, body=None, headers=None):
        self.requests.append((method, path, body))

    def getresponse(self):
        return self

    status = 200

    def read(self, _amount):
        return json.dumps({"choices": [{"message": {"content": self.response}}]}).encode()

    def close(self):
        pass


class TestProtocolAmendmentV2(unittest.TestCase):
    def setUp(self):
        self.env = EpisodeEnvironment(S1, run_id=FIXTURE["hybrid"]["run_id"], random_seed=1001)
        belief = self.env.get_belief_state()
        candidates = CandidateGenerator().generate(belief)
        self.context = PlannerDecisionContext(
            run_id=FIXTURE["hybrid"]["run_id"], step_index=0, max_steps=10,
            current_phase="RECON", remaining_budget=10, max_budget=10,
            visible_target_ids=frozenset(belief.visible_target_ids), belief_state=belief,
            candidate_proposals=candidates.all_proposals,
            eligible_proposals=candidates.eligible_proposals,
            rejected_proposals=candidates.rejected_proposals,
            objective_statement="Access target crown jewels",
        )
        self.http_guard = patch.object(http.client, "HTTPConnection", side_effect=AssertionError("REAL_HTTP_FORBIDDEN"))
        self.https_guard = patch.object(http.client, "HTTPSConnection", side_effect=AssertionError("REAL_HTTPS_FORBIDDEN"))
        self.http_guard.start()
        self.https_guard.start()
        self.addCleanup(self.http_guard.stop)
        self.addCleanup(self.https_guard.stop)
        estimator = patch.object(RealLLMProviderAdapter, "estimate_prompt_tokens", return_value=1)
        estimator.start()
        self.addCleanup(estimator.stop)

    def provider(self, response):
        conn = MockConnection(response)
        cfg = RealLLMProviderConfig(
            provider_type=FIXTURE["provider_type"], model=FIXTURE["model"], api_base=FIXTURE["api_base"],
        )
        return RealLLMProviderAdapter(config=cfg, http_transport_factory=lambda *a, **k: conn), conn

    @staticmethod
    def ranking(keys=None, **fields):
        return {"ranked_candidate_keys": ["CAND-001"] if keys is None else keys,
                "reason_code": "STRATEGIC_PRIORITY", "brief_justification": "Development fixture", **fields}

    def decide(self, response, version=HYBRID_PLANNER_PROMPT_V2, context=None):
        provider, conn = self.provider(response)
        planner = HybridPlanner(provider=provider, scoring_config=HybridScoringConfig.frozen(), prompt_version=version)
        decision = planner.plan_decision(context or self.context)
        self.assertEqual(self.env.step_count, 0)
        return decision, planner, provider, conn

    def test_exact_v1_v2_requests_and_unchanged_context(self):
        for name in ("pure_llm", "hybrid"):
            for version in ("v1", "v2"):
                with self.subTest(planner=name, version=version):
                    ctx = dataclasses.replace(self.context, run_id=FIXTURE[name]["run_id"])
                    provider, conn = self.provider(json.dumps(self.ranking()))
                    if name == "pure_llm":
                        conn.response = json.dumps({"selected_candidate_key": "CAND-001", "reason_code": "RECON", "brief_justification": "Initial recon"})
                        decision = LLMPlanner(provider=provider, fallback_to_rule=False).plan_decision(ctx)
                    else:
                        prompt_version = HYBRID_PLANNER_PROMPT_V1 if version == "v1" else HYBRID_PLANNER_PROMPT_V2
                        decision = HybridPlanner(provider=provider, scoring_config=HybridScoringConfig.frozen(), prompt_version=prompt_version).plan_decision(ctx)
                    body = conn.requests[0][2]
                    payload = json.loads(body)
                    content = payload["messages"][0]["content"]
                    self.assertEqual(payload["messages"], [{"role": "user", "content": content}])
                    self.assertEqual(sha(body), FIXTURE[name][f"request_body_sha256_{version}"])
                    self.assertEqual(sha(content), FIXTURE[name][f"effective_prompt_sha256_{version}"])
                    self.assertEqual(decision.metadata["prompt_hash"], sha(content))
                    self.assertEqual(provider.request_history[0]["effective_request_sha256"], sha(body))
                    self.assertEqual(set(payload), {"model", "messages", "max_tokens", "temperature", "top_p", "stream"})
                    self.assertEqual((payload["max_tokens"], payload["temperature"], payload["top_p"], payload["stream"]), (512, 0.0, 1.0, False))
                    footer = HYBRID_RANKING_FOOTER_V2 if name == "hybrid" and version == "v2" else LLM_SELECTION_FOOTER_V1
                    self.assertTrue(content.endswith(footer))
                    if name == "hybrid" and version == "v2":
                        self.assertNotIn(LLM_SELECTION_FOOTER_V1, content)
        original = serialize_llm_context(self.context, HYBRID_PLANNER_SYSTEM_PROMPT)
        amended = serialize_llm_context(self.context, HYBRID_PLANNER_SYSTEM_PROMPT, task_footer=HYBRID_RANKING_FOOTER_V2)
        self.assertEqual(original[2:], amended[2:])

    def test_valid_rankings_reach_exact_frozen_fusion(self):
        for keys in (["CAND-001"], ["CAND-002", "CAND-001"]):
            for fenced in (False, True):
                with self.subTest(keys=keys, fenced=fenced):
                    raw = json.dumps(self.ranking(keys))
                    decision, planner, _, _ = self.decide(f"```json\n{raw}\n```" if fenced else raw)
                    meta = decision.metadata
                    self.assertTrue(meta["semantic_component_valid"])
                    self.assertTrue(meta["semantic_contribution_used"])
                    self.assertFalse(meta["fallback_used"])
                    self.assertEqual(meta["weights_hash"], AMENDMENT["unchanged_controls"]["frozen_weights_hash"])
                    self.assertEqual(planner.metrics["valid_semantic_rankings"], 1)
                    self.assertEqual(meta["output_schema_version"], "HYBRID_OUTPUT_SCHEMA_V2")
                    for score in meta["all_candidate_scores"]:
                        expected = (.4 * score["semantic_score"] + .3 * score["progress_score"]
                                    - .1 * score["noise_cost_norm"] - .05 * score["step_cost_norm"]
                                    - .15 * score["repeat_penalty"] - .2 * score["failure_penalty"])
                        self.assertAlmostEqual(score["fused_score"], expected, places=4)
                    if keys[0] == "CAND-002":
                        self.assertEqual(meta["selected_candidate"], "CAND-002")

    def test_invalid_rankings_never_contribute_or_become_provider_errors(self):
        missing_rank = self.ranking()
        del missing_rank["ranked_candidate_keys"]
        missing_reason = self.ranking()
        del missing_reason["reason_code"]
        missing_justification = self.ranking()
        del missing_justification["brief_justification"]
        cases = [None, [], 1, "text", {}, missing_rank, missing_reason, missing_justification,
                 self.ranking([]), self.ranking("CAND-001"), self.ranking({}),
                 self.ranking([123]), self.ranking([False]), self.ranking([None]),
                 self.ranking([{}]), self.ranking([[]]), self.ranking(["CAND-999"]),
                 self.ranking(["CAND-001", "CAND-001"]),
                 self.ranking(reason_code=123), self.ranking(reason_code=None),
                 self.ranking(brief_justification=[]), self.ranking(brief_justification=None),
                 {"selected_candidate_key": "CAND-001"}]
        raw_cases = [json.dumps(case) for case in cases]
        raw_cases += ['{"ranked_candidate_keys":["CAND-001"',
                      'prose ' + json.dumps(self.ranking()),
                      '{"ranked_candidate_keys":["CAND-001"],"ranked_candidate_keys":[],"reason_code":"x","brief_justification":"x"}',
                      json.dumps(self.ranking(extra=float("nan"))),
                      json.dumps(self.ranking()).replace('"Development fixture"', '1e999')]
        for raw in raw_cases:
            with self.subTest(raw=raw):
                decision, planner, _, _ = self.decide(raw)
                meta = decision.metadata
                self.assertFalse(meta["semantic_component_valid"])
                self.assertFalse(meta["semantic_contribution_used"])
                self.assertTrue(meta["fallback_used"])
                self.assertEqual(meta["semantic_fallback_mode"], "SYMBOLIC_ONLY")
                self.assertIsNotNone(meta["semantic_validation_error"])
                self.assertEqual(planner.metrics["provider_errors"], 0)
                self.assertEqual(planner.metrics["valid_semantic_rankings"], 0)
                self.assertEqual(meta["scoring_weights"]["w_semantic"], 0)
                for score in meta["all_candidate_scores"]:
                    self.assertIsNone(score["semantic_rank"])
                    self.assertEqual(score["semantic_score"], 0)

    def test_v1_leniency_and_single_candidate_history_remain_selectable(self):
        for response in ({"ranked_candidate_keys": []}, {"ranked_candidate_keys": ["CAND-001"]},
                         self.ranking(reason_code=123, brief_justification=[])):
            decision, _, _, _ = self.decide(json.dumps(response), HYBRID_PLANNER_PROMPT_V1)
            self.assertTrue(decision.metadata["semantic_component_valid"])
            self.assertFalse(decision.metadata["fallback_used"])
        single = dataclasses.replace(self.context, eligible_proposals=self.context.eligible_proposals[:1])
        legacy, _, _, conn = self.decide("unused", HYBRID_PLANNER_PROMPT_V1, single)
        self.assertTrue(legacy.metadata["semantic_component_valid"])
        self.assertEqual(legacy.metadata["normalized_semantic_score"], 1)
        self.assertEqual(conn.requests, [])
        current, planner, _, conn = self.decide("unused", context=single)
        self.assertFalse(current.metadata["semantic_component_valid"])
        self.assertFalse(current.metadata["semantic_contribution_used"])
        self.assertFalse(current.metadata["fallback_used"])
        self.assertEqual(current.metadata["normalized_semantic_score"], 0)
        self.assertEqual(current.metadata["semantic_call_skipped_reason"], "SINGLE_CANDIDATE")
        self.assertEqual(planner.metrics["semantic_calls"], 0)
        self.assertEqual(conn.requests, [])

    def test_empty_candidate_set_has_explicit_v2_identity_without_semantics(self):
        context = dataclasses.replace(self.context, eligible_proposals=())
        decision, _, _, conn = self.decide("unused", context=context)
        self.assertFalse(decision.metadata["semantic_component_valid"])
        self.assertFalse(decision.metadata["semantic_contribution_used"])
        self.assertEqual(decision.metadata["prompt_version"], HYBRID_PLANNER_PROMPT_V2)
        self.assertEqual(conn.requests, [])

    def test_v1_pins_system_hashes_weights_and_heldout_bytes(self):
        for path, expected in AMENDMENT["pinned_v1_files"].items():
            self.assertEqual(sha((ROOT / path).read_bytes()), expected, path)
        for name, text in (("pure_llm", ATTACK_PLANNER_SYSTEM_PROMPT), ("hybrid", HYBRID_PLANNER_SYSTEM_PROMPT)):
            for version in ("v1", "v2"):
                self.assertEqual(sha(text), AMENDMENT["prompt_contracts"][name][f"system_prompt_sha256_{version}"])
        self.assertEqual(HybridScoringConfig.frozen().weights_hash(), AMENDMENT["unchanged_controls"]["frozen_weights_hash"])
        self.assertEqual(HybridScoringConfig().weights_hash(), AMENDMENT["unchanged_controls"]["weights_hash_v1"])
        manifest = json.loads((ROOT / "evaluation/datasets/held_out/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["scenarios"]), 12)
        for entry in manifest["scenarios"]:
            self.assertEqual(sha((ROOT / "evaluation/datasets/held_out" / entry["filename"]).read_bytes()), entry["sha256"])

    def test_protocol_selection_provenance_and_unsealed_guard(self):
        with tempfile.TemporaryDirectory() as temp:
            legacy = run_benchmark.BenchmarkRunner(results_dir=Path(temp) / "v1")
            current = run_benchmark.BenchmarkRunner(results_dir=Path(temp) / "v2", protocol_version=PROPOSED_PROTOCOL_ID_V2)
            self.assertEqual(len(legacy.load_pre_registered_matrix()), 420)
            with self.assertRaisesRegex(run_benchmark.BenchmarkAuthorizationError, "V2_PROTOCOL_NOT_SEALED"):
                current.load_pre_registered_matrix()
            for planner_id in ("HYBRID_FULL", "HYBRID_NO_NOISE", "HYBRID_NO_PENALTIES", "HYBRID_SEMANTIC_ONLY", "HYBRID_SYMBOLIC_ONLY"):
                self.assertEqual(legacy.instantiate_planner(planner_id)[0].prompt_version, HYBRID_PLANNER_PROMPT_V1)
                self.assertEqual(current.instantiate_planner(planner_id)[0].prompt_version, HYBRID_PLANNER_PROMPT_V2)
            with patch.object(run_benchmark, "EpisodeEnvironment", side_effect=AssertionError("NO_ENVIRONMENT")), patch.object(current.preflight_checker, "run_preflight", side_effect=AssertionError("NO_EXECUTION_PREFLIGHT")):
                with self.assertRaisesRegex(run_benchmark.BenchmarkAuthorizationError, "V2_PROTOCOL_NOT_SEALED"):
                    current.check_held_out_execution_authorization(authorize_rt07b=True)
                spec = legacy.load_pre_registered_matrix()[0]
                for path in (ROOT / "evaluation/datasets/held_out/scenario_h01_straight.json", Path(temp) / S1.name):
                    with self.assertRaises(run_benchmark.BenchmarkAuthorizationError):
                        current.run_episode(spec, path)
                with self.assertRaises(run_benchmark.BenchmarkAuthorizationError):
                    current.run_episode({**spec, "protocol_version": FROZEN_PROTOCOL_ID}, S1)
        for factory in (run_benchmark.BenchmarkRunner, benchmark_preflight.BenchmarkPreflightChecker, build_source_snapshot):
            with self.assertRaises(ValueError):
                factory(protocol_version="UNKNOWN")
        for version in ("HYBRID_ATTACK_PLANNER_V3", None, 2, True, b"V2", [], {}):
            provider, conn = self.provider("unused")
            with self.assertRaises(ValueError):
                HybridPlanner(provider=provider, prompt_version=version)
            self.assertEqual(conn.requests, [])
        checker = benchmark_preflight.BenchmarkPreflightChecker(protocol_version=PROPOSED_PROTOCOL_ID_V2)
        checks = checker.verify_v2_amendment()
        self.assertTrue(any(c.code == "V2_PROTOCOL_NOT_SEALED" and c.is_blocker and not c.passed for c in checks))
        self.assertTrue(next(c for c in checks if c.code == "CHK-V2-PINS").passed)
        with patch.object(benchmark_preflight, "compute_file_sha256", return_value="0" * 64):
            self.assertFalse(next(c for c in checker.verify_v2_amendment() if c.code == "CHK-V2-PINS").passed)

    def test_v2_development_result_schema_and_per_episode_request_provenance(self):
        provider, _ = self.provider(json.dumps(self.ranking(["CAND-002", "CAND-001"])))
        with tempfile.TemporaryDirectory() as temp:
            runner = run_benchmark.BenchmarkRunner(results_dir=Path(temp), protocol_version=PROPOSED_PROTOCOL_ID_V2, provider=provider)
            spec = {"protocol_version": PROPOSED_PROTOCOL_ID_V2, "planner_id": "HYBRID_FULL", "scenario_id": "SCN-DEV-S1"}
            first_result = runner.run_episode({**spec, "experiment_id": "DEV_V2_FIRST"}, S1)
            first = first_result.to_dict()
            second = runner.run_episode({**spec, "experiment_id": "DEV_V2_SECOND"}, S1).to_dict()
            saved_file = Path(temp) / "DEV_V2_FIRST.json"
            original_bytes = saved_file.read_bytes()
            runner.save_episode_result(first_result)
            self.assertEqual(saved_file.read_bytes(), original_bytes)
            changed_provenance = {**first_result.prompt_provenance, "requests": [
                {**first_result.prompt_provenance["requests"][0], "effective_request_sha256": "f" * 64}
            ]}
            with self.assertRaises(FileExistsError):
                runner.save_episode_result(dataclasses.replace(first_result, prompt_provenance=changed_provenance))
            self.assertEqual(saved_file.read_bytes(), original_bytes)
            schema = json.loads((ROOT / "evaluation/results/result_v2.schema.json").read_text(encoding="utf-8"))
            for result in (first, second):
                self.assertEqual(result["protocol_version"], PROPOSED_PROTOCOL_ID_V2)
                self.assertTrue(result["experiment_id"].startswith("DEV_V2_"))
                self.assertIn(HYBRID_PLANNER_PROMPT_V2, result["planner_version"])
                self.assertEqual(result["prompt_provenance"]["output_schema_version"], "HYBRID_OUTPUT_SCHEMA_V2")
                self.assertEqual(len(result["prompt_provenance"]["requests"]), 1)
                self.assertEqual(validate_shape(result, schema, _root=schema), [])
            self.assertNotEqual(first["experiment_id"], second["experiment_id"])
            self.assertNotEqual(first["prompt_provenance"]["requests"], second["prompt_provenance"]["requests"])
            legacy = run_benchmark.BenchmarkRunner(results_dir=Path(temp)).run_development_dry_run(scenario_key="S1", planner_id="RULE").to_dict()
            self.assertNotIn("prompt_provenance", legacy)

    def test_git_status_preserves_worktree_column_and_v2_source_closure(self):
        status = subprocess.CompletedProcess([], 0, " M runtime/planners/hybrid_planner.py\n?? evaluation/experiments/protocol_amendment_v2.json\n", "")
        with patch("evaluation.experiments.source_snapshot.subprocess.run", return_value=status):
            dirty, modified, staged, untracked = get_git_status()
        self.assertTrue(dirty)
        self.assertEqual(modified, ["runtime/planners/hybrid_planner.py"])
        self.assertEqual(staged, [])
        self.assertEqual(untracked, ["evaluation/experiments/protocol_amendment_v2.json"])
        self.assertEqual(len(RELEVANT_SOURCE_FILES), 65)
        snapshot = build_source_snapshot(protocol_version=PROPOSED_PROTOCOL_ID_V2)
        self.assertEqual(snapshot.protocol_version, PROPOSED_PROTOCOL_ID_V2)
        self.assertEqual(snapshot.provenance_status, "BLOCKED")
        for path in ("evaluation/experiments/protocol_amendment_v2.json", "evaluation/results/result_v2.schema.json"):
            self.assertIn(path, snapshot.relevant_files_manifest)


if __name__ == "__main__":
    unittest.main()
