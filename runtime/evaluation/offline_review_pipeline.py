"""TASK-018 -> TASK-019 -> TASK-020/021 integration for offline metadata review.

Only pinned, local Nuclei report data is normalized. Persist minimized evidence
before ingesting state; proposals remain data and never reach a dispatcher.
"""
from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path

from agent.perception.normalizers.observation_normalizer import ObservationNormalizer
from runtime.audit.audit_support import pinned_json
from runtime.evidence.discovery_recorder import DurableEvidenceRecorder, EvidenceFailure
from runtime.state.knowledge_state_store import KnowledgeStateStore, StoreContext
from runtime.planners.planner_interface import PlanningInput, PlanProposal, StateSnapshot
from runtime.planners.rule_based_planner import REVIEW_ACTION, RuleBasedPlanner
from runtime.evaluation.usage_costs import no_links


class OfflineReviewPipeline:
    """Single-writer offline consumer with a sticky stop after any ingest failure."""

    def __init__(self, store: KnowledgeStateStore, context: StoreContext,
                 recorder: DurableEvidenceRecorder, *, input_root: Path,
                 allowed_targets: frozenset[str], target_origin: str,
                 template_families: dict[str, str]):
        if type(store) is not KnowledgeStateStore or type(context) is not StoreContext:
            raise ValueError("typed store and context required")
        if type(recorder) is not DurableEvidenceRecorder or recorder.run_id != context.run_id:
            raise ValueError("recorder must match the state context")
        if type(allowed_targets) is not frozenset or not allowed_targets:
            raise ValueError("immutable offline target scope required")
        root = Path(__file__).resolve().parents[2]
        canonical = json.loads((root / "configs/safety/target-allowlist.yaml").read_text("utf-8"))
        if not allowed_targets <= set(canonical["allowed_target_ids"]):
            raise ValueError("offline target scope outside canonical allowlist")
        no_links(Path(input_root).absolute())
        self.input_root = Path(input_root).resolve()
        self.store, self.context, self.recorder = store, context, recorder
        self.allowed_targets = allowed_targets
        self.target_origin = target_origin
        self.template_families = copy.deepcopy(template_families)
        self.halted = False

    def _ready(self):
        if self.halted:
            raise EvidenceFailure("offline pipeline halted; partial evidence retained")

    def ingest_report(self, path: Path, expected_sha256: str, *, source: str):
        """Pinned input -> strict normalizer -> durable minimized receipt -> state.

        External scanner execution remains unresolved. Imported data consumes no
        network budget. Identical journal replay preserves the original receipt.
        """
        self._ready()
        try:
            if source not in ("IMPORTED_OFFLINE", "SIMULATED_FIXTURE"):
                raise ValueError("explicit offline provenance required")
            path = Path(path).absolute()
            no_links(path)
            if not path.resolve().is_relative_to(self.input_root):
                raise ValueError("input outside approved root")
            envelope = pinned_json(path, expected_sha256)
            if envelope.get("run_id") != self.context.run_id or envelope.get("evidence_refs") != []:
                raise ValueError("input run identity or unverified references")
            normalized = ObservationNormalizer().normalize_nuclei(
                envelope, allowed_target_ids=self.allowed_targets,
                target_origin=self.target_origin, template_families=self.template_families,
            )
            observation = normalized["observation"]
            # A bounded journal lookup keeps idempotence across consumer restarts.
            for offset in range(0, 10_000, 1000):
                page = self.store.observations(self.context, limit=1000, offset=offset)
                for row in page:
                    old = row["envelope"]
                    if old["observation"]["observation_id"] == observation["observation_id"]:
                        expected = copy.deepcopy(old["observation"])
                        expected["evidence_refs"] = []
                        if expected != observation or old["source_sha256"] != expected_sha256 or old["source"] != source:
                            raise ValueError("conflicting replay provenance")
                        # Check the original receipt, not a newly invented replacement.
                        self._verify_observation(old)
                        return False
                if len(page) < 1000:
                    break
            else:
                raise ValueError("offline journal lookup bound exceeded")
            artifact = self.recorder.persist_phase_artifact(
                "offline_normalization", dict(
                    source=source, source_sha256=expected_sha256,
                    context_sha256=hashlib.sha256(self.context.key.encode()).hexdigest(),
                    observation=observation, provenance=normalized["provenance"],
                    external_execution="UNRESOLVED",
                ), expected_state="OFFLINE_NORMALIZATION_RECORDED",
                observed_state="OFFLINE_NORMALIZATION_RECORDED",
            )
            observation = copy.deepcopy(observation)
            observation["evidence_refs"] = [artifact["evidence_id"]]
            return self.store.ingest(self.context, observation, source=source,
                                     source_sha256=expected_sha256, phase="ANALYSIS")
        except Exception:
            self.halted = True
            raise

    def _verify_observation(self, envelope):
        from runtime.evidence.evidence_readonly import read_object, verify_records

        integrity = verify_records(self.recorder.directory, self.context.run_id)
        if integrity.state != "VERIFIED":
            raise EvidenceFailure("offline evidence integrity failed")
        records = {record["evidence_id"]: record for record in (
            read_object(p, self.recorder.directory)
            for p in self.recorder.directory.glob("record-*.json"))}
        observation = copy.deepcopy(envelope["observation"])
        refs = observation.get("evidence_refs", [])
        if len(refs) != 1 or refs[0] not in records:
            raise EvidenceFailure("offline observation evidence reference missing")
        record = records[refs[0]]
        path = Path(record["path"])
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / path
        receipt = read_object(path, self.recorder.directory)
        observation["evidence_refs"] = []
        if (receipt.get("observation") != observation or
                receipt.get("source_sha256") != envelope["source_sha256"] or
                receipt.get("source") != envelope["source"] or
                receipt.get("context_sha256") != hashlib.sha256(self.context.key.encode()).hexdigest()):
            raise EvidenceFailure("offline observation does not match persisted evidence")

    def propose_review(self):
        """The fixed RULE metadata reviewer returns a schema-bound proposal only."""
        self._ready()
        try:
            # Journal reconstruction verifies source/state consistency before planning.
            self.store.reconstruct(self.context)
            for offset in range(0, 10_000, 1000):
                page = self.store.observations(self.context, limit=1000, offset=offset)
                for row in page:
                    self._verify_observation(row["envelope"])
                if len(page) < 1000:
                    break
            else:
                raise ValueError("offline journal lookup bound exceeded")
            request = PlanningInput(StateSnapshot.from_store(self.store, self.context),
                                    frozenset({REVIEW_ACTION}), self.allowed_targets)
            decision = RuleBasedPlanner().plan(request)
            refs = []
            if decision.proposal:
                plan = decision.proposal.to_dict()
                for offset in range(0, 10_000, 1000):
                    page = self.store.observations(self.context, limit=1000, offset=offset)
                    for row in page:
                        observation = row["envelope"]["observation"]
                        if observation["observation_id"] == plan["source_observation_id"]:
                            refs = observation["evidence_refs"]
                    if len(page) < 1000:
                        break
                if not refs:
                    raise EvidenceFailure("proposal source observation evidence missing")
                plan["evidence_refs"] = refs
                decision = replace(decision, proposal=PlanProposal.from_dict(plan))
            self.recorder.persist_phase_artifact("offline_review_proposal", dict(
                source="OFFLINE_METADATA_REVIEW", run_id=self.context.run_id,
                input_revision=decision.input_revision,
                requested_mode=decision.requested_mode, actual_mode=decision.actual_mode,
                proposal=decision.proposal.to_dict() if decision.proposal else None,
                stop_reason=decision.stop_reason, network_dispatches=0, provider_calls=0,
                execution_authority="NONE",
            ), expected_state="PROPOSAL_RECORDED", observed_state="PROPOSAL_RECORDED",
                derived_from=refs)
            return decision
        except Exception:
            self.halted = True
            raise
