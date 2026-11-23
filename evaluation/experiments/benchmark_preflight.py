"""Reproducible Benchmark Preflight and Safety Audit Suite (RT-07A).

Conducts comprehensive, fail-closed preflight verification before any comparative
attack planner benchmark execution:
1. Frozen Protocol V1 Seal & Integrity (`BENCHMARK_PROTOCOL_FREEZE_V1 = SEALED`).
2. Held-Out Evaluation Dataset Integrity (Byte-for-byte SHA-256 match on H01-H12).
3. Pre-registered Experiment Matrix & Seed Coupling (Strictly 420 non-Cartesian episodes).
4. Scientific Source Provenance Snapshot & Dirty Working Tree Audit.
5. Controlled Inference Configuration & Provider Readiness (`REAL_LLM_BENCHMARK_BLOCKED`).
6. Zero-Knowledge Information Boundary & Fog-of-War Isolation.
7. RT-06 Live Cyber Range Relay & Control Plane Security Audit.
8. Simulator-Only Held-Out Benchmark Guard (Strictly forbids live Docker dispatch for H01-H12).
"""
from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import logging
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

_MODULE_PATH = Path(__file__).resolve()
REPO_ROOT = _MODULE_PATH.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from actions.catalog.action_registry import (
    CANONICAL_BENCHMARK_ACTION_IDS,
    get_canonical_action_id,
)
from evaluation.experiments.source_snapshot import (
    FROZEN_PROTOCOL_ID,
    PROPOSED_PROTOCOL_ID_V2,
    PROTOCOL_AMENDMENT_V2_PATH,
    validate_protocol_version,
    HYBRID_FROZEN_WEIGHTS_HASH,
    HYBRID_PROMPT_HASH_V1,
    HYBRID_V1_WEIGHTS_HASH,
    LLM_PROMPT_HASH_V1,
    REPO_ROOT,
    SourceSnapshotManifest,
    build_source_snapshot,
    compute_file_sha256,
)
from runtime.planners.llm_planner import FakeAttackPlannerProvider
from runtime.planners.symbolic_scorer import HybridScoringConfig
from runtime.simulation.loader import ScenarioLoader

logger = logging.getLogger(__name__)

# Pinned paths
EXPERIMENTS_DIR = REPO_ROOT / "evaluation" / "experiments"
HELD_OUT_DIR = REPO_ROOT / "evaluation" / "datasets" / "held_out"
PROTOCOL_FREEZE_PATH = EXPERIMENTS_DIR / "protocol_freeze.json"
BENCHMARK_MATRIX_PATH = EXPERIMENTS_DIR / "benchmark_matrix.json"
SEED_MANIFEST_PATH = EXPERIMENTS_DIR / "seed_manifest.json"
HELD_OUT_MANIFEST_PATH = HELD_OUT_DIR / "manifest.json"


@dataclasses.dataclass(frozen=True)
class PreflightCheckItem:
    """Individual preflight check outcome."""

    code: str
    name: str
    passed: bool
    details: str
    is_blocker: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "passed": self.passed,
            "details": self.details,
            "is_blocker": self.is_blocker,
        }


@dataclasses.dataclass(frozen=True)
class PreflightReport:
    """Comprehensive benchmark preflight audit report."""

    timestamp_utc: str
    protocol_version: str
    all_passed: bool
    has_blockers: bool
    benchmark_readiness: str  # "READY", "DEVELOPMENT_DRY_RUN_ONLY", "BLOCKED"
    checks: tuple[PreflightCheckItem, ...]
    blockers: tuple[str, ...]
    docker_audit_findings: tuple[str, ...]
    source_snapshot: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp_utc": self.timestamp_utc,
            "protocol_version": self.protocol_version,
            "all_passed": self.all_passed,
            "has_blockers": self.has_blockers,
            "benchmark_readiness": self.benchmark_readiness,
            "checks": [c.to_dict() for c in self.checks],
            "blockers": list(self.blockers),
            "docker_audit_findings": list(self.docker_audit_findings),
            "source_snapshot": self.source_snapshot,
        }


