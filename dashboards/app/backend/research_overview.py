"""Read-only research inventory, not task acceptance or execution readiness.

Contract v1: errors are static codes, unavailable metrics are null, and source
hashes are self-computed observations rather than authenticated producer pins.
Only fixed paths are inspected. No known module is imported to test availability.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from runtime.evaluation.evaluation_package import verify_evaluation_package
from runtime.evidence.evidence_readonly import bounded_bytes, read_object


ROOT = Path(__file__).absolute().parents[3]
EVALUATION_ROOT = "runtime/evaluation-runs"
MAX_TASK_BYTES = 512 * 1024
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_PACKAGE_BYTES = 8 * 1024 * 1024
MAX_OVERVIEW_BYTES = 32 * 1024 * 1024
MAX_PACKAGES = 32
STATUSES = frozenset(("SPEC_ONLY", "TBD", "UNRESOLVED", "IMPLEMENTED",
                      "VALIDATED", "DEFERRED", "BLOCKED"))
TASK_IDS = tuple(f"TASK-{n:03d}" for n in range(1, 36))
SPLITS = ("validation", "test")
CANDIDATES = ("synthetic-review", "synthetic-random")
METRICS = ("success_rate", "mean_steps", "mean_cost_credits")
PACKAGE_FILES = frozenset(("manifest.json", "configuration.json", "analysis.json", "report.md")) | frozenset(
    f"{split}-{candidate}.{kind}.json" for split in SPLITS
    for candidate in CANDIDATES for kind in ("log", "metrics"))
OFFLINE = "OFFLINE_MODULE"
WEB = "READ_ONLY_WEB_EXISTING"
DOCUMENTATION = "DOCUMENTATION_ONLY"
# Associations describe implementation subsets only, never full task completion.
KNOWN_MODULES = (
    ("discovery_import", "runtime/discovery/discovery_report_importer.py", (15,), OFFLINE),
    ("zap_parser", "tools/parsers/zap_parser.py", (16,), OFFLINE),
    ("nuclei_parser", "tools/parsers/nuclei_parser.py", (17,), OFFLINE),
    ("observation_normalizer", "agent/perception/normalizers/observation_normalizer.py", (18,), OFFLINE),
    ("nuclei_normalizer", "agent/perception/normalizers/nuclei_normalizer.py", (18,), OFFLINE),
    ("knowledge_state", "runtime/state/knowledge_state_store.py", (19,), OFFLINE),
    ("planner_interface", "runtime/planners/planner_interface.py", (20,), OFFLINE),
    ("rule_planner", "runtime/planners/rule_based_planner.py", (21,), OFFLINE),
    ("llm_planner", "runtime/planners/llm_planner.py", (22,), OFFLINE),
    ("rl_environment", "runtime/evaluation/rl_environment.py", (23,), OFFLINE),
    ("reward_model", "runtime/evaluation/reward_model.py", (24,), OFFLINE),
    ("q_learning", "runtime/evaluation/q_learning.py", (25,), OFFLINE),
    ("replay_preparation", "runtime/evaluation/replay_wrappers.py", (26,), OFFLINE),
    ("offline_protocol", "runtime/evaluation/offline_evaluation.py", (26, 30), OFFLINE),
    ("hybrid_router", "runtime/planners/hybrid_router.py", (27,), OFFLINE),
    ("offline_evaluation", "runtime/evaluation/evaluate_all.py", (28, 29, 30, 31, 33), OFFLINE),
    ("evaluation_verifier", "runtime/evaluation/evaluation_package.py", (34,), OFFLINE),
    ("web_history", "dashboards/app/backend/run_history.py", (32,), WEB),
)


class OverviewError(ValueError):
    """A static, safe public error code."""


def _utc(timestamp=None):
    value = datetime.now(timezone.utc) if timestamp is None else datetime.fromtimestamp(timestamp, timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def _checked(path, root, *, directory=False):
    """Check lexical ancestors before resolve, including all Windows reparse types."""
    path, root = Path(path).absolute(), Path(root).absolute()
    if ".." in path.parts or ".." in root.parts or not path.is_relative_to(root):
        raise OverviewError("UNSAFE_PATH")
    # Start at the volume root, so missing descendants cannot hide linked parents.
    for part in reversed((path, *path.parents)):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise OverviewError("LINK_OR_REPARSE_POINT")
    if not path.resolve().is_relative_to(root.resolve()):
        raise OverviewError("UNSAFE_PATH")
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise OverviewError("INVALID_FILE_TYPE")
    return info


def _stamp(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _read(path, root, limit=MAX_FILE_BYTES):
    before = _checked(path, root)
    if before.st_size > limit:
        raise OverviewError("FILE_SIZE_LIMIT")
    data = bounded_bytes(path, root)
    after = _checked(path, root)
    if len(data) > limit:
        raise OverviewError("FILE_SIZE_LIMIT")
    if _stamp(before) != _stamp(after) or len(data) != after.st_size:
        raise OverviewError("SOURCE_CHANGED")
    return data, after


def _object(path, root):
    data, info = _read(path, root)
    value = read_object(path, root)  # duplicate fields and nonfinite constants rejected
    again, after = _read(path, root)
    if data != again or _stamp(info) != _stamp(after) or value != json.loads(data):
        raise OverviewError("SOURCE_CHANGED")
    return value, data, info


def _source(path):
    return dict(path=path, modified_at_utc=None, sha256=None)


def _metadata(source, data, info):
    source.update(modified_at_utc=_utc(info.st_mtime), sha256=hashlib.sha256(data).hexdigest())


def _code(exc, fallback):
    if isinstance(exc, OverviewError):
        return str(exc)
    if isinstance(exc, FileNotFoundError):
        return "SOURCE_MISSING"
    return fallback  # Never expose raw exceptions, local paths or payload text.


READ_ERRORS = (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError, StopIteration)


def _parse_tasks(data):
    lines = data.decode("utf-8-sig").splitlines()
    header = ["ID", "Descriptive name", "Status", "Dependencies"]

    def cells(line):
        return [cell.strip() for cell in line.strip().strip("|").split("|")]

    starts = [i for i, line in enumerate(lines) if cells(line) == header]
    if len(starts) != 1:
        raise OverviewError("TASK_TABLE_INVALID")
    start = starts[0]
    if start + 1 >= len(lines) or not re.fullmatch(r"\|\s*:?-+:?\s*\|\s*:?-+:?\s*\|\s*:?-+:?\s*\|\s*:?-+:?\s*\|", lines[start + 1]):
        raise OverviewError("TASK_TABLE_INVALID")
    tasks = []
    for line in lines[start + 2:]:
        if not line.strip():
            break
        if not line.startswith("|") or not line.rstrip().endswith("|"):
            raise OverviewError("TASK_TABLE_INVALID")
        row = cells(line)
        if len(row) != 4 or len(tasks) >= 35:
            raise OverviewError("TASK_TABLE_INVALID")
        identity, name, status, dependencies = row
        if identity != TASK_IDS[len(tasks)] or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 /(),.-]{0,119}", name):
            raise OverviewError("TASK_TABLE_INVALID")
        if status not in STATUSES and status not in {f"`{value}`" for value in STATUSES}:
            raise OverviewError("TASK_STATUS_INVALID")
        status = status.strip("`")
        if identity in ("TASK-026", "TASK-032") and status != "DEFERRED":
            raise OverviewError("DEFERRED_STATUS_CONFLICT")
        deps = [] if dependencies == "none" else [part.strip() for part in dependencies.split(",")]
        if dependencies == "all-required":
            if identity != "TASK-035":
                raise OverviewError("TASK_DEPENDENCIES_INVALID")
        elif (not deps and dependencies != "none") or len(set(deps)) != len(deps) or any(
                dep not in TASK_IDS or dep >= identity for dep in deps):
            raise OverviewError("TASK_DEPENDENCIES_INVALID")
        tasks.append(dict(id=identity, name=name, status=status, dependencies=deps,
                          integration_scope=DOCUMENTATION, module_ids=[]))
    if len(tasks) != 35:
        raise OverviewError("TASK_TABLE_INVALID")
    return tasks


def _inventory(directory, root):
    _checked(directory, root, directory=True)
    stamps, total = {}, 0
    with os.scandir(directory) as entries:
        for entry in entries:
            if entry.name not in PACKAGE_FILES or len(stamps) >= len(PACKAGE_FILES):
                raise OverviewError("PACKAGE_INVENTORY_INVALID")
            info = _checked(directory / entry.name, root)
            if info.st_size > MAX_FILE_BYTES:
                raise OverviewError("FILE_SIZE_LIMIT")
            total += info.st_size
            if total > MAX_PACKAGE_BYTES:
                raise OverviewError("PACKAGE_SIZE_LIMIT")
            stamps[entry.name] = _stamp(info)
    if stamps.keys() != PACKAGE_FILES:
        raise OverviewError("PACKAGE_INVENTORY_INVALID")
    return stamps, total


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1e12:
        raise OverviewError("METRICS_INVALID")
    return value


def _metrics(analysis):
    rows = analysis["observed_state"]["summaries"]
    if type(rows) is not list or len(rows) != 4:
        raise OverviewError("METRICS_INVALID")
    result, seen = [], set()
    for row in rows:
        split, candidate = row["split"], row["candidate_id"]
        if split not in SPLITS or candidate not in CANDIDATES or (split, candidate) in seen:
            raise OverviewError("METRICS_INVALID")
        seen.add((split, candidate))
        values = {}
        for name in METRICS:
            item = row["metrics"][name]
            mean, interval = _number(item["mean"]), item["ci"]
            if mean < 0 or (name == "success_rate" and mean > 1):
                raise OverviewError("METRICS_INVALID")
            if interval is None:
                low = high = None
            else:
                if type(interval) is not list or len(interval) != 2:
                    raise OverviewError("METRICS_INVALID")
                low, high = map(_number, interval)
                if not low <= mean <= high:
                    raise OverviewError("METRICS_INVALID")
            values[name] = dict(mean=mean, ci_low=low, ci_high=high)
        result.append(dict(split=split, candidate_id=candidate, values=values))
    return sorted(result, key=lambda item: (item["split"], item["candidate_id"]))


def _package(directory, root, budget):
    source = _source(f"{EVALUATION_ROOT}/{directory.name}/manifest.json")
    source["provenance"] = None
    result = dict(run_id=directory.name, source=source, metrics=None, verification=dict(
        state="FAILED", hash_basis="SELF_COMPUTED_NOT_TRUSTED_PRODUCER_PIN",
        integrity_scope="ARTIFACT_HASHES_AND_ENVELOPES", experimental_claims="UNRESOLVED", error_code=None))
    try:
        before, size = _inventory(directory, root)
        if size > budget[0]:
            raise OverviewError("OVERVIEW_SIZE_LIMIT")
        budget[0] -= size
        manifest, data, info = _object(directory / "manifest.json", root)
        _metadata(source, data, info)
        verify_evaluation_package(directory, source["sha256"])
        analysis, analysis_data, _ = _object(directory / "analysis.json", root)
        refs = manifest["observed_state"]["artifacts"]
        expected = next(ref["sha256"] for ref in refs if ref["name"] == "analysis.json")
        if hashlib.sha256(analysis_data).hexdigest() != expected:
            raise OverviewError("SOURCE_CHANGED")
        metrics = _metrics(analysis)
        after, _ = _inventory(directory, root)
        if before != after:
            raise OverviewError("SOURCE_CHANGED")
        source["provenance"] = "SIMULATED_FIXTURE"
        result["metrics"] = metrics
        result["verification"]["state"] = "VERIFIED"
    except READ_ERRORS as exc:
        result["verification"]["error_code"] = _code(exc, "PACKAGE_VERIFICATION_FAILED")
    return result


# A separate viewer process preserves the user-owned control server's memory.
# Disable documentation/OpenAPI routes so this app exposes just one GET route.
app = FastAPI(title="Read-only research overview", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/research/overview")
def get_research_overview() -> dict:
    return build_research_overview(ROOT)


def _evaluations(root):
    result = dict(state="OK", root=EVALUATION_ROOT, packages=[], errors=[])
    directory = root / EVALUATION_ROOT
    try:
        _checked(directory, root, directory=True)
        names = []
        with os.scandir(directory) as entries:
            for entry in entries:
                if len(names) >= MAX_PACKAGES:
                    raise OverviewError("PACKAGE_COUNT_LIMIT")
                names.append(entry.name)
        budget = [MAX_OVERVIEW_BYTES]
        for name in sorted(names):
            # Never echo unknown entry names; they can contain sensitive text.
            if not re.fullmatch(r"RUN-EVAL-[a-f0-9]{32}", name):
                result["errors"].append(dict(code="PACKAGE_NAME_INVALID", source=EVALUATION_ROOT))
                continue
            result["packages"].append(_package(directory / name, root, budget))
        if result["errors"] or any(p["verification"]["state"] == "FAILED" for p in result["packages"]):
            result["state"] = "PARTIAL"
    except READ_ERRORS as exc:
        result["state"] = "ERROR"
        result["errors"].append(dict(code=_code(exc, "EVALUATION_READ_FAILED"), source=EVALUATION_ROOT))
    return result


def build_research_overview(root: Path = ROOT) -> dict:
    """Trusted root injection is for isolated tests; the GET route accepts no paths."""
    root = Path(root).absolute()
    result = dict(schema_version=1, generated_at_utc=_utc(), state="OK", integration=dict(
        scope="READ_ONLY_OVERVIEW", fully_connected=False, execution_enabled=False, status_authority="TASKS.md"),
        task_source=_source("TASKS.md"), tasks=[], modules=[], errors=[])
    try:
        data, info = _read(root / "TASKS.md", root, MAX_TASK_BYTES)
        _metadata(result["task_source"], data, info)
        result["tasks"] = _parse_tasks(data)
    except READ_ERRORS as exc:
        result["errors"].append(dict(code=_code(exc, "TASK_SOURCE_INVALID"), source="TASKS.md"))
        result["state"] = "ERROR"
    for identity, path, numbers, scope in KNOWN_MODULES:
        availability = "PRESENT"
        try:
            _checked(root / path, root)
        except FileNotFoundError:
            availability = "MISSING"
        except READ_ERRORS as exc:
            availability = "ERROR"
            result["errors"].append(dict(code=_code(exc, "MODULE_READ_FAILED"), source=path))
        task_ids = [f"TASK-{n:03d}" for n in numbers]
        result["modules"].append(dict(id=identity, path=path, task_ids=task_ids,
                                      availability=availability, integration_scope=scope))
        for task in result["tasks"]:
            if task["id"] in task_ids:
                task["module_ids"].append(identity)
                if availability == "PRESENT":
                    task["integration_scope"] = scope
    result["evaluations"] = _evaluations(root)
    if result["state"] != "ERROR" and (result["errors"] or result["evaluations"]["state"] != "OK"):
        result["state"] = "PARTIAL"
    return result
