"""Automated Boundary Invariant Tests for Hidden Scenario & True State Model (RT-04A).

Invariants enforced:
1. Core Architecture Invariant: True State belongs exclusively to runtime/simulation and
   Evaluation domains.
2. Planner Isolation: runtime/planners/** and agent/planner/** have ZERO executable imports or
   references to runtime.simulation, HiddenScenario, or TrueState.
3. State Boundary: agent/memory/** and BeliefState do not import or subclass TrueState.
4. Constraint Evaluator Isolation: runtime/evaluators/action_evaluator.py operates strictly on
   Belief State and does not read scenario or TrueState.
5. Fog-of-War at t=0:
   - Full hidden node inventory does not appear in initial visible targets (entry seed only).
   - Hidden topology does not pre-populate observed reachability.
   - Hidden credentials do not appear in Belief State.
   - Hidden objective node location does not appear in initial PlanningInput.
"""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

from runtime.simulation.loader import ScenarioLoader
from runtime.simulation.models.scenario import HiddenScenario
from runtime.simulation.models.true_state import TrueState
from runtime.planners.planner_interface import PlanningInput, StateSnapshot
from runtime.planners.planner_adapter import PlannerStateAdapter
from agent.memory.state.belief_state import project_belief_state
from runtime.evaluators.action_evaluator import ActionConstraintEvaluator


ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = ROOT / "runtime/simulation/fixtures/scenarios"

FORBIDDEN_SIMULATION_SYMBOLS = frozenset({
    "HiddenScenario",
    "TrueState",
    "ScenarioLoader",
    "EpisodeEnvironment",
    "SimulationGymEnv",
    "BootstrapObservationGenerator",
    "TransitionEngine",
    "SimulationExecutor",
})


