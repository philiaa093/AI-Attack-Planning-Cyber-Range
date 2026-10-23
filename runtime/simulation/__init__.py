"""Runtime Simulation Domain for Enterprise Attack Simulator (RT-04).

Defines the hidden environment state, hidden scenario models, and evaluator contracts.
Invariants:
- True State belongs strictly to the simulation and evaluation environments.
- Planner domain has zero visibility into hidden scenario, topology, vulnerabilities, or true state.
"""
from __future__ import annotations

from runtime.simulation.models.scenario import (
    HiddenScenario,
    HiddenNode,
    HiddenTopology,
    HiddenCredential,
    ObjectiveDefinition,
    ScenarioTransition,
    DetectionModel,
)
from runtime.simulation.models.true_state import (
    TrueState,
    NodeTrueState,
    SimulatedSession,
    CredentialTruth,
    ReachabilityEdge,
    ObjectiveTruth,
    DefenderState,
    SimulatorActionRecord,
)
from runtime.simulation.models.evaluator_view import ScenarioEvaluationView
from runtime.simulation.loader import ScenarioLoader
from runtime.simulation.engine.transition_engine import TransitionEngine, TransitionResult
from runtime.simulation.engine.observation_generator import ObservationGenerator
from runtime.simulation.engine.simulation_executor import SimulationExecutor, SimulationExecutionResult
from runtime.simulation.bootstrap import BootstrapObservationGenerator
from runtime.simulation.models.step_result import EpisodeStepResult, TerminationReason
from runtime.simulation.environment import EpisodeEnvironment, create_default_safety_gate
from runtime.simulation.gym_adapter import SimulationGymEnv, encode_belief_state_features

__all__ = [
    "HiddenScenario",
    "HiddenNode",
    "HiddenTopology",
    "HiddenCredential",
    "ObjectiveDefinition",
    "ScenarioTransition",
    "DetectionModel",
    "TrueState",
    "NodeTrueState",
    "SimulatedSession",
    "CredentialTruth",
    "ReachabilityEdge",
    "ObjectiveTruth",
    "DefenderState",
    "SimulatorActionRecord",
    "ScenarioEvaluationView",
    "ScenarioLoader",
    "TransitionEngine",
    "TransitionResult",
    "ObservationGenerator",
    "SimulationExecutor",
    "SimulationExecutionResult",
    "BootstrapObservationGenerator",
    "EpisodeStepResult",
    "TerminationReason",
    "EpisodeEnvironment",
    "create_default_safety_gate",
    "SimulationGymEnv",
    "encode_belief_state_features",
]


