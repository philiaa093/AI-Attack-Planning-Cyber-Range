"""Small deterministic binary-classification metric formulas."""
from __future__ import annotations


def _count(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("counts must be non-negative integers")
    return value


def _ratio(numerator: int, denominator: int) -> float | None:
    numerator, denominator = _count(numerator), _count(denominator)
    return numerator / denominator if denominator else None


def precision(true_positive: int, false_positive: int) -> float | None:
    return _ratio(true_positive, true_positive + false_positive)


def recall(true_positive: int, false_negative: int) -> float | None:
    return _ratio(true_positive, true_positive + false_negative)


def f1(true_positive: int, false_positive: int, false_negative: int) -> float | None:
    true_positive = _count(true_positive)
    false_positive = _count(false_positive)
    false_negative = _count(false_negative)
    denominator = 2 * true_positive + false_positive + false_negative
    return 2 * true_positive / denominator if denominator else None


def false_positive_rate(false_positive: int, true_negative: int) -> float | None:
    return _ratio(false_positive, false_positive + true_negative)


def goal_success_rate(successes: int, goals: int) -> float | None:
    return _ratio(successes, goals)


def planning_validity_rate(valid_plans: int, plans: int) -> float | None:
    return _ratio(valid_plans, plans)


def replanning_success_rate(successful_replans: int, replans: int) -> float | None:
    return _ratio(successful_replans, replans)


def redundant_action_rate(redundant_actions: int, actions: int) -> float | None:
    return _ratio(redundant_actions, actions)
