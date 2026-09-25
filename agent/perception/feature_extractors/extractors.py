"""Feature extraction utilities for observation facts.

Extract typed subsets from observation facts for planner consumption.
Isolation: no expected-data references.
"""


def extract_services(facts):
    """Extract SERVICE facts from a list of facts."""
    return [f for f in facts if f.get("fact_type") == "SERVICE"]


def extract_endpoints(facts):
    """Extract ENDPOINT facts from a list of facts."""
    return [f for f in facts if f.get("fact_type") == "ENDPOINT"]


def extract_parameters(facts):
    """Extract PARAMETER facts from a list of facts."""
    return [f for f in facts if f.get("fact_type") == "PARAMETER"]


def extract_findings(facts, min_confidence=0.0):
    """Extract CANDIDATE_FINDING and CONFIRMED_FINDING facts.

    Args:
        facts: list of fact dicts
        min_confidence: minimum confidence threshold (inclusive)

    Returns:
        list of finding facts above threshold
    """
    return [
        f for f in facts
        if f.get("fact_type") in ("CANDIDATE_FINDING", "CONFIRMED_FINDING")
        and f.get("confidence", 0) >= min_confidence
    ]


def group_by_subject(facts):
    """Group facts by subject (target_id)."""
    groups = {}
    for f in facts:
        subj = f.get("subject", "")
        groups.setdefault(subj, []).append(f)
    return groups


def group_by_type(facts):
    """Group facts by fact_type."""
    groups = {}
    for f in facts:
        ft = f.get("fact_type", "")
        groups.setdefault(ft, []).append(f)
    return groups