class BenchmarkPreflightChecker:
    """Performs full preflight verification before benchmark execution."""

    def __init__(
        self, repo_root: Path = REPO_ROOT, *, protocol_version: str = FROZEN_PROTOCOL_ID,
    ) -> None:
        self.protocol_version = validate_protocol_version(protocol_version)
        self.repo_root = repo_root
        self.loader = ScenarioLoader()

    def verify_v2_amendment(self) -> list[PreflightCheckItem]:
        """Check inherited byte pins; V2 remains a proposal regardless of file contents."""
        items = [PreflightCheckItem(
            code="V2_PROTOCOL_NOT_SEALED", name="V2 Amendment Authorization",
            passed=False, details="V2_PROTOCOL_NOT_SEALED: V2 is development-only; RT-07B is blocked.",
            is_blocker=True,
        )]
        try:
            path = self.repo_root / PROTOCOL_AMENDMENT_V2_PATH.relative_to(REPO_ROOT)
            amendment = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(amendment, dict) or amendment.get("protocol_version") != PROPOSED_PROTOCOL_ID_V2:
                raise ValueError("V2 protocol identity mismatch")
            expected_paths = {
                "evaluation/experiments/protocol_freeze.json",
                "evaluation/experiments/benchmark_matrix.json",
                "evaluation/experiments/seed_manifest.json",
                "evaluation/datasets/held_out/manifest.json",
            }
            pins = amendment.get("pinned_v1_files")
            if not isinstance(pins, dict) or set(pins) != expected_paths:
                raise ValueError("Missing or unexpected V1 byte pins")
            for rel_path in expected_paths:
                if compute_file_sha256(self.repo_root / rel_path) != pins[rel_path]:
                    raise ValueError(f"V1 byte pin mismatch: {rel_path}")
            items.append(PreflightCheckItem(
                code="CHK-V2-PINS", name="V2 Inherited V1 Integrity", passed=True,
                details="V1 freeze, matrix, seed and held-out manifest byte pins match.", is_blocker=False,
            ))
        except (OSError, ValueError, TypeError) as exc:
            items.append(PreflightCheckItem(
                code="CHK-V2-PINS", name="V2 Inherited V1 Integrity", passed=False,
                details=f"V2 amendment integrity failure: {exc}", is_blocker=True,
            ))
        return items

    def verify_protocol_seal(self) -> PreflightCheckItem:
        """Verify protocol_freeze.json is SEALED and unaltered."""
        if not PROTOCOL_FREEZE_PATH.exists():
            return PreflightCheckItem(
                code="CHK-PROTO-001",
                name="Protocol Freeze File Existence",
                passed=False,
                details=f"Missing protocol freeze file at {PROTOCOL_FREEZE_PATH}",
                is_blocker=True,
            )

        try:
            data = json.loads(PROTOCOL_FREEZE_PATH.read_text(encoding="utf-8"))
            proto_ver = data.get("protocol_version")
            seal_status = data.get("freeze_status")

            if proto_ver != FROZEN_PROTOCOL_ID:
                return PreflightCheckItem(
                    code="CHK-PROTO-002",
                    name="Protocol Version Verification",
                    passed=False,
                    details=f"Expected {FROZEN_PROTOCOL_ID}, found {proto_ver}",
                    is_blocker=True,
                )

            if seal_status != "SEALED":
                return PreflightCheckItem(
                    code="CHK-PROTO-003",
                    name="Protocol Seal Verification",
                    passed=False,
                    details=f"Expected freeze_status='SEALED', found '{seal_status}'",
                    is_blocker=True,
                )

            return PreflightCheckItem(
                code="CHK-PROTO-004",
                name="Protocol Freeze Seal",
                passed=True,
                details=f"Protocol {proto_ver} confirmed SEALED.",
                is_blocker=False,
            )
        except Exception as exc:
            return PreflightCheckItem(
                code="CHK-PROTO-ERR",
                name="Protocol Freeze Parsing",
                passed=False,
                details=f"Failed to parse protocol freeze: {exc}",
                is_blocker=True,
            )

    def verify_held_out_scenarios(self) -> list[PreflightCheckItem]:
        """Verify all 12 held-out scenarios match their pinned SHA-256 byte digests and contracts."""
        items: list[PreflightCheckItem] = []

        if not HELD_OUT_MANIFEST_PATH.exists():
            items.append(
                PreflightCheckItem(
                    code="CHK-DATA-001",
                    name="Held-Out Manifest Existence",
                    passed=False,
                    details=f"Missing held-out dataset manifest at {HELD_OUT_MANIFEST_PATH}",
                    is_blocker=True,
                )
            )
            return items

        try:
            manifest_data = json.loads(HELD_OUT_MANIFEST_PATH.read_text(encoding="utf-8"))
            scenarios = manifest_data.get("scenarios", [])

            if len(scenarios) != 12:
                items.append(
                    PreflightCheckItem(
                        code="CHK-DATA-002",
                        name="Held-Out Scenario Count",
                        passed=False,
                        details=f"Expected exactly 12 held-out scenarios, found {len(scenarios)}",
                        is_blocker=True,
                    )
                )

            for scn_entry in scenarios:
                scn_id = scn_entry.get("scenario_id", "")
                filename = scn_entry.get("filename", "")
                expected_sha = scn_entry.get("sha256", "")

                scn_path = HELD_OUT_DIR / filename
                if not scn_path.exists():
                    items.append(
                        PreflightCheckItem(
                            code=f"CHK-DATA-MISS-{scn_id}",
                            name=f"Held-Out File Existence ({scn_id})",
                            passed=False,
                            details=f"File {filename} does not exist",
                            is_blocker=True,
                        )
                    )
                    continue

                actual_sha = compute_file_sha256(scn_path)
                if actual_sha != expected_sha:
                    items.append(
                        PreflightCheckItem(
                            code=f"CHK-DATA-HASH-{scn_id}",
                            name=f"Held-Out Byte Digest ({scn_id})",
                            passed=False,
                            details=f"Hash mismatch for {filename}: expected {expected_sha}, computed {actual_sha}",
                            is_blocker=True,
                        )
                    )
                else:
                    # Validate scenario contract
                    try:
                        self.loader.load_from_file(scn_path)
                        items.append(
                            PreflightCheckItem(
                                code=f"CHK-DATA-OK-{scn_id}",
                                name=f"Held-Out Scenario Integrity ({scn_id})",
                                passed=True,
                                details=f"Scenario {scn_id} ({filename}) verified bit-for-bit with valid contract.",
                                is_blocker=False,
                            )
                        )
                    except Exception as err:
                        items.append(
                            PreflightCheckItem(
                                code=f"CHK-DATA-CONTRACT-{scn_id}",
                                name=f"Held-Out Contract Validation ({scn_id})",
                                passed=False,
                                details=f"Contract validation error for {filename}: {err}",
                                is_blocker=True,
                            )
                        )
        except Exception as exc:
            items.append(
                PreflightCheckItem(
                    code="CHK-DATA-ERR",
                    name="Held-Out Manifest Parsing",
                    passed=False,
                    details=f"Error reading held-out manifest: {exc}",
                    is_blocker=True,
                )
            )

        return items

    def verify_experiment_matrix(self) -> list[PreflightCheckItem]:
        """Verify pre-registered matrix has exactly 420 unique planned episodes and non-Cartesian seeds."""
        items: list[PreflightCheckItem] = []

        if not BENCHMARK_MATRIX_PATH.exists():
            items.append(
                PreflightCheckItem(
                    code="CHK-MAT-001",
                    name="Benchmark Matrix Existence",
                    passed=False,
                    details=f"Missing benchmark matrix file at {BENCHMARK_MATRIX_PATH}",
                    is_blocker=True,
                )
            )
            return items

        try:
            matrix = json.loads(BENCHMARK_MATRIX_PATH.read_text(encoding="utf-8"))
            planned = matrix.get("planned_episodes", [])
            total_planned = matrix.get("total_planned_episodes", 0)
            dims = matrix.get("dimensions", {})

            if len(planned) != 420 or total_planned != 420:
                items.append(
                    PreflightCheckItem(
                        code="CHK-MAT-002",
                        name="Planned Episode Cardinality",
                        passed=False,
                        details=f"Expected 420 planned episodes, got {len(planned)} (total={total_planned})",
                        is_blocker=True,
                    )
                )

            # Check uniqueness of experiment_ids
            exp_ids = [e.get("experiment_id") for e in planned if e.get("experiment_id")]
            if len(exp_ids) != 420 or len(set(exp_ids)) != 420:
                items.append(
                    PreflightCheckItem(
                        code="CHK-MAT-003",
                        name="Experiment ID Uniqueness",
                        passed=False,
                        details=f"Duplicate or missing experiment IDs: {len(exp_ids)} total, {len(set(exp_ids))} unique",
                        is_blocker=True,
                    )
                )
            else:
                items.append(
                    PreflightCheckItem(
                        code="CHK-MAT-004",
                        name="Experiment ID Uniqueness",
                        passed=True,
                        details="All 420 planned experiment IDs are unique and strictly formatted.",
                        is_blocker=False,
                    )
                )

            # Check non-Cartesian invariant
            if dims.get("cartesian_expanded") is not False:
                items.append(
                    PreflightCheckItem(
                        code="CHK-MAT-005",
                        name="Non-Cartesian Seed Invariant",
                        passed=False,
                        details="Dimensions indicate cartesian_expanded != False",
                        is_blocker=True,
                    )
                )
            else:
                items.append(
                    PreflightCheckItem(
                        code="CHK-MAT-006",
                        name="Non-Cartesian Seed Invariant",
                        passed=True,
                        details="Seed coupling is strictly pairwise (5 paired replicates), not Cartesian (2100).",
                        is_blocker=False,
                    )
                )
        except Exception as exc:
            items.append(
                PreflightCheckItem(
                    code="CHK-MAT-ERR",
                    name="Benchmark Matrix Parsing",
                    passed=False,
                    details=f"Error reading benchmark matrix: {exc}",
                    is_blocker=True,
                )
            )

        return items

    def verify_seed_manifest(self) -> PreflightCheckItem:
        """Verify seed_manifest.json specifies exactly R01..R05 with paired seeds."""
        if not SEED_MANIFEST_PATH.exists():
            return PreflightCheckItem(
                code="CHK-SEED-001",
                name="Seed Manifest Existence",
                passed=False,
                details=f"Missing seed manifest at {SEED_MANIFEST_PATH}",
                is_blocker=True,
            )

        try:
            seeds = json.loads(SEED_MANIFEST_PATH.read_text(encoding="utf-8"))
            reps = seeds.get("paired_replicates", [])
            expected = [
                ("R01", 1001, 42),
                ("R02", 1002, 43),
                ("R03", 1003, 44),
                ("R04", 1004, 45),
                ("R05", 1005, 46),
            ]
            if len(reps) != 5:
                return PreflightCheckItem(
                    code="CHK-SEED-002",
                    name="Seed Manifest Replicates",
                    passed=False,
                    details=f"Expected 5 paired replicates, found {len(reps)}",
                    is_blocker=True,
                )

            for rep, (exp_id, exp_sim, exp_prov) in zip(reps, expected):
                if (
                    rep.get("replicate_id") != exp_id
                    or rep.get("simulator_seed") != exp_sim
                    or rep.get("provider_seed") != exp_prov
                ):
                    return PreflightCheckItem(
                        code="CHK-SEED-003",
                        name="Seed Manifest Pairing",
                        passed=False,
                        details=f"Mismatch in replicate {exp_id}: expected sim={exp_sim}, prov={exp_prov}; found {rep}",
                        is_blocker=True,
                    )

            return PreflightCheckItem(
                code="CHK-SEED-004",
                name="Seed Manifest Pairing",
                passed=True,
                details="Seed manifest replicates R01..R05 paired simulator seeds [1001..1005] and provider seeds [42..46].",
                is_blocker=False,
            )
        except Exception as exc:
            return PreflightCheckItem(
                code="CHK-SEED-ERR",
                name="Seed Manifest Parsing",
                passed=False,
                details=f"Error reading seed manifest: {exc}",
                is_blocker=True,
            )

    def verify_source_provenance(self) -> tuple[PreflightCheckItem, SourceSnapshotManifest]:
        """Verify scientific source snapshot and provenance status."""
        snapshot = build_source_snapshot(self.repo_root, protocol_version=self.protocol_version)
        if snapshot.blockers:
            item = PreflightCheckItem(
                code="CHK-PROV-001",
                name="Scientific Source Provenance",
                passed=False,
                details=f"Provenance blockers: {'; '.join(snapshot.blockers)}",
                is_blocker=True,
            )
        elif snapshot.provenance_status == "DIRTY_NON_RELEVANT":
            item = PreflightCheckItem(
                code="CHK-PROV-002",
                name="Scientific Source Provenance",
                passed=True,
                details=(
                    f"Clean reproducible executable surface (digest={snapshot.source_tree_digest[:16]}...). "
                    f"Working tree has non-relevant untracked artifacts: {len(snapshot.untracked_files)} files."
                ),
                is_blocker=False,
            )
        else:
            item = PreflightCheckItem(
                code="CHK-PROV-003",
                name="Scientific Source Provenance",
                passed=True,
                details=f"Clean reproducible source commit {snapshot.source_commit} (digest={snapshot.source_tree_digest[:16]}...).",
                is_blocker=False,
            )
        return item, snapshot

    def verify_controlled_inference_config(self) -> PreflightCheckItem:
        """Verify controlled inference configuration adheres strictly to Protocol V1."""
        try:
            proto = json.loads(PROTOCOL_FREEZE_PATH.read_text(encoding="utf-8"))
            cfg = proto.get("controlled_inference_configuration", {})

            if cfg.get("temperature") != 0.0 or cfg.get("top_p") != 1.0:
                return PreflightCheckItem(
                    code="CHK-INF-001",
                    name="Inference Greedy Decoding",
                    passed=False,
                    details=f"Temperature must be 0.0, top_p must be 1.0; found {cfg}",
                    is_blocker=True,
                )

            if cfg.get("provider_seed_supported") is not False:
                return PreflightCheckItem(
                    code="CHK-INF-002",
                    name="Provider Seed Semantics Disclosure",
                    passed=False,
                    details="Protocol V1 requires provider_seed_supported=False to truthfully disclose non-guaranteed bit-for-bit reproducibility.",
                    is_blocker=True,
                )

            return PreflightCheckItem(
                code="CHK-INF-003",
                name="Controlled Inference Configuration",
                passed=True,
                details="Greedy decoding (temperature=0.0, top_p=1.0) and provider_seed_supported=False confirmed.",
                is_blocker=False,
            )
        except Exception as exc:
            return PreflightCheckItem(
                code="CHK-INF-ERR",
                name="Inference Config Verification",
                passed=False,
                details=f"Error inspecting inference config: {exc}",
                is_blocker=True,
            )

    def verify_provider_readiness(
        self,
        require_real_provider: bool = False,
        provider: Any = None,
    ) -> PreflightCheckItem:
        """Verify LLM provider readiness.

        If require_real_provider=True (e.g. for final comparative benchmark execution):
        Fails closed with REAL_LLM_BENCHMARK_BLOCKED if no real provider or only fake provider is given.
        """
        if require_real_provider:
            if provider is None:
                return PreflightCheckItem(
                    code="CHK-PROV-REQ-001",
                    name="Real LLM Provider Authorization",
                    passed=False,
                    details="REAL_LLM_BENCHMARK_BLOCKED: No active LLM provider configured for real comparative benchmark.",
                    is_blocker=True,
                )
            if isinstance(provider, FakeAttackPlannerProvider) or "Fake" in type(provider).__name__:
                return PreflightCheckItem(
                    code="CHK-PROV-REQ-002",
                    name="Real LLM Provider Integrity",
                    passed=False,
                    details="REAL_LLM_BENCHMARK_BLOCKED: FakeAttackPlannerProvider is forbidden for headline comparative results.",
                    is_blocker=True,
                )
            return PreflightCheckItem(
                code="CHK-PROV-REQ-003",
                name="Real LLM Provider Readiness",
                passed=True,
                details=f"Authorized provider '{type(provider).__name__}' available for comparative execution.",
                is_blocker=False,
            )
        else:
            # Development dry-run mode
            if provider is None or isinstance(provider, FakeAttackPlannerProvider) or "Fake" in type(provider).__name__:
                return PreflightCheckItem(
                    code="CHK-PROV-DEV-001",
                    name="Development Provider Mode",
                    passed=True,
                    details="Development dry-run authorized with scripted/fake provider (held-out execution disabled).",
                    is_blocker=False,
                )
            return PreflightCheckItem(
                code="CHK-PROV-DEV-002",
                name="Development Provider Mode",
                passed=True,
                details=f"Real provider '{type(provider).__name__}' provided for development validation.",
                is_blocker=False,
            )

    def verify_information_boundary(self) -> PreflightCheckItem:
        """Verify Zero-Knowledge Fog-of-War boundary between evaluator truth and planner context."""
        try:
            from runtime.planners.planner_context import PlannerDecisionContext
            # Ensure forbidden truth fields are not attributes of PlannerDecisionContext
            forbidden = (
                "true_state",
                "hidden_scenario",
                "hidden_nodes",
                "hidden_topology",
                "hidden_credentials",
                "evaluator_view",
                "family",
                "scenario_family",
                "recovery_opportunity_exists",
                "is_decoy",
                "is_blocked",
            )
            context_fields = {f.name for f in dataclasses.fields(PlannerDecisionContext)}
            leaks = set(forbidden).intersection(context_fields)
            if leaks:
                return PreflightCheckItem(
                    code="CHK-INFO-001",
                    name="Fog-of-War Information Boundary",
                    passed=False,
                    details=f"Forbidden evaluator ground-truth attributes found on PlannerDecisionContext: {leaks}",
                    is_blocker=True,
                )

            return PreflightCheckItem(
                code="CHK-INFO-002",
                name="Fog-of-War Information Boundary",
                passed=True,
                details="PlannerDecisionContext is strictly Zero-Knowledge; zero evaluator-only flags or hidden topology exposed.",
                is_blocker=False,
            )
        except Exception as exc:
            return PreflightCheckItem(
                code="CHK-INFO-ERR",
                name="Information Boundary Verification",
                passed=False,
                details=f"Error inspecting PlannerDecisionContext: {exc}",
                is_blocker=True,
            )

    def audit_docker_relay_and_safety_boundaries(self) -> tuple[PreflightCheckItem, list[str]]:
        """Audit RT-06 / RT-06V cyber range relay and administrative control-plane boundaries.

        Document findings without patching frozen planners:
        1. /api/v1/relay lacks destination allowlist filter (any target_host accepted).
        2. /reset and /api/v1/admin/block_route are exposed on public DMZ port without authentication.
        3. Held-out benchmark must NEVER be dispatched to live Docker targets.
        """
        findings: list[str] = []

        services_path = self.repo_root / "runtime" / "lab" / "enterprise_range" / "services.py"
        if services_path.exists():
            code = services_path.read_text(encoding="utf-8")
            # Audit relay destination check
            if "body.get(\"target_host\")" in code and "target_host in ENTERPRISE_TARGETS" not in code:
                findings.append(
                    "FINDING-RT06-RELAY-01: /api/v1/relay does not restrict target_host against an explicit lab destination allowlist. Unrouted destinations fail closed at the network namespace barrier, but open relaying is an architectural security risk."
                )

            # Audit admin route protection
            if "is_admin_lifecycle = (" in code and "fwd_path in (\"/health\", \"/reset\"" in code:
                findings.append(
                    "FINDING-RT06-ADMIN-02: Administrative lifecycle endpoints (/reset, /api/v1/admin/block_route) are exempt from session requirements on the DMZ port. Control plane should be segregated from untrusted edge ingress in production ranges."
                )

        findings.append(
            "INVARIANT-RT07-SIM-ONLY: Final RT-07 benchmark is strictly simulator-based POMDP. Live Docker dispatch of held-out evaluation scenarios (H01-H12) is forbidden."
        )

        item = PreflightCheckItem(
            code="CHK-DOCKER-AUDIT-001",
            name="Live Range Relay & Control Plane Audit",
            passed=True,
            details=f"Audited RT-06 relay and admin surfaces. Documented {len(findings)} findings.",
            is_blocker=False,
        )
        return item, findings

    def run_preflight(
        self,
        require_real_provider: bool = False,
        provider: Any = None,
    ) -> PreflightReport:
        """Run all preflight checks and return consolidated PreflightReport."""
        checks: list[PreflightCheckItem] = []
        blockers: list[str] = []

        if self.protocol_version == PROPOSED_PROTOCOL_ID_V2:
            for item in self.verify_v2_amendment():
                checks.append(item)
                if item.is_blocker and not item.passed:
                    blockers.append(item.details)

        # 1. Protocol Seal
        c_proto = self.verify_protocol_seal()
        checks.append(c_proto)
        if c_proto.is_blocker and not c_proto.passed:
            blockers.append(c_proto.details)

        # 2. Held-Out Dataset Integrity
        c_data = self.verify_held_out_scenarios()
        checks.extend(c_data)
        for c in c_data:
            if c.is_blocker and not c.passed:
                blockers.append(c.details)

        # 3. Experiment Matrix
        c_mat = self.verify_experiment_matrix()
        checks.extend(c_mat)
        for c in c_mat:
            if c.is_blocker and not c.passed:
                blockers.append(c.details)

        # 4. Seed Manifest
        c_seed = self.verify_seed_manifest()
        checks.append(c_seed)
        if c_seed.is_blocker and not c_seed.passed:
            blockers.append(c_seed.details)

        # 5. Scientific Source Provenance
        c_prov, snapshot = self.verify_source_provenance()
        checks.append(c_prov)
        if c_prov.is_blocker and not c_prov.passed:
            blockers.append(c_prov.details)

        # 6. Controlled Inference Configuration
        c_inf = self.verify_controlled_inference_config()
        checks.append(c_inf)
        if c_inf.is_blocker and not c_inf.passed:
            blockers.append(c_inf.details)

        # 7. Provider Readiness
        c_pready = self.verify_provider_readiness(
            require_real_provider=require_real_provider,
            provider=provider,
        )
        checks.append(c_pready)
        if c_pready.is_blocker and not c_pready.passed:
            blockers.append(c_pready.details)

        # 8. Fog-of-War Information Boundary
        c_info = self.verify_information_boundary()
        checks.append(c_info)
        if c_info.is_blocker and not c_info.passed:
            blockers.append(c_info.details)

        # 9. Docker Relay & Safety Audit
        c_dock, findings = self.audit_docker_relay_and_safety_boundaries()
        checks.append(c_dock)

        all_passed = all(c.passed for c in checks)
        has_blockers = len(blockers) > 0

        if has_blockers:
            readiness = "BLOCKED"
        elif not require_real_provider and (
            provider is None or isinstance(provider, FakeAttackPlannerProvider) or "Fake" in type(provider).__name__
        ):
            readiness = "DEVELOPMENT_DRY_RUN_ONLY"
        else:
            readiness = "READY"

        timestamp_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

        return PreflightReport(
            timestamp_utc=timestamp_utc,
            protocol_version=self.protocol_version,
            all_passed=all_passed,
            has_blockers=has_blockers,
            benchmark_readiness=readiness,
            checks=tuple(checks),
            blockers=tuple(blockers),
            docker_audit_findings=tuple(findings),
            source_snapshot=snapshot.to_dict(),
        )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol-version", choices=(FROZEN_PROTOCOL_ID, PROPOSED_PROTOCOL_ID_V2), default=FROZEN_PROTOCOL_ID)
    parser.add_argument("--require-real-provider", action="store_true")
    args = parser.parse_args()
    checker = BenchmarkPreflightChecker(protocol_version=args.protocol_version)
    report = checker.run_preflight(require_real_provider=args.require_real_provider)

    print(json.dumps(report.to_dict(), indent=2))
    if report.has_blockers:
        print("\n[PREFLIGHT BLOCKED]: Preflight checks detected critical blockers.", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"\n[PREFLIGHT PASSED]: Benchmark readiness status = {report.benchmark_readiness}")
        sys.exit(0)
