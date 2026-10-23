"""Simulation Engine Package (RT-04B).

Provides canonical transition engine, observation generator, and end-to-end
simulation executor for the Enterprise Attack Simulator.
"""
from runtime.simulation.engine.observation_generator import ObservationGenerator
from runtime.simulation.engine.simulation_executor import (
    SimulationExecutionResult,
    SimulationExecutor,
)
from runtime.simulation.engine.transition_engine import (
    TransitionEngine,
    TransitionResult,
)

__all__ = [
    "ObservationGenerator",
    "SimulationExecutionResult",
    "SimulationExecutor",
    "TransitionEngine",
    "TransitionResult",
]
