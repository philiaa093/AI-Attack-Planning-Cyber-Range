"""Automated Boundary Invariant Tests for Ground Truth Physical Isolation (RT-01A).

Invariants enforced:
1. Physical Isolation: Ground Truth canonical schema lives exclusively in the Evaluation domain.
   It has been completely removed from agent/planner/contracts/.
2. Planner Boundary: runtime/planners/** and agent/planner/** do not import, load, or reference Ground Truth.
3. State Boundary: agent/memory/** and runtime/state/** do not ingest, store, or expose Ground Truth.
4. Runtime Orchestration Boundary: runtime/orchestration/** and execution pipelines do not inject Ground Truth into planner input.
5. Evaluation Domain Exception: Evaluation code retains authority to load Ground Truth for scoring and comparison.
6. No Source Leakage: No helper, oracle query, or indirect route exists to supply Ground Truth to the Planner.
7. Active Regression Detection: Regression checker affirmatively flags any future attempts to introduce Ground Truth into the Planner/State domains.
"""

import ast
import json
from pathlib import Path
import tempfile
import unittest

from scripts.validation.validate_scaffold import validate_shape

ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN_GROUND_TRUTH_IDENTIFIERS = frozenset({
    "ground_truth",
    "ground_truth_records",
    "truth_records",
    "expected_detection",
    "load_ground_truth",
    "get_ground_truth",
    "oracle_truth",
})


def _scan_ast_for_ground_truth_violations(path: Path) -> list[str]:
    """Scan a Python file for executable ground-truth imports, calls, or variable definitions."""
    violations: list[str] = []
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except Exception as exc:
        return [f"{path}: failed to parse AST: {exc}"]

    module_docstring = ast.get_docstring(tree)

    for node in ast.walk(tree):
        # 1. Check imports: import evaluation.ground_truth, from evaluation import ground_truth, etc.
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "ground_truth" in alias.name.lower() or "ground-truth" in alias.name.lower():
                    violations.append(f"{path}:{node.lineno}: forbidden import {alias.name}")
                if alias.name.startswith("evaluation.ground_truth"):
                    violations.append(f"{path}:{node.lineno}: forbidden import from evaluation ground truth ({alias.name})")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if "ground_truth" in mod.lower() or "ground-truth" in mod.lower():
                violations.append(f"{path}:{node.lineno}: forbidden import from evaluation ground truth: {mod}")
            for alias in node.names:
                if "ground_truth" in alias.name.lower() or alias.name in FORBIDDEN_GROUND_TRUTH_IDENTIFIERS:
                    violations.append(f"{path}:{node.lineno}: forbidden import name {alias.name}")

        # 2. Check function / class / method names
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.lower() in FORBIDDEN_GROUND_TRUTH_IDENTIFIERS:
                violations.append(f"{path}:{node.lineno}: forbidden function/method name {node.name}")
        elif isinstance(node, ast.ClassDef):
            if "groundtruth" in node.name.lower():
                violations.append(f"{path}:{node.lineno}: forbidden class name {node.name}")

        # 3. Check string constants in executable code (excluding module docstring)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            val = node.value.strip()
            if module_docstring and val == module_docstring.strip():
                continue
            if "ground-truth.schema.json" in val or "ground_truth.schema.json" in val:
                violations.append(f"{path}:{node.lineno}: literal ground-truth schema path reference '{val}'")
            if val.endswith("ground-truth.json") or val.endswith("ground_truth.json"):
                violations.append(f"{path}:{node.lineno}: literal ground-truth data file reference '{val}'")

    return violations


