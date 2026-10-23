"""Bounded runtime: lab."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from runtime.lab.live_environment import LiveEpisodeEnvironment, create_live_safety_gate
    from runtime.lab.live_executor_adapter import LiveExecutionResult, LiveExecutorAdapter

__all__ = [
    "LiveEpisodeEnvironment",
    "create_live_safety_gate",
    "LiveExecutionResult",
    "LiveExecutorAdapter",
]


def __getattr__(name: str):
    if name in ("LiveEpisodeEnvironment", "create_live_safety_gate"):
        import runtime.lab.live_environment as _env
        return getattr(_env, name)
    if name in ("LiveExecutionResult", "LiveExecutorAdapter"):
        import runtime.lab.live_executor_adapter as _adapter
        return getattr(_adapter, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
