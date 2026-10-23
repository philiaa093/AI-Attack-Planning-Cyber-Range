"""Deterministic, offline validation for project contracts and documentation."""
from __future__ import annotations

import ast
import ipaddress
import json
import math
import os
import re
import sys
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.schema_validation import _actual_type, _format_errors, _resolve_ref, validate_shape

ROOT = Path(__file__).resolve().parents[2]
STATUSES = {"SPEC_ONLY", "TBD", "UNRESOLVED", "IMPLEMENTED", "VALIDATED", "DEFERRED", "BLOCKED"}
ACTION_IDS = {f"ACTION-{group}-{number:03d}" for group, numbers in {
    "RECON": (1, 2), "SCAN": (1, 2), "WEB": (1, 2, 3), "AUTH": (1,), "FLOW": (1, 2), "PLAN": (1, 2, 3), "END": (1, 2, 3)
}.items() for number in numbers}
ACTION_CLASSES = {
    **{f"ACTION-RECON-{number:03d}": "RECON" for number in (1, 2)},
    **{f"ACTION-SCAN-{number:03d}": "SCAN" for number in (1, 2)},
    **{f"ACTION-WEB-{number:03d}": "WEB_TEST" for number in (1, 2, 3)},
    "ACTION-AUTH-001": "WEB_TEST",
    "ACTION-FLOW-001": "WEB_TEST",
    "ACTION-FLOW-002": "WEB_TEST",
    **{f"ACTION-PLAN-{number:03d}": "PLAN" for number in (1, 2, 3)},
    **{f"ACTION-END-{number:03d}": "STOP" for number in (1, 2, 3)},
}
TARGET_PATTERN = re.compile(r"^lab-[a-z0-9-]+$")
SCENARIO_PATTERN = re.compile(r"^SCN-[0-9]{3}$")
ADR_FILENAME_PATTERN = re.compile(r"^ADR-([0-9]{3})-([a-z0-9]+(?:-[a-z0-9]+)*)\.md$")
RT_SPEC_PATTERN = re.compile(r"^RT-([0-9]{2}[A-Za-z]?)-([a-z0-9]+(?:-[a-z0-9]+)*)\.md$")
SCHEMA_NAMES = {"state", "action", "plan", "observation", "scanner-result", "scenario-manifest", "experiment-manifest", "ground-truth", "evidence", "model-metadata"}
GUIDES = {
    "01-project-overview.md", "02-penetration-testing-lifecycle.md", "03-cyber-range-fundamentals.md",
    "04-web-security-testing.md", "05-security-scanners.md", "06-ai-agent-fundamentals.md",
    "07-planning-and-replanning.md", "08-llm-agent-planning.md", "09-reinforcement-learning.md",
    "10-mdp-and-pomdp.md", "11-q-learning.md", "12-dqn.md", "13-ppo.md", "14-hybrid-planning.md",
    "15-ground-truth.md", "16-evaluation-methodology.md", "17-cyber-range-safety.md",
}
TASK_SPECS = {f"TASK-{n:03d}-{name}.md" for n, name in enumerate((
    "foundation-validator", "root-governance-docs", "safety-contracts", "action-catalog", "state-contract",
    "observation-contract", "evidence-contract", "scenario-contract", "ground-truth-contract", "experiment-contract",
    "cyber-range-network", "web-target-a", "web-target-b", "clean-control-target", "discovery-adapter",
    "zap-adapter", "nuclei-adapter", "observation-normalizer", "knowledge-state-store", "planner-interface",
    "rule-based-planner", "llm-planner", "rl-environment", "reward-model", "q-learning-baseline", "dqn-ppo-candidate",
    "hybrid-planner", "experiment-runner", "metrics-engine", "held-out-evaluation", "statistical-analysis",
    "dashboard", "report-artifact-generator", "reproducibility-package", "final-foundation-audit",
), 1)}
SL_SPECS = {f"SL-{n:02d}-{name}.md" for n, name in enumerate((
    "baseline-checks", "storage-lifecycle", "auth-authorization", "cart-checkout",
    "orders-reviews", "product-admin", "lab-runtime", "discovery-safety",
    "observation-planner", "ptes-orchestration", "evidence-reporting", "verification-handoff",
), 1)}
RUNBOOKS = {
    "start-cyber-range.md", "stop-cyber-range.md", "validate-isolation.md", "run-rule-planner.md",
    "run-llm-planner.md", "train-agent.md", "run-hybrid-planner.md", "run-experiment.md",
    "collect-evidence.md", "restore-range.md",
}
CHAPTERS = {f"{n:02d}-{name}.md" for n, name in {
    1: "introduction", 2: "background", 3: "related-work", 4: "problem-formulation", 5: "system-architecture",
    6: "planner-design", 7: "implementation", 8: "experimental-methodology", 9: "results", 10: "discussion", 11: "conclusion",
}.items()}
APPENDICES = {"action-catalog.md", "scenario-catalog.md", "safety-policy.md", "experiment-manifests.md", "metric-definitions.md", "reproducibility.md"}
ROOT_FILES = {
    "README.md", "AGENTS.md", "PROJECT_CONTEXT.md", "PROJECT_PLAN.md", "TASKS.md", "CHANGELOG.md", ".gitignore", "Makefile", ".env.example",
    "actions/README.md", "actions/catalog/README.md", "actions/catalog/action-catalog.json",
    "agent/planner/contracts/README.md", "evaluation/README.md", "evidence/README.md", "evidence/policy.json", "evidence/manifest.json",
    "scenarios/README.md", "docs/thesis/README.md", "docs/guides/index.md", "docs/task-specs/index.md", "docs/runbooks/index.md", "docs/adr/index.md",
}
CONTRACT_DIR = "agent/planner/contracts"
GROUND_TRUTH_SCHEMA_PATH = "evaluation/ground_truth/ground-truth.schema.json"
SAFETY_FILES = {
    "configs/safety/lab-policy.yaml", "configs/safety/target-allowlist.yaml", "configs/safety/action-allowlist.yaml",
    "configs/safety/request-budget.yaml", "configs/safety/rate-limit.yaml", "configs/safety/kill-switch.yaml",
}
SCAFFOLD_PLACEHOLDER_DIRS = {
    "configs/tools/zap", "configs/tools/nuclei", "configs/tools/discovery",
    "cyber-range/network", "cyber-range/targets/juice-shop",
    "agent/planner/rule_based", "agent/planner/llm", "agent/planner/rl", "agent/planner/hybrid",
    "agent/memory/state", "agent/memory/history", "agent/memory/knowledge_base",
    "agent/perception/normalizers", "agent/perception/feature_extractors", "agent/orchestration",
    "actions/recon", "actions/scanning", "actions/web-testing", "actions/termination", "actions/executor",
    "tools/adapters/zap", "tools/adapters/nuclei", "tools/adapters/discovery", "tools/parsers", "tools/contracts",
    "scenarios/sqli", "scenarios/xss", "scenarios/path-traversal", "scenarios/mixed", "scenarios/clean", "scenarios/held-out",
    "evaluation/ground-truth/schema", "evaluation/ground-truth/manifests", "evaluation/ground-truth/fixtures",
    "evaluation/datasets", "evaluation/experiments", "evaluation/statistical-analysis", "evaluation/results",
    "evidence/raw/tool-output", "evidence/raw/observations", "evidence/raw/planner-output", "evidence/normalized",
    "evidence/episodes", "evidence/experiments", "evidence/manifests",
    "dashboards/designs", "dashboards/exports", "dashboards/screenshots",
    "scripts/bootstrap", "scripts/cyber-range", "scripts/experiments", "scripts/evaluation", "scripts/cleanup",
    "tests/unit", "tests/rl", "tests/integration", "tests/smoke",
}
FORBIDDEN_KEY = re.compile(r"(?:command|payload)", re.IGNORECASE)
FORBIDDEN_ARTIFACTS = {"__pycache__", ".pytest_cache", ".pyc", ".pyo"}
# Exact workspace-relative trees, not arbitrary directory basenames. In
# particular, a node_modules directory under contracts/configs remains checked.
SCAN_EXCLUDED_TREES = frozenset({
    ".git", ".venv", "venv",
    "dashboards/app/frontend/node_modules", "dashboards/app/frontend/dist",
})
FRONTEND_METADATA_FILES = frozenset({
    "dashboards/app/frontend/package.json",
    "dashboards/app/frontend/package-lock.json",
    "dashboards/app/frontend/tsconfig.json",
})
COMMENT_JSON_FILES = frozenset({"dashboards/app/frontend/tsconfig.json"})
# ponytail: one frozen handoff link; extend only for documented source moves.
HISTORICAL_SOURCE_LINKS = {
    ("reports/TASK-015-offline-handoff.md", "../runtime/discovery_report_importer.py"):
        "runtime/discovery/discovery_report_importer.py",
}
_JSON_COMMENTS = re.compile(r'("(?:\\.|[^"\\])*")|//[^\r\n]*|/\*[\s\S]*?\*/')
PROMPT_HEADINGS = ()
GUIDE_HEADINGS = ("Learning Objectives", "Why This Matters", "Core Concepts", "Terminology", "Mathematical / Technical Foundations", "Project Mapping", "Security Boundaries", "Common Mistakes", "Self-check Questions", "Related Artifacts", "Read Next", "References", "Status")
TASK_HEADINGS = ("Status", "Purpose", "Background", "Scope", "Out of Scope", "Inputs", "Outputs", "Interfaces", "Data Contracts", "Dependencies", "Implementation Requirements", "Safety Requirements", "Testing Requirements", "Acceptance Criteria", "Evidence Required", "Failure Conditions", "Related Guides", "Related Runbooks", "Related ADRs")
ADR_HEADINGS = ("Status", "Context", "Decision", "Alternatives Considered", "Consequences", "Risks", "Revisit Conditions")
RUNBOOK_HEADINGS = ("Status", "Purpose", "Preconditions", "Required Configuration", "Safety Checks", "Inputs", "Procedure", "Expected Artifacts", "Validation", "Failure Handling", "Cleanup", "Evidence", "Related Tasks")
ROOT_HEADINGS = {
    "README.md": ("Project Overview", "Research Problem", "Research Questions", "Scope", "Out of Scope", "Threat and Safety Boundary", "Architecture", "Planner Types", "Cyber Range", "Action Catalog", "Vulnerability Families", "Evaluation Methodology", "Repository Structure", "Development Workflow", "Validation", "Current Status", "Reproducibility", "References"),
    "AGENTS.md": ("Authority and Source Hierarchy", "Scope and Allowed Paths", "Trust Boundary and Input Validation", "Security and Safety", "Evidence and Data Preservation", "Status and Validation", "Change and Handoff"),
    "PROJECT_CONTEXT.md": ("Purpose", "Architecture", "Planner model", "Current state", "Boundaries", "Source hierarchy"),
    "PROJECT_PLAN.md": ("Foundation", "Literature/Threat", "Cyber Range", "Perception/Tooling", "Rule", "LLM", "RL Environment", "RL Planner", "Hybrid", "Evaluation", "Dashboard", "Final Reproducibility", "Completion rule"),
    "TASKS.md": ("ShopLab/PTES implementation backlog", "Checks and observed implementation state", "Blockers"),
    "docs/guides/index.md": (), "docs/task-specs/index.md": (), "docs/runbooks/index.md": (), "docs/adr/index.md": (),
    "docs/thesis/README.md": (),
}


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _workspace_files():
    """Walk owned files deterministically, pruning installed/generated trees.

    This does not use .gitignore, whose user-controlled patterns must not hide
    canonical contracts, evidence or forbidden artifacts from validation.
    """
    def fail_walk(error):
        raise error

    for directory, dirs, files in os.walk(ROOT, onerror=fail_walk, followlinks=False):
        base = Path(directory)
        dirs[:] = sorted(name for name in dirs
                         if rel(base / name) not in SCAN_EXCLUDED_TREES)
        for name in sorted(files):
            path = base / name
            if path.is_file():
                yield path


