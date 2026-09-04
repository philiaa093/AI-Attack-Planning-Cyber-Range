"""Deterministic, offline validation for project contracts and documentation."""
from __future__ import annotations

import ast
import datetime as dt
import ipaddress
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATUSES = {"SPEC_ONLY", "TBD", "UNRESOLVED", "IMPLEMENTED", "VALIDATED", "DEFERRED", "BLOCKED"}
ACTION_IDS = {f"ACTION-{group}-{number:03d}" for group, numbers in {
    "RECON": (1, 2), "SCAN": (1, 2), "WEB": (1, 2, 3), "PLAN": (1, 2, 3), "END": (1, 2, 3)
}.items() for number in numbers}
ACTION_CLASSES = {
    **{f"ACTION-RECON-{number:03d}": "RECON" for number in (1, 2)},
    **{f"ACTION-SCAN-{number:03d}": "SCAN" for number in (1, 2)},
    **{f"ACTION-WEB-{number:03d}": "WEB_TEST" for number in (1, 2, 3)},
    **{f"ACTION-PLAN-{number:03d}": "PLAN" for number in (1, 2, 3)},
    **{f"ACTION-END-{number:03d}": "STOP" for number in (1, 2, 3)},
}
TARGET_PATTERN = re.compile(r"^lab-[a-z0-9-]+$")
SCENARIO_PATTERN = re.compile(r"^SCN-[0-9]{3}$")
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
RUNBOOKS = {
    "start-cyber-range.md", "stop-cyber-range.md", "validate-isolation.md", "run-rule-planner.md",
    "run-llm-planner.md", "train-agent.md", "run-hybrid-planner.md", "run-experiment.md",
    "collect-evidence.md", "restore-range.md",
}
ADRS = {
    "ADR-001-planner-centered-scope.md", "ADR-002-web-only-cyber-range-mvp.md", "ADR-003-three-vulnerability-families.md",
    "ADR-004-bounded-action-catalog.md", "ADR-005-planner-executor-perception-separation.md", "ADR-006-shared-planner-interface.md",
    "ADR-007-simulator-before-cyber-range-rl.md", "ADR-008-held-out-scenarios.md", "ADR-009-ground-truth-isolation.md",
    "ADR-010-evidence-immutability.md", "ADR-011-same-budgets-across-planners.md", "ADR-012-safety-engine-control.md",
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
    "scenarios/README.md", "report/README.md", "docs/guides/index.md", "docs/task-specs/index.md", "docs/runbooks/index.md", "docs/adr/index.md",
}
CONTRACT_DIR = "agent/planner/contracts"
SAFETY_FILES = {
    "configs/safety/lab-policy.yaml", "configs/safety/target-allowlist.yaml", "configs/safety/action-allowlist.yaml",
    "configs/safety/request-budget.yaml", "configs/safety/rate-limit.yaml", "configs/safety/kill-switch.yaml",
}
SCAFFOLD_PLACEHOLDER_DIRS = {
    "configs/tools/zap", "configs/tools/nuclei", "configs/tools/discovery",
    "cyber-range/network", "cyber-range/targets/juice-shop", "cyber-range/targets/custom-webapp-a",
    "cyber-range/targets/custom-webapp-b", "cyber-range/targets/clean-control", "cyber-range/snapshots", "cyber-range/reset",
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
    "TASKS.md": ("Blockers",),
    "docs/guides/index.md": (), "docs/task-specs/index.md": (), "docs/runbooks/index.md": (), "docs/adr/index.md": (),
    "report/README.md": (),
}


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load_json(path: Path, errors: list[str]):
    try:
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            fail(errors, f"{rel(path)}: empty file")
            return None
        return json.loads(text, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"non-finite constant {value}")))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        fail(errors, f"{rel(path)}: invalid JSON-compatible YAML/JSON: {exc}")
        return None


def _actual_type(value) -> str:
    if value is None: return "null"
    if isinstance(value, bool): return "boolean"
    if isinstance(value, int): return "integer"
    if isinstance(value, float): return "number"
    if isinstance(value, str): return "string"
    if isinstance(value, list): return "array"
    return "object"


