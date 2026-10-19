"""Unit tests for BootstrapObservationGenerator (RT-04C Requirements A & B)."""
from __future__ import annotations

import unittest
from pathlib import Path

from agent.memory.state.belief_state import BeliefState
from agent.memory.state.state_manager import StateManager
from agent.perception.normalizers.enterprise_normalizer import validate_canonical_observation
from runtime.simulation.bootstrap import BootstrapObservationGenerator
from runtime.simulation.loader import ScenarioLoader


class TestBootstrapObservationGenerator(unittest.TestCase):
    """Test t=0 bootstrap observation generation and Fog-of-War enforcement."""

    def setUp(self) -> None:
        self.fixtures_dir = (
            Path(__file__).parent.parent.parent
            / "runtime"
            / "simulation"
            / "fixtures"
            / "scenarios"
        )
        self.loader = ScenarioLoader()
        self.s1 = self.loader.load_from_file(self.fixtures_dir / "scenario_s1_straight.json")
        self.s2 = self.loader.load_from_file(self.fixtures_dir / "scenario_s2_decoy.json")
        self.s3 = self.loader.load_from_file(self.fixtures_dir / "scenario_s3_blocked.json")
        self.s4 = self.loader.load_from_file(self.fixtures_dir / "scenario_s4_clean.json")
        self.generator = BootstrapObservationGenerator()

    def test_bootstrap_schema_validity(self) -> None:
        """Bootstrap observation must strictly conform to canonical observation.schema.json."""
        obs = self.generator.generate_bootstrap_observation(self.s1, run_id="RUN-TEST-BOOT-01")
        errors = validate_canonical_observation(obs)
        self.assertEqual(errors, [])
        self.assertEqual(obs["outcome"], "SUCCESS")
        self.assertEqual(obs["source_kind"], "SIMULATED")
        self.assertEqual(obs["sequence_num"], 0)
        self.assertEqual(len(obs["new_facts"]), 1)

    def test_bootstrap_exposes_only_entry_seed(self) -> None:
        """Requirement A: Bootstrap observation must expose ONLY the entry seed."""
        for scenario in (self.s1, self.s2, self.s3, self.s4):
            with self.subTest(scenario=scenario.scenario_id):
                obs = self.generator.generate_bootstrap_observation(scenario, run_id="RUN-TEST-BOOT")
                fact = obs["new_facts"][0]
                self.assertEqual(fact["fact_type"], "TARGET")
                self.assertEqual(fact["subject"], scenario.entry_seed)
                self.assertEqual(fact["value"]["target_id"], scenario.entry_seed)

    def test_hidden_inventory_absent_from_initial_observation(self) -> None:
        """Requirement B: Non-entry hidden nodes must NOT leak in bootstrap observation or initial belief."""
        for scenario in (self.s1, self.s2, self.s3, self.s4):
            with self.subTest(scenario=scenario.scenario_id):
                obs = self.generator.generate_bootstrap_observation(scenario, run_id="RUN-TEST-FOG")

                # StateManager ingests bootstrap
                sm = StateManager(
                    run_id="RUN-TEST-FOG",
                    scenario_id=scenario.scenario_id,
                    objective_id=scenario.objective.objective_id,
                )
                sm.apply_observation(obs)
                belief: BeliefState = sm.get_belief_state()

                # Visible target IDs should contain ONLY the entry seed
                self.assertEqual(belief.visible_target_ids, frozenset({scenario.entry_seed}))
                self.assertEqual(set(belief.known_hosts.keys()), {scenario.entry_seed})

                # All other hidden nodes must NOT be known
                non_entry_nodes = {n.node_id for n in scenario.hidden_nodes} - {scenario.entry_seed}
                for hidden_id in non_entry_nodes:
                    self.assertNotIn(hidden_id, belief.visible_target_ids)
                    self.assertFalse(belief.is_host_known(hidden_id))

                # No credentials, findings, reachability, or sessions should be exposed at t=0
                self.assertEqual(len(belief.known_credentials), 0)
                self.assertEqual(len(belief.confirmed_findings), 0)
                self.assertEqual(len(belief.observed_reachability), 0)
                self.assertEqual(len(belief.active_sessions), 0)


if __name__ == "__main__":
    unittest.main()