def _is_contract_data(path: Path) -> bool:
    """Task status and action-field rules do not describe npm or audit receipts.

    These documents still undergo syntax validation. This role assignment is
    path-based; a document_type field cannot exempt a runtime contract.
    """
    relative = rel(path)
    return (_metadata_origin(path) not in FRONTEND_METADATA_FILES
            and relative != ".demo-session.json"
            and not re.fullmatch(r"dashboards/app/handoffs/UI-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}/receipts\.json", relative)
            and not re.fullmatch(r"runtime/gate-hygiene/UI-(?:CHECK|REPAIR)-[0-9a-f]{32}/(?:(?:[a-z-]+\.)?receipt|viewer-process|inspection)\.json", relative)
            and not relative.startswith("reports/"))


def _metadata_origin(path: Path) -> str:
    relative = rel(path)
    match = re.fullmatch(
        r"dashboards/app/handoffs/UI-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}/(?:source|before)/(dashboards/app/frontend/(?:package\.json|package-lock\.json|tsconfig\.json))",
        relative)
    return match[1] if match else relative


def _session_errors(data) -> list[str]:
    fields = {"session_id", "started_at_utc", "status", "backend_pid", "frontend_pid",
              "backend_url", "frontend_url", "gateway_url", "project_root"}
    if not isinstance(data, dict) or set(data) != fields:
        return ["invalid session fields"]
    errors = []
    if data["status"] not in ("INITIALIZING", "READY", "DEGRADED"):
        errors.append("invalid session lifecycle status")
    if not isinstance(data["session_id"], str) or not re.fullmatch(r"DEMO-SES-[0-9a-f]{8}", data["session_id"]):
        errors.append("invalid session identity")
    for key in ("backend_pid", "frontend_pid"):
        if type(data[key]) is not int or not 0 < data[key] <= 2**32 - 1:
            errors.append(f"invalid {key}")
    for key in ("backend_url", "frontend_url", "gateway_url"):
        match = re.fullmatch(r"http://127\.0\.0\.1:([1-9][0-9]{0,4})", data[key]) if isinstance(data[key], str) else None
        if not match or int(match[1]) > 65535:
            errors.append(f"invalid loopback {key}")
    if not isinstance(data["project_root"], str) or Path(data["project_root"]) != ROOT:
        errors.append("session project_root mismatch")
    if not isinstance(data["started_at_utc"], str):
        errors.append("invalid session UTC timestamp")
    else:
        errors.extend(_format_errors(data["started_at_utc"], {"format": "date-time"}, "started_at_utc"))
    return errors


