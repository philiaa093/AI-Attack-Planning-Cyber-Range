"""Minimized, deterministic web-surface projection for LLM planning.

The projection is derived only from normalized observations already present in
planner state. It never reads live target responses, evidence artifacts,
provider output, or hidden scenario metadata.

Design rules:
  - Observed methods and provenance stay distinct: an observed POST form input is
    not silently converted into an executable GET parameter.
  - Bounded lists always report totals and an explicit ``truncated`` flag; the
    caller can then refuse to treat an incomplete projection as success.
  - Action semantics are run-approved catalog metadata, not planner invention.
"""
from __future__ import annotations

import urllib.parse
from typing import Any

TEST_ACTIONS = frozenset({
    "ACTION-WEB-001", "ACTION-WEB-002", "ACTION-WEB-003", "ACTION-LOGIC-001",
})
SCAN_ACTIONS = frozenset({"ACTION-SCAN-001", "ACTION-SCAN-002"})

_CONTROL_PARTS = ("csrf", "token", "session", "secret", "password", "passwd", "credential")
_PATH_PARTS = ("file", "path", "template", "document", "download", "folder", "dir", "include")
_LOGIC_PARTS = ("cart", "checkout", "order", "payment", "quantity", "price", "total", "coupon", "idempot")

ACTION_SEMANTICS = {
    "ACTION-RECON-001": "Discover the authorized target's initial reachability without route assumptions.",
    "ACTION-RECON-002": "Crawl links and forms from live lab responses; no invented routes.",
    "ACTION-SCAN-001": "Passive inventory analysis of observed metadata; zero network requests; records GET and POST/form inputs.",
    "ACTION-SCAN-002": "Run isolated ZAP/Nuclei active scanners over observed GET scope; results are unconfirmed candidates, never proof.",
    "ACTION-WEB-001": "Bounded SQL injection (SQLi) class check: differential quote-balance probes against one observed GET input; requires resource_ref and parameter_name.",
    "ACTION-WEB-002": "Bounded cross-site scripting (XSS) class check: inert marker reflection probes against one observed GET input; requires resource_ref and parameter_name.",
    "ACTION-WEB-003": "Bounded path-traversal class check on an observed file/path-like GET input; requires resource_ref and parameter_name.",
    "ACTION-LOGIC-001": "Bounded business-logic check on an observed cart/checkout/order/quantity/idempotency input; requires resource_ref and parameter_name.",
    "ACTION-PLAN-001": "Change to another already-authorized observed target.",
    "ACTION-PLAN-002": "Change the current hypothesis using observed evidence only.",
    "ACTION-PLAN-003": "Revisit existing evidence without inventing new surface.",
    "ACTION-END-001": "Stop only when observed checks support the objective; the runtime independently validates coverage.",
    "ACTION-END-002": "Stop because the run budget is exhausted.",
    "ACTION-END-003": "Stop because no approved action can make progress or unresolved coverage remains.",
}

_ACCEPTED_METHODS = {
    "ACTION-WEB-001": ["GET"],
    "ACTION-WEB-002": ["GET"],
    "ACTION-WEB-003": ["GET"],
    "ACTION-LOGIC-001": ["GET"],
}

_DEFAULT_LIMIT = 32
_RESOURCE_LIMIT = 512
_TEXT_LIMIT = 128
_POST_FORM_PREFIX = "post_form_input_"
_POST_PARAMETER_LIMIT = 200 - len(_POST_FORM_PREFIX)


