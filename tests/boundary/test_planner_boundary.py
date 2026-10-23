"""Boundary tests verifying Planner isolation from simulation ground truth (RT-05A).

Enforces:
  Test G: Planners in runtime/planners/** NEVER import simulation hidden models,
          loaders, TrueState, HiddenScenario, or ground truth evaluators.
"""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

from scripts.validation.validate_scaffold import ROOT


FORBIDDEN_SIMULATION_IMPORTS = frozenset({
    "runtime.simulation.models.true_state",
    "runtime.simulation.models.scenario",
    "runtime.simulation.loader",
    "runtime.simulation.models.evaluator_view",
    "runtime.simulation.engine.transition_engine",
    "runtime.simulation.environment",
    "evaluation.ground_truth",
})


class TestPlannerGroundTruthBoundary(unittest.TestCase):
    """Enforce strict AST import isolation on runtime/planners/**."""

    def test_g_planners_never_import_simulation_hidden_models(self) -> None:
        """Test G: Planners in runtime/planners/** have zero imports of hidden simulation models."""
        planners_dir = ROOT / "runtime" / "planners"
        self.assertTrue(planners_dir.is_dir(), f"Directory not found: {planners_dir}")

        planner_py_files = list(planners_dir.glob("*.py"))
        self.assertTrue(len(planner_py_files) >= 4, f"Too few files found: {planner_py_files}")

        violations: list[str] = []

        for py_path in planner_py_files:
            rel_path = py_path.relative_to(ROOT).as_posix()
            source = py_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_path))

            for node in ast.walk(tree):
                # import foo.bar
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        for forbidden in FORBIDDEN_SIMULATION_IMPORTS:
                            if alias.name == forbidden or alias.name.startswith(forbidden + "."):
                                violations.append(
                                    f"{rel_path}:{node.lineno} imports forbidden module '{alias.name}'"
                                )
                # from foo.bar import baz
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    for forbidden in FORBIDDEN_SIMULATION_IMPORTS:
                        if mod == forbidden or mod.startswith(forbidden + "."):
                            violations.append(
                                f"{rel_path}:{node.lineno} imports from forbidden module '{mod}'"
                            )

        self.assertEqual(
            violations,
            [],
            f"Planner boundary violated: runtime/planners/** must NEVER import simulation hidden models:\n"
            + "\n".join(violations),
        )


if __name__ == "__main__":
    unittest.main()