def _strip_json_comments(text: str) -> str:
    """Allow comments in the single frontend tsconfig, preserving strings/lines.

    This is not a relaxed parser for safety files: JSON syntax, finite numbers
    and errors such as unterminated comments remain enforced by json.loads.
    """
    return _JSON_COMMENTS.sub(
        lambda match: match.group(0) if match.group(1) is not None
        else re.sub(r"[^\r\n]", " ", match.group(0)), text)


def load_json(path: Path, errors: list[str]):
    try:
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            fail(errors, f"{rel(path)}: empty file")
            return None
        if _metadata_origin(path) in COMMENT_JSON_FILES:
            text = _strip_json_comments(text)
        data = json.loads(text, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"non-finite constant {value}")))
        if rel(path) == ".demo-session.json":
            errors.extend(f"{rel(path)}: {error}" for error in _session_errors(data))
        return data
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        fail(errors, f"{rel(path)}: invalid JSON-compatible YAML/JSON: {exc}")
        return None


def walk_keys(value, path="$"):
    if isinstance(value, dict):
        for key, item in value.items():
            yield path, key, item
            yield from walk_keys(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from walk_keys(item, f"{path}[{index}]")


def _headings(text: str) -> tuple[str, ...]:
    return tuple(match.group(1).strip() for match in re.finditer(r"^##\s+(.+?)\s*$", text, re.MULTILINE))


def _check_markdown(path: Path, errors: list[str], expected: tuple[str, ...] | None = None) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        fail(errors, f"{rel(path)}: invalid UTF-8: {exc}")
        return
    if not text.strip(): fail(errors, f"{rel(path)}: empty file")
    if not re.search(r"^#\s+\S+", text, re.MULTILINE): fail(errors, f"{rel(path)}: missing H1")
    if expected is not None and _headings(text) != expected:
        fail(errors, f"{rel(path)}: headings do not match source template")


def _exact_dir(errors: list[str], directory: str, expected: set[str], exceptions: set[str] = {"index.md", "README.md"}) -> None:
    path = ROOT / directory
    actual = {item.name for item in path.glob("*.md")} if path.is_dir() else set()
    missing, extra = expected - actual, actual - expected - exceptions
    for name in sorted(missing): fail(errors, f"{directory}: missing required file {name}")
    for name in sorted(extra): fail(errors, f"{directory}: extraneous file {name}")


def validate_scaffold_placeholders(errors: list[str]) -> None:
    for relative in sorted(SCAFFOLD_PLACEHOLDER_DIRS):
        directory = ROOT / relative
        readme = directory / "README.md"
        if not directory.is_dir():
            fail(errors, f"missing required directory: {relative}")
            continue
        if not readme.is_file():
            fail(errors, f"missing SPEC_ONLY placeholder: {relative}/README.md")
            continue
        try:
            text = readme.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            fail(errors, f"invalid placeholder UTF-8: {relative}/README.md: {exc}")
            continue
        if "> Status: SPEC_ONLY" not in text or "No runtime" not in text:
            fail(errors, f"placeholder status boundary missing: {relative}/README.md")


def validate_documents(errors: list[str]) -> None:
    validate_scaffold_placeholders(errors)
    for required in ROOT_FILES | {f"docs/{name}" for name in ("architecture.md", "system-boundaries.md", "threat-model.md", "planning-model.md", "mdp-pomdp-model.md", "safety-model.md", "experiment-design.md", "metrics.md", "ground-truth.md", "references.md", "reproducibility.md", "versions.md")}:
        if not (ROOT / required).is_file(): fail(errors, f"missing required file: {required}")
    _exact_dir(errors, "docs/guides", GUIDES)
    rt_task_specs = {item.name for item in (ROOT / "docs/task-specs").glob("RT-*.md") if RT_SPEC_PATTERN.fullmatch(item.name)}
    _exact_dir(errors, "docs/task-specs", TASK_SPECS | SL_SPECS, exceptions={"index.md", "README.md"} | rt_task_specs)
    _exact_dir(errors, "docs/runbooks", RUNBOOKS)
    adr_dir = ROOT / "docs/adr"
    if not adr_dir.is_dir():
        fail(errors, "missing required directory: docs/adr")
    else:
        for item in sorted(adr_dir.iterdir()):
            if item.name in {"index.md", "README.md"}:
                continue
            if not item.is_file() or not ADR_FILENAME_PATTERN.match(item.name):
                fail(errors, f"docs/adr: malformed ADR filename {item.name}")
    _exact_dir(errors, "docs/thesis/chapters", CHAPTERS)
    _exact_dir(errors, "docs/thesis/appendices", APPENDICES, set())
    heading_sets = {**ROOT_HEADINGS, "docs/guides/index.md": (), "docs/task-specs/index.md": (), "docs/runbooks/index.md": (), "docs/adr/index.md": (), "docs/thesis/README.md": (), "docs/thesis/chapters/09-results.md": ()}
    for relative, headings in heading_sets.items():
        path = ROOT / relative
        if path.is_file(): _check_markdown(path, errors, headings if headings else None)
    for path in (ROOT / "docs/guides").glob("[0-9][0-9]-*.md"):
        _check_markdown(path, errors, GUIDE_HEADINGS)
    for name in sorted(TASK_SPECS | SL_SPECS | rt_task_specs):
        path = ROOT / "docs/task-specs" / name
        if path.is_file():
            _check_markdown(path, errors, TASK_HEADINGS)
    for path in (ROOT / "docs/runbooks").glob("*-*.md"):
        _check_markdown(path, errors, RUNBOOK_HEADINGS)
    for path in (ROOT / "docs/adr").glob("ADR-*.md"):
        _check_markdown(path, errors, ADR_HEADINGS)
    for path in (ROOT / "docs/thesis/chapters").glob("[0-9][0-9]-*.md"):
        _check_markdown(path, errors)
    results = ROOT / "docs/thesis/chapters/09-results.md"
    if results.is_file() and results.read_text(encoding="utf-8") != "# 09 Results\n\nStatus: SPEC_ONLY\n\nNo experimental results are available.\nDo not populate this chapter until experiment evidence exists.\n":
        fail(errors, "docs/thesis/chapters/09-results.md: exact no-results guard mismatch")
    readme = ROOT / "README.md"
    if readme.is_file() and not all(re.search(rf"^##\s+{re.escape(heading)}\s*$", readme.read_text(encoding="utf-8"), re.MULTILINE) for heading in PROMPT_HEADINGS):
        fail(errors, "README.md: master prompt headings incomplete")


def _link_target(raw: str):
    target = raw.strip().strip("<>")
    if "\\" in target or re.match(r"^[A-Za-z]:", target) or target.startswith("/"):
        return "invalid", target
    if target.startswith("#") or not target:
        return "skip", target
    base = target.split("#", 1)[0]
    if re.match(r"^https?://", base, re.IGNORECASE): return "external", base
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", base) or base.startswith("//"):
        return "invalid", base
    return "local", base


def validate_markdown_links(errors: list[str]) -> None:
    pattern = re.compile(r"!?(?:\[[^\]]*\])\(([^)]+)\)")
    for path in _workspace_files():
        if path.suffix.lower() != ".md": continue
        try: text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError): continue
        for raw in pattern.findall(text):
            kind, target = _link_target(raw)
            if kind == "skip": continue
            if kind == "invalid": fail(errors, f"{rel(path)}: invalid Markdown link {target}")
            elif kind == "external":
                if rel(path) != "docs/references.md": fail(errors, f"{rel(path)}: external URL outside docs/references.md")
            else:
                moved = HISTORICAL_SOURCE_LINKS.get((rel(path), target))
                destination = (ROOT / moved if moved else path.parent / target).resolve()
                if not destination.is_relative_to(ROOT) or not destination.exists():
                    fail(errors, f"{rel(path)}: broken or escaping local link {target}")


