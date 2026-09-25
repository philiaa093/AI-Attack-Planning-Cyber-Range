"""State manager — aggregate observations into planner state.

Builds state.schema.json from sequential observations.
Tracks: run_id, scenario_id, phase, remaining_budget, observed_facts, previous_actions.
Supports deterministic reconstruction from history log.

Isolation: no expected-data references.
"""

import copy


_VALID_PHASES = ("RECON", "DISCOVERY", "ANALYSIS", "TESTING", "REPLAN", "TERMINAL")

_DEFAULT_BUDGET = {
    "actions": 100,
    "requests": 500,
    "seconds": 3600.0,
}


class StateManager:
    """Aggregate observations sequentially to build planner state.

    Usage:
        sm = StateManager(run_id="RUN-001", scenario_id="SCN-001", objective_id="OBJ-001")
        sm.apply_observation(observation_dict)
        state = sm.get_state()  # conforms to state.schema.json
    """

    def __init__(self, run_id, scenario_id, objective_id, budget=None):
        self._run_id = run_id
        self._scenario_id = scenario_id
        self._objective_id = objective_id
        self._phase = "RECON"
        self._budget = copy.deepcopy(budget or _DEFAULT_BUDGET)
        self._facts = {}  # fact_id → fact dict (with source_observation_id)
        self._previous_actions = []

    @property
    def phase(self):
        return self._phase

    def set_phase(self, phase):
        """Transition to new phase."""
        if phase not in _VALID_PHASES:
            raise ValueError(f"invalid phase '{phase}'; must be one of {_VALID_PHASES}")
        self._phase = phase

    def apply_observation(self, observation):
        """Ingest one observation, update facts and budget.

        Args:
            observation: dict conforming to observation.schema.json
        """
        obs_id = observation.get("observation_id", "")
        action_id = observation.get("action_id", "")

        # Track action
        if action_id and action_id not in self._previous_actions:
            self._previous_actions.append(action_id)

        # Decrement budget
        self._budget["actions"] = max(0, self._budget["actions"] - 1)

        # Merge new facts
        for fact in observation.get("new_facts", []):
            state_fact = dict(fact)
            state_fact["source_observation_id"] = obs_id
            fact_id = state_fact["fact_id"]

            # Keep higher confidence on collision
            if fact_id in self._facts:
                if state_fact.get("confidence", 0) > self._facts[fact_id].get("confidence", 0):
                    self._facts[fact_id] = state_fact
            else:
                self._facts[fact_id] = state_fact

    def decrement_requests(self, n=1):
        """Decrement request budget by n."""
        self._budget["requests"] = max(0, self._budget["requests"] - n)

    def decrement_seconds(self, s):
        """Decrement time budget by s seconds."""
        self._budget["seconds"] = max(0.0, self._budget["seconds"] - s)

    def get_state(self):
        """Build state dict conforming to state.schema.json."""
        return {
            "schema_version": "1.0",
            "run_id": self._run_id,
            "scenario_id": self._scenario_id,
            "objective_id": self._objective_id,
            "phase": self._phase,
            "remaining_budget": copy.deepcopy(self._budget),
            "observed_facts": list(self._facts.values()),
            "previous_actions": list(self._previous_actions),
        }

    def get_fact_count(self):
        """Return number of observed facts."""
        return len(self._facts)

    @classmethod
    def reconstruct_from_observations(cls, observations, run_id, scenario_id,
                                       objective_id, budget=None):
        """Deterministically reconstruct state by replaying observations.

        Args:
            observations: iterable of observation dicts in sequence order
            run_id, scenario_id, objective_id: identifiers
            budget: optional initial budget dict

        Returns:
            StateManager with fully reconstructed state
        """
        sm = cls(run_id, scenario_id, objective_id, budget)
        for obs in observations:
            sm.apply_observation(obs)
        return sm
