"""Closed-config and secret-boundary tests for RT-06P."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from runtime.lab.range_provider import RangeProviderError
from runtime.lab.remote_range_config import (
    load_remote_range_config,
    parse_remote_range_config,
)


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "configs" / "lab" / "remote-range.example.json"


class TestRemoteRangeConfig(unittest.TestCase):
    def setUp(self) -> None:
        self.raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))

    def test_example_is_valid_and_contains_only_secret_references(self) -> None:
        config = load_remote_range_config(EXAMPLE)
        self.assertEqual(config.schema_version, 1)
        self.assertEqual(len(config.targets), 5)
        serialized = EXAMPLE.read_text(encoding="utf-8").lower()
        self.assertNotIn('"password":', serialized)
        self.assertNotIn('"token":', serialized)

    def test_insecure_url_is_rejected(self) -> None:
        raw = copy.deepcopy(self.raw)
        raw["gns3"]["base_url"] = "http://gns3.example.invalid"
        with self.assertRaises(RangeProviderError) as ctx:
            parse_remote_range_config(raw)
        self.assertEqual(ctx.exception.code, "REMOTE_CONFIG_INSECURE_URL")

    def test_public_ip_literal_is_rejected(self) -> None:
        raw = copy.deepcopy(self.raw)
        raw["gns3"]["base_url"] = "https://8.8.8.8"
        with self.assertRaises(RangeProviderError) as ctx:
            parse_remote_range_config(raw)
        self.assertEqual(ctx.exception.code, "REMOTE_CONFIG_PUBLIC_IP_DENIED")

    def test_unknown_secret_field_is_rejected(self) -> None:
        raw = copy.deepcopy(self.raw)
        raw["vsphere"]["password"] = "must-not-be-accepted"
        with self.assertRaises(RangeProviderError) as ctx:
            parse_remote_range_config(raw)
        self.assertEqual(ctx.exception.code, "REMOTE_CONFIG_UNKNOWN_FIELD")
        self.assertNotIn("must-not-be-accepted", str(ctx.exception))

    def test_target_set_must_match_canonical_range(self) -> None:
        raw = copy.deepcopy(self.raw)
        raw["targets"].pop("lab-enterprise-decoy")
        with self.assertRaises(RangeProviderError) as ctx:
            parse_remote_range_config(raw)
        self.assertEqual(ctx.exception.code, "REMOTE_CONFIG_TARGET_SET_MISMATCH")

    def test_remote_bindings_must_be_unique(self) -> None:
        raw = copy.deepcopy(self.raw)
        raw["targets"]["lab-enterprise-decoy"]["vsphere_vm_id"] = (
            raw["targets"]["lab-enterprise-clean"]["vsphere_vm_id"]
        )
        with self.assertRaises(RangeProviderError) as ctx:
            parse_remote_range_config(raw)
        self.assertEqual(ctx.exception.code, "REMOTE_CONFIG_DUPLICATE_BINDING")

    def test_control_secret_is_resolved_only_from_environment(self) -> None:
        config = parse_remote_range_config(self.raw)
        with self.assertRaises(RangeProviderError) as ctx:
            config.resolve_control_token({})
        self.assertEqual(ctx.exception.code, "REMOTE_SECRET_MISSING")
        token = "x" * 48
        self.assertEqual(config.resolve_control_token({"RANGE_CONTROL_TOKEN": token}), token)


if __name__ == "__main__":
    unittest.main()
