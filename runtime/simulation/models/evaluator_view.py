"""Read-only Evaluation View Interface (RT-04A).

Provides a read-only scoring interface combining True State, Belief State, and Action History
strictly for evaluation tools, scoring harnesses, and research benchmarks.

HARD INVARIANTS:
1. Ground Truth Isolation: The Planner domain CANNOT instantiate or read ScenarioEvaluationView.
2. Read-Only Contract: Does NOT expose mutation or transition methods.
3. No Metrics Execution: Does not implement full empirical metrics in RT-04A.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from runtime.simulation.models.true_state import TrueState, SimulatorActionRecord


@dataclass(frozen=True)
class ScenarioEvaluationView:
    """Read-only evaluator contract for future benchmark and scoring engines."""

    true_state: TrueState
    belief_state: Mapping[str, Any]
    action_history: tuple[SimulatorActionRecord, ...]

    def is_objective_achieved(self) -> bool:
        """Return ground truth objective achievement state."""
        return self.true_state.is_objective_achieved()

    def get_detection_state(self) -> str:
        """Return ground truth defender detection state."""
        return self.true_state.defender_state.detection_state

    def get_accumulated_noise(self) -> float:
        """Return ground truth accumulated operational noise."""
        return self.true_state.defender_state.accumulated_noise

    def get_compromised_node_ids(self) -> frozenset[str]:
        """Return ground truth set of compromised node IDs."""
        return frozenset(self.true_state.get_compromised_nodes())

    def get_discovered_node_ids_in_belief(self) -> frozenset[str]:
        """Return set of known host IDs reported in the agent's Belief State."""
        known_hosts = self.belief_state.get("known_hosts", {})
        if isinstance(known_hosts, dict):
            return frozenset(known_hosts.keys())
        return frozenset()

    def get_reachability_edges_count(self) -> int:
        """Return count of unblocked reachability edges in ground truth."""
        return len([e for e in self.true_state.reachability_truth if not e.is_blocked])

    def get_alignment_summary(self) -> dict[str, Any]:
        """Return read-only alignment summary between Belief State and True State."""
        true_compromised = self.get_compromised_node_ids()
        belief_known = self.get_discovered_node_ids_in_belief()

        # Nodes the agent knows about that are actually compromised
        accurate_discoveries = true_compromised.intersection(belief_known)

        return {
            "scenario_id": self.true_state.scenario_id,
            "run_id": self.true_state.run_id,
            "step": self.true_state.current_step,
            "objective_achieved": self.is_objective_achieved(),
            "detection_state": self.get_detection_state(),
            "accumulated_noise": self.get_accumulated_noise(),
            "true_compromised_count": len(true_compromised),
            "belief_known_count": len(belief_known),
            "accurate_discoveries_count": len(accurate_discoveries),
            "total_actions_taken": len(self.action_history),
        }