def _canonical_resource(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urllib.parse.urlsplit(text)
    if parsed.scheme or parsed.netloc:
        text = parsed.path or "/"
    text = text.split("#", 1)[0].split("?", 1)[0]
    return text or "/"


def _is_control_field(name: str) -> bool:
    lower = name.lower()
    return any(part in lower for part in _CONTROL_PARTS)


def is_path_like(resource: str, parameter: str) -> bool:
    return isinstance(parameter, str) and any(part in parameter.lower() for part in _PATH_PARTS)


def candidate_key(proposal: dict[str, Any]) -> tuple[str, str, str, str, str]:
    """Scheduling identity only; authorization still belongs to the gate."""
    return (str(proposal.get("target_id", "")), str(proposal.get("action_id", "")),
            str(proposal.get("method", "GET")).upper(),
            _canonical_resource(proposal.get("resource_ref")),
            str(proposal.get("parameter_name", "")))


def candidate_blocker(proposal: dict[str, Any], attempts: list[dict[str, Any]]) -> str | None:
    if proposal.get("action_id") not in TEST_ACTIONS:
        return None
    if proposal.get("action_id") == "ACTION-WEB-003" and not is_path_like(
            str(proposal.get("resource_ref", "")), proposal.get("parameter_name")):
        return "PATH_INPUT_NOT_OBSERVED"
    key = candidate_key(proposal)
    row = next((row for row in attempts if candidate_key(row) == key), None)
    if row and row.get("attempts", 0) >= 3:
        return "CANDIDATE_ATTEMPTS_EXHAUSTED"
    return None


def has_unresolved_outcomes(state: dict[str, Any], facts: list[dict[str, Any]]) -> bool:
    latest = {}
    for fact in facts:
        if fact.get("fact_type") == "ACTION_OUTCOME":
            action, _, tail = str(fact.get("subject", "")).partition(":")
            resource, _, param = tail.rpartition(":")
            if action in TEST_ACTIONS and resource and param:
                latest[(action, _canonical_resource(resource), param)] = fact.get("value")
    for row in state.get("candidate_attempts", []):
        latest[(row["action_id"], row["resource_ref"], row["parameter_name"])] = row["result"]
    return any(value == "INCONCLUSIVE" for value in latest.values())


def _is_logic_like(resource: str, parameter: str) -> bool:
    text = (resource + " " + parameter).lower()
    return any(part in text for part in _LOGIC_PARTS)


def _eligible_actions(resource: str, parameter: str, effective_actions: set[str]) -> list[str]:
    eligible: list[str] = []
    if "ACTION-WEB-001" in effective_actions:
        eligible.append("ACTION-WEB-001")
    if "ACTION-WEB-002" in effective_actions:
        eligible.append("ACTION-WEB-002")
    if "ACTION-WEB-003" in effective_actions and is_path_like(resource, parameter):
        eligible.append("ACTION-WEB-003")
    if "ACTION-LOGIC-001" in effective_actions and _is_logic_like(resource, parameter):
        eligible.append("ACTION-LOGIC-001")
    return eligible


def _dedupe(records: list[dict[str, Any]], key) -> list[dict[str, Any]]:
    seen: set[Any] = set()
    result: list[dict[str, Any]] = []
    for record in records:
        identity = key(record)
        if identity in seen:
            continue
        seen.add(identity)
        result.append(record)
    return result


def _action_metadata(effective_actions: set[str]) -> list[dict[str, Any]]:
    from agent.planner.action_catalog import ACTION_CATALOG

    rows: list[dict[str, Any]] = []
    for action_id in sorted(effective_actions):
        catalog = ACTION_CATALOG.get(action_id, {"name": "TEST_BUSINESS_LOGIC", "class": "WEB_TEST"})
        rows.append({
            "action_id": action_id,
            "name": catalog["name"],
            "class": catalog["class"],
            "semantics": ACTION_SEMANTICS.get(action_id, "Bounded run-approved action."),
            "accepted_methods": _ACCEPTED_METHODS.get(action_id, []),
        })
    return rows


def build_web_planning_context(
    state: dict[str, Any],
    endpoints: list[str],
    facts: list[dict[str, Any]],
    previous: list[str],
    effective_actions: set[str],
    limit: int = _DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Return a bounded projection of observed web surface and check coverage."""
    endpoint_sources: dict[str, set[str]] = {}

    def add_endpoint(value: Any, source: str) -> None:
        resource = _canonical_resource(value)
        if resource:
            endpoint_sources.setdefault(resource, set()).add(source)

    for endpoint in endpoints:
        add_endpoint(endpoint, "ENDPOINT")
    for fact in facts:
        fact_type = fact.get("fact_type")
        if fact_type == "ENDPOINT":
            add_endpoint(fact.get("value") or fact.get("subject"), "ENDPOINT")
        elif fact_type == "PARAMETER":
            add_endpoint(fact.get("subject"), "PARAMETER")

    get_inputs: list[dict[str, Any]] = []
    for fact in facts:
        if fact.get("fact_type") != "PARAMETER":
            continue
        resource = _canonical_resource(fact.get("subject"))
        parameter = str(fact.get("value") or "")
        if not resource or not parameter or _is_control_field(parameter):
            continue
        get_inputs.append({
            "resource_ref": resource,
            "parameter_name": parameter,
            "method": "GET",
            "source_observation_id": str(fact.get("source_observation_id") or ""),
        })

    post_inputs: list[dict[str, Any]] = []
    for fact in facts:
        value = str(fact.get("value") or "")
        if fact.get("fact_type") != "CANDIDATE_FINDING" or not value.startswith(_POST_FORM_PREFIX):
            continue
        resource = _canonical_resource(fact.get("subject"))
        parameter = value[len(_POST_FORM_PREFIX):]
        if not resource or not parameter or _is_control_field(parameter):
            continue
        post_inputs.append({
            "resource_ref": resource,
            "parameter_name": parameter,
            "method": "POST",
            "source_observation_id": str(fact.get("source_observation_id") or ""),
        })

    get_inputs = _dedupe(get_inputs, lambda row: (row["resource_ref"], row["parameter_name"]))
    post_inputs = _dedupe(post_inputs, lambda row: (row["resource_ref"], row["parameter_name"]))

    refused_actions: set[str] = set(str(value) for value in state.get("refused_actions", []))

    checks: list[dict[str, Any]] = []
    latest_results: dict[tuple[str, str, str], str] = {}
    scans: list[dict[str, Any]] = []
    for fact in facts:
        fact_type = fact.get("fact_type")
        if fact_type in ("REFUSAL", "DENIAL", "ACTION_REFUSED") or (
                fact_type == "ACTION_OUTCOME" and str(fact.get("value")) in ("REFUSED", "DENIED")):
            action_ref = (fact.get("subject") if fact_type == "ACTION_OUTCOME"
                          else (fact.get("value") or fact.get("action_id")))
            if action_ref:
                refused_actions.add(str(action_ref))
        if fact_type != "ACTION_OUTCOME":
            continue
        subject = str(fact.get("subject", ""))
        action, separator, remainder = subject.partition(":")
        if not separator:
            continue
        if action in TEST_ACTIONS:
            resource_raw, param_separator, parameter = remainder.rpartition(":")
            if not param_separator or not resource_raw or not parameter:
                continue
            check = {
                "action": action,
                "resource_ref": _canonical_resource(resource_raw),
                "parameter_name": parameter,
                "result": str(fact.get("value") or ""),
            }
            checks.append(check)
            latest_results[(action, check["resource_ref"], check["parameter_name"])] = check["result"]
        elif action in SCAN_ACTIONS:
            tool, tool_separator, field = remainder.partition(":")
            match = next((row for row in scans if row["action"] == action and row["tool"] == tool), None)
            if match is None:
                match = {"action": action, "tool": tool, "status": None, "coverage": None,
                         "unrequested_seeds": None}
                scans.append(match)
            value = fact.get("value")
            if not tool_separator:
                match["status"] = value if isinstance(value, str) else None
            elif field == "coverage":
                match["coverage"] = value if value in ("BOUNDED", "PARTIAL", "INCOMPLETE") else None
            elif field == "unrequested_seeds":
                match["unrequested_seeds"] = value if type(value) is int and value >= 0 else None

    attempt_rows = [{**row, "retry_block_reason": candidate_blocker(row, state.get("candidate_attempts", []))}
                    for row in state.get("candidate_attempts", [])]
    for row in attempt_rows:
        latest_results[(row["action_id"], row["resource_ref"], row["parameter_name"])] = row["result"]

    checks = _dedupe(checks, lambda row: (row["action"], row["resource_ref"],
                                           row["parameter_name"], row["result"]))
    checks.sort(key=lambda row: (row["resource_ref"], row["parameter_name"],
                                 row["action"], row["result"]))
    scans.sort(key=lambda row: (row["action"], row["tool"]))

    resolved_results = {"NEGATIVE", "VERIFIED_IN_LAB"}
    unresolved: list[dict[str, Any]] = []
    untestable: list[dict[str, Any]] = []
    for row in get_inputs:
        eligible = _eligible_actions(row["resource_ref"], row["parameter_name"], effective_actions)
        if not eligible:
            untestable.append({**row, "reason": "no approved action accepts this observed input"})
            continue
        pending = []
        for action in eligible:
            result = latest_results.get((action, row["resource_ref"], row["parameter_name"]))
            if result is None:
                pending.append({"action": action, "reason": "not_run"})
            elif result not in resolved_results:
                pending_result = {"action": action, "reason": "unresolved_result"}
                if len(result) <= _TEXT_LIMIT:
                    pending_result["last_result"] = result
                pending.append(pending_result)
        if pending:
            unresolved.append({
                **row,
                "reason": "approved checks remain unresolved",
                "pending_checks": pending,
            })

    incomplete_scans = [
        scan for scan in scans
        if scan["status"] != "COMPLETED"
        or (scan["coverage"] is not None and scan["coverage"] != "BOUNDED")
        or (scan["unrequested_seeds"] is not None and scan["unrequested_seeds"] > 0)
    ]

    endpoint_rows = [
        {"resource": resource, "sources": sorted(sources)}
        for resource, sources in sorted(endpoint_sources.items())
    ]

    counts = {
        "endpoints": len(endpoint_rows),
        "get_inputs": len(get_inputs),
        "post_inputs": len(post_inputs),
        "checks": len(checks),
        "scans": len(scans),
        "refused_actions": len(refused_actions),
        "unresolved_checks": len(unresolved),
        "untestable_inputs": len(untestable),
        "incomplete_scans": len(incomplete_scans),
    }

    truncated = False

    def bounded_rows(rows, **field_limits):
        nonlocal truncated
        visible = [
            row for row in rows[:limit]
            if all(len(row.get(field) or "") <= maximum for field, maximum in field_limits.items())
        ]
        truncated |= len(visible) != len(rows)
        return visible

    input_limits = {
        "resource_ref": _RESOURCE_LIMIT, "parameter_name": _TEXT_LIMIT,
        "source_observation_id": _TEXT_LIMIT,
    }
    scan_limits = {"tool": _TEXT_LIMIT, "status": _TEXT_LIMIT}
    visible_refusals = [value for value in sorted(refused_actions)[:limit] if len(value) <= _RESOURCE_LIMIT]
    truncated |= len(visible_refusals) != len(refused_actions)

    return {
        "schema": "web-planning-context/1",
        "approved_actions": _action_metadata(effective_actions),
        "observed_endpoints": bounded_rows(endpoint_rows, resource=_RESOURCE_LIMIT),
        "observed_get_inputs": bounded_rows(get_inputs, **input_limits),
        "observed_post_inputs": bounded_rows(
            post_inputs, **{**input_limits, "parameter_name": _POST_PARAMETER_LIMIT},
        ),
        "post_inputs_unsupported": bool(post_inputs),
        "post_inputs_note": (
            "POST form inputs are observed but no run-approved action accepts POST; they are not executable candidates."
            if post_inputs else None
        ),
        "probe_results": bounded_rows(checks, resource_ref=_RESOURCE_LIMIT,
                                     parameter_name=_TEXT_LIMIT, result=_TEXT_LIMIT),
        "candidate_attempts": bounded_rows(attempt_rows, resource_ref=_RESOURCE_LIMIT,
                                            parameter_name=_TEXT_LIMIT, target_id=_TEXT_LIMIT),
        "retry_policy": "Prefer untried eligible checks; never retry blocked candidates; maximum three executions per candidate.",
        "scanner_coverage": bounded_rows(scans, **scan_limits),
        "refused_actions": visible_refusals,
        "unresolved_checks": bounded_rows(unresolved, **input_limits),
        "untestable_inputs": bounded_rows(untestable, **input_limits),
        "incomplete_scans": bounded_rows(incomplete_scans, **scan_limits),
        "counts": counts,
        "previous_actions": list(previous),
        "budget": {
            "actions": int((state.get("remaining_budget") or {}).get("actions", 0) or 0),
            "requests": int((state.get("remaining_budget") or {}).get("requests", 0) or 0),
        },
        "truncated": truncated,
    }


def completion_blocker(
    state: dict[str, Any],
    effective_actions: set[str],
    limit: int = 128,
) -> str | None:
    """Assess objective coverage without trusting a provider-supplied rationale."""
    facts = list(state.get("observed_facts", []))
    context = build_web_planning_context(
        state,
        list(state.get("discovered_endpoints", [])),
        facts,
        list(state.get("previous_actions", [])),
        effective_actions,
        limit=limit,
    )
    if has_unresolved_outcomes(state, facts):
        return "unresolved_candidate_surface"
    if (context["unresolved_checks"] or context["untestable_inputs"]
            or context["post_inputs_unsupported"]):
        return "unresolved_candidate_surface"
    if context["incomplete_scans"]:
        return "unresolved_scan_coverage"
    if (context["truncated"] or not context["observed_endpoints"]
            or not any(fact.get("fact_type") in ("ENDPOINT", "PARAMETER") for fact in facts)):
        return "unresolved_candidate_surface"
    return None
