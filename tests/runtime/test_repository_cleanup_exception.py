"""Run with python -B -m unittest tests.runtime.test_repository_cleanup_exception -v."""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.audit import repository_cleanup as cleanup


class IncidentExceptionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.manifest = self.root / cleanup.UI_CACHE_MANIFEST
        self.manifest.parent.joinpath("bytecode-copies").mkdir(parents=True)
        files, errors = [], []
        for index in range(28):
            name = f"runtime/__pycache__/fixture{index}.cpython-314.pyc"
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.parent.parent.joinpath(f"fixture{index}.py").write_text("pass\n")
            data = importlib.util.MAGIC_NUMBER + b"\0" * 12 + bytes([index])
            path.write_bytes(data)
            relative = f"bytecode-copies/{index}.archive"
            (self.manifest.parent / relative).write_bytes(data)
            files.append(dict(source_path=name, copy_path=relative, sha256=cleanup.sha(data), bytes=len(data)))
            errors.append("- forbidden artifact " + name)
        self.manifest.write_text(json.dumps(dict(files=files)))
        pinned = patch.object(cleanup, "UI_CACHE_MANIFEST_SHA256", cleanup.sha(self.manifest.read_bytes()))
        pinned.start()
        self.addCleanup(pinned.stop)
        self.plan = cleanup.make_plan(self.root, "\n".join(errors))

    def apply(self, plan=None, approved=True):
        return cleanup.apply_cache_plan(self.root, self.plan if plan is None else plan,
                                       self.root / "runtime/gate-remediation",
                                       approved_ui_cache_exception=approved)

    def test_default_still_denies_and_exception_preserves_all_bytes(self):
        with self.assertRaises(ValueError):
            self.apply(approved=False)
        before = {a["relative_path"]: (self.root / a["relative_path"]).read_bytes()
                  for a in self.plan["proposed_cache_actions"]}
        archive = self.apply()
        saved = json.loads((archive / "plan.json").read_text())
        self.assertEqual(saved["evidence_failures"], self.plan["evidence_failures"])
        self.assertEqual(saved["exception_disposition"]["historical_evidence"], "MISSING_UNVERIFIABLE")
        for receipt in archive.glob("receipt-*.json"):
            row = json.loads(receipt.read_text())
            self.assertEqual((archive / row["archive"]).read_bytes(), before[row["source"]])
            self.assertFalse((self.root / row["source"]).exists())
        self.assertEqual(len(list(archive.glob("*.archive"))), 28)

    def test_modified_copy_manifest_source_and_scope_are_rejected_before_mutation(self):
        targets = [self.manifest, self.manifest.parent / "bytecode-copies/0.archive",
                   self.root / self.plan["proposed_cache_actions"][0]["relative_path"]]
        for target in targets:
            with self.subTest(target=target):
                raw = target.read_bytes()
                target.write_bytes(raw + b"changed")
                with self.assertRaises(ValueError):
                    self.apply()
                target.write_bytes(raw)
                self.assertFalse((self.root / "runtime/gate-remediation").exists())
        plan = copy.deepcopy(self.plan)
        plan["proposed_cache_actions"].pop()
        with self.assertRaises(ValueError):
            self.apply(plan)
        self.assertTrue(all((self.root / a["relative_path"]).exists() for a in self.plan["proposed_cache_actions"]))

    def test_reappeared_history_in_either_root_blocks_exception(self):
        for base in ("evidence/runtime", "runtime/evaluation-runs"):
            with self.subTest(base=base):
                path = self.root / base / cleanup.HISTORICAL_RUNS[0]
                path.mkdir(parents=True)
                with self.assertRaises(ValueError):
                    self.apply()
                path.rmdir()
        self.assertFalse((self.root / "runtime/gate-remediation").exists())


if __name__ == "__main__":
    unittest.main()