def _all_data_files():
    return [path for path in _workspace_files() if path.suffix.lower() in {".json", ".yaml", ".yml"}]


def validate_ids_and_status(errors: list[str]) -> None:
    task_ids, adr_ids = [], []
    for path in sorted((ROOT / "docs/task-specs").glob("TASK-*.md")):
        match = re.match(r"^(TASK-[0-9]{3})-", path.stem)
        text = path.read_text(encoding="utf-8")
        heading = re.search(r"^#\s+(TASK-[0-9]{3})\s+—\s+", text, re.MULTILINE)
        if not match or not heading or heading.group(1) != match.group(1): fail(errors, f"{rel(path)}: exact task ID mismatch")
        task_ids.append(match.group(1) if match else path.stem)
        status = re.search(r"`([^`]+)`", text[text.find("## Status"):], re.MULTILINE)
        if not status or status.group(1) not in STATUSES: fail(errors, f"{rel(path)}: invalid status marker")
    if set(task_ids) != {f"TASK-{n:03d}" for n in range(1, 36)} or len(task_ids) != len(set(task_ids)): fail(errors, "task IDs are not exact and unique")
    for name in sorted(SL_SPECS):
        path = ROOT / "docs/task-specs" / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        heading = re.search(r"^#\s+(SL-[0-9]{2})\s+—\s+", text, re.MULTILINE)
        if not heading or heading.group(1) != name[:5]:
            fail(errors, f"{rel(path)}: exact SL ID mismatch")
        section = re.search(r"^## Status\s*$([\s\S]*?)(?=^## |\Z)", text, re.MULTILINE)
        status = re.search(r"`([^`]+)`", section.group(1)) if section else None
        if not status or status.group(1) not in STATUSES:
            fail(errors, f"{rel(path)}: invalid SL status marker")
    adr_ids, numeric_ids = [], []
    for path in sorted((ROOT / "docs/adr").glob("ADR-*.md")):
        match = ADR_FILENAME_PATTERN.match(path.name)
        heading = re.search(r"^#\s+(.*)$", path.read_text(encoding="utf-8"), re.MULTILINE)
        if not match or not heading: fail(errors, f"{rel(path)}: exact ADR ID mismatch")
        if match:
            adr_ids.append(f"ADR-{match.group(1)}")
            numeric_ids.append(int(match.group(1)))
        else:
            adr_ids.append(path.stem)
    seen_ids, duplicate_ids = set(), set()
    for adr_id in adr_ids:
        if adr_id in seen_ids:
            duplicate_ids.add(adr_id)
        seen_ids.add(adr_id)
    if duplicate_ids:
        fail(errors, f"duplicate ADR IDs: {', '.join(sorted(duplicate_ids))}")
    if not numeric_ids:
        fail(errors, "docs/adr: no ADR files found")
    else:
        max_id = max(numeric_ids)
        expected_ids = {f"ADR-{n:03d}" for n in range(1, max_id + 1)}
        missing_ids = expected_ids - set(adr_ids)
        if missing_ids:
            fail(errors, f"missing ADR IDs in sequence: {', '.join(sorted(missing_ids))}")
        unexpected_ids = set(adr_ids) - expected_ids
        if unexpected_ids:
            fail(errors, f"unexpected ADR IDs: {', '.join(sorted(unexpected_ids))}")
    catalog = load_json(ROOT / "actions/catalog/action-catalog.json", errors)
    if isinstance(catalog, dict):
        ids = [item.get("action_id") for item in catalog.get("actions", [])]
        if set(ids) != ACTION_IDS or len(ids) != len(set(ids)): fail(errors, "action catalog IDs are not exact 13-action set")
    for path in _all_data_files():
        data = load_json(path, errors)
        if data is None or not _is_contract_data(path): continue
        for _, key, value in walk_keys(data):
            if key == "status" and isinstance(value, str) and value not in STATUSES and value not in {"COMPLETED", "ERROR", "ok", "reset", "detected", "not_detected", "ready", "not_found"}:
                fail(errors, f"{rel(path)}: invalid status {value!r}")


