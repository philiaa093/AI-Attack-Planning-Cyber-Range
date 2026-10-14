"""Normalize externally collected defensive summaries; no target/agent dispatch."""
from __future__ import annotations

from pathlib import Path
from collections import defaultdict

from runtime.evaluation.usage_costs import LIMIT, count, identifier, load_json_bytes, no_links, sha, utc_timestamp


FIELDS = {"schema_version", "run_id", "episode_id", "agent_id", "scenario_id", "split",
          "seed", "created_at_utc", "outcome", "steps"}
OUTCOMES = {"succeeded", "failed", "error", "timeout", "refused"}


def import_defensive_summaries(path, expected_sha256):
    """JSONL summaries from an external, authorized defensive test harness.

    A file digest verifies byte consistency, not that a live test took place or
    that the harness correctly applied its outcome oracle. Outcomes are claims.
    """
    path = Path(path).absolute()
    no_links(path)
    with path.open("rb") as stream:
        data = stream.read(LIMIT + 1)
    if len(data) > LIMIT or sha(data) != expected_sha256:
        raise ValueError("defensive log size/hash mismatch")
    rows, identities, episode_ids, run_ids = [], set(), set(), set()
    by_group = defaultdict(list)
    for line in data.splitlines():
        if not line.strip():
            raise ValueError("blank defensive log record")
        row = load_json_bytes(line)
        if type(row) is not dict or set(row) != FIELDS or type(row["schema_version"]) is not int or row["schema_version"] != 1:
            raise ValueError("closed defensive summary schema required")
        for field in ("run_id", "episode_id", "agent_id", "scenario_id"):
            identifier(row[field])
        utc_timestamp(row["created_at_utc"])
        count(row["seed"]); count(row["steps"])
        if (type(row["split"]) is not str or type(row["outcome"]) is not str
                or row["split"] not in ("standard", "heldout") or row["outcome"] not in OUTCOMES):
            raise ValueError("supported defensive split/outcome required")
        key = row["agent_id"], row["split"], row["scenario_id"], row["seed"]
        if key in identities or row["episode_id"] in episode_ids:
            raise ValueError("duplicate defensive episode or experimental unit")
        identities.add(key); episode_ids.add(row["episode_id"])
        run_ids.add(row["run_id"]); rows.append(row)
        by_group[row["agent_id"], row["split"]].append(row)
        if len(rows) > 100_000:
            raise ValueError("too many defensive summaries")
    if not rows or len(run_ids) != 1:
        raise ValueError("nonempty single-run defensive log required")
    groups = []
    for (agent, split), group in sorted(by_group.items()):
        successes = sum(r["outcome"] == "succeeded" for r in group)
        groups.append(dict(agent_id=agent, split=split, episodes=len(group), successes_claimed=successes,
                           success_claim_rate=successes / len(group),
                           mean_steps=sum(r["steps"] for r in group) / len(group), exclusions=0))
    return dict(run_id=next(iter(run_ids)), source="IMPORTED_UNVERIFIED_DEFENSIVE_LOG",
                source_log_sha256=expected_sha256, normalized_episodes=rows, summaries=groups,
                live_execution="UNRESOLVED", oracle_validation="UNRESOLVED")
