"""Task 28-31 offline orchestration: replay -> hashed logs -> KPIs -> report.

Run from the repository root: python -B -m runtime.evaluation.evaluate_all --demo
Only the two fixed, stateless metadata selectors below are executable. There is
no live runner, plugin loading, training, provider, shell or network integration.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import math
import os
import platform
import re
import uuid
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import gymnasium
import numpy as np
import scipy
from scipy import stats

from evaluation.metrics.formulas import goal_success_rate
from runtime.evaluation.offline_evaluation import (
    OfflineEvaluationProtocol, ReplayFixture, evaluate_offline,
)
from runtime.evaluation.rl_environment import ReplayAsset
from runtime.evaluation.usage_costs import summarize_ledger
from runtime.evaluation.defensive_log_import import import_defensive_summaries


SOURCE = "SIMULATED_FIXTURE"
SPLITS = ("validation", "test")  # Standard evaluation, then held-out evaluation.
CANDIDATES = ("synthetic-review", "synthetic-random")
KPI_NAMES = ("success_rate", "mean_steps", "mean_cost_credits")
MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
_NAME = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}")


def _json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _finite(value, low=0, high=1e9):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError("finite number outside supported bounds")
    return float(value)


def _int(value, high):
    if type(value) is not int or not 0 <= value <= high:
        raise ValueError("bounded non-negative integer required")
    return value


def _no_links(path):
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError("symlink/junction artifact paths are not supported")


@dataclass(frozen=True)
class ArtifactRef:
    name: str
    sha256: str


class ArtifactStore:
    """Exclusive new run directory; partial runs survive failures for inspection.

    Local single-writer storage, not a sandbox against hostile concurrent path
    replacement and not a guarantee of directory durability after power loss.
    """

    def __init__(self, output_parent):
        parent = Path(output_parent).absolute()
        _no_links(parent)
        parent.mkdir(parents=True, exist_ok=True)
        self.run_id = "RUN-EVAL-" + uuid.uuid4().hex
        self.root = parent.resolve() / self.run_id
        self.root.mkdir(exist_ok=False)
        self.created_at_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self.refs = []

    def _path(self, name):
        if type(name) is not str or not _NAME.fullmatch(name) or ".." in name:
            raise ValueError("bounded artifact filename required")
        _no_links(self.root)
        path = self.root / name
        _no_links(path)
        if path.resolve().parent != self.root:
            raise ValueError("artifact path escaped run directory")
        return path

    def write(self, name, value, *, text=False):
        data = value.encode("utf-8") if text else _json_bytes(value)
        if len(data) > MAX_ARTIFACT_BYTES:
            raise ValueError("artifact exceeds size limit")
        with self._path(name).open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        ref = ArtifactRef(name, _sha(data))
        self.refs.append(ref)
        return ref

    def read_json(self, ref):
        if type(ref) is not ArtifactRef or ref not in self.refs:
            raise ValueError("artifact reference from this run required")
        with self._path(ref.name).open("rb") as stream:
            data = stream.read(MAX_ARTIFACT_BYTES + 1)
        if len(data) > MAX_ARTIFACT_BYTES or _sha(data) != ref.sha256:
            raise ValueError("artifact size/hash mismatch")
        return json.loads(data)

    def envelope(self, expected, observed, *, source=SOURCE):
        if source not in (SOURCE, "IMPORTED_API_USAGE", "IMPORTED_DEFENSIVE_LOG"):
            raise ValueError("supported artifact provenance required")
        return dict(run_id=self.run_id, created_at_utc=self.created_at_utc,
                    source=source, redaction="METADATA_ONLY", schema_version=2,
                    expected_state=expected, observed_state=observed)


def _review_selector(observation, mask, rng):
    flags = observation["assets"]
    n = len(flags)
    for slot in range(n):
        if not flags[slot, 0] and mask[slot]:
            return slot
        if not flags[slot, 1] and mask[n + slot]:
            return n + slot
    return 2 * n


def _random_selector(observation, mask, rng):
    return int(rng.choice(np.flatnonzero(mask)))


def _selector(candidate_id):
    # Closed registry; caller strings cannot become arbitrary code or imports.
    if candidate_id == CANDIDATES[0]:
        return _review_selector
    if candidate_id == CANDIDATES[1]:
        return _random_selector
    raise ValueError("unsupported offline candidate")


class ExperimentRunner:
    """Task 28: existing replay runner, resetting the simulator per episode."""

    def run(self, protocol, candidate_id, split, store):
        result = evaluate_offline(protocol, _selector(candidate_id),
                                  candidate_id=candidate_id, split=split)
        return store.write(f"{split}-{candidate_id}.log.json", store.envelope(
            dict(candidate_id=candidate_id, split=split,
                 protocol_sha256=protocol.fingerprint(), terminal="REVIEW_COMPLETE"),
            asdict(result),
        ))


@dataclass(frozen=True)
class EpisodeKPI:
    candidate_id: str
    split: str
    fixture_id: str
    seed: int
    success: bool
    steps: int
    cost_credits: float
    stop_reason: str

    def __post_init__(self):
        _selector(self.candidate_id)
        if self.split not in SPLITS or type(self.fixture_id) is not str or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", self.fixture_id):
            raise ValueError("bounded metric identity required")
        _int(self.seed, 2**32 - 1)
        _int(self.steps, 10_000)
        _finite(self.cost_credits, high=1e10)
        if type(self.success) is not bool or type(self.stop_reason) is not str or not re.fullmatch(r"[A-Z_]{1,64}", self.stop_reason):
            raise ValueError("typed metric outcome required")


class MetricsEngine:
    """Task 29: hash-verified persisted runner logs are the measurement source."""

    def compute_monetary(self, ledger_path, expected_sha256, calculator=None):
        """Price only a sealed, hash-verified API-usage ledger, not replay credits."""
        return summarize_ledger(ledger_path, expected_sha256, calculator)

    def compute_defensive(self, log_path, expected_sha256):
        return import_defensive_summaries(log_path, expected_sha256)

    def compute(self, store, log_ref, protocol, candidate_id, split, cost_per_step):
        cost_per_step = _finite(cost_per_step, high=1e6)
        _selector(candidate_id)
        if split not in SPLITS or type(protocol) is not OfflineEvaluationProtocol:
            raise ValueError("validated split/protocol required")
        envelope = store.read_json(log_ref)
        expected = dict(candidate_id=candidate_id, split=split,
                        protocol_sha256=protocol.fingerprint(), terminal="REVIEW_COMPLETE")
        if (type(envelope) is not dict
                or set(envelope) != set(store.envelope(expected, {}))
                or envelope["expected_state"] != expected
                or any(envelope[k] != store.envelope(expected, {})[k]
                       for k in ("run_id", "created_at_utc", "source", "redaction", "schema_version"))):
            raise ValueError("runner log provenance mismatch")
        result = envelope["observed_state"]
        if (type(result) is not dict
                or set(result) != {"candidate_id", "split", "protocol_sha256", "episodes"}
                or any(result[k] != expected[k] for k in ("candidate_id", "split", "protocol_sha256"))):
            raise ValueError("runner result identity mismatch")
        fixtures = {f.fixture_id: f for f in getattr(protocol, split)}
        grid = {(f, s) for f in fixtures for s in protocol.episode_seeds}
        episodes = result["episodes"]
        if type(episodes) is not list or len(episodes) != len(grid):
            raise ValueError("incomplete episode grid")
        rows, seen = [], set()
        episode_fields = {"fixture_id", "episode_seed", "decisions", "episode_return", "complete",
                          "refusals", "repeated_reads", "invalid_proposals", "stop_reason", "outcomes"}
        outcomes_allowed = {"INVENTORY_OBSERVED", "REPORT_REVIEWED", "REPORT_UNAVAILABLE",
                            "REVIEW_COMPLETE", "STOPPED_EARLY", "NO_PROGRESS", "DENIED_LAB_MODE", "DENIED_APPROVAL",
                            "DENIED_TARGET", "DENIED_RATE", "DENIED_ORDER"}
        stop_allowed = outcomes_allowed | {"BUDGET_EXHAUSTED", "NO_VALID_ACTION", "POLICY_ERROR",
                                           "MALFORMED_PROPOSAL", "MASK_VIOLATION"}
        for episode in episodes:
            if type(episode) is not dict or set(episode) != episode_fields:
                raise ValueError("closed episode schema required")
            fixture_id, seed = episode["fixture_id"], episode["episode_seed"]
            if type(fixture_id) is not str:
                raise ValueError("fixture identifier required")
            _int(seed, 2**32 - 1)
            key = fixture_id, seed
            if key not in grid or key in seen:
                raise ValueError("unknown/duplicate episode")
            seen.add(key)
            steps = _int(episode["decisions"], fixtures[fixture_id].max_steps)
            outcomes = episode["outcomes"]
            if (type(outcomes) is not list or len(outcomes) != steps
                    or any(type(o) is not str or o not in outcomes_allowed for o in outcomes)):
                raise ValueError("step/outcome mismatch")
            stop, complete = episode["stop_reason"], episode["complete"]
            if type(stop) is not str or stop not in stop_allowed or type(complete) is not bool:
                raise ValueError("invalid completion/stop state")
            observed_complete = bool(outcomes and outcomes[-1] == "REVIEW_COMPLETE")
            if any(o in {"REVIEW_COMPLETE", "STOPPED_EARLY"} for o in outcomes[:-1]):
                raise ValueError("transitions after terminal outcome")
            if complete != observed_complete or (complete and stop not in {"REVIEW_COMPLETE", "BUDGET_EXHAUSTED"}):
                raise ValueError("completion is unsupported by observed outcomes")
            _finite(episode["episode_return"], low=-1e9)
            if (_int(episode["refusals"], steps) != sum(o.startswith("DENIED_") for o in outcomes)
                    or _int(episode["repeated_reads"], steps) != outcomes.count("NO_PROGRESS")):
                raise ValueError("inconsistent refusal/repetition counters")
            if _int(episode["invalid_proposals"], 1) != int(stop in {"MALFORMED_PROPOSAL", "MASK_VIOLATION"}):
                raise ValueError("invalid proposal counter mismatch")
            rows.append(EpisodeKPI(candidate_id, split, fixture_id, seed, complete, steps,
                                   steps * cost_per_step, stop))
        metrics_ref = store.write(f"{split}-{candidate_id}.metrics.json", store.envelope(
            dict(source_log=asdict(log_ref), cost_per_step=cost_per_step, cost_unit="credit"),
            dict(episodes=[asdict(row) for row in rows],
                 successes=sum(row.success for row in rows), denominator=len(rows),
                 success_rate=goal_success_rate(sum(row.success for row in rows), len(rows)),
                 exclusions=0, stop_reasons=dict(Counter(row.stop_reason for row in rows))),
        ))
        return tuple(rows), metrics_ref


def _mean_ci(values, alpha):
    mean = float(np.mean(values))
    if len(values) < 2:
        return dict(mean=mean, ci=None, inference_state="INSUFFICIENT_SEEDS")
    sd = float(np.std(values, ddof=1))
    half = float(stats.t.ppf(1 - alpha / 2, len(values) - 1)) * sd / math.sqrt(len(values))
    return dict(mean=mean, ci=[mean - half, mean + half],
                inference_state="ZERO_VARIANCE" if sd == 0 else "ESTIMATED")


class StatisticalAnalysis:
    """Task 31: fixed-scenario means per seed; paired candidates within each split."""

    def analyze(self, rows, protocol, *, alpha=0.05):
        if type(protocol) is not OfflineEvaluationProtocol:
            raise ValueError("validated protocol required")
        protocol.__post_init__()
        alpha = _finite(alpha, low=0.001, high=0.2)
        grid = {(c, split, f.fixture_id, seed) for c in CANDIDATES for split in SPLITS
                for f in getattr(protocol, split) for seed in protocol.episode_seeds}
        if any(type(row) is not EpisodeKPI for row in rows):
            raise ValueError("typed metric rows required")
        for row in rows:
            row.__post_init__()
        keys = [(r.candidate_id, r.split, r.fixture_id, r.seed) for r in rows]
        if len(keys) != len(set(keys)) or set(keys) != grid:
            raise ValueError("complete matched metrics required")
        summaries, tests, seed_means = [], [], {}
        for split in SPLITS:
            for candidate in CANDIDATES:
                group = [r for r in rows if r.split == split and r.candidate_id == candidate]
                values = {name: [] for name in KPI_NAMES}
                for seed in protocol.episode_seeds:
                    sample = [r for r in group if r.seed == seed]
                    values["success_rate"].append(sum(r.success for r in sample) / len(sample))
                    values["mean_steps"].append(float(np.mean([r.steps for r in sample])))
                    values["mean_cost_credits"].append(float(np.mean([r.cost_credits for r in sample])))
                seed_means[split, candidate] = values
                summaries.append(dict(split=split, candidate_id=candidate, episodes=len(group),
                                      seeds=len(protocol.episode_seeds), exclusions=0,
                                      successes=sum(r.success for r in group),
                                      stop_reasons=dict(Counter(r.stop_reason for r in group)),
                                      metrics={name: _mean_ci(v, alpha) for name, v in values.items()}))
            for metric in KPI_NAMES:
                baseline = np.asarray(seed_means[split, CANDIDATES[0]][metric])
                candidate = np.asarray(seed_means[split, CANDIDATES[1]][metric])
                differences = candidate - baseline
                test = dict(split=split, metric=metric, method="paired-seed-mean-t-test",
                            hypothesis="H0: mean(candidate - baseline) = 0", n=len(differences),
                            difference=_mean_ci(differences, alpha), statistic=None, df=None,
                            pvalue=None, pvalue_holm=None, reject_h0=None)
                if len(differences) < 2:
                    test["inference_state"] = "INSUFFICIENT_SEEDS"
                elif float(np.std(differences, ddof=1)) == 0:
                    # Avoid NaN/Inf and unsupported significance for deterministic deltas.
                    test["inference_state"] = "ZERO_VARIANCE"
                else:
                    result = stats.ttest_rel(candidate, baseline, nan_policy="raise")
                    test.update(inference_state="COMPUTED", statistic=float(result.statistic),
                                df=int(result.df), pvalue=float(result.pvalue))
                tests.append(test)
        # Six planned hypotheses; untestable comparisons still count in the family.
        ordered = sorted((t for t in tests if t["pvalue"] is not None), key=lambda t: t["pvalue"])
        running = 0.0
        for rank, test in enumerate(ordered):
            running = max(running, min(1.0, (len(tests) - rank) * test["pvalue"]))
            test.update(pvalue_holm=running, reject_h0=running < alpha)
        gaps = []
        for candidate in CANDIDATES:
            gaps.append(dict(candidate_id=candidate, method="DESCRIPTIVE_ONLY",
                             heldout_minus_standard={k: float(np.mean(seed_means["test", candidate][k])
                                                             - np.mean(seed_means["validation", candidate][k]))
                                                     for k in KPI_NAMES}))
        return dict(alpha=alpha, confidence_level=1-alpha, correction="Holm; 6 planned tests",
                    analysis_unit="seed mean over fixed scenarios", summaries=summaries,
                    tests=tests, generalization_gaps=gaps)


def _report(store, analysis, protocol, cost_per_step):
    lines = ["# Offline evaluation report", "", "## Summary", "",
             f"Run: `{store.run_id}`; source: `{SOURCE}`; live evaluation: `UNRESOLVED`.",
             "Observed values measure synthetic metadata review only.", "",
             "## 1. Experiment Motivation", "",
             "Compare fixed review and seeded random selectors; exercise Task 28-31 data flow.", "",
             "## 2. Experiment Setup", "",
             f"Protocol SHA-256: `{protocol.fingerprint()}`. Seeds: {list(protocol.episode_seeds)}.",
             "Standard = validation; held-out = test. Train split is never evaluated or tuned.",
             "Both candidates use the same scenario, seed, decision budget and tick rate.", "",
             "## 3. Core Algorithm or Method", "",
             "Runner -> persisted hashed log -> MetricsEngine -> StatisticalAnalysis -> report.",
             "Selectors are fixed before both splits; each episode resets its replay environment.", "",
             "## 4. Metrics", "",
             "Success = observed REVIEW_COMPLETE (metadata-review completion, not vulnerability detection).",
             "Steps = committed simulator transitions; invalid proposals are recorded separately in logs.",
             f"Cost = steps * {cost_per_step:g} credits; monetary/provider cost is unmeasured.",
             "Failed, denied and budget-exhausted episodes remain in the denominator; exclusions = 0.", "",
             "## 5. Results", "",
             "| Split | Candidate | Successes / episodes | Steps (mean) | Cost (credits) |",
             "|---|---|---:|---:|---:|"]
    for row in analysis["summaries"]:
        m = row["metrics"]
        lines.append(f"| {row['split']} | {row['candidate_id']} | {row['successes']} / {row['episodes']} "
                     f"| {m['mean_steps']['mean']:.4g} | {m['mean_cost_credits']['mean']:.4g} |")
    lines.extend(["", "Seed means and confidence intervals:", "",
                  "| Split / candidate | KPI | Mean | CI | Status |", "|---|---|---:|---|---|"])
    for row in analysis["summaries"]:
        for metric, estimate in row["metrics"].items():
            lines.append(f"| {row['split']} / {row['candidate_id']} | {metric} | {estimate['mean']:.4g} "
                         f"| {estimate['ci']} | {estimate['inference_state']} |")
    lines.extend(["", "H0: mean(candidate - baseline) = 0; two-sided paired t-test:", "",
                  "| Split | KPI | Delta | Delta CI | t / df | Raw p | Holm p | Reject H0 | Status |",
                  "|---|---|---:|---|---|---|---|---|---|"])
    for test in analysis["tests"]:
        lines.append(f"| {test['split']} | {test['metric']} | {test['difference']['mean']:.4g} "
                     f"| {test['difference']['ci']} | {test['statistic']} / {test['df']} "
                     f"| {test['pvalue']} | {test['pvalue_holm']} | {test['reject_h0']} | {test['inference_state']} |")
    lines.extend(["", "Held-out minus standard (descriptive; different scenarios):", ""])
    for gap in analysis["generalization_gaps"]:
        lines.append(f"- {gap['candidate_id']}: {gap['heldout_minus_standard']}")
    lines.extend(["", "## 6. How to Read the Tables", "",
                  "Delta is random minus review. Higher success and lower steps/cost are preferred.",
                  f"CI level = {analysis['confidence_level']:.0%}; CIs are marginal, not simultaneous.", "",
                  "## 7. Interpretation", "",
                  "Reject H0 only where Holm p < alpha; a large p does not establish equivalence.",
                  "ZERO_VARIANCE and INSUFFICIENT_SEEDS have no inferential verdict.", "",
                  "## 8. Conclusion and Discussion", "",
                  "These observations establish only the offline pipeline's measured synthetic behavior.", "",
                  "## 9. Limitations and Caveats", "",
                  "Seed units must be independent, and paired differences approximately normal for t inference.",
                  "Repeated deterministic seeds add no independent evidence; CI [mean, mean] is descriptive.",
                  "Rate CIs are approximate and may extend beyond [0, 1]. Scenario-population inference is absent.",
                  "Cost is proportional to steps, so the two tests do not supply independent support.",
                  "Held-out separation is structural; no external sealed service or learned-model freeze is claimed.",
                  "Artifacts are derived offline records, not canonical evidence-contract approval.",
                  "Hostile concurrent filesystem replacement and power-loss directory durability are unverified.", "",
                  "## 10. Next Steps", "",
                  "Independent review of protocol, failure accounting, source binding and statistical assumptions.",
                  "Live defensive benchmark integration, measured monetary cost and model evaluation remain UNRESOLVED.", "",
                  "## Reproducibility Notes", "",
                  "Full data, source hashes, policy fingerprints and dependency versions are in manifest.json.",
                  "No task status or historical evidence was updated.", "",
                  "Method reference: SciPy documentation, scipy.stats.ttest_rel (paired samples).", ""])
    return "\n".join(lines)


def evaluate_all(protocol, output_parent, *, cost_per_step=1.0, alpha=0.05,
                 protocol_input_sha256=None):
    """One sequential pipeline. Task 30 chooses test only after standard is done.

    Caller provides an immutable, validated replay protocol. Only the closed
    synthetic registry is run; no arbitrary selector/executor is accepted.
    An exception stops subsequent stages; existing artifacts are preserved.
    """
    if type(protocol) is not OfflineEvaluationProtocol:
        raise ValueError("OfflineEvaluationProtocol required")
    # Revalidate even if caller circumvented frozen dataclass construction.
    protocol.__post_init__()
    if protocol_input_sha256 is not None and (type(protocol_input_sha256) is not str or
            not re.fullmatch(r"[a-f0-9]{64}", protocol_input_sha256)):
        raise ValueError("pinned protocol SHA-256 required")
    cost_per_step = _finite(cost_per_step, high=1e6)
    alpha = _finite(alpha, low=0.001, high=0.2)
    store = ArtifactStore(output_parent)
    sources = {}
    root = Path(__file__).resolve().parents[2]
    for name in ("evaluation/evaluate_all.py", "evaluation/offline_evaluation.py",
                 "evaluation/rl_environment.py", "evaluation/replay_wrappers.py",
                 "evaluation/reward_model.py", "planners/planner_interface.py",
                 "evaluation/usage_costs.py", "evaluation/defensive_log_import.py",
                 "evaluation/evaluation_protocol_io.py", "audit/audit_support.py"):
        sources["runtime/" + name] = _sha((root / "runtime" / name).read_bytes())
    metric_source = Path(inspect.getfile(goal_success_rate))
    sources["evaluation/metrics/formulas.py"] = _sha(metric_source.read_bytes())
    policies = {c: _sha(inspect.getsource(_selector(c)).encode()) for c in CANDIDATES}
    configuration = dict(protocol_sha256=protocol.fingerprint(),
                         protocol_input_sha256=protocol_input_sha256,
                         splits={s: [f.identity_record() for f in getattr(protocol, s)]
                                 for s in ("train", *SPLITS)},
                         seeds=list(protocol.episode_seeds), masking=protocol.masking,
                         cost_per_step=cost_per_step, cost_unit="credit", monetary_cost=None,
                         alpha=alpha, policy_sha256=policies, source_sha256=sources,
                         versions=dict(python=platform.python_version(), numpy=np.__version__,
                                       scipy=scipy.__version__, gymnasium=gymnasium.__version__))
    store.write("configuration.json", store.envelope(
        dict(scope="OFFLINE_REPLAY", tuning=False, planned_hypotheses=6), configuration))
    runner, metrics = ExperimentRunner(), MetricsEngine()
    all_rows = []
    for split in SPLITS:  # Task 30: held-out selection; no training or feedback.
        for candidate in CANDIDATES:
            log_ref = runner.run(protocol, candidate, split, store)  # Task 28
            rows, _ = metrics.compute(store, log_ref, protocol, candidate, split,
                                      cost_per_step)  # Task 29, immediately after log commit
            all_rows.extend(rows)
    analysis = StatisticalAnalysis().analyze(tuple(all_rows), protocol, alpha=alpha)  # Task 31
    store.write("analysis.json", store.envelope(dict(protocol_sha256=protocol.fingerprint()), analysis))
    store.write("report.md", _report(store, analysis, protocol, cost_per_step), text=True)
    for ref in store.refs:  # Verify each publication before publishing final manifest.
        data = store._path(ref.name).read_bytes()
        if _sha(data) != ref.sha256:
            raise ValueError("artifact changed during evaluation")
    store.write("manifest.json", store.envelope(
        dict(scope="OFFLINE_REPLAY", source_sha256=sources),
        dict(pipeline="COMPLETED_OFFLINE", live_evaluation="UNRESOLVED",
             independent_review="UNRESOLVED", configuration=configuration,
             artifacts=[asdict(ref) for ref in store.refs]),
    ))
    return store.root


def demo_protocol():
    """Explicit synthetic metadata; not the canonical scenario/ground-truth set."""
    def fixture(name, count, reported):
        return ReplayFixture(name, name, (ReplayAsset("lab-fixture", count, reported),),
                             ("lab-fixture",), max_steps=10)
    return OfflineEvaluationProtocol(
        train=(fixture("demo-train", 3, True),),
        validation=(fixture("demo-standard", 5, False),),
        test=(fixture("demo-heldout", 7, None),),
        episode_seeds=(101, 102, 103, 104, 105),
    )


def report_usage_costs(ledger_path, expected_sha256, output_parent, *, calculator=None):
    """Accounting branch for externally captured real API usage; no API dispatch.

    This reports measured token counts and rate-derived dollars. It does not
    attach unrelated API costs to synthetic replay episodes or claim an invoice.
    """
    summary = MetricsEngine().compute_monetary(ledger_path, expected_sha256, calculator)
    store = ArtifactStore(output_parent)
    expected = dict(source_ledger_sha256=expected_sha256, source_run_id=summary["run_id"])
    store.write("monetary-costs.json", store.envelope(expected, summary, source="IMPORTED_API_USAGE"))
    lines = ["# API usage accounting report", "",
             f"Source run: `{summary['run_id']}`; usage provenance: `{summary['source']}`.",
             f"Calls: {summary['calls']}; unresolved calls: {summary['unknown_calls']}.",
             f"Known text-token subtotal (USD): {summary['known_token_subtotal_usd']}.",
             f"Complete token cost (USD): {summary['token_cost_usd']}.",
             "Actual invoiced cost: UNRESOLVED; this is provider usage multiplied by a dated rate card.",
             "Tool fees, taxes, discounts, credits and account-specific billing are excluded.",
             "No agent/model/live benchmark was run by this accounting branch.", "",
             "| Episode | Token cost USD | Unresolved reason |", "|---|---:|---|"]
    for event in summary["calls_detail"]:
        amount = event["quote"]["token_cost_usd"] if event["quote"] else None
        lines.append(f"| {event['episode_id']} | {amount} | {event['unresolved_reason']} |")
    lines.extend(["", f"Ledger SHA-256: `{expected_sha256}`.", ""])
    store.write("report.md", "\n".join(lines), text=True)
    store.write("manifest.json", store.envelope(expected, dict(
        pipeline="COMPLETED_ACCOUNTING", live_evaluation="UNRESOLVED",
        artifacts=[asdict(ref) for ref in store.refs]), source="IMPORTED_API_USAGE"))
    return store.root


def report_defensive_logs(log_path, expected_sha256, output_parent):
    summary = MetricsEngine().compute_defensive(log_path, expected_sha256)
    store = ArtifactStore(output_parent)
    expected = dict(source_log_sha256=expected_sha256, source_run_id=summary["run_id"])
    store.write("defensive-metrics.json", store.envelope(expected, summary, source="IMPORTED_DEFENSIVE_LOG"))
    lines = ["# Imported defensive summary report", "",
             "Source: externally supplied JSONL; live execution and outcome oracle remain UNRESOLVED.",
             "Success rates below reflect recorded claims, not independently confirmed defensive performance.",
             "Failed/refused/error/timeout episodes remain in the denominator.", "",
             "| Agent | Split | Episodes | Success claim rate | Mean steps |", "|---|---|---:|---:|---:|"]
    for row in summary["summaries"]:
        lines.append(f"| {row['agent_id']} | {row['split']} | {row['episodes']} "
                     f"| {row['success_claim_rate']:.6g} | {row['mean_steps']:.6g} |")
    lines.extend(["", "No target containers or security agents were started by this importer.",
                  f"Source SHA-256: `{expected_sha256}`.", ""])
    store.write("report.md", "\n".join(lines), text=True)
    store.write("manifest.json", store.envelope(expected, dict(
        pipeline="COMPLETED_IMPORT", live_evaluation="UNRESOLVED",
        artifacts=[asdict(ref) for ref in store.refs]), source="IMPORTED_DEFENSIVE_LOG"))
    return store.root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--demo", action="store_true",
                        help="evaluate only explicit synthetic metadata fixtures")
    mode.add_argument("--protocol", type=Path, help="load a pinned offline metadata protocol under runtime")
    parser.add_argument("--protocol-sha256", help="independently supplied protocol file SHA-256")
    mode.add_argument("--usage-ledger", type=Path, help="report a sealed provider-usage ledger offline")
    parser.add_argument("--usage-sha256", help="expected SHA-256 of the sealed ledger")
    mode.add_argument("--defensive-log", type=Path, help="normalize an externally captured defensive JSONL log")
    parser.add_argument("--defensive-sha256", help="expected SHA-256 of the defensive log")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "evaluation-runs")
    parser.add_argument("--cost-per-step", type=float, default=1.0, help="modeled credits per transition")
    parser.add_argument("--alpha", type=float, default=0.05)
    args = parser.parse_args()
    if bool(args.usage_ledger) != bool(args.usage_sha256):
        parser.error("--usage-ledger and --usage-sha256 must be supplied together")
    if bool(args.protocol) != bool(args.protocol_sha256):
        parser.error("--protocol and --protocol-sha256 must be supplied together")
    if bool(args.defensive_log) != bool(args.defensive_sha256):
        parser.error("--defensive-log and --defensive-sha256 must be supplied together")
    allowed = Path(__file__).resolve().parents[1] / "evaluation-runs"
    _no_links(args.output.absolute())
    if not args.output.resolve().is_relative_to(allowed):
        parser.error("CLI output must stay within runtime/evaluation-runs")
    try:
        if args.usage_ledger:
            root = report_usage_costs(args.usage_ledger, args.usage_sha256, args.output)
        elif args.defensive_log:
            root = report_defensive_logs(args.defensive_log, args.defensive_sha256, args.output)
        elif args.protocol:
            from runtime.evaluation.evaluation_protocol_io import load_protocol
            pinned = load_protocol(args.protocol, args.protocol_sha256, input_root=Path(__file__).resolve().parents[1])
            root = evaluate_all(pinned.protocol, args.output, cost_per_step=args.cost_per_step,
                                alpha=args.alpha, protocol_input_sha256=pinned.input_sha256)
        else:
            root = evaluate_all(demo_protocol(), args.output, cost_per_step=args.cost_per_step, alpha=args.alpha)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Evaluation stopped; partial artifacts preserved: {exc}\n")
    print(f"COMPLETED_OFFLINE: {root / 'report.md'}")


if __name__ == "__main__":
    main()
