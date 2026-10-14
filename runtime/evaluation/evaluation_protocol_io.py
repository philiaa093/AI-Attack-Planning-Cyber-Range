"""Pinned input boundary for the existing offline metadata evaluation protocol.

This separate format never modifies canonical scenarios or grants execution
approval. Only the two existing synthetic selectors are evaluated downstream.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from runtime.audit.audit_support import closed, pinned_json
from runtime.evaluation.offline_evaluation import OfflineEvaluationProtocol, ReplayFixture
from runtime.evaluation.rl_environment import ReplayAsset
from runtime.evaluation.usage_costs import no_links


@dataclass(frozen=True)
class PinnedProtocol:
    protocol: OfflineEvaluationProtocol
    input_sha256: str


def protocol_document(protocol: OfflineEvaluationProtocol) -> dict:
    if type(protocol) is not OfflineEvaluationProtocol:
        raise ValueError("offline protocol required")
    protocol.__post_init__()
    return dict(schema_version=1, source="SIMULATED_FIXTURE",
                splits={split: [fixture.identity_record() for fixture in getattr(protocol, split)]
                        for split in ("train", "validation", "test")},
                seeds=list(protocol.episode_seeds), masking=protocol.masking)


def load_protocol(path: Path, expected_sha256: str, *, input_root: Path) -> PinnedProtocol:
    path, root = Path(path).absolute(), Path(input_root).absolute()
    no_links(root); no_links(path)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("protocol outside approved input root")
    data = pinned_json(path, expected_sha256)
    closed(data, {"schema_version", "source", "splits", "seeds", "masking"})
    if type(data["schema_version"]) is not int or data["schema_version"] != 1 or data["source"] != "SIMULATED_FIXTURE":
        raise ValueError("supported offline protocol format required")
    closed(data["splits"], {"train", "validation", "test"})
    if type(data["seeds"]) is not list or not 1 <= len(data["seeds"]) <= 100:
        raise ValueError("bounded seed list required")
    fixtures = {}
    for split in ("train", "validation", "test"):
        rows = data["splits"][split]
        if type(rows) is not list or not 1 <= len(rows) <= 100:
            raise ValueError("bounded split list required")
        items = []
        for row in rows:
            closed(row, {"fixture_id", "family_id", "assets", "targets", "operations", "lab_mode", "max_steps", "interval"})
            if type(row["assets"]) is not list or not 1 <= len(row["assets"]) <= 64:
                raise ValueError("bounded asset list required")
            if any(type(a) is not list or len(a) != 3 for a in row["assets"]):
                raise ValueError("three-column metadata assets required")
            if type(row["targets"]) is not list or type(row["operations"]) is not list:
                raise ValueError("explicit simulation approval lists required")
            items.append(ReplayFixture(
                row["fixture_id"], row["family_id"], tuple(ReplayAsset(*a) for a in row["assets"]),
                tuple(row["targets"]), tuple(row["operations"]), row["lab_mode"],
                row["max_steps"], row["interval"],
            ))
        fixtures[split] = tuple(items)
    protocol = OfflineEvaluationProtocol(**fixtures, episode_seeds=tuple(data["seeds"]), masking=data["masking"])
    return PinnedProtocol(protocol, expected_sha256)
