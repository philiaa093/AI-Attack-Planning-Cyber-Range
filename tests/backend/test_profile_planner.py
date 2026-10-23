"""Offline profile-to-planner checks; all provider transport is mocked."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from dashboards.app.backend.model_profiles import ProfileInput, ProfileStore
from dashboards.app.backend.models import StartRunRequest
from dashboards.app.backend.event_sink import EventSink
from dashboards.app.backend.run_manager import RunManager
from runtime.planners.observed_planner import ObservedStatePlanner, _call_real_provider


class ProfilePlannerTests(unittest.TestCase):
    def setUp(self):
        self.store = ProfileStore()
        self.value = ProfileInput(name="Fixture", protocol="openai-compatible",
                                  model="fixture-model", endpoint="https://provider.example/v1",
                                  api_key="fixture-secret")
        self.saved = self.store.save(self.value)

    def test_snapshot_selection_and_removal(self):
        first = self.store.snapshot()
        second = self.store.save(self.value.model_copy(update={"model": "second"}))
        self.assertEqual(self.store.snapshot().model, "second")
        self.assertEqual(first.model, "fixture-model")
        self.assertNotIn("fixture-secret", repr(first))
        self.assertEqual(sum(p["is_active"] for p in self.store.list_profiles()), 1)
        self.store.remove(second["id"])
        self.assertIsNone(self.store.snapshot())
        self.assertEqual(first.api_key, "fixture-secret")

    def test_run_captures_profile_without_environment_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            for planner in ("llm", "rule", "llm-unavailable"):
                manager = RunManager(Path(directory), model_profiles=self.store)
                with patch("dashboards.app.backend.run_manager.threading.Thread") as thread:
                    result = manager.start_run(StartRunRequest(planner=planner), EventSink())
                self.assertTrue(result.success)
                snapshot = thread.call_args.kwargs["args"][-1]
                self.assertEqual(snapshot, self.store.snapshot() if planner == "llm" else None)

    def test_worker_passes_snapshot_to_runner(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = RunManager(Path(directory), model_profiles=self.store)
            config = self.store.snapshot()
            with patch("dashboards.app.backend.run_manager.lab.new_recorder"), \
                 patch("dashboards.app.backend.run_manager.AutonomousRunner") as runner:
                # Stop before report persistence; no target/provider dispatch occurs.
                runner.return_value.run.side_effect = RuntimeError("fixture stop")
                manager._worker("RUN-FIXTURE-001", StartRunRequest(planner="llm"),
                                Path(directory), EventSink(), config)
            self.assertEqual(runner.call_args.kwargs["planner_provider_config"], config)

    def test_protocols_use_saved_key_model_and_endpoint(self):
        for protocol in ("openai-compatible", "anthropic"):
            self.store.save(self.value.model_copy(update={"protocol": protocol}))
            response = Mock(status=200)
            response.read.return_value = json.dumps(
                {"choices": [{"message": {"content": "{}"}}],
                 "content": [{"type": "text", "text": "{}"}]}).encode()
            with patch("runtime.planners.observed_planner.http.client.HTTPSConnection") as connection:
                connection.return_value.getresponse.return_value = response
                text, error, meta = _call_real_provider("system", "user", config=self.store.snapshot())
                args = connection.return_value.request.call_args
                self.assertEqual(connection.call_args.args, ("provider.example", 443))
                self.assertEqual(args.args[1], "/v1/messages" if protocol == "anthropic" else "/v1/chat/completions")
                body = json.loads(args.kwargs["body"])
                self.assertEqual(body["model"], "fixture-model")
                headers = args.kwargs["headers"]
                self.assertEqual(headers.get("x-api-key") if protocol == "anthropic" else headers.get("Authorization"),
                                 "fixture-secret" if protocol == "anthropic" else "Bearer fixture-secret")
                connection.return_value.close.assert_called_once()
            self.assertEqual(text, "{}")
            self.assertIsNone(error)
            self.assertNotIn("fixture-secret", repr(meta))

    def test_errors_bounded_response_and_secret_echo(self):
        for status, body, expected in ((401, b"fixture-secret", "HTTP_401"),
                                       (302, b"", "HTTP_302"),
                                       (200, b"x" * 8193, "PROVIDER_RESPONSE_TOO_LARGE"),
                                       (200, b'{"choices":[{"message":{"content":"fixture-secret"}}]}', "INVALID_PROVIDER_CONTENT")):
            with patch("runtime.planners.observed_planner.http.client.HTTPSConnection") as connection:
                response = connection.return_value.getresponse.return_value
                response.status, response.read.return_value = status, body
                result = _call_real_provider("system", "user", config=self.store.snapshot())
                self.assertEqual(result[1], expected)
                self.assertNotIn("fixture-secret", repr(result))
                connection.return_value.request.assert_called_once()
                connection.return_value.close.assert_called_once()

    def test_planner_uses_profile_and_preserves_fallback_policy(self):
        config = self.store.snapshot()
        for allow_fallback in (True, False):
            planner = ObservedStatePlanner("lab-ecommerce", requested_mode="LLM",
                                           fallback_allowed=allow_fallback, provider_config=config)
            with patch("runtime.planners.observed_planner._call_real_provider",
                       return_value=(None, "HTTP_401", {})) as provider:
                result = planner.propose({"remaining_budget": {"actions": 5}})
            self.assertEqual(provider.call_args.kwargs["config"], config)
            self.assertEqual(planner.configured_model, "fixture-model")
            self.assertEqual(result.mode_provenance["fallback_reason"],
                             "HTTP_401" if allow_fallback else "FALLBACK_NOT_ALLOWED:HTTP_401")
            if not allow_fallback:
                self.assertTrue(result.proposal["action_id"].startswith("ACTION-END-"))

    def test_saved_profile_produces_llm_provenance_with_mock_transport(self):
        proposal = {"schema_version": "1.0", "plan_id": "PLAN-FIXTURE-001",
                    "objective_id": "OBJ-001", "action_id": "ACTION-RECON-002",
                    "target_id": "lab-ecommerce", "reason_code": "explore_surface", "confidence": 0.8}
        planner = ObservedStatePlanner("lab-ecommerce", requested_mode="LLM",
                                       provider_config=self.store.snapshot())
        with patch("runtime.planners.observed_planner.http.client.HTTPSConnection") as connection:
            response = connection.return_value.getresponse.return_value
            response.status = 200
            response.read.return_value = json.dumps({"choices": [{"message": {"content": json.dumps(proposal)}}]}).encode()
            result = planner.propose({"remaining_budget": {"actions": 5}})
        self.assertTrue(result.is_valid)
        self.assertEqual(result.mode_provenance["actual_mode"], "LLM")
        self.assertEqual(result.mode_provenance["model"], "fixture-model")
        self.assertEqual(result.mode_provenance["provider"], "openai-compatible")
        self.assertNotIn("fixture-secret", repr(result))


if __name__ == "__main__":
    unittest.main()