def _format_errors(value, schema, path):
    fmt = schema.get("format")
    if fmt != "date-time" or not isinstance(value, str):
        return []
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return [f"{path}: invalid date-time"]
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        return [f"{path}: date-time must be UTC"]
    return []


def _resolve_ref(schema, root):
    ref = schema.get("$ref") if isinstance(schema, dict) else None
    if not ref or not ref.startswith("#/"):
        return schema
    value = root
    for part in ref[2:].split("/"):
        value = value[part]
    return value


def validate_shape(value, schema, path="$", _root=None) -> list[str]:
    """Validate supported JSON Schema keywords without imports or network access."""
    if not isinstance(schema, dict):
        return []
    _root = schema if _root is None else _root
    schema = _resolve_ref(schema, _root)
    errors: list[str] = []
    for branch_key in ("oneOf", "anyOf"):
        if branch_key in schema:
            results = [validate_shape(value, branch, path, _root) for branch in schema[branch_key]]
            valid = [result for result in results if not result]
            if branch_key == "oneOf" and len(valid) != 1:
                errors.append(f"{path}: oneOf mismatch")
            elif branch_key == "anyOf" and not valid:
                errors.append(f"{path}: anyOf mismatch")
            return errors
    expected = schema.get("type")
    types = expected if isinstance(expected, list) else [expected]
    if expected is not None:
        actual = _actual_type(value)
        if actual not in types and not (actual == "integer" and "number" in types):
            return [f"{path}: expected {types}, got {actual}"]
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: enum mismatch")
    errors.extend(_format_errors(value, schema, path))
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        missing = set(schema.get("required", [])) - set(value)
        errors.extend(f"{path}: missing required {key}" for key in sorted(missing))
        if schema.get("additionalProperties") is False:
            errors.extend(f"{path}: unknown property {key}" for key in sorted(set(value) - set(properties)))
        for key, subschema in properties.items():
            if key in value:
                errors.extend(validate_shape(value[key], subschema, f"{path}.{key}", _root))
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]: errors.append(f"{path}: fewer than minItems")
        if "maxItems" in schema and len(value) > schema["maxItems"]: errors.append(f"{path}: more than maxItems")
        if schema.get("uniqueItems") and len({json.dumps(item, sort_keys=True) for item in value}) != len(value): errors.append(f"{path}: duplicate items")
        for index, item in enumerate(value):
            errors.extend(validate_shape(item, schema.get("items", {}), f"{path}[{index}]", _root))
    if isinstance(value, str):
        if "pattern" in schema and not re.fullmatch(schema["pattern"], value): errors.append(f"{path}: pattern mismatch")
        if "minLength" in schema and len(value) < schema["minLength"]: errors.append(f"{path}: shorter than minLength")
        if "maxLength" in schema and len(value) > schema["maxLength"]: errors.append(f"{path}: longer than maxLength")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value):
            errors.append(f"{path}: number must be finite")
        elif "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: below minimum")
        elif "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: above maximum")
    return errors


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
    _exact_dir(errors, "docs/task-specs", TASK_SPECS)
    _exact_dir(errors, "docs/runbooks", RUNBOOKS)
    _exact_dir(errors, "docs/adr", ADRS)
    _exact_dir(errors, "report/chapters", CHAPTERS)
    _exact_dir(errors, "report/appendices", APPENDICES, set())
    heading_sets = {**ROOT_HEADINGS, "docs/guides/index.md": (), "docs/task-specs/index.md": (), "docs/runbooks/index.md": (), "docs/adr/index.md": (), "report/README.md": (), "report/chapters/09-results.md": ()}
    for relative, headings in heading_sets.items():
        path = ROOT / relative
        if path.is_file(): _check_markdown(path, errors, headings if headings else None)
    for path in (ROOT / "docs/guides").glob("[0-9][0-9]-*.md"):
        _check_markdown(path, errors, GUIDE_HEADINGS)
    for path in (ROOT / "docs/task-specs").glob("TASK-*.md"):
        _check_markdown(path, errors, TASK_HEADINGS)
    for path in (ROOT / "docs/runbooks").glob("*-*.md"):
        _check_markdown(path, errors, RUNBOOK_HEADINGS)
    for path in (ROOT / "docs/adr").glob("ADR-*.md"):
        _check_markdown(path, errors, ADR_HEADINGS)
    for path in (ROOT / "report/chapters").glob("[0-9][0-9]-*.md"):
        _check_markdown(path, errors)
    results = ROOT / "report/chapters/09-results.md"
    if results.is_file() and results.read_text(encoding="utf-8") != "# 09 Results\n\nStatus: SPEC_ONLY\n\nNo experimental results are available.\nDo not populate this chapter until experiment evidence exists.\n":
        fail(errors, "report/chapters/09-results.md: exact no-results guard mismatch")
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
    for path in ROOT.rglob("*.md"):
        try: text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError): continue
        for raw in pattern.findall(text):
            kind, target = _link_target(raw)
            if kind == "skip": continue
            if kind == "invalid": fail(errors, f"{rel(path)}: invalid Markdown link {target}")
            elif kind == "external":
                if rel(path) != "docs/references.md": fail(errors, f"{rel(path)}: external URL outside docs/references.md")
            elif not (path.parent / target).resolve().is_relative_to(ROOT) or not (path.parent / target).resolve().exists():
                fail(errors, f"{rel(path)}: broken or escaping local link {target}")


