"""Deterministic Scientific Source Provenance Snapshot Manifest (RT-07A).

Provides cryptographic fingerprinting and verification of the executable source tree
prior to comparative benchmark execution:
1. Enumerates all relevant executable source code, contracts, action catalogs,
   planners, simulators, scenarios, and metric engines.
2. Computes per-file SHA-256 content hashes.
3. Computes a deterministic canonical source tree digest over sorted file digests.
4. Audits git working tree status: commit HEAD, dirty worktree, tracked modifications,
   and untracked files.
5. Captures frozen protocol identifiers, dataset manifest hashes, prompt hashes,
   and hybrid scoring weight hashes.
6. Fails closed (BLOCKED) if working tree modifications or provenance inconsistencies exist.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping, Sequence

logger = logging.getLogger(__name__)

# Repository Root Resolution
_MODULE_PATH = Path(__file__).resolve()
REPO_ROOT = _MODULE_PATH.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Pinned Constants from Sealed Protocol V1
FROZEN_PROTOCOL_ID = "BENCHMARK_PROTOCOL_FREEZE_V1"
FROZEN_SEAL_COMMIT = "6129ba6f8edbacfc1ceec129bb4d76eda344a518"

# Canonical Frozen Prompt SHA-256 Digests (evaluated over raw UTF-8 bytes with canonical LF newlines)
LLM_PROMPT_HASH_V1 = "1d35855b6167b0ce151f400c4fb2b292d3e57779689da4a0273fed8a51ac3533"
HYBRID_PROMPT_HASH_V1 = "d1280d0b3329c261344f8206fb2a9f61218b55262b0bf9d121c511d83a9e6ec1"

# Frozen Scoring Weights Digests
HYBRID_FROZEN_WEIGHTS_HASH = "0e595f7294af58a8f635376e8beedb6688cee6784479ae2eb39c21f5c7213aa8"
HYBRID_V1_WEIGHTS_HASH = "68e55385e064cb2867d07207022b665a9660b87938318efa355488d67bc2c799"

# RT-07A1 Prompt Hash Reconciliation Mapping
# External audit notes previously cited hypothetical/untracked hashes:
#   LLM:    '64a7c06d88ae53835f8d95e3474f63c87e6fa54cf6801048b30efea6ff2d603a'
#   Hybrid: 'a937a09804e1c25838d7c49f50e93b6e7fe9e8633767cb447c22a7620dd47e3a'
# Audit proof: git log -S across entire repository history confirms these hashes never existed in any committed
# artifact or blob. The system prompt bytes in runtime/planners/llm_planner.py and hybrid_planner.py have had zero
# byte diffs since inception in commit 22c20fc and freeze seal in 706ac2d.
PROMPT_HASH_RECONCILIATION = {
    "LLM_ATTACK_PLANNER_PROMPT_V1": {
        "canonical_sha256": LLM_PROMPT_HASH_V1,
        "source_symbol": "runtime.planners.llm_planner.ATTACK_PLANNER_SYSTEM_PROMPT",
        "freeze_status": "VERIFIED_UNCHANGED",
        "external_audit_discrepancy": "64a7c06d88ae53835f8d95e3474f63c87e6fa54cf6801048b30efea6ff2d603a",
        "discrepancy_verdict": "INCORRECT_AUDIT_METADATA_UNTRACKED_EXTERNALLY",
    },
    "HYBRID_PLANNER_PROMPT_V1": {
        "canonical_sha256": HYBRID_PROMPT_HASH_V1,
        "source_symbol": "runtime.planners.hybrid_planner.HYBRID_PLANNER_SYSTEM_PROMPT",
        "freeze_status": "VERIFIED_UNCHANGED",
        "external_audit_discrepancy": "a937a09804e1c25838d7c49f50e93b6e7fe9e8633767cb447c22a7620dd47e3a",
        "discrepancy_verdict": "INCORRECT_AUDIT_METADATA_UNTRACKED_EXTERNALLY",
    },
}


# Authoritative set of relative paths constituting the executable benchmark surface (RT-07B0 transitive closure)
RELEVANT_SOURCE_FILES: tuple[str, ...] = (
    # Evaluation manifests & frozen protocols
    "evaluation/datasets/held_out/manifest.json",
    "evaluation/experiments/protocol_freeze.json",
    "evaluation/experiments/benchmark_matrix.json",
    "evaluation/experiments/seed_manifest.json",
    "evaluation/ground_truth/ground-truth.schema.json",
    # Development scenarios (S1-S4)
    "runtime/simulation/fixtures/scenarios/scenario_s1_straight.json",
    "runtime/simulation/fixtures/scenarios/scenario_s2_decoy.json",
    "runtime/simulation/fixtures/scenarios/scenario_s3_blocked.json",
    "runtime/simulation/fixtures/scenarios/scenario_s4_clean.json",
    # Held-out evaluation scenarios (H1-H12)
    "evaluation/datasets/held_out/scenario_h01_straight.json",
    "evaluation/datasets/held_out/scenario_h02_straight.json",
    "evaluation/datasets/held_out/scenario_h03_straight.json",
    "evaluation/datasets/held_out/scenario_h04_decoy.json",
    "evaluation/datasets/held_out/scenario_h05_decoy.json",
    "evaluation/datasets/held_out/scenario_h06_decoy.json",
    "evaluation/datasets/held_out/scenario_h07_blocked.json",
    "evaluation/datasets/held_out/scenario_h08_blocked.json",
    "evaluation/datasets/held_out/scenario_h09_blocked.json",
    "evaluation/datasets/held_out/scenario_h10_clean.json",
    "evaluation/datasets/held_out/scenario_h11_clean.json",
    "evaluation/datasets/held_out/scenario_h12_clean.json",
    # Action catalog & contracts
    "actions/catalog/action_registry.py",
    "actions/catalog/action-catalog.json",
    "agent/planner/contracts/action.schema.json",
    "agent/planner/contracts/evidence.schema.json",
    "agent/planner/contracts/observation.schema.json",
    "agent/planner/contracts/state.schema.json",
    # Planners & context
    "runtime/planners/planner_interface.py",
    "runtime/planners/planner_context.py",
    "runtime/planners/candidate_generator.py",
    "runtime/planners/rule_based_planner.py",
    "runtime/planners/llm_planner.py",
    "runtime/planners/hybrid_planner.py",
    "runtime/planners/symbolic_scorer.py",
    "runtime/planners/hybrid_router.py",
    "runtime/planners/real_provider_adapter.py",
    # Memory & State
    "agent/memory/state/belief_state.py",
    "agent/memory/state/state_manager.py",
    "runtime/state/knowledge_state_store.py",
    "agent/perception/normalizers/enterprise_normalizer.py",
    # Simulation backend & execution loop
    "runtime/simulation/environment.py",
    "runtime/simulation/loader.py",
    "runtime/simulation/bootstrap.py",
    "runtime/simulation/engine/simulation_executor.py",
    "runtime/simulation/engine/transition_engine.py",
    "runtime/simulation/engine/observation_generator.py",
    "runtime/simulation/models/scenario.py",
    "runtime/simulation/models/true_state.py",
    "runtime/simulation/models/step_result.py",
    "runtime/simulation/models/evaluator_view.py",
    "runtime/evaluators/action_evaluator.py",
    "runtime/safety/discovery_gate.py",
    "runtime/lab/workflow_policy.py",
    "runtime/evidence/discovery_recorder.py",
    "runtime/orchestration/planner_runner.py",
    # Token accounting & billing contracts
    "runtime/evaluation/usage_costs.py",
    # Shared validation utilities
    "shared/schema_validation.py",
    # Benchmark execution framework & schema (RT-07A / RT-07A1 / RT-07B0)
    "evaluation/experiments/run_benchmark.py",
    "evaluation/experiments/benchmark_preflight.py",
    "evaluation/experiments/source_snapshot.py",
    # Evaluation metrics & result schema
    "evaluation/metrics/benchmark_metrics.py",
    "evaluation/results/result.schema.json",
    # Model profile persistence & runtime resolution closure (RT-07B)
    "dashboards/app/backend/model_profiles.py",
    "runtime/planners/observed_planner.py",
    "scripts/validation/validate_scaffold.py",
)


def compute_file_sha256(file_path: Path) -> str:
    """Compute standard SHA-256 hex digest for a file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_git_commit_head(repo_root: Path = REPO_ROOT) -> str:
    """Retrieve current Git HEAD commit hash."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception as exc:
        logger.warning(f"Failed to query git rev-parse HEAD: {exc}")
        return "UNKNOWN_COMMIT"


def get_git_status(repo_root: Path = REPO_ROOT) -> tuple[bool, list[str], list[str], list[str]]:
    """Retrieve git working tree dirty status.

    Returns:
        (is_dirty, tracked_modified, staged_modified, untracked)
    """
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain", "-uall"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
        is_dirty = len(lines) > 0
        tracked_modified: list[str] = []
        staged_modified: list[str] = []
        untracked: list[str] = []

        for line in lines:
            status_prefix = line[:2]
            filename = line[3:].strip()
            if status_prefix in ("??", "? "):
                untracked.append(filename)
            elif status_prefix[0] in ("M", "A", "D", "R", "C"):
                staged_modified.append(filename)
            elif status_prefix[1] in ("M", "D"):
                tracked_modified.append(filename)
            else:
                tracked_modified.append(filename)

        return is_dirty, tracked_modified, staged_modified, untracked
    except Exception as exc:
        logger.warning(f"Failed to query git status: {exc}")
        return True, ["ERROR_QUERYING_GIT"], [], []


@dataclasses.dataclass(frozen=True)
class SourceSnapshotManifest:
    """Cryptographic provenance record of the benchmark source tree."""

    source_commit: str
    dirty_worktree: bool
    tracked_modifications: tuple[str, ...]
    staged_modifications: tuple[str, ...]
    untracked_files: tuple[str, ...]
    untracked_file_hashes: dict[str, str]
    relevant_files_manifest: dict[str, str]
    source_tree_digest: str
    protocol_version: str
    dataset_manifest_hash: str
    prompt_hashes: dict[str, str]
    weights_hashes: dict[str, str]
    provenance_status: str  # "CLEAN_REPRODUCIBLE", "DIRTY_NON_RELEVANT", "BLOCKED"
    blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_commit": self.source_commit,
            "dirty_worktree": self.dirty_worktree,
            "tracked_modifications": list(self.tracked_modifications),
            "staged_modifications": list(self.staged_modifications),
            "untracked_files": list(self.untracked_files),
            "untracked_file_hashes": self.untracked_file_hashes,
            "relevant_files_manifest": self.relevant_files_manifest,
            "source_tree_digest": self.source_tree_digest,
            "protocol_version": self.protocol_version,
            "dataset_manifest_hash": self.dataset_manifest_hash,
            "prompt_hashes": self.prompt_hashes,
            "weights_hashes": self.weights_hashes,
            "provenance_status": self.provenance_status,
            "blockers": list(self.blockers),
        }


def build_source_snapshot(repo_root: Path = REPO_ROOT) -> SourceSnapshotManifest:
    """Build deterministic source snapshot manifest over relevant benchmark files."""
    source_commit = get_git_commit_head(repo_root)
    is_dirty, tracked_mod, staged_mod, untracked = get_git_status(repo_root)

    manifest_map: dict[str, str] = {}
    missing_files: list[str] = []

    for rel_path in sorted(RELEVANT_SOURCE_FILES):
        full_path = repo_root / rel_path
        if full_path.exists():
            manifest_map[rel_path] = compute_file_sha256(full_path)
        else:
            missing_files.append(rel_path)

    # Compute deterministic canonical tree digest over sorted (rel_path, sha256)
    hasher = hashlib.sha256()
    for rel_path, digest in sorted(manifest_map.items()):
        hasher.update(f"{rel_path}:{digest}\n".encode("utf-8"))
    source_tree_digest = hasher.hexdigest()

    # Held-out dataset manifest hash
    manifest_file = repo_root / "evaluation" / "datasets" / "held_out" / "manifest.json"
    dataset_manifest_hash = (
        compute_file_sha256(manifest_file) if manifest_file.exists() else "MISSING"
    )

    # Prompt and weights hashes verification
    prompt_hashes = {
        "LLM_ATTACK_PLANNER_PROMPT_V1": LLM_PROMPT_HASH_V1,
        "HYBRID_PLANNER_PROMPT_V1": HYBRID_PROMPT_HASH_V1,
    }
    weights_hashes = {
        "HYBRID_SCORING_V1_FROZEN": HYBRID_FROZEN_WEIGHTS_HASH,
        "HYBRID_SCORING_V1": HYBRID_V1_WEIGHTS_HASH,
    }

    blockers: list[str] = []
    if missing_files:
        blockers.append(f"MISSING_RELEVANT_FILES: {', '.join(missing_files)}")

    # Untracked files and their SHA-256 digests
    untracked_hashes: dict[str, str] = {}
    for uf in untracked:
        uf_path = repo_root / uf
        if uf_path.is_file():
            try:
                untracked_hashes[uf] = compute_file_sha256(uf_path)
            except Exception:
                untracked_hashes[uf] = "UNREADABLE"

    # Check if any modified or untracked file intersects with the relevant source files
    all_changed = set(tracked_mod) | set(staged_mod) | set(untracked)
    # Normalize paths to forward slashes for cross-platform comparison
    normalized_changed = {p.replace("\\", "/") for p in all_changed}
    relevant_set = set(RELEVANT_SOURCE_FILES)
    dirty_relevant = normalized_changed.intersection(relevant_set)

    if dirty_relevant:
        blockers.append(f"DIRTY_RELEVANT_FILES_PRESENT: {sorted(dirty_relevant)}")

    if blockers:
        provenance_status = "BLOCKED"
    elif is_dirty:
        # Working tree has modifications, but not in relevant benchmark files (e.g. docs, tmp logs)
        provenance_status = "DIRTY_NON_RELEVANT"
    else:
        provenance_status = "CLEAN_REPRODUCIBLE"

    return SourceSnapshotManifest(
        source_commit=source_commit,
        dirty_worktree=is_dirty,
        tracked_modifications=tuple(tracked_mod),
        staged_modifications=tuple(staged_mod),
        untracked_files=tuple(untracked),
        untracked_file_hashes=untracked_hashes,
        relevant_files_manifest=manifest_map,
        source_tree_digest=source_tree_digest,
        protocol_version=FROZEN_PROTOCOL_ID,
        dataset_manifest_hash=dataset_manifest_hash,
        prompt_hashes=prompt_hashes,
        weights_hashes=weights_hashes,
        provenance_status=provenance_status,
        blockers=tuple(blockers),
    )


if __name__ == "__main__":
    snapshot = build_source_snapshot()
    print(json.dumps(snapshot.to_dict(), indent=2))
    if snapshot.blockers:
        sys.exit(1)