def _schema_set(errors):
    schemas = {}
    for path in (ROOT / CONTRACT_DIR).glob("*.schema.json"):
        data = load_json(path, errors)
        if isinstance(data, dict):
            name = path.name.removesuffix(".schema.json")
            schemas[name] = data
            if data.get("$schema") != "https://json-schema.org/draft/2020-12/schema" or data.get("type") != "object" or data.get("additionalProperties") is not False:
                fail(errors, f"{rel(path)}: not closed Draft 2020-12 root object")
    gt_path = ROOT / GROUND_TRUTH_SCHEMA_PATH
    if gt_path.is_file():
        gt_data = load_json(gt_path, errors)
        if isinstance(gt_data, dict):
            name = gt_path.name.removesuffix(".schema.json")
            schemas[name] = gt_data
            if gt_data.get("$schema") != "https://json-schema.org/draft/2020-12/schema" or gt_data.get("type") != "object" or gt_data.get("additionalProperties") is not False:
                fail(errors, f"{rel(gt_path)}: not closed Draft 2020-12 root object")
    if set(schemas) != SCHEMA_NAMES: fail(errors, "schema set is not exact 10 schemas")
    return schemas


def _validate_fixture(data, schema, path, errors):
    errors.extend(f"{rel(path)}: {error}" for error in validate_shape(data, schema))


def _check_forbidden(data, path, errors):
    for _, key, _ in walk_keys(data):
        if key.lower() in {"shell_command", "arbitrary_command", "raw_exploit_command", "command", "commands", "payload", "payloads", "shell", "exec", "executable", "script", "dynamic_action", "arbitrary_action"} or (FORBIDDEN_KEY.search(key) and key.lower() not in {"deny_payload_fields", "deny_command_fields"}):
            fail(errors, f"{rel(path)}: forbidden command/payload field {key}")


def safety_contract_errors(
    *,
    policy: dict,
    targets: dict,
    actions: dict,
    budget: dict,
    rate: dict,
    kill: dict,
) -> list[str]:
    """Validate detached safety values so mutation tests exercise real checks."""
    errors: list[str] = []
    if not (policy.get("lab_mode") is True and policy.get("public_targets") is False and policy.get("dry_run") is True and policy.get("external_network") is False):
        errors.append("safety policy defaults unsafe")
    if not (targets.get("deny_public_targets") is True and targets.get("deny_external_hosts") is True and targets.get("allowed_target_ids") and all(TARGET_PATTERN.fullmatch(value) for value in targets["allowed_target_ids"])):
        errors.append("target allowlist unsafe")
    action_classes = actions.get("action_classes", {})
    if not (
        actions.get("deny_unknown_actions") is True
        and actions.get("deny_payload_fields") is True
        and actions.get("deny_command_fields") is True
        and set(actions.get("allowed_action_ids", [])) == ACTION_IDS
        and action_classes == ACTION_CLASSES
    ):
        errors.append("action allowlist unsafe")
    if not (budget.get("max_actions") == 100 and budget.get("max_requests") == 2000 and budget.get("max_rps") == 5 and budget.get("on_exhaustion") in {"ACTION-END-002", "ACTION-END-003"}):
        errors.append("request budget unsafe")
    if not (rate.get("requests_per_second") == 5 and rate.get("burst") == 1):
        errors.append("rate limit unsafe")
    if not (kill.get("enabled") is True and kill.get("halts_new_actions") is True and kill.get("preserve_evidence") is True and kill.get("activation_action_id") == "ACTION-END-003"):
        errors.append("kill switch unsafe")
    return errors


