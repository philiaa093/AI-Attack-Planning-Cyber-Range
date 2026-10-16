"""Configuration-only API checks; no provider, target, evidence or Docker I/O."""
import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboards.app.backend.model_profiles import ProfileInput, ProfileStore, create_router


class ModelProfileTests(unittest.TestCase):
    def setUp(self):
        self.store = ProfileStore()
        app = FastAPI()
        app.include_router(create_router(self.store))
        self.client = TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
        self.headers = {"Origin": "http://127.0.0.1:5173"}
        self.value = {"name": "Research", "protocol": "openai-compatible", "model": "custom/model",
                      "endpoint": "https://PROVIDER.example/v1/", "api_key": "fixture-secret-only"}

    def create(self, value=None):
        return self.client.post("/api/model-profiles", headers=self.headers, json=value or self.value)

    def test_redacted_create_list_and_remove(self):
        response = self.create()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["endpoint"], "https://provider.example/v1")
        self.assertTrue(data["has_api_key"])
        self.assertEqual(data["connection_status"], "NOT_TESTED")
        listing = self.client.get("/api/model-profiles")
        self.assertNotIn("fixture-secret-only", response.text + listing.text)
        self.assertNotIn('"api_key"', response.text + listing.text)
        self.assertEqual(listing.headers["cache-control"], "no-store")
        self.assertEqual(listing.json()["execution_integration"], "CONNECTED")
        removed = self.client.post(f'/api/model-profiles/{data["id"]}/remove', headers=self.headers)
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(self.store.list_profiles(), [])

    def test_update_keeps_replaces_or_removes_key(self):
        profile_id = self.create().json()["id"]
        value = {**self.value, "api_key": "", "model": "updated-model"}
        path = f"/api/model-profiles/{profile_id}"
        saved = self.client.post(path, headers=self.headers, json=value)
        self.assertTrue(saved.json()["has_api_key"])
        self.assertEqual(self.store._profiles[profile_id].api_key.get_secret_value(), self.value["api_key"])
        saved = self.client.post(path, headers=self.headers, json={**value, "api_key": "replacement-fixture"})
        self.assertTrue(saved.json()["has_api_key"])
        self.assertEqual(self.store._profiles[profile_id].api_key.get_secret_value(), "replacement-fixture")
        saved = self.client.post(path, headers=self.headers, json={**value, "clear_key": True})
        self.assertFalse(saved.json()["has_api_key"])
        self.assertNotIn("replacement-fixture", repr(self.store._profiles[profile_id]))

    def test_errors_never_echo_submitted_key(self):
        for patch in ({"api_key": "secret\nnewline"}, {"endpoint": "http://remote.example"},
                      {"extra": "fixture-secret-only"}, {"clear_key": "yes"},
                      {"clear_key": True}, {"name": "\t"}):
            with self.subTest(patch=patch):
                response = self.create({**self.value, **patch})
                self.assertEqual(response.status_code, 422)
                self.assertNotIn("fixture-secret-only", response.text)
                self.assertNotIn("secret\\nnewline", response.text)
        self.assertEqual(self.store.list_profiles(), [])

    def test_endpoint_validation(self):
        bad = ["file:///tmp/model", "https://user:password@host/v1", "https://host/v1?key=secret",
               "https://host/v1#secret", "https://host:99999/v1", "https://host/../v1",
               "https://host/%2e%2e/v1", "https://host\\evil/v1", "http://10.0.0.1/v1"]
        for endpoint in bad:
            with self.subTest(endpoint=endpoint):
                self.assertEqual(self.create({**self.value, "endpoint": endpoint}).status_code, 422)
        for endpoint in ("http://localhost:11434/v1", "http://127.0.0.1:1234/v1", "http://[::1]:1234/v1"):
            with self.subTest(endpoint=endpoint):
                self.assertEqual(self.create({**self.value, "endpoint": endpoint, "api_key": ""}).status_code, 200)

    def test_origin_peer_and_host_checks(self):
        for origin in (None, "https://evil.example", "http://localhost:9999", "null"):
            response = self.client.post("/api/model-profiles", json=self.value,
                                        headers={"Origin": origin} if origin else {})
            self.assertEqual(response.status_code, 403)
        app = FastAPI()
        app.include_router(create_router(self.store))
        remote = TestClient(app, base_url="http://127.0.0.1:8000", client=("10.0.0.2", 50000))
        self.assertEqual(remote.get("/api/model-profiles").status_code, 403)
        self.assertEqual(self.client.get("/api/model-profiles", headers={"Host": "evil.example"}).status_code, 403)
        self.assertEqual(self.client.get("/api/model-profiles", headers={"Origin": "https://evil.example"}).status_code, 403)

    def test_bounded_request_and_profile_count(self):
        response = self.client.post("/api/model-profiles", content=b"x" * 17000,
                                    headers={**self.headers, "Content-Type": "application/json"})
        self.assertEqual(response.status_code, 413)
        for _ in range(20):
            self.assertEqual(self.create().status_code, 200)
        self.assertEqual(self.create().status_code, 409)
        self.assertEqual(len(self.store.list_profiles()), 20)

    def test_missing_profile_invalid_json_and_content_type(self):
        self.assertEqual(self.client.post("/api/model-profiles/missing", headers=self.headers, json=self.value).status_code, 404)
        self.assertEqual(self.client.post("/api/model-profiles/missing/remove", headers=self.headers).status_code, 404)
        response = self.client.post("/api/model-profiles", content=b'{"api_key":"fixture-secret-only",',
                                    headers={**self.headers, "Content-Type": "application/json"})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn("fixture-secret-only", response.text)
        self.assertEqual(self.client.post("/api/model-profiles", data=self.value, headers=self.headers).status_code, 415)

    def test_new_store_starts_empty_without_environment_mutation(self):
        import os
        previous = dict(os.environ)
        self.store.save(ProfileInput.model_validate(self.value))
        self.assertEqual(ProfileStore().list_profiles(), [])
        self.assertEqual(dict(os.environ), previous)


class PersistentModelProfileTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / ".env"
        self.original = b"# preserve comments\r\nOTHER_SETTING=keep-me\r\n"
        self.path.write_bytes(self.original)
        self.store = ProfileStore(self.path)
        self.value = ProfileInput(name="Local model", protocol="anthropic", model="custom/model",
                                  endpoint="https://provider.example/v1", persist=True,
                                  api_key="fixture'\"\\$#=secret")

    def test_restart_roundtrip_redaction_and_unrelated_settings(self):
        saved = self.store.save(self.value)
        self.assertTrue(saved["persisted"])
        self.assertTrue(self.path.read_bytes().startswith(self.original))
        restarted = ProfileStore(self.path)
        self.assertEqual(restarted.snapshot(), self.store.snapshot())
        self.assertTrue(restarted.list_profiles()[0]["is_active"])
        self.assertNotIn(self.value.api_key.get_secret_value(), repr(restarted.list_profiles()))
        self.assertNotIn("api_key", restarted.list_profiles()[0])

    def test_blank_key_preserves_clear_key_removes_and_delete_persists(self):
        saved = self.store.save(self.value)
        blank = self.value.model_copy(update={"api_key": ProfileInput.model_fields["api_key"].default_factory()})
        self.store.save(blank, saved["id"])
        self.assertEqual(ProfileStore(self.path).snapshot().api_key, self.value.api_key.get_secret_value())
        self.store.save(blank.model_copy(update={"clear_key": True}), saved["id"])
        self.assertEqual(ProfileStore(self.path).snapshot().api_key, "")
        self.store.remove(saved["id"])
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual(ProfileStore(self.path).list_profiles(), [])

    def test_replacement_and_unchecking_persistence(self):
        first = self.store.save(self.value)
        second = self.store.save(self.value.model_copy(update={"model": "replacement"}))
        self.assertFalse(self.store.list_profiles()[0]["persisted"])
        self.assertEqual(ProfileStore(self.path).snapshot().model, "replacement")
        self.store.remove(first["id"])
        self.assertEqual(ProfileStore(self.path).snapshot().model, "replacement")
        self.store.save(self.value.model_copy(update={"persist": False}), second["id"])
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertIsNotNone(self.store.snapshot())

    def test_failed_write_preserves_file_and_memory(self):
        from fastapi import HTTPException
        self.store.save(self.value)
        original = self.path.read_bytes()
        snapshot = self.store.snapshot()
        with patch("dashboards.app.backend.model_profiles.os.replace", side_effect=OSError("fixture failure")):
            with self.assertRaises(HTTPException) as caught:
                self.store.save(self.value.model_copy(update={"model": "new"}))
        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.store.snapshot(), snapshot)
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_invalid_saved_profile_fails_without_disclosing_content(self):
        self.path.write_text("DASHBOARD_MODEL_PROFILE='fixture-secret-invalid'\n", encoding="utf-8")
        with self.assertRaises(RuntimeError) as caught:
            ProfileStore(self.path)
        self.assertNotIn("fixture-secret-invalid", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