class GroundTruthPhysicalIsolationTests(unittest.TestCase):
    """Enforce physical isolation of Ground Truth and verify zero-knowledge boundary."""

    def test_canonical_schema_location_and_old_path_removal(self):
        """Invariant: ground-truth.schema.json must NOT exist in agent/planner/contracts/ and MUST exist in evaluation."""
        old_canonical = ROOT / "agent/planner/contracts/ground-truth.schema.json"
        self.assertFalse(
            old_canonical.exists(),
            f"Physical isolation violated: Ground Truth schema still exists at {old_canonical}",
        )

        canonical_path = ROOT / "evaluation/ground_truth/ground-truth.schema.json"
        self.assertTrue(
            canonical_path.is_file(),
            f"Canonical Ground Truth schema missing at {canonical_path}",
        )

        # Validate Draft 2020-12 closed schema properties
        schema = json.loads(canonical_path.read_text(encoding="utf-8"))
        self.assertEqual(schema.get("$schema"), "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(schema.get("type"), "object")
        self.assertIs(schema.get("additionalProperties"), False)
        self.assertIn("scenario_id", schema.get("properties", {}))
        self.assertIn("truth_records", schema.get("properties", {}))

    def test_schema_link_manifest_points_to_evaluation_domain(self):
        """Invariant: schema-link.json must declare canonical schema under evaluation domain with 0 runtime consumers."""
        link_path = ROOT / "evaluation/ground-truth/schema-link.json"
        self.assertTrue(link_path.is_file(), f"Missing schema link manifest at {link_path}")

        link = json.loads(link_path.read_text(encoding="utf-8"))
        self.assertEqual(
            link.get("ground_truth_schema"),
            "evaluation/ground_truth/ground-truth.schema.json",
            "schema-link.json must reference canonical schema in evaluation domain",
        )
        self.assertEqual(
            link.get("runtime_consumers"),
            [],
            "Ground Truth must have ZERO runtime consumers",
        )

    def test_planner_boundary_ast_invariants(self):
        """Invariant A: runtime/planners/** and agent/planner/** have zero executable imports or path loads of Ground Truth."""
        scan_dirs = [
            ROOT / "runtime/planners",
            ROOT / "agent/planner",
        ]
        all_violations = []
        for scan_dir in scan_dirs:
            if not scan_dir.exists():
                continue
            for py_path in scan_dir.rglob("*.py"):
                violations = _scan_ast_for_ground_truth_violations(py_path)
                all_violations.extend(violations)

        self.assertEqual(
            all_violations,
            [],
            f"Planner boundary violated with ground-truth references: {all_violations}",
        )

    def test_state_boundary_ast_and_rejection_invariants(self):
        """Invariant B: agent/memory/** and runtime/state/** do not read or store Ground Truth."""
        scan_dirs = [
            ROOT / "agent/memory",
            ROOT / "runtime/state",
        ]
        all_violations = []
        for scan_dir in scan_dirs:
            if not scan_dir.exists():
                continue
            for py_path in scan_dir.rglob("*.py"):
                violations = _scan_ast_for_ground_truth_violations(py_path)
                all_violations.extend(violations)

        self.assertEqual(
            all_violations,
            [],
            f"State boundary violated with ground-truth references: {all_violations}",
        )

        # Behavioral verification: StateSnapshot rejects state dictionaries containing truth keys
        from agent.memory.state.state_manager import StateManager
        from runtime.planners.planner_interface import StateSnapshot
        from runtime.state.knowledge_state_store import StoreContext
        ctx = StoreContext(run_id="RUN-BOUND-001", session_id="SES-001", episode_id="EP-001")
        base_state = StateManager(ctx.run_id, "SCN-001", "OBJ-001", {"actions": 10, "requests": 100, "seconds": 30.0}).get_state()

        for forbidden_key in ("ground_truth", "truth_records", "truth", "expected_detection"):
            corrupted_state = dict(base_state)
            corrupted_state[forbidden_key] = {"some": "truth"}
            with self.subTest(forbidden_key=forbidden_key):
                with self.assertRaises(ValueError, msg=f"StateSnapshot must reject {forbidden_key}"):
                    StateSnapshot.from_state(corrupted_state, context=ctx)

    def test_runtime_orchestration_boundary_invariants(self):
        """Invariant C: runtime/orchestration/** does not inject expected answers or ground truth into planner inputs."""
        scan_dirs = [
            ROOT / "runtime/orchestration",
        ]
        all_violations = []
        for scan_dir in scan_dirs:
            if not scan_dir.exists():
                continue
            for py_path in scan_dir.rglob("*.py"):
                violations = _scan_ast_for_ground_truth_violations(py_path)
                all_violations.extend(violations)

        self.assertEqual(
            all_violations,
            [],
            f"Orchestration boundary violated with ground-truth references: {all_violations}",
        )

        # Verify PlanningInput contract has no ground-truth accessors
        from agent.memory.state.state_manager import StateManager
        from runtime.planners.planner_interface import PlanningInput, StateSnapshot
        from runtime.state.knowledge_state_store import StoreContext
        ctx = StoreContext(run_id="RUN-BOUND-001", session_id="SES-001", episode_id="EP-001")
        base_state = StateManager(ctx.run_id, "SCN-001", "OBJ-001", {"actions": 10, "requests": 100, "seconds": 30.0}).get_state()
        snapshot = StateSnapshot.from_state(base_state, context=ctx)
        p_input = PlanningInput(
            state=snapshot,
            allowed_action_ids={"ACTION-RECON-001"},
            allowed_target_ids={"lab-webapp-a"},
        )
        self.assertFalse(hasattr(p_input, "ground_truth"))
        self.assertFalse(hasattr(p_input, "truth_records"))
        self.assertFalse(hasattr(p_input, "expected_answers"))

    def test_evaluation_domain_exception_can_load_ground_truth(self):
        """Invariant D: Code in Evaluation domain is authorized to load and validate canonical Ground Truth."""
        schema_path = ROOT / "evaluation/ground_truth/ground-truth.schema.json"
        self.assertTrue(schema_path.is_file())
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        sample_path = ROOT / "evaluation/ground-truth/sample.json"
        self.assertTrue(sample_path.is_file())
        sample_data = json.loads(sample_path.read_text(encoding="utf-8"))

        # Verify sample data validates cleanly against the canonical Ground Truth schema
        validation_errors = validate_shape(sample_data, schema)
        self.assertEqual(
            validation_errors,
            [],
            f"Sample ground-truth data failed validation against canonical schema: {validation_errors}",
        )

    def test_no_source_leakage_in_planner_public_apis(self):
        """Invariant E: Neither Planner base class nor standard planners expose indirect truth query methods."""
        from runtime.planners.planner_interface import Planner
        from runtime.planners.rule_based_planner import RuleBasedPlanner
        from runtime.planners.llm_planner import LLMPlanner
        from runtime.planners.hybrid_router import HybridReviewRouter
        from runtime.planners.observed_planner import ObservedStatePlanner

        planner_classes = [Planner, RuleBasedPlanner, LLMPlanner, HybridReviewRouter, ObservedStatePlanner]
        for cls in planner_classes:
            for attr in dir(cls):
                attr_lower = attr.lower()
                self.assertNotIn(
                    "ground_truth",
                    attr_lower,
                    f"Class {cls.__name__} exposes forbidden attribute {attr}",
                )
                self.assertNotIn(
                    "oracle_truth",
                    attr_lower,
                    f"Class {cls.__name__} exposes forbidden attribute {attr}",
                )

    def test_regression_scanner_actively_detects_violations(self):
        """Invariant: Test the regression scanner itself to prove it detects newly added ground-truth imports or loads."""
        synthetic_bad_code = """
import os
from evaluation.ground_truth import something
with open("evaluation/ground_truth/ground-truth.schema.json") as f:
    data = f.read()

def get_ground_truth():
    return "leak"
"""
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tmp:
            tmp.write(synthetic_bad_code)
            tmp_path = Path(tmp.name)

        try:
            violations = _scan_ast_for_ground_truth_violations(tmp_path)
            self.assertTrue(
                len(violations) >= 3,
                f"Regression scanner failed to detect synthetic violations: {violations}",
            )
            self.assertTrue(any("forbidden import from evaluation ground truth" in v for v in violations))
            self.assertTrue(any("literal ground-truth schema path reference" in v for v in violations))
            self.assertTrue(any("forbidden function/method name get_ground_truth" in v for v in violations))
        finally:
            tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