def catalog_consistency_errors(
    action_fixtures: dict[str, dict],
    catalog_entries: dict[str, dict],
    allowed_targets: set[str],
) -> list[str]:
    """Bind each action fixture to filename, catalog class, and target allowlist."""
    errors: list[str] = []
    expected_filenames = {f"{action_id}.json" for action_id in ACTION_IDS}
    missing = expected_filenames - set(action_fixtures)
    extra = set(action_fixtures) - expected_filenames
    errors.extend(f"{filename}: required action fixture missing" for filename in sorted(missing))
    errors.extend(f"{filename}: unexpected action fixture" for filename in sorted(extra))
    for filename, fixture in action_fixtures.items():
        expected_id = filename.removesuffix(".json")
        action_id = fixture.get("action_id")
        if action_id != expected_id:
            errors.append(f"{filename}: action_id does not match filename")
        catalog = catalog_entries.get(str(action_id))
        if catalog is None:
            errors.append(f"{filename}: action_id missing from catalog")
        elif fixture.get("action_class") != catalog.get("action_class"):
            errors.append(f"{filename}: action_class does not match catalog")
        if fixture.get("target_id") not in allowed_targets:
            errors.append(f"{filename}: target_id not allowlisted")
    return errors


def scenario_consistency_errors(
    manifests: list[dict],
    allowed_actions: set[str],
    allowed_targets: set[str],
) -> list[str]:
    """Enforce fair budgets and bounded action/target scope across scenarios."""
    errors: list[str] = []
    budgets = {json.dumps(manifest.get("budgets"), sort_keys=True) for manifest in manifests}
    if len(budgets) > 1:
        errors.append("scenario budgets differ")
    for manifest in manifests:
        scenario_id = manifest.get("scenario_id", "UNKNOWN")
        budget = manifest.get("budgets")
        if not isinstance(budget, dict):
            errors.append(f"{scenario_id}: malformed budget")
        elif any(
            isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
            for value in (budget.get("actions"), budget.get("requests"), budget.get("seconds"))
        ):
            errors.append(f"{scenario_id}: budget must contain finite numbers")
        elif budget.get("actions", 101) > 100 or budget.get("requests", 2001) > 2000 or budget.get("seconds", -1) < 0:
            errors.append(f"{scenario_id}: budget exceeds safety limits")
        if not set(manifest.get("allowed_actions", [])) <= allowed_actions:
            errors.append(f"{scenario_id}: unknown allowed action")
        if not set(manifest.get("target_ids", [])) <= allowed_targets:
            errors.append(f"{scenario_id}: unknown target")
    return errors


def validate_structured_data(errors: list[str]) -> None:
    schemas = _schema_set(errors)
    for path in _all_data_files():
        data = load_json(path, errors)
        if data is None: continue
        if _is_contract_data(path):
            _check_forbidden(data, path, errors)
    action_fixture_names = {f"{action}.json" for action in ACTION_IDS}
    action_fixtures: dict[str, dict] = {}
    for path in sorted((ROOT / "actions/catalog").glob("ACTION-*.json")):
        if path.name == "action-catalog.json":
            continue
        if path.name not in action_fixture_names:
            fail(errors, f"{rel(path)}: action fixture filename not in exact catalog")
        data = load_json(path, errors)
        if not isinstance(data, dict):
            fail(errors, f"{rel(path)}: root must be object")
            continue
        action_fixtures[path.name] = data
        if "action" in schemas:
            _validate_fixture(data, schemas["action"], path, errors)
    catalog_path = ROOT / "actions/catalog/action-catalog.json"
    targets_path = ROOT / "configs/safety/target-allowlist.yaml"
    catalog_data = load_json(catalog_path, errors)
    targets_data = load_json(targets_path, errors)
    if not isinstance(catalog_data, dict):
        fail(errors, f"{rel(catalog_path)}: root must be object")
    if not isinstance(targets_data, dict):
        fail(errors, f"{rel(targets_path)}: root must be object")
    if isinstance(catalog_data, dict) and isinstance(targets_data, dict):
        catalog_entries = {item.get("action_id"): item for item in catalog_data.get("actions", []) if isinstance(item, dict)}
        errors.extend(catalog_consistency_errors(action_fixtures, catalog_entries, set(targets_data.get("allowed_target_ids", []))))
        actions_data_for_classes = load_json(ROOT / "configs/safety/action-allowlist.yaml", errors)
        if isinstance(actions_data_for_classes, dict):
            declared_classes = actions_data_for_classes.get("action_classes", {})
            expected_classes = {action_id: entry.get("action_class") for action_id, entry in catalog_entries.items()}
            if declared_classes != expected_classes:
                fail(errors, "action allowlist classes do not match catalog")
    scenario_manifests: list[dict] = []
    for path in sorted((ROOT / "scenarios/manifests").glob("*.json")):
        data = load_json(path, errors)
        if not isinstance(data, dict):
            fail(errors, f"{rel(path)}: root must be object")
            continue
        scenario_manifests.append(data)
        if "scenario-manifest" in schemas:
            _validate_fixture(data, schemas["scenario-manifest"], path, errors)
        if any(key in {"ground_truth", "truth", "expected_detection"} for _, key, _ in walk_keys(data)):
            fail(errors, f"{rel(path)}: scenario manifest contains truth field")
    actions_path = ROOT / "configs/safety/action-allowlist.yaml"
    actions_data = load_json(actions_path, errors)
    if not isinstance(actions_data, dict):
        fail(errors, f"{rel(actions_path)}: root must be object")
    if isinstance(actions_data, dict) and isinstance(targets_data, dict):
        errors.extend(scenario_consistency_errors(scenario_manifests, set(actions_data.get("allowed_action_ids", [])), set(targets_data.get("allowed_target_ids", []))))
    gt = ROOT / "evaluation/ground-truth/sample.json"
    if gt.is_file() and "ground-truth" in schemas:
        data = load_json(gt, errors)
        if not isinstance(data, dict):
            fail(errors, f"{rel(gt)}: root must be object")
        else:
            _validate_fixture(data, schemas["ground-truth"], gt, errors)
    evidence = ROOT / "evidence"
    evidence_data: dict[str, dict] = {}
    for path in sorted(evidence.glob("*.json")):
        data = load_json(path, errors)
        if not isinstance(data, dict):
            fail(errors, f"{rel(path)}: root must be object")
            continue
        evidence_data[path.name] = data
        if "evidence_id" in data and "evidence" in schemas:
            _validate_fixture(data, schemas["evidence"], path, errors)
    manifest_data = evidence_data.get("manifest.json")
    if manifest_data is not None:
        if not {"evidence_schema", "retention", "append_only", "traceable", "status"} <= set(manifest_data):
            fail(errors, "evidence/manifest.json: missing traceability fields")
        elif not (
            manifest_data.get("evidence_schema") == "agent/planner/contracts/evidence.schema.json"
            and manifest_data.get("retention") == "append_only"
            and manifest_data.get("append_only") is True
            and manifest_data.get("traceable") is True
        ):
            fail(errors, "evidence/manifest.json: unsafe retention or traceability")


