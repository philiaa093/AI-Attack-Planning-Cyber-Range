"""Bounded metadata-replay evaluation; no learned model or runtime success claim."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

import numpy as np

from runtime.evaluation.replay_wrappers import (
    OBSERVATION_VERSION, REWARD_VERSION, ReplayRewardMaskWrapper,
)
from runtime.evaluation.rl_environment import OPERATIONS, ReplayAsset, ReplayAssessmentEnv


_ID = re.compile(r"[a-z][a-z0-9-]{0,63}")


def _identifier(value):
    if type(value) is not str or not _ID.fullmatch(value):
        raise ValueError("bounded metadata identifier required")
    return value


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("integer outside evaluation bounds")
    return value


def _hash(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()).hexdigest()


@dataclass(frozen=True)
class ReplayFixture:
    """Immutable synthetic metadata, visible to the evaluator, not the policy."""

    fixture_id: str
    family_id: str
    assets: tuple[ReplayAsset, ...]
    approved_targets: tuple[str, ...]
    approved_operations: tuple[str, ...] = OPERATIONS
    lab_mode: bool = True
    max_steps: int = 20
    min_interval_ticks: int = 1

    def __post_init__(self):
        _identifier(self.fixture_id)
        _identifier(self.family_id)
        if any(type(x) is not tuple for x in (
            self.assets, self.approved_targets, self.approved_operations
        )):
            raise ValueError("immutable fixture tuples required")
        # Reuse canonical replay validation; no reset or transition is executed.
        self.make_env().close()
        if len(set(self.approved_targets)) != len(self.approved_targets):
            raise ValueError("duplicate approval")
        if len(set(self.approved_operations)) != len(self.approved_operations):
            raise ValueError("duplicate operation")

    def make_env(self):
        return ReplayAssessmentEnv(
            self.assets, approved_targets=self.approved_targets,
            approved_operations=self.approved_operations, lab_mode=self.lab_mode,
            max_steps=self.max_steps, min_interval_ticks=self.min_interval_ticks,
        )

    def content_hash(self):
        # Ignore names and slot permutations when detecting split contamination.
        rows = sorted((a.inventory_items,
                       "unknown" if a.candidate_reported is None else str(a.candidate_reported),
                       a.target_id in self.approved_targets) for a in self.assets)
        return _hash(dict(rows=rows, operations=sorted(self.approved_operations),
                          lab_mode=self.lab_mode, max_steps=self.max_steps,
                          interval=self.min_interval_ticks))

    def identity_record(self):
        return dict(fixture_id=self.fixture_id, family_id=self.family_id,
                    assets=[[a.target_id, a.inventory_items, a.candidate_reported]
                            for a in self.assets],
                    targets=sorted(self.approved_targets),
                    operations=sorted(self.approved_operations), lab_mode=self.lab_mode,
                    max_steps=self.max_steps, interval=self.min_interval_ticks)


@dataclass(frozen=True)
class OfflineEvaluationProtocol:
    """Matched spaces/budgets and split disjointness, not a sealed test service."""

    train: tuple[ReplayFixture, ...]
    validation: tuple[ReplayFixture, ...]
    test: tuple[ReplayFixture, ...]
    episode_seeds: tuple[int, ...] = (101, 102, 103, 104, 105)
    masking: bool = True

    def __post_init__(self):
        if type(self.masking) is not bool:
            raise ValueError("boolean masking mode required")
        if type(self.episode_seeds) is not tuple or not 1 <= len(self.episode_seeds) <= 100:
            raise ValueError("1-100 immutable evaluation seeds required")
        for seed in self.episode_seeds:
            _integer(seed, 0, 2**32 - 1)
        if len(set(self.episode_seeds)) != len(self.episode_seeds):
            raise ValueError("unique seeds required")
        ids, owners, shapes = set(), {}, set()
        for split in ("train", "validation", "test"):
            fixtures = getattr(self, split)
            if type(fixtures) is not tuple or not 1 <= len(fixtures) <= 100:
                raise ValueError("1-100 immutable fixtures per split required")
            for fixture in fixtures:
                if type(fixture) is not ReplayFixture:
                    raise ValueError("ReplayFixture required")
                if fixture.fixture_id in ids:
                    raise ValueError("fixture IDs must be globally unique")
                ids.add(fixture.fixture_id)
                for key in (("family", fixture.family_id), ("content", fixture.content_hash())):
                    if key in owners and owners[key] != split:
                        raise ValueError("fixture family/content overlaps evaluation splits")
                    owners[key] = split
                shapes.add((len(fixture.assets), fixture.max_steps, fixture.min_interval_ticks))
        if len(shapes) != 1:
            raise ValueError("matched N, decision budget and tick rate required")

    def fingerprint(self):
        return _hash(dict(
            splits={name: [f.identity_record() for f in getattr(self, name)]
                    for name in ("train", "validation", "test")},
            seeds=self.episode_seeds, masking=self.masking,
            observation_version=OBSERVATION_VERSION, reward_version=REWARD_VERSION,
            intrinsic_budget_terminal=True,
        ))


@dataclass(frozen=True)
class OfflineEpisodeResult:
    fixture_id: str
    episode_seed: int
    decisions: int
    episode_return: float
    complete: bool
    refusals: int
    repeated_reads: int
    invalid_proposals: int
    stop_reason: str
    outcomes: tuple[str, ...]


@dataclass(frozen=True)
class OfflineEvaluationResult:
    candidate_id: str
    split: str
    protocol_sha256: str
    episodes: tuple[OfflineEpisodeResult, ...]

    def metrics(self):
        completed = [e.decisions for e in self.episodes if e.complete]
        returns = [e.episode_return for e in self.episodes]
        return dict(
            episodes=len(self.episodes),
            completion_rate=sum(e.complete for e in self.episodes) / len(self.episodes),
            mean_return=float(np.mean(returns)),
            return_std=float(np.std(returns)),
            mean_decisions=float(np.mean([e.decisions for e in self.episodes])),
            mean_decisions_completed=float(np.mean(completed)) if completed else None,
            refusals=sum(e.refusals for e in self.episodes),
            repeated_reads=sum(e.repeated_reads for e in self.episodes),
            invalid_proposals=sum(e.invalid_proposals for e in self.episodes),
            budget_exhaustions=sum(e.stop_reason == "BUDGET_EXHAUSTED" for e in self.episodes),
            empty_masks=sum(e.stop_reason == "NO_VALID_ACTION" for e in self.episodes),
            policy_errors=sum(e.stop_reason == "POLICY_ERROR" for e in self.episodes),
        )


def evaluate_offline(protocol, selector, *, candidate_id, split="validation"):
    """selector(observation, boolean_mask, seeded_rng) returns a scalar index.

    Selector is trusted local code, expected to perform inference only. It receives
    detached public arrays, never the environment, IDs, fixtures or unrevealed facts.
    This function cannot enforce weight immutability or prevent caller I/O/tuning.
    Simulator/audit/scorer exceptions abort evaluation rather than minting results.
    """
    if type(protocol) is not OfflineEvaluationProtocol or not callable(selector):
        raise ValueError("validated protocol and trusted selector required")
    _identifier(candidate_id)
    if type(split) is not str or split not in ("validation", "test"):
        raise ValueError("validation or test split required")
    episodes = []
    for fixture in getattr(protocol, split):
        for seed in protocol.episode_seeds:
            env = ReplayRewardMaskWrapper(fixture.make_env())
            outcomes, total, repeated, refusals, invalid = [], 0.0, 0, 0, 0
            stop, complete = "BUDGET_EXHAUSTED", False
            try:
                observation, _ = env.reset(seed=seed)
                rng = np.random.default_rng(seed)
                for _ in range(fixture.max_steps):
                    mask = env.action_masks()
                    if not mask.any():
                        stop = "NO_VALID_ACTION"
                        break
                    try:
                        action = selector({k: v.copy() for k, v in observation.items()},
                                          mask.copy(), rng)
                    except Exception:
                        stop = "POLICY_ERROR"
                        break
                    if (isinstance(action, (bool, np.bool_))
                            or not isinstance(action, (int, np.integer))
                            or not env.action_space.contains(action)):
                        invalid, stop = 1, "MALFORMED_PROPOSAL"
                        break
                    action = int(action)
                    if protocol.masking and not mask[action]:
                        invalid, stop = 1, "MASK_VIOLATION"
                        break
                    observation, reward, terminated, truncated, info = env.step(action)
                    outcome = info["outcome"]
                    outcomes.append(outcome)
                    total += reward
                    repeated += outcome == "NO_PROGRESS"
                    refusals += outcome.startswith("DENIED_")
                    if terminated or truncated:
                        complete = outcome == "REVIEW_COMPLETE"
                        stop = "BUDGET_EXHAUSTED" if info["budget_exhausted"] else outcome
                        break
            finally:
                env.close()
            episodes.append(OfflineEpisodeResult(
                fixture.fixture_id, seed, len(outcomes), float(total), complete,
                refusals, repeated, invalid, stop, tuple(outcomes),
            ))
    return OfflineEvaluationResult(candidate_id, split, protocol.fingerprint(), tuple(episodes))