def _all_data_files():
    return [path for path in ROOT.rglob("*") if path.is_file() and path.suffix.lower() in {".json", ".yaml", ".yml"}]


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
    for path in sorted((ROOT / "docs/adr").glob("ADR-*.md")):
        match = re.match(r"^(ADR-[0-9]{3})-", path.stem)
        heading = re.search(r"^#\s+(.*)$", path.read_text(encoding="utf-8"), re.MULTILINE)
        if not match or not heading: fail(errors, f"{rel(path)}: exact ADR ID mismatch")
        adr_ids.append(match.group(1) if match else path.stem)
    if set(adr_ids) != {f"ADR-{n:03d}" for n in range(1, 13)} or len(adr_ids) != len(set(adr_ids)): fail(errors, "ADR IDs are not exact and unique")
    catalog = load_json(ROOT / "actions/catalog/action-catalog.json", errors)
    if isinstance(catalog, dict):
        ids = [item.get("action_id") for item in catalog.get("actions", [])]
        if set(ids) != ACTION_IDS or len(ids) != len(set(ids)): fail(errors, "action catalog IDs are not exact 13-action set")
    for path in _all_data_files():
        data = load_json(path, errors)
        if data is None: continue
        for _, key, value in walk_keys(data):
            if key == "status" and isinstance(value, str) and value not in STATUSES and value not in {"COMPLETED", "ERROR"}:
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
    runtime_roots = (ROOT / "configs/agent", ROOT / "configs/llm", ROOT / "configs/rl", ROOT / "actions", ROOT / "agent")
    forbidden_truth = re.compile(r"ground[_-]?truth|expected[_-]?detection|\btruth\b", re.IGNORECASE)
    for directory in runtime_roots:
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".json", ".yaml", ".yml"} or path.name == "ground-truth.schema.json":
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
    rows = re.findall(r"\|\s*(TASK-\d{3})\s*\|.*?\|\s*([^|]+?)\s*\|", text)
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
    for path in ROOT.rglob("*"):
        if not path.is_file(): continue
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
    file_count = sum(1 for path in ROOT.rglob("*") if path.is_file() and not any(part in FORBIDDEN_ARTIFACTS for part in path.parts))
    action_count = len([path for path in (ROOT / "actions/catalog").glob("ACTION-*.json") if path.name != "action-catalog.json"])
    task_count = len(list((ROOT / "docs/task-specs").glob("TASK-*.md")))
    adr_count = len(list((ROOT / "docs/adr").glob("ADR-*.md")))
    print("SCAFFOLD VALID")
    print(f"files_checked={file_count}")
    print(f"schemas_checked={len(SCHEMA_NAMES)} actions_checked={action_count} tasks_checked={task_count} adrs_checked={adr_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
