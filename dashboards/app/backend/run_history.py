"""Run history indexing, timeline reconstruction, and experiment comparison service."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dashboards.app.backend.models import (
    ActionSequenceItem,
    ComparisonMetric,
    PlannerVerificationStatus,
    RunComparisonResponse,
    RunHistoryItem,
    RunHistoryResponse,
    RunTimelineResponse,
    TimelineEventItem,
    SECURITY_FINDING_CLASSES,
)
from dashboards.app.backend.run_manager import RunManager
from runtime.evidence.evidence_readonly import IntegritySummary, bounded_bytes, no_link_ancestors, read_object, verify_records


def _parse_iso_or_none(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        clean = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(clean)
    except Exception:
        return None


def _calc_duration_ms(start_ts: Optional[str], end_ts: Optional[str]) -> Optional[int]:
    dt_start = _parse_iso_or_none(start_ts)
    dt_end = _parse_iso_or_none(end_ts)
    if dt_start and dt_end:
        if dt_start.tzinfo is None or dt_end.tzinfo is None:
            return None
        diff = (dt_end - dt_start).total_seconds()
        return int(diff * 1000) if diff >= 0 else None
    return None


def _delta(a: int | None, b: int | None) -> int | None:
    return b - a if a is not None and b is not None else None


def _text(value, default=None):
    return value if type(value) is str else default


def recorded_report(run_dir: Path) -> dict:
    """One bounded identity boundary for every history/report reader."""
    for path in [run_dir / "report.json", *sorted(run_dir.glob("autonomous_pentest_report-*.json")),
                 *sorted(run_dir.glob("*summary*.json"))]:
        if path.is_file():
            data = read_object(path, run_dir)
            if data.get("run_id", run_dir.name) != run_dir.name:
                raise ValueError("report run identity mismatch")
            return data
    return {}


class RunIndex:
    """Filesystem-backed index for canonical execution runs and timeline reconstruction."""

    def __init__(
        self,
        run_roots: Optional[List[Path]] = None,
        run_manager: Optional[RunManager] = None,
    ) -> None:
        self.roots: List[Path] = run_roots or [
            ROOT / "evidence" / "runtime",
            ROOT / "scripts" / "demo" / "demo-output",
        ]
        self.roots = [Path(root).absolute() for root in self.roots]
        self.run_manager = run_manager

    def validate_run_id(self, run_id: str) -> None:
        """Validate run_id format to prevent path traversal."""
        if type(run_id) is not str or len(run_id) > 128 or not re.fullmatch(r"[a-zA-Z0-9_\-]+", run_id):
            raise ValueError(f"Invalid run_id format: {run_id}")

    def find_run_dir(self, run_id: str) -> Optional[Path]:
        """Locate run directory across approved roots with path containment validation."""
        self.validate_run_id(run_id)
        for root in self.roots:
            try:
                no_link_ancestors(root)
                cand = (root / run_id).absolute()
                no_link_ancestors(cand)
                if cand.is_dir() and cand.is_relative_to(root.resolve()):
                    return cand
            except (OSError, ValueError):
                continue
        return None

    def _determine_planner_verification(
        self,
        requested: str,
        actual: str,
        provider: Optional[str] = None,
        fallback_reason: Optional[str] = None,
    ) -> str:
        req_upper = _text(requested, "UNKNOWN").upper()
        act_upper = _text(actual, "UNKNOWN").upper()
        if req_upper == "HYBRID":
            return PlannerVerificationStatus.HYBRID_NOT_IMPLEMENTED.value
        if req_upper in ("LLM", "LLM-UNAVAILABLE"):
            if act_upper == "RULE":
                return PlannerVerificationStatus.LLM_FALLBACK_TO_RULE.value
            if act_upper == "NOT_RUN":
                return PlannerVerificationStatus.LLM_PROVIDER_NOT_AVAILABLE.value
            if act_upper == "LLM" and provider not in (None, "none", "rule_engine", "mock"):
                return PlannerVerificationStatus.LLM_PROVIDER_RECORDED.value
        if act_upper == "RULE":
            return PlannerVerificationStatus.RULE_EXECUTED.value
        return PlannerVerificationStatus.UNKNOWN.value

    def _extract_run_item(self, run_dir: Path, *, verify: bool = True) -> Optional[RunHistoryItem]:
        """Read recorded metadata; absent counters and unverified claims stay unknown."""
        run_id = run_dir.name
        try:
            self.validate_run_id(run_id)
            integrity = (verify_records(run_dir / "assessment" if (run_dir / "assessment").is_dir() else run_dir, run_id)
                         if verify else IntegritySummary("NOT_VERIFIED", 0, None))
            rep_data = recorded_report(run_dir)
            provenance = rep_data.get("planner_provenance", {})
            if type(provenance) is not dict:
                raise ValueError("invalid planner provenance")
            def field(*keys, default=None):
                for key in keys:
                    if key in rep_data:
                        return rep_data[key]
                    if key in provenance:
                        return provenance[key]
                return default
            def count(*keys):
                value = field(*keys)
                return value if type(value) is int and value >= 0 else None
            def text(*keys, default=None):
                return _text(field(*keys), default)
            req_mode = text("requested_planner_mode", "requested_mode", default="UNKNOWN")
            act_mode = text("actual_planner_mode", "actual_mode", default="UNKNOWN")
            provider = text("provider")
            fallback = text("fallback_reason")
            start = text("started_at_utc")
            end = text("ended_at_utc")
            # Record timestamps measure artifact creation, not execution duration.
            created = text("created_at_utc", "generated_at_utc")
            stop = text("stop_reason")
            state = text("state", "outcome", default="INCOMPLETE")
            if state not in {"COMPLETED", "FAILED", "BLOCKED", "STOPPED", "RUNNING", "PAUSED", "INCOMPLETE"}:
                state = "INCOMPLETE"
            if rep_data.get("pipeline_control_completed") is True:
                state = "COMPLETED"
            if stop in ("EMERGENCY_KILL_SWITCH_ACTIVATED", "KILL_SWITCH_ACTIVATED"):
                state = "BLOCKED"
            elif stop in ("STOP_REQUESTED", "MANUAL_STOP"):
                state = "STOPPED"
            findings = rep_data.get("findings")
            return RunHistoryItem(
                run_id=run_id, created_at_utc=created, started_at_utc=start,
                ended_at_utc=end, duration_ms=_calc_duration_ms(start, end),
                scenario=text("scenario", "scenario_id", default="UNKNOWN"),
                target_id=text("target_id", "target", default="UNKNOWN"),
                planner_requested=req_mode, planner_actual=act_mode,
                planner_verification=self._determine_planner_verification(req_mode, act_mode, provider, fallback),
                provider=provider, model=text("model"),
                control_mode=text("control_mode", default="UNKNOWN"), fallback_reason=fallback,
                state=state, outcome=state, stop_reason=stop,
                iterations=count("decisions_count", "iterations"), proposals=count("decisions_count", "proposals"),
                permits=count("approved_actions_count", "permits_count"),
                denials=count("denied_actions_count", "denials_count"),
                network_dispatches=count("network_dispatch_count", "network_dispatches"),
                observations=count("observations_added_count", "observations"),
                evidence_count=integrity.record_count, verified_evidence_count=integrity.verified_count,
                evidence_integrity=integrity.state,
                findings_count=sum(type(f) is dict and type(f.get("classification")) is str
                                   and f["classification"] in SECURITY_FINDING_CLASSES
                                   for f in findings) if type(findings) is list else None,
                pause_count=count("pause_count"), operator_approvals=count("operator_approvals_count"),
                operator_rejections=count("operator_rejections_count"),
            )
        except (OSError, ValueError, TypeError, KeyError, RecursionError):
            return RunHistoryItem(run_id=run_id, stop_reason="CORRUPT_OR_INCOMPLETE",
                                  evidence_integrity="FAILED")

    def list_runs(
        self,
        planner: Optional[str] = None,
        control_mode: Optional[str] = None,
        state: Optional[str] = None,
        scenario: Optional[str] = None,
        search: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
        include_test_runs: bool = True,
    ) -> RunHistoryResponse:
        """Scan canonical run directories and return filtered, chronologically sorted run history."""
        seen_run_ids: Set[str] = set()
        items: List[RunHistoryItem] = []
        if (limit is not None and (type(limit) is not int or not 1 <= limit <= 100)) or type(offset) is not int or offset < 0:
            raise ValueError("invalid history pagination")
        directories: Dict[str, Path] = {}

        # 1. Include active/current run from RunManager if running
        if self.run_manager:
            run_stat, agent_stat, safety_stat, evidence_stat, _ = self.run_manager.get_snapshot()
            if run_stat.run_id:
                active_id = run_stat.run_id
                seen_run_ids.add(active_id)
                verification = self._determine_planner_verification(
                    requested=run_stat.planner,
                    actual=agent_stat.actual_mode,
                    provider=agent_stat.provider,
                    fallback_reason=agent_stat.fallback_reason,
                )
                duration = _calc_duration_ms(run_stat.started_at_utc, run_stat.ended_at_utc)
                items.append(RunHistoryItem(
                    run_id=active_id,
                    created_at_utc=run_stat.started_at_utc,
                    started_at_utc=run_stat.started_at_utc,
                    ended_at_utc=run_stat.ended_at_utc,
                    duration_ms=duration,
                    scenario=run_stat.scenario,
                    target_id=run_stat.target,
                    planner_requested=run_stat.planner.upper(),
                    planner_actual=agent_stat.actual_mode.upper(),
                    planner_verification=verification,
                    provider=agent_stat.provider,
                    model=agent_stat.model,
                    control_mode=run_stat.control_mode,
                    fallback_reason=agent_stat.fallback_reason,
                    state=run_stat.state.value,
                    outcome=run_stat.state.value,
                    stop_reason=run_stat.stop_reason,
                    iterations=run_stat.decisions_count,
                    proposals=run_stat.decisions_count,
                    permits=safety_stat.permits_count,
                    denials=safety_stat.denials_count,
                    network_dispatches=safety_stat.network_dispatches,
                    observations=agent_stat.facts_count,
                    evidence_count=evidence_stat.count,
                    verified_evidence_count=None,
                    evidence_integrity="NOT_VERIFIED",
                    findings_count=0,
                    pause_count=run_stat.pause_count,
                    operator_approvals=run_stat.operator_approvals,
                    operator_rejections=run_stat.operator_rejections,
                ))

        # 2. Scan directories from roots
        for root in self.roots:
            try:
                no_link_ancestors(root)
            except (OSError, ValueError):
                continue
            if not root.is_dir():
                continue
            for entry in root.iterdir():
                if not entry.is_dir() or entry.is_symlink() or (hasattr(entry, "is_junction") and entry.is_junction()):
                    continue
                run_id = entry.name
                if run_id in seen_run_ids:
                    continue
                seen_run_ids.add(run_id)
                if not include_test_runs and re.match(r"^(TEST-|RUN-TEST-|RUN-SL\d+-TEST-)", run_id, re.I):
                    continue

                directories[run_id] = entry
                item = self._extract_run_item(entry, verify=limit is None)
                if item:
                    items.append(item)

        # 3. Apply filters
        filtered: List[RunHistoryItem] = []
        for it in items:
            if not include_test_runs and re.match(r"^(TEST-|RUN-TEST-|RUN-SL\d+-TEST-)", it.run_id, re.I):
                continue
            if planner:
                p_filter = planner.upper()
                if (
                    p_filter not in it.planner_requested.upper()
                    and p_filter not in it.planner_actual.upper()
                    and p_filter not in it.planner_verification.upper()
                ):
                    continue

            if control_mode:
                if control_mode.upper() != (it.control_mode or "").upper():
                    continue

            if state:
                if state.upper() != (it.state or "").upper():
                    continue

            if scenario:
                if scenario.upper() != (it.scenario or "").upper():
                    continue

            if search:
                s_lower = search.lower()
                matches = (
                    s_lower in it.run_id.lower()
                    or s_lower in (it.stop_reason or "").lower()
                    or s_lower in it.target_id.lower()
                    or s_lower in it.planner_verification.lower()
                )
                if not matches:
                    continue

            filtered.append(it)

        # 4. Sort chronologically descending
        filtered.sort(
            key=lambda x: x.started_at_utc or x.created_at_utc or "",
            reverse=True,
        )

        total = len(filtered)
        if limit is not None:
            # ponytail: scan metadata for sorting; verify only the requested page.
            # A persistent index is warranted only if metadata scanning becomes slow.
            filtered = filtered[offset:offset + limit]
            filtered = [self._extract_run_item(directories[item.run_id])
                        if item.run_id in directories else item for item in filtered]
        return RunHistoryResponse(runs=filtered, total_count=total)

    def get_run(self, run_id: str) -> Optional[RunHistoryItem]:
        """Fetch single run details by run_id."""
        self.validate_run_id(run_id)

        # Check active run in RunManager
        if self.run_manager:
            run_stat, agent_stat, safety_stat, evidence_stat, _ = self.run_manager.get_snapshot()
            if run_stat.run_id == run_id:
                verification = self._determine_planner_verification(
                    requested=run_stat.planner,
                    actual=agent_stat.actual_mode,
                    provider=agent_stat.provider,
                    fallback_reason=agent_stat.fallback_reason,
                )
                duration = _calc_duration_ms(run_stat.started_at_utc, run_stat.ended_at_utc)
                return RunHistoryItem(
                    run_id=run_id,
                    created_at_utc=run_stat.started_at_utc,
                    started_at_utc=run_stat.started_at_utc,
                    ended_at_utc=run_stat.ended_at_utc,
                    duration_ms=duration,
                    scenario=run_stat.scenario,
                    target_id=run_stat.target,
                    planner_requested=run_stat.planner.upper(),
                    planner_actual=agent_stat.actual_mode.upper(),
                    planner_verification=verification,
                    provider=agent_stat.provider,
                    model=agent_stat.model,
                    control_mode=run_stat.control_mode,
                    fallback_reason=agent_stat.fallback_reason,
                    state=run_stat.state.value,
                    outcome=run_stat.state.value,
                    stop_reason=run_stat.stop_reason,
                    iterations=run_stat.decisions_count,
                    proposals=run_stat.decisions_count,
                    permits=safety_stat.permits_count,
                    denials=safety_stat.denials_count,
                    network_dispatches=safety_stat.network_dispatches,
                    observations=agent_stat.facts_count,
                    evidence_count=evidence_stat.count,
                    verified_evidence_count=None,
                    evidence_integrity="NOT_VERIFIED",
                    findings_count=0,
                    pause_count=run_stat.pause_count,
                    operator_approvals=run_stat.operator_approvals,
                    operator_rejections=run_stat.operator_rejections,
                )

        run_dir = self.find_run_dir(run_id)
        if not run_dir:
            return None

        return self._extract_run_item(run_dir)

    def get_run_timeline(self, run_id: str) -> Optional[RunTimelineResponse]:
        """Reconstruct chronological timeline events from events.jsonl or evidence artifacts."""
        run_dir = self.find_run_dir(run_id)
        if not run_dir:
            return None

        events: List[TimelineEventItem] = []

        # 1. Read events.jsonl if present
        events_file = run_dir / "events.jsonl"
        if events_file.is_file():
            try:
                step_idx = 1
                for line in bounded_bytes(events_file, run_dir).decode("utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        raw = json.loads(line)
                        if raw.get("run_id") != run_id:
                            raise ValueError("event run identity mismatch")
                        ev_type = raw.get("type", "EVENT")
                        payload = raw.get("payload", {})
                        title = ev_type.replace("_", " ").title()
                        desc = ""
                        if ev_type == "RUN_STARTED":
                            desc = f"Run initialized in {payload.get('control_mode', 'UNKNOWN')} mode."
                        elif ev_type == "PLANNER_PROPOSED":
                            desc = f"Planner proposed {payload.get('action_id', raw.get('action_id', 'UNKNOWN'))} ({payload.get('actual_mode', 'UNKNOWN')})."
                        elif ev_type == "SAFETY_PERMITTED":
                            desc = "Safety Gate evaluated proposal and permitted execution."
                        elif ev_type == "SAFETY_DENIED":
                            desc = f"Safety Gate denied proposal: {payload.get('reason', 'Policy violation')}."
                        elif ev_type == "ACTION_DISPATCHED":
                            desc = "Network action dispatched to isolated ShopLab target."
                        elif ev_type == "OBSERVATION_RECEIVED":
                            desc = "HTTP response and target telemetry recorded."
                        elif ev_type == "EVIDENCE_RECORDED":
                            desc = f"Cryptographic evidence persisted ({payload.get('evidence_id', 'EV')})."
                        elif ev_type == "EVIDENCE_VERIFIED":
                            desc = "Hash integrity verified against canonical records."
                        elif ev_type == "RUN_COMPLETED":
                            desc = f"Execution completed cleanly. Reason: {payload.get('stop_reason', 'FINISHED')}."
                        else:
                            desc = f"Execution step {ev_type} logged."

                        events.append(TimelineEventItem(
                            step_index=step_idx,
                            event_id=raw.get("event_id", f"EVT-{step_idx}"),
                            run_id=run_id,
                            type=ev_type,
                            timestamp_utc=raw.get("timestamp_utc", ""),
                            phase=raw.get("phase", "RECON"),
                            iteration=raw.get("iteration", step_idx),
                            title=title,
                            description=desc,
                            payload=payload,
                        ))
                        step_idx += 1
                    except Exception:
                        continue

                if events:
                    return RunTimelineResponse(run_id=run_id, events=events)
            except Exception:
                pass

        # Only display report traces that actually exist. Never synthesize a
        # start, permission, dispatch or completion from filesystem timestamps.
        try:
            report = recorded_report(run_dir)
        except (OSError, ValueError, TypeError, RecursionError):
            return RunTimelineResponse(run_id=run_id)
        traces = report.get("traces", [])
        if type(traces) is not list:
            return RunTimelineResponse(run_id=run_id)
        for trace in traces[:1024]:
            if type(trace) is not dict:
                continue
            events.append(TimelineEventItem(
                step_index=len(events) + 1, event_id=f"REPORTED-TRACE-{len(events) + 1}",
                run_id=run_id, type="TRACE_RECORDED", timestamp_utc=_text(trace.get("timestamp_utc"), ""),
                title="Recorded report trace", description="Report metadata; event ledger not available.",
                payload=trace,
            ))
        return RunTimelineResponse(run_id=run_id, events=events)

    def compare_runs(self, run_a_id: str, run_b_id: str) -> Optional[RunComparisonResponse]:
        """Perform side-by-side comparative analysis of two execution runs."""
        run_a = self.get_run(run_a_id)
        run_b = self.get_run(run_b_id)
        if not run_a or not run_b:
            return None

        # 1. Comparative Metrics
        metrics: List[ComparisonMetric] = [
            ComparisonMetric(
                metric="planner_requested",
                label="Planner Requested",
                run_a_value=run_a.planner_requested,
                run_b_value=run_b.planner_requested,
                delta=None,
            ),
            ComparisonMetric(
                metric="planner_actual",
                label="Planner Actual",
                run_a_value=run_a.planner_actual,
                run_b_value=run_b.planner_actual,
                delta=None,
            ),
            ComparisonMetric(
                metric="planner_verification",
                label="Planner Verification Status",
                run_a_value=run_a.planner_verification,
                run_b_value=run_b.planner_verification,
                delta=None,
            ),
            ComparisonMetric(
                metric="control_mode",
                label="Control Mode",
                run_a_value=run_a.control_mode,
                run_b_value=run_b.control_mode,
                delta=None,
            ),
            ComparisonMetric(
                metric="duration_ms",
                label="Execution Duration",
                run_a_value=run_a.duration_ms,
                run_b_value=run_b.duration_ms,
                delta=_delta(run_a.duration_ms, run_b.duration_ms),
                unit="ms",
            ),
            ComparisonMetric(
                metric="iterations",
                label="Decisions / Iterations",
                run_a_value=run_a.iterations,
                run_b_value=run_b.iterations,
                delta=_delta(run_a.iterations, run_b.iterations),
            ),
            ComparisonMetric(
                metric="network_dispatches",
                label="Network Dispatches",
                run_a_value=run_a.network_dispatches,
                run_b_value=run_b.network_dispatches,
                delta=_delta(run_a.network_dispatches, run_b.network_dispatches),
            ),
            ComparisonMetric(
                metric="permits",
                label="Safety Permits",
                run_a_value=run_a.permits,
                run_b_value=run_b.permits,
                delta=_delta(run_a.permits, run_b.permits),
            ),
            ComparisonMetric(
                metric="denials",
                label="Safety Denials",
                run_a_value=run_a.denials,
                run_b_value=run_b.denials,
                delta=_delta(run_a.denials, run_b.denials),
            ),
            ComparisonMetric(
                metric="evidence_count",
                label="Persisted Evidence Artifacts",
                run_a_value=run_a.evidence_count,
                run_b_value=run_b.evidence_count,
                delta=_delta(run_a.evidence_count, run_b.evidence_count),
            ),
            ComparisonMetric(
                metric="findings_count",
                label="Security Findings",
                run_a_value=run_a.findings_count,
                run_b_value=run_b.findings_count,
                delta=_delta(run_a.findings_count, run_b.findings_count),
            ),
            ComparisonMetric(
                metric="pause_count",
                label="Cooperative Pauses",
                run_a_value=run_a.pause_count,
                run_b_value=run_b.pause_count,
                delta=_delta(run_a.pause_count, run_b.pause_count),
            ),
            ComparisonMetric(
                metric="operator_approvals",
                label="Operator Approvals",
                run_a_value=run_a.operator_approvals,
                run_b_value=run_b.operator_approvals,
                delta=_delta(run_a.operator_approvals, run_b.operator_approvals),
            ),
        ]

        # 2. Action Sequences extraction
        seq_a = self._get_action_sequence(run_a_id)
        seq_b = self._get_action_sequence(run_b_id)

        # 3. Findings Overlap
        findings_a = self._get_finding_titles(run_a_id)
        findings_b = self._get_finding_titles(run_b_id)
        shared_findings = list(findings_a.intersection(findings_b))
        unique_a = list(findings_a - findings_b)
        unique_b = list(findings_b - findings_a)

        findings_overlap = {
            "shared_count": len(shared_findings),
            "unique_a_count": len(unique_a),
            "unique_b_count": len(unique_b),
            "shared_findings": shared_findings,
            "unique_a_findings": unique_a,
            "unique_b_findings": unique_b,
        }

        # 4. Safety Diff
        safety_diff = {
            "run_a_permits": run_a.permits,
            "run_b_permits": run_b.permits,
            "run_a_denials": run_a.denials,
            "run_b_denials": run_b.denials,
            "permits_delta": _delta(run_a.permits, run_b.permits),
            "denials_delta": _delta(run_a.denials, run_b.denials),
            "policy_adherence": "UNRESOLVED: recorded counters do not prove policy adherence or absence of bypass.",
        }

        # 5. Neutral academic summary verdict
        verdict = (
            f"Recorded descriptive comparison between {run_a_id} ({run_a.planner_actual}, {run_a.control_mode}) "
            f"and {run_b_id} ({run_b.planner_actual}, {run_b.control_mode}). "
            f"Reported network dispatches: {run_a.network_dispatches} vs {run_b.network_dispatches}. "
            f"Recorded safety enforcement: {run_a.denials} refusals vs {run_b.denials} refusals."
        )

        return RunComparisonResponse(
            run_a=run_a,
            run_b=run_b,
            metrics=metrics,
            action_sequence_a=seq_a,
            action_sequence_b=seq_b,
            findings_overlap=findings_overlap,
            safety_diff=safety_diff,
            summary_verdict=verdict,
            comparability_reasons=["Scenario snapshot, seed, budget and protocol equivalence have not been verified.",
                                   "Run metadata and record hashes do not establish a controlled planner experiment."],
        )

    def _get_action_sequence(self, run_id: str) -> List[ActionSequenceItem]:
        run_dir = self.find_run_dir(run_id)
        if not run_dir:
            return []

        try:
            rep_data = recorded_report(run_dir)
        except (OSError, ValueError, TypeError, RecursionError):
            return []

        items: List[ActionSequenceItem] = []
        traces = rep_data.get("traces", [])
        if type(traces) is list and traces:
            for tr in traces[:1024]:
                if type(tr) is not dict:
                    continue
                iteration = tr.get("iteration")
                dispatched = tr.get("dispatched")
                items.append(ActionSequenceItem(
                    iteration=iteration if type(iteration) is int and iteration >= 0 else len(items) + 1,
                    action_id=_text(tr.get("action_id"), "UNKNOWN"),
                    target_id=_text(rep_data.get("target_id")),
                    safety_decision=_text(tr.get("safety_decision"), "UNKNOWN"),
                    dispatched=dispatched if type(dispatched) is bool else None,
                    outcome=_text(tr.get("outcome")),
                    resource_ref=_text(tr.get("resource_ref")),
                    parameter_name=_text(tr.get("parameter_name")),
                    reason=_text(tr.get("safety_reason")),
                ))
            return items

        # Fallback to decision files
        assessment_dir = run_dir / "assessment" if (run_dir / "assessment").is_dir() else run_dir
        idx = 1
        for dec_file in sorted(assessment_dir.glob("decision-*.json")):
            try:
                dec = read_object(dec_file, run_dir)
                if dec.get("run_id") != run_id:
                    continue
                prop = dec.get("proposal", {})
                if type(prop) is not dict:
                    continue
                items.append(ActionSequenceItem(
                    iteration=idx,
                    action_id=_text(prop.get("action_id"), "UNKNOWN"),
                    target_id=_text(prop.get("target_id")),
                    safety_decision=_text(dec.get("decision"), "UNKNOWN"),
                    dispatched=None,
                    outcome=None,
                    reason=_text(dec.get("reason")),
                ))
                idx += 1
            except Exception:
                continue

        return items

    def _get_finding_titles(self, run_id: str) -> Set[str]:
        titles: Set[str] = set()
        run_dir = self.find_run_dir(run_id)
        if not run_dir:
            return titles

        try:
            rep_data = recorded_report(run_dir)
        except (OSError, ValueError, TypeError, RecursionError):
            return titles
        findings = rep_data.get("findings", [])
        if type(findings) is not list:
            return titles
        for f in findings[:1024]:
            if type(f) is not dict:
                continue
            fam = f.get("family") or f.get("title") or f.get("finding_id", "")
            if type(fam) is str and fam:
                titles.add(fam)

        return titles

    def export_comparison(self, run_a_id: str, run_b_id: str, format: str = "json") -> Tuple[str, str]:
        """Export comparative results as formatted JSON or CSV string."""
        comp = self.compare_runs(run_a_id, run_b_id)
        if not comp:
            raise ValueError(f"Unable to compare runs {run_a_id} and {run_b_id}")

        if format.lower() == "csv":
            buf = io.StringIO()
            writer = csv.writer(buf)

            # Section 1: Overview
            writer.writerow(["EXPERIMENT RUN COMPARISON"])
            writer.writerow(["Run A", comp.run_a.run_id, comp.run_a.planner_actual, comp.run_a.control_mode])
            writer.writerow(["Run B", comp.run_b.run_id, comp.run_b.planner_actual, comp.run_b.control_mode])
            writer.writerow([])

            # Section 2: Metrics Table
            writer.writerow(["Metric", "Run A", "Run B", "Delta", "Unit"])
            for m in comp.metrics:
                writer.writerow([m.label, m.run_a_value, m.run_b_value, m.delta if m.delta is not None else "", m.unit or ""])
            writer.writerow([])

            # Section 3: Action Sequences
            writer.writerow(["ACTION SEQUENCE COMPARISON"])
            writer.writerow(["Iteration", "Run A Action", "Run A Safety", "Run A Dispatched", "Run B Action", "Run B Safety", "Run B Dispatched"])
            max_len = max(len(comp.action_sequence_a), len(comp.action_sequence_b))
            for i in range(max_len):
                act_a = comp.action_sequence_a[i] if i < len(comp.action_sequence_a) else None
                act_b = comp.action_sequence_b[i] if i < len(comp.action_sequence_b) else None
                writer.writerow([
                    i + 1,
                    act_a.action_id if act_a else "",
                    act_a.safety_decision if act_a else "",
                    act_a.dispatched if act_a else "",
                    act_b.action_id if act_b else "",
                    act_b.safety_decision if act_b else "",
                    act_b.dispatched if act_b else "",
                ])
            writer.writerow([])

            # Section 4: Summary Verdict
            writer.writerow(["COMPARISON KIND", comp.comparison_kind])
            writer.writerow(["COMPARABILITY", *comp.comparability_reasons])
            writer.writerow(["POLICY ADHERENCE", comp.safety_diff["policy_adherence"]])
            writer.writerow(["SUMMARY VERDICT", comp.summary_verdict])

            return buf.getvalue(), "text/csv"

        # Default JSON
        return comp.model_dump_json(indent=2), "application/json"