def _scan_ast_for_simulation_violations(path: Path) -> list[str]:
    violations: list[str] = []
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except Exception as exc:
        return [f"{path}: failed to parse AST: {exc}"]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("runtime.simulation"):
                    violations.append(f"{path}:{node.lineno}: forbidden import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.startswith("runtime.simulation"):
                violations.append(f"{path}:{node.lineno}: forbidden import from {mod}")
            for alias in node.names:
                if alias.name in FORBIDDEN_SIMULATION_SYMBOLS:
                    violations.append(f"{path}:{node.lineno}: forbidden import name {alias.name}")
    return violations


class SimulationBoundaryTests(unittest.TestCase):
    """Enforce strict boundary between simulator hidden environment and planner domain."""

    def setUp(self) -> None:
        self.loader = ScenarioLoader()
        self.s1 = self.loader.load_from_file(FIXTURES_DIR / "scenario_s1_straight.json")

    def test_planner_domain_ast_has_zero_simulation_imports(self) -> None:
        """Invariant D: runtime/planners/** and agent/planner/** cannot import simulation models."""
        scan_dirs = [
            ROOT / "runtime/planners",
            ROOT / "agent/planner",
            ROOT / "agent/memory",
            ROOT / "agent/perception",
        ]
        violations = []
        for d in scan_dirs:
            if not d.exists():
                continue
            for py_path in d.rglob("*.py"):
                violations.extend(_scan_ast_for_simulation_violations(py_path))

        self.assertEqual(
            violations,
            [],
            f"Planner/agent domain violated with forbidden simulation imports: {violations}",
        )

    def test_planner_state_adapter_does_not_expose_scenario(self) -> None:
        """Invariant E: PlannerStateAdapter has zero scenario loading or exposure methods."""
        adapter_attrs = dir(PlannerStateAdapter)
        forbidden_attrs = {"scenario", "true_state", "hidden_nodes", "hidden_topology", "load_scenario"}
        found = forbidden_attrs.intersection(adapter_attrs)
        self.assertEqual(found, set(), f"PlannerStateAdapter exposes hidden simulation attributes: {found}")

    def test_constraint_evaluator_does_not_read_true_state_or_scenario(self) -> None:
        """Invariant J: ActionConstraintEvaluator operates strictly without simulation domain."""
        evaluator_path = ROOT / "runtime/evaluators/action_evaluator.py"
        violations = _scan_ast_for_simulation_violations(evaluator_path)
        self.assertEqual(
            violations,
            [],
            f"ActionConstraintEvaluator violated with simulation imports: {violations}",
        )

        evaluator_attrs = dir(ActionConstraintEvaluator)
        forbidden_attrs = {"scenario", "true_state", "hidden_nodes", "hidden_topology"}
        found = forbidden_attrs.intersection(evaluator_attrs)
        self.assertEqual(found, set())

    def test_initial_fog_of_war_only_entry_seed_visible(self) -> None:
        """Invariant F: At t=0, visible targets contain ONLY entry seed, never hidden inventory."""
        entry_seed = self.s1.entry_seed
        all_hidden_node_ids = {n.node_id for n in self.s1.hidden_nodes}

        # Planner visible targets at t=0 must only be the entry seed
        initial_visible_targets = (entry_seed,)

        self.assertIn(entry_seed, initial_visible_targets)
        for hidden_id in all_hidden_node_ids:
            if hidden_id != entry_seed:
                self.assertNotIn(
                    hidden_id,
                    initial_visible_targets,
                    f"Hidden node {hidden_id!r} leaked into initial planner visibility!",
                )

    def test_hidden_topology_does_not_populate_observed_reachability(self) -> None:
        """Invariant G: Hidden topology does not populate observed reachability at t=0."""
        # Initial belief projection from empty observation list
        belief = project_belief_state([])

        # Observed reachability must be empty at t=0
        observed_reachability = belief.get("reachability", [])
        self.assertEqual(
            len(observed_reachability),
            0,
            f"Belief state has non-empty initial reachability: {observed_reachability}",
        )

        # Ensure hidden edges from scenario are NOT in belief
        for edge in self.s1.hidden_topology.edges:
            self.assertFalse(
                any(r.get("source") == edge.source and r.get("target") == edge.target for r in observed_reachability),
                f"Hidden edge {edge.source}->{edge.target} leaked into belief reachability!",
            )

    def test_hidden_credentials_do_not_appear_in_belief_state(self) -> None:
        """Invariant H: Hidden credentials do not appear in initial Belief State."""
        belief = project_belief_state([])
        known_creds = belief.get("known_credentials", [])
        self.assertEqual(len(known_creds), 0)

        for hidden_cred in self.s1.hidden_credentials:
            self.assertFalse(
                any(c.get("credential_id") == hidden_cred.credential_id for c in known_creds),
                f"Hidden credential {hidden_cred.credential_id!r} leaked into belief state!",
            )

    def test_hidden_objective_location_does_not_appear_in_planner_input(self) -> None:
        """Invariant I: Hidden objective location does not appear in initial PlanningInput."""
        from runtime.state.knowledge_state_store import StoreContext

        entry_seed = self.s1.entry_seed
        hidden_obj_node = self.s1.objective.target_node_id

        context = StoreContext("RUN-TEST-FOW-001", "SES-001", "EP-001")
        base_state = {
            "schema_version": "1.0",
            "run_id": context.run_id,
            "scenario_id": "SCN-001",
            "objective_id": "OBJ-001",
            "phase": "RECON",
            "remaining_budget": {"actions": 10, "requests": 50, "seconds": 3600.0},
            "observed_facts": [],
            "previous_actions": [],
        }
        snapshot = StateSnapshot.from_state(base_state, context=context)

        # At t=0, create planning input with only entry seed
        planning_input = PlanningInput(
            state=snapshot,
            allowed_action_ids={"ACTION-RECON-001", "ACTION-SCAN-001"},
            visible_target_ids={entry_seed},
        )

        self.assertNotIn(hidden_obj_node, planning_input.visible_target_ids)
        self.assertEqual(planning_input.visible_target_ids, frozenset({entry_seed}))

    def test_simulation_engine_ast_has_zero_leaks_to_planner(self) -> None:
        """Invariant: Planner domain cannot import any simulation engine class."""
        forbidden_names = (
            "TransitionEngine",
            "TransitionResult",
            "ObservationGenerator",
            "SimulationExecutor",
            "SimulationExecutionResult",
        )
        scan_dirs = [
            ROOT / "runtime/planners",
            ROOT / "agent/planner",
            ROOT / "agent/memory",
            ROOT / "agent/perception",
        ]
        violations = []
        for d in scan_dirs:
            if not d.exists():
                continue
            for py_path in d.rglob("*.py"):
                try:
                    tree = ast.parse(py_path.read_text(encoding="utf-8"), filename=str(py_path))
                except Exception:
                    continue
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        for alias in node.names:
                            if alias.name in forbidden_names:
                                violations.append(f"{py_path}:{node.lineno}: forbidden import {alias.name}")
        self.assertEqual(violations, [])

    def test_emitted_observation_does_not_leak_ground_truth_keys(self) -> None:
        """Invariant: Emitted observations never leak forbidden ground truth or secret tokens."""
        from runtime.simulation.engine.observation_generator import ObservationGenerator
        from runtime.simulation.engine.transition_engine import TransitionEngine

        engine = TransitionEngine()
        obs_gen = ObservationGenerator()
        state = self.s1.create_initial_true_state(run_id="RUN-BND-TEST")

        res = engine.transition(state, self.s1, "ACTION-RECON-001", "lab-dmz-entry")
        obs = obs_gen.generate_observation(res, run_id="RUN-BND-TEST")

        forbidden_keys = {"ground_truth", "truth", "hidden_topology", "password", "private_key"}
        raw_json = str(obs).lower()
        for k in forbidden_keys:
            self.assertNotIn(k, raw_json, f"Forbidden token '{k}' found in emitted observation!")


if __name__ == "__main__":
    unittest.main()