def _runtime_string_is_public(value: str) -> bool:
    text = value.strip()
    if text.startswith(("//", "\\\\")) or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", text):
        return True
    host = re.split(r"[/#?]", text, maxsplit=1)[0]
    if host.startswith("[") and "]" in host:
        host, suffix = host[1:].split("]", 1)
        if suffix and not re.fullmatch(r":\d{1,5}", suffix):
            return False
    elif host.count(":") == 1 and re.fullmatch(r".+:\d{1,5}", host):
        host = host.rsplit(":", 1)[0]
    host = host.rstrip(".")
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    # Paths and identifiers may contain dots; classify only raw DNS endpoints as a whole.
    return bool(re.fullmatch(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", host, re.IGNORECASE))


def validate_safety(errors: list[str]) -> None:
    expected_env = "# Safe lab defaults\nLAB_MODE=true\nPUBLIC_TARGETS=false\nDRY_RUN=true\nALLOW_ARBITRARY_SHELL=false\nALLOW_DYNAMIC_ACTIONS=false\nMAX_ACTIONS=100\nMAX_REQUESTS=2000\nMAX_RPS=5\nEVIDENCE_APPEND_ONLY=true\n"
    env = ROOT / ".env.example"
    if env.is_file():
        try:
            if env.read_text(encoding="utf-8") != expected_env: fail(errors, ".env.example: defaults differ from exact safe defaults")
        except (OSError, UnicodeError): fail(errors, ".env.example: invalid UTF-8")
    safety_paths = {
        "policy": ROOT / "configs/safety/lab-policy.yaml",
        "targets": ROOT / "configs/safety/target-allowlist.yaml",
        "actions": ROOT / "configs/safety/action-allowlist.yaml",
        "budget": ROOT / "configs/safety/request-budget.yaml",
        "rate": ROOT / "configs/safety/rate-limit.yaml",
        "kill": ROOT / "configs/safety/kill-switch.yaml",
    }
    safety_values = {name: load_json(path, errors) for name, path in safety_paths.items()}
    malformed = False
    for name, value in safety_values.items():
        if not isinstance(value, dict):
            fail(errors, f"{rel(safety_paths[name])}: root must be object")
            malformed = True
    if not malformed:
        errors.extend(safety_contract_errors(**safety_values))
    policy_path = ROOT / "evidence/policy.json"
    policy_data = load_json(policy_path, errors)
    if not isinstance(policy_data, dict):
        fail(errors, f"{rel(policy_path)}: root must be object")
    elif not (
        policy_data.get("append_only") is True
        and policy_data.get("traceable") is True
        and policy_data.get("redaction_required") is True
        and policy_data.get("record_schema") == "agent/planner/contracts/evidence.schema.json"
    ):
        fail(errors, "evidence policy unsafe")
    link_path = ROOT / "evaluation/ground-truth/schema-link.json"
    link = load_json(link_path, errors)
    if not isinstance(link, dict):
        fail(errors, f"{rel(link_path)}: root must be object")
    elif link.get("runtime_consumers"):
        fail(errors, "ground truth has runtime consumers")
    elif link.get("ground_truth_schema") != GROUND_TRUTH_SCHEMA_PATH:
        fail(errors, "schema-link does not point to canonical ground-truth schema")
    runtime_roots = (ROOT / "configs/agent", ROOT / "configs/llm", ROOT / "configs/rl", ROOT / "actions", ROOT / "agent")
    forbidden_truth = re.compile(r"ground[_-]?truth|expected[_-]?detection|\btruth\b", re.IGNORECASE)
    for directory in runtime_roots:
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".json", ".yaml", ".yml"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            if forbidden_truth.search(text):
                fail(errors, f"{rel(path)}: runtime ground-truth reference")
    for path in (ROOT / "scenarios/manifests").glob("*.json"):
        data = load_json(path, errors)
        if data is not None and any(key in {"ground_truth", "truth", "expected_detection"} for _, key, _ in walk_keys(data)): fail(errors, f"{rel(path)}: truth isolation failure")
    for path in _all_data_files():
        if not (rel(path).startswith("configs/") or rel(path).startswith("actions/") or rel(path).startswith("agent/") or rel(path).startswith("scenarios/")): continue
        data = load_json(path, errors)
        if data is None: continue
        for key_path, key, value in walk_keys(data):
            if isinstance(value, str) and key not in {"$schema", "$id"} and _runtime_string_is_public(value): fail(errors, f"{rel(path)}{key_path}: public URL/IP/hostname in runtime config")


def validate_dependencies(errors: list[str]) -> None:
    tasks_file = ROOT / "TASKS.md"
    if not tasks_file.is_file(): return
    text = tasks_file.read_text(encoding="utf-8")
    tasks_text = text
    rows = re.findall(r"^\|\s*(TASK-\d{3})\s*\|[^|\n]*\|[^|\n]*\|\s*([^|\n]+?)\s*\|\s*$", text, re.MULTILINE)
    ids = [task for task, _ in rows]
    expected = {f"TASK-{n:03d}" for n in range(1, 36)}
    if set(ids) != expected or len(ids) != len(set(ids)): fail(errors, "TASKS.md dependency IDs incomplete or duplicated")
    for task, deps in rows:
        if deps.strip().lower() in {"none", "all-required"}: continue
        for dep in re.findall(r"TASK-\d{3}", deps):
            if dep == task or dep not in expected or int(dep[-3:]) >= int(task[-3:]): fail(errors, f"invalid dependency {task} -> {dep}")
    for path in (ROOT / "docs/task-specs").glob("TASK-*.md"):
        text = path.read_text(encoding="utf-8")
        task_match = re.match(r"TASK-(\d{3})-", path.stem)
        section = re.search(r"^## Dependencies\s*$([\s\S]*?)(?=^## |\Z)", text, re.MULTILINE)
        if not task_match or not section: continue
        for dep in re.findall(r"TASK-(\d{3})", section.group(1)):
            if dep == task_match.group(1) or int(dep) >= int(task_match.group(1)): fail(errors, f"invalid dependency in {rel(path)}: TASK-{dep}")
    sl_expected = {f"SL-{n:02d}" for n in range(1, 13)}
    sl_names = {name[:5]: name for name in SL_SPECS}
    sl_rows = re.findall(
        r"^\|\s*\[(SL-\d{2})\]\(([^)\n]+)\)\s*\|([^|\n]*)\|[^|\n]*\|([^|\n]*)\|[^|\n]*\|\s*$",
        tasks_text, re.MULTILINE,
    )
    sl_ids = [task for task, _, _, _ in sl_rows]
    if set(sl_ids) != sl_expected or len(sl_ids) != len(set(sl_ids)):
        fail(errors, "TASKS.md SL dependency IDs incomplete or duplicated")

    def check_sl(task: str, deps: str, source: str) -> None:
        for dep in re.findall(r"SL-\d+", deps):
            if dep not in sl_expected or int(dep[3:]) >= int(task[3:]):
                fail(errors, f"invalid SL dependency {task} -> {dep} in {source}")
        for dep in re.findall(r"TASK-\d+", deps):
            if dep not in expected:
                fail(errors, f"invalid canonical reference {task} -> {dep} in {source}")
        for dep, link in re.findall(r"\[(SL-\d+)\]\(([^)]+)\)", deps):
            if dep not in sl_names or Path(link).name != sl_names[dep]:
                fail(errors, f"invalid SL dependency link in {source}: {dep}")

    for task, link, foundations, deps in sl_rows:
        if task not in sl_names or link != f"docs/task-specs/{sl_names[task]}":
            fail(errors, f"invalid SL spec link in TASKS.md: {task}")
        check_sl(task, foundations + " " + deps, "TASKS.md")
    for name in sorted(SL_SPECS):
        path = ROOT / "docs/task-specs" / name
        if not path.is_file():
            continue
        spec_text = path.read_text(encoding="utf-8")
        section = re.search(r"^## Dependencies\s*$([\s\S]*?)(?=^## |\Z)", spec_text, re.MULTILINE)
        if section is None:
            fail(errors, f"missing Dependencies section in {rel(path)}")
        else:
            # Danh sách khai báo ở đầu mục; phần giải thích sau dấu chấm không tạo cạnh.
            declaration = section.group(1).strip().split(". ", 1)[0]
            declaration = declaration.split(".\n", 1)[0]
            check_sl(name[:5], declaration, rel(path))


def validate_experiment_identity(errors: list[str]) -> None:
    scenario_ids = set()
    for path in (ROOT / "scenarios/manifests").glob("*.json"):
        data = load_json(path, errors)
        if isinstance(data, dict) and SCENARIO_PATTERN.fullmatch(str(data.get("scenario_id", ""))):
            scenario_ids.add(data["scenario_id"])
    schema = load_json(ROOT / CONTRACT_DIR / "experiment-manifest.schema.json", errors)
    seen = set()
    for path in (ROOT / "configs/experiments").glob("*.yaml"):
        data = load_json(path, errors)
        if not isinstance(data, dict):
            fail(errors, f"{rel(path)}: root must be object")
            continue
        experiment_id = data.get("experiment_id")
        if not isinstance(experiment_id, str) or not re.fullmatch(r"EXP-[0-9]{4}", experiment_id) or experiment_id in seen:
            fail(errors, f"{rel(path)}: experiment identity invalid or duplicated")
        seen.add(experiment_id)
        if isinstance(schema, dict):
            errors.extend(f"{rel(path)}: {error}" for error in validate_shape(data, schema))
        if not set(data.get("scenario_ids", [])) <= scenario_ids:
            fail(errors, f"{rel(path)}: unknown scenario ID")


def validate_ast_and_artifacts(errors: list[str]) -> None:
    for path in _workspace_files():
        if any(part in FORBIDDEN_ARTIFACTS for part in path.parts) or path.suffix.lower() in {".exe", ".dll", ".so", ".bin", ".pyc", ".pyo"}:
            fail(errors, f"forbidden artifact {rel(path)}")
        if path.suffix == ".py":
            try: ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (OSError, UnicodeError, SyntaxError) as exc: fail(errors, f"Python AST failure {rel(path)}: {exc}")


def validate() -> list[str]:
    errors: list[str] = []
    validate_documents(errors)
    validate_markdown_links(errors)
    validate_ids_and_status(errors)
    validate_structured_data(errors)
    validate_safety(errors)
    validate_dependencies(errors)
    validate_experiment_identity(errors)
    validate_ast_and_artifacts(errors)
    return sorted(set(errors))


def main() -> int:
    errors = validate()
    if errors:
        print("SCAFFOLD INVALID")
        for error in errors: print(f"- {error}")
        return 1
    file_count = sum(1 for path in _workspace_files() if not any(part in FORBIDDEN_ARTIFACTS for part in path.parts))
    action_count = len([path for path in (ROOT / "actions/catalog").glob("ACTION-*.json") if path.name != "action-catalog.json"])
    task_count = len(list((ROOT / "docs/task-specs").glob("TASK-*.md")))
    adr_count = len(list((ROOT / "docs/adr").glob("ADR-*.md")))
    print("SCAFFOLD VALID")
    print(f"files_checked={file_count}")
    print(f"schemas_checked={len(SCHEMA_NAMES)} actions_checked={action_count} tasks_checked={task_count} adrs_checked={adr_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
