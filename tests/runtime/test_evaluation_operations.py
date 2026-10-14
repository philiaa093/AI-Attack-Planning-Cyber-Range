"""Accounting, audit-only cleanup and defensive log ingestion acceptance."""
import importlib.util
import json
import socket
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from runtime.evaluation.evaluate_all import report_defensive_logs, report_usage_costs
from runtime.planners.llm_planner import LLMPlanner, ProviderFailure
from runtime.audit.repository_cleanup import HISTORICAL_RUNS, apply_cache_plan, make_plan, parse_gate_errors
from runtime.evaluation.usage_costs import (
    MeteredReviewResponse, PricingCalculator, UsageExtractor, UsageLedger,
    canonical, sha, summarize_ledger,
)
from runtime.evaluation.defensive_log_import import import_defensive_summaries
from test_llm_planner import FixtureProvider, request


def response(**changes):
    return dict(id="resp-example-1", model="gpt-4.1-mini", service_tier="default",
                usage=dict(input_tokens=1000, output_tokens=100, total_tokens=1100,
                           input_tokens_details=dict(cached_tokens=500, cache_write_tokens=0),
                           output_tokens_details=dict(reasoning_tokens=80))) | changes


def usage(**changes):
    return UsageExtractor.extract(response(**changes), provider="openai", api="responses")


class EvaluationOperationsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def ledger(self):
        return UsageLedger(self.root / "usage", run_id=request().state.context.run_id, source="SIMULATED_FIXTURE")

    def test_openai_cache_subtraction_and_reasoning_not_double_billed(self):
        row = usage()
        self.assertEqual(row.input_uncached, 500)
        self.assertEqual(row.output_tokens, 100)
        self.assertEqual(row.reasoning_tokens, 80)
        quote = PricingCalculator().quote(row)
        self.assertEqual(quote["token_cost_usd"], "0.00041")
        self.assertIsNone(quote["actual_billed_usd"])
        self.assertEqual(len(quote["rate_card_sha256"]), 64)
        self.assertEqual(PricingCalculator().quote(usage(model="gpt-4.1-mini-2025-04-14"))["token_cost_usd"], "0.00041")

    def test_chat_completion_usage(self):
        raw = response(usage=dict(prompt_tokens=1000, completion_tokens=100,
                                  total_tokens=1100, prompt_tokens_details=dict(cached_tokens=500),
                                  completion_tokens_details=dict(reasoning_tokens=80)))
        row = UsageExtractor.extract(raw, provider="openai", api="chat_completions")
        self.assertEqual(PricingCalculator().quote(row)["token_cost_usd"], "0.00041")

    def test_sdk_capture_uses_final_usage_and_respects_reported_region(self):
        class SDKResponse:
            def model_dump(self, *, mode):
                self.mode = mode
                return response()
        sdk = SDKResponse()
        captured = MeteredReviewResponse.capture(sdk, review_json="{}", provider="openai", api="responses")
        self.assertEqual(sdk.mode, "json")
        self.assertEqual(captured.usage.output_tokens, 100)
        raw = dict(id="msg-example", model="claude-sonnet-4-6", usage=dict(
            input_tokens=100, output_tokens=10, inference_geo="us"))
        row = UsageExtractor.extract(raw, provider="anthropic", api="messages", resolved_tier="standard")
        self.assertEqual(row.region, "us")
        with self.assertRaises(ValueError):
            PricingCalculator().quote(row)

    def test_anthropic_cache_writes_have_distinct_ttls(self):
        raw = dict(id="msg-example", model="claude-sonnet-4-6", usage=dict(
            input_tokens=400, output_tokens=80, cache_read_input_tokens=100,
            cache_creation_input_tokens=250,
            cache_creation=dict(ephemeral_5m_input_tokens=200, ephemeral_1h_input_tokens=50)))
        row = UsageExtractor.extract(raw, provider="anthropic", api="messages", resolved_tier="standard")
        self.assertEqual(row.input_uncached, 400)
        self.assertEqual(PricingCalculator().quote(row)["token_cost_usd"], "0.00348")
        raw["usage"].pop("cache_creation")
        row = UsageExtractor.extract(raw, provider="anthropic", api="messages", resolved_tier="standard")
        self.assertEqual(row.cache_write_unknown_ttl, 250)
        with self.assertRaises(ValueError):
            PricingCalculator().quote(row)

    def test_missing_usage_never_becomes_zero_cost(self):
        self.assertIsNone(UsageExtractor.extract(response(usage=None), provider="openai", api="responses"))
        ledger = self.ledger()
        ledger.record(episode_id="EP-1", usage=usage())
        ledger.record(episode_id="EP-1", usage=None)
        path, digest = ledger.seal()
        summary = summarize_ledger(path, digest)
        self.assertEqual(summary["calls"], 2)
        self.assertEqual(summary["unknown_calls"], 1)
        self.assertEqual(summary["known_token_subtotal_usd"], "0.00041")
        self.assertIsNone(summary["token_cost_usd"])

    def test_invalid_counts_tiers_totals_and_unknown_rates(self):
        for raw in (response(service_tier="auto"), response(usage=dict(input_tokens=True, output_tokens=1)),
                    response(usage=dict(input_tokens=10, output_tokens=1, total_tokens=11,
                                       input_tokens_details=dict(cached_tokens=12))),
                    response(usage=dict(input_tokens=10, output_tokens=1, total_tokens=99,
                                       input_tokens_details=dict(cached_tokens=0)))):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                UsageExtractor.extract(raw, provider="openai", api="responses")
        for change in (dict(model="unknown-model"), dict(service_tier="batch"), dict(region="us")):
            with self.subTest(change=change), self.assertRaises(ValueError):
                PricingCalculator().quote(replace(usage(), **change))

    def test_ledger_dedup_conflicts_seal_and_hash_tamper(self):
        ledger = self.ledger()
        first = ledger.record(episode_id="EP-1", usage=usage())
        self.assertEqual(first, ledger.record(episode_id="EP-1", usage=usage()))
        with self.assertRaisesRegex(ValueError, "conflicting"):
            ledger.record(episode_id="EP-2", usage=usage())
        path, digest = ledger.seal()
        self.assertEqual(summarize_ledger(path, digest)["calls"], 1)
        with self.assertRaises(ValueError):
            ledger.record(episode_id="EP-1", usage=None)
        with (ledger.root / first["name"]).open("ab") as stream:
            stream.write(b" ")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            summarize_ledger(path, digest)

    def metered_provider(self, *, invalid_output=False):
        class Provider(FixtureProvider):
            def complete(self, document):
                raw = super().complete(document)
                return MeteredReviewResponse("invalid" if invalid_output else raw, usage())
        return Provider()

    def test_planner_records_usage_before_refusal_or_invalid_output(self):
        ledger = self.ledger()
        obj = LLMPlanner(self.metered_provider(invalid_output=True), count_tokens=len,
                         usage_sink=ledger.planner_sink)
        with self.assertRaises(ProviderFailure):
            obj.plan(request())
        path, digest = ledger.seal()
        self.assertEqual(summarize_ledger(path, digest)["token_cost_usd"], "0.00041")

    def test_planner_success_sink_and_sticky_failure(self):
        ledger, provider = self.ledger(), self.metered_provider()
        obj = LLMPlanner(provider, count_tokens=len, usage_sink=ledger.planner_sink)
        self.assertEqual(obj.plan(request()).actual_mode, "LLM")
        self.assertEqual(len(ledger.refs), 1)
        def denied_sink(req, tokens):
            raise OSError("synthetic secret should not escape")
        obj = LLMPlanner(provider, count_tokens=len, usage_sink=denied_sink)
        with self.assertRaisesRegex(ProviderFailure, "ACCOUNTING_WRITE_FAILED"):
            obj.plan(request())
        calls = len(provider.requests)
        with self.assertRaisesRegex(ProviderFailure, "ACCOUNTING_HALTED"):
            obj.plan(request())
        self.assertEqual(len(provider.requests), calls)

    def test_timeout_records_unknown_and_metered_reply_requires_sink(self):
        ledger = self.ledger()
        class TimeoutProvider:
            def complete(self, document):
                raise TimeoutError()
        obj = LLMPlanner(TimeoutProvider(), count_tokens=len, usage_sink=ledger.planner_sink)
        self.assertEqual(obj.plan(request(fallback=True)).actual_mode, "RULE")
        path, digest = ledger.seal()
        self.assertIsNone(summarize_ledger(path, digest)["token_cost_usd"])
        with self.assertRaisesRegex(ProviderFailure, "MISSING_USAGE_SINK"):
            LLMPlanner(self.metered_provider(), count_tokens=len).plan(request())

    def test_accounting_report_branch_does_not_dispatch(self):
        ledger = self.ledger()
        ledger.record(episode_id="EP-1", usage=usage())
        path, digest = ledger.seal()
        with patch.object(socket, "create_connection", side_effect=AssertionError("network")), \
             patch.object(subprocess, "Popen", side_effect=AssertionError("process")):
            root = report_usage_costs(path, digest, self.root / "reports")
        data = json.loads((root / "monetary-costs.json").read_text())
        self.assertEqual(data["source"], "IMPORTED_API_USAGE")
        self.assertEqual(data["observed_state"]["source"], "SIMULATED_FIXTURE")
        self.assertIn("0.00041", (root / "report.md").read_text())

    def historical_fixture(self):
        run_id = "RUN-EVAL-" + "1" * 32
        directory = self.root / "runtime/evaluation-runs" / run_id
        directory.mkdir(parents=True)
        blob = b"preserve historical bytes\n"
        (directory / "report.md").write_bytes(blob)
        manifest = dict(run_id=run_id, observed_state=dict(artifacts=[dict(name="report.md", sha256=sha(blob))]))
        (directory / "manifest.json").write_bytes(canonical(manifest))
        return run_id, directory

    def generated_cache(self):
        path = self.root / "runtime/__pycache__/example.cpython-314.pyc"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.parent.parent.joinpath("example.py").write_text("answer = 42\n")
        path.write_bytes(importlib.util.MAGIC_NUMBER + b"\0" * 12 + b"synthetic bytecode")
        return path

    def test_missing_historical_runs_block_mutation(self):
        cache = self.generated_cache()
        original = cache.read_bytes()
        plan = make_plan(self.root, "SCAFFOLD INVALID\n- forbidden artifact runtime/__pycache__/example.cpython-314.pyc\n")
        self.assertEqual(len(plan["evidence_failures"]), len(HISTORICAL_RUNS))
        with self.assertRaisesRegex(ValueError, "cleanup prohibited"):
            apply_cache_plan(self.root, plan, self.root / "runtime/gate-remediation")
        self.assertEqual(cache.read_bytes(), original)
        self.assertFalse((self.root / "runtime/gate-remediation").exists())

    def test_cache_quarantine_preserves_bytes_and_historical_evidence(self):
        run, directory = self.historical_fixture()
        history = {p.name: p.read_bytes() for p in directory.iterdir()}
        cache = self.generated_cache()
        original = cache.read_bytes()
        plan = make_plan(self.root, "SCAFFOLD INVALID\n- forbidden artifact runtime/__pycache__/example.cpython-314.pyc\n", (run,))
        archive = apply_cache_plan(self.root, plan, self.root / "runtime/gate-remediation")
        self.assertEqual(next(archive.glob("*.archive")).read_bytes(), original)
        self.assertFalse(cache.exists())
        self.assertEqual({p.name: p.read_bytes() for p in directory.iterdir()}, history)

    def test_hash_mismatch_never_rewrites_manifest(self):
        run, directory = self.historical_fixture()
        manifest_before = (directory / "manifest.json").read_bytes()
        (directory / "report.md").write_bytes(b"tampered fixture")
        plan = make_plan(self.root, "SCAFFOLD INVALID\n", (run,))
        self.assertTrue(plan["evidence_failures"])
        self.assertEqual((directory / "manifest.json").read_bytes(), manifest_before)

    def test_cleanup_path_escape_and_forged_noncache_action_rejected(self):
        with self.assertRaises(ValueError):
            make_plan(self.root, "- forbidden artifact ../../outside.pyc\n")
        run, _ = self.historical_fixture()
        plan = make_plan(self.root, "SCAFFOLD VALID\n", (run,))
        important = self.root / "runtime/important.json"
        important.write_bytes(b"important")
        plan["proposed_cache_actions"] = [dict(relative_path="runtime/important.json", size=9,
                                              preimage_sha256=sha(b"important"), operation="QUARANTINE_GENERATED_BYTECODE")]
        with self.assertRaises(ValueError):
            apply_cache_plan(self.root, plan, self.root / "runtime/gate-remediation")
        self.assertEqual(important.read_bytes(), b"important")
        self.assertEqual(parse_gate_errors("SCAFFOLD INVALID\n- duplicate\n- duplicate\n"), ("duplicate",))

    def defensive_log(self, records=None):
        records = [dict(schema_version=1, run_id="RUN-DEFENSE-1", episode_id="EP-1", agent_id="agent-a",
                        scenario_id="scenario-a", split="heldout", seed=1, created_at_utc="2026-10-12T10:36:01Z",
                        outcome="succeeded", steps=3),
                   dict(schema_version=1, run_id="RUN-DEFENSE-1", episode_id="EP-2", agent_id="agent-a",
                        scenario_id="scenario-a", split="heldout", seed=2, created_at_utc="2026-10-12T10:36:01Z",
                        outcome="refused", steps=1)] if records is None else records
        data = b"".join(json.dumps(row).encode() + b"\n" for row in records)
        path = self.root / "defense.jsonl"
        path.write_bytes(data)
        return path, sha(data)

    def test_defensive_import_keeps_failures_and_marks_claims(self):
        path, digest = self.defensive_log()
        result = import_defensive_summaries(path, digest)
        self.assertEqual(result["summaries"][0]["success_claim_rate"], 0.5)
        self.assertEqual(result["summaries"][0]["mean_steps"], 2)
        self.assertEqual(result["oracle_validation"], "UNRESOLVED")
        root = report_defensive_logs(path, digest, self.root / "reports")
        self.assertIn("recorded claims", (root / "report.md").read_text())

    def test_defensive_import_rejects_tampering_duplicates_and_extra_fields(self):
        path, digest = self.defensive_log()
        with self.assertRaises(ValueError):
            import_defensive_summaries(path, "0" * 64)
        row = json.loads(path.read_text().splitlines()[0])
        for records in ([row, row], [row | {"credential": "synthetic"}], [row | {"steps": True}],
                        [row | {"created_at_utc": "2026-10-12T17:00:00+07:00"}]):
            path, digest = self.defensive_log(records)
            with self.assertRaises(ValueError):
                import_defensive_summaries(path, digest)


if __name__ == "__main__":
    unittest.main()
