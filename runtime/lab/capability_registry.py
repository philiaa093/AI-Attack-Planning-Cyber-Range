"""Canonical bounded capability registry and safe verifiers for isolated ShopLab.

Enforces:
  - Bounded capability catalog strictly mapped to canonical action IDs.
  - ZERO DIRECT HTTP TRANSPORT: all network probes flow exclusively through CentralizedSafetyGate.
  - Input injection (ACTION-WEB-001): bounded inert test-vectors, differential analysis, zero arbitrary SQL.
  - Script injection (ACTION-WEB-002): inert marker fixtures, encoding detection, zero arbitrary JS/cookie theft.
  - Path traversal (ACTION-WEB-003): safe fixture sentinel only, NEVER /etc/passwd or host files.
  - Finding classification: NEGATIVE, SIGNAL, VERIFIED_IN_LAB, INCONCLUSIVE, REFUSED.
  - Provenance: resource and input parameters must resolve to observed inventory.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import urllib.parse
import uuid
from http.cookies import SimpleCookie
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

# Names describe the actual internal implementation, not external scanners.
ACTION_EXECUTION_DETAILS = {
    "ACTION-RECON-001": {"tool": "AutonomousRunner HTTP health probe", "family": "DISCOVERY"},
    "ACTION-RECON-002": {"tool": "ObservationDrivenDiscovery", "family": "DISCOVERY"},
    "ACTION-SCAN-001": {"tool": "PassiveSurfaceAnalyzer", "family": "PASSIVE_ANALYSIS"},
    "ACTION-SCAN-002": {"tool": "Isolated ZAP / Nuclei", "family": "BOUNDED_WEB_SCAN"},
    "ACTION-WEB-001": {"tool": "SafeInputVerificationExecutor", "family": "SQL_INJECTION"},
    "ACTION-WEB-002": {"tool": "SafeReflectionVerificationExecutor", "family": "SCRIPT_INJECTION"},
    "ACTION-WEB-003": {"tool": "SafePathFixtureVerificationExecutor", "family": "PATH_TRAVERSAL"},
    "ACTION-LOGIC-001": {"tool": "SafeBusinessLogicVerificationExecutor", "family": "BUSINESS_LOGIC"},
}

from runtime.discovery.discovery_engine import InventoryItem, InventoryStore
from runtime.lab.authenticated_workflow import Forms
from runtime.safety.discovery_gate import (
    ApprovalToken,
    CentralizedSafetyGate,
    DiscoveryRequest,
    DispatchResponse,
)
from runtime.evidence.discovery_recorder import (
    DurableEvidenceRecorder,
    EvidenceFailure,
    redact_secrets,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class VerificationFinding:
    """Standardized finding record adhering to Section 16 confirmation semantics."""
    finding_id: str
    family: str           # "SQL_INJECTION", "SCRIPT_INJECTION", "PATH_TRAVERSAL", "INPUT_VALIDATION"
    classification: str   # "OBSERVATION", "CANDIDATE", "SIGNAL", "VERIFIED_IN_LAB", "NEGATIVE_RESULT", "INCONCLUSIVE"
    resource_ref: str
    input_ref: str
    source_observation_refs: list[str]
    verification_action: str
    result_evidence_refs: list[str]
    confidence: float
    limitations: list[str]
    reason: str
    path_input_evidence: bool | None = None


@dataclass
class CapabilityExecutionResult:
    """Normalized output from bounded capability execution."""
    action_id: str
    target_id: str
    outcome: str          # "SUCCESS", "FAILURE", "DENIED"
    classification: str   # "NEGATIVE", "SIGNAL", "VERIFIED_IN_LAB", "INCONCLUSIVE", "REFUSED"
    findings: list[VerificationFinding] = field(default_factory=list)
    new_facts: list[dict[str, Any]] = field(default_factory=list)
    network_dispatch_count: int = 0
    intent_evidence_id: str | None = None
    result_evidence_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class BaseCapabilityExecutor:
    """Abstract base executor interface for bounded capabilities."""

    def execute(
        self,
        proposal: dict[str, Any],
        gate: CentralizedSafetyGate,
        recorder: DurableEvidenceRecorder,
        run_id: str,
        target_id: str,
        inventory: InventoryStore,
        approval: ApprovalToken | None,
    ) -> CapabilityExecutionResult:
        raise NotImplementedError


class ReconProbeExecutor(BaseCapabilityExecutor):
    """Executor for ACTION-RECON-001 (Target Identification Probe)."""

    def execute(
        self,
        proposal: dict[str, Any],
        gate: CentralizedSafetyGate,
        recorder: DurableEvidenceRecorder,
        run_id: str,
        target_id: str,
        inventory: InventoryStore,
        approval: ApprovalToken | None,
    ) -> CapabilityExecutionResult:
        req = DiscoveryRequest(
            run_id=run_id,
            target_id=target_id,
            action_id="ACTION-RECON-001",
            url=f"{gate.base_origin}/health",
            method="GET",
            approval=approval,
        )
        resp: DispatchResponse = gate.dispatch(req)
        if gate.halted_due_to_evidence or (
            not resp.durable_confirmed and "EVIDENCE" in (resp.refusal_reason or "")
        ):
            raise EvidenceFailure(resp.refusal_reason or "Gate halted due to evidence failure")

        intent_art_id = None
        result_art_id = None
        for art in reversed(recorder.artifacts):
            ev = art.get("evidence_id", "")
            if not result_art_id and "result" in ev.lower():
                result_art_id = ev
            elif not intent_art_id and "intent" in ev.lower():
                intent_art_id = ev
            if intent_art_id and result_art_id:
                break

        outcome = "SUCCESS" if resp.status_code == 200 else "FAILURE"
        classification = "VERIFIED_IN_LAB" if resp.status_code == 200 else "NEGATIVE"
        facts = [
            {
                "fact_id": f"FACT-TGT-{target_id}",
                "fact_type": "TARGET",
                "subject": target_id,
                "value": target_id,
                "confidence": 1.0,
            }
        ]
        return CapabilityExecutionResult(
            action_id="ACTION-RECON-001",
            target_id=target_id,
            outcome=outcome,
            classification=classification,
            new_facts=facts,
            network_dispatch_count=1,
            intent_evidence_id=intent_art_id,
            result_evidence_id=result_art_id,
            details={"status_code": resp.status_code},
        )


class PassiveSurfaceAnalyzer(BaseCapabilityExecutor):
    """Executor for ACTION-SCAN-001 (Passive Inventory Analysis — zero network dispatches)."""

    def execute(
        self,
        proposal: dict[str, Any],
        gate: CentralizedSafetyGate,
        recorder: DurableEvidenceRecorder,
        run_id: str,
        target_id: str,
        inventory: InventoryStore,
        approval: ApprovalToken | None,
    ) -> CapabilityExecutionResult:
        candidate_facts: list[dict[str, Any]] = []
        seen_facts: set[tuple[Any, ...]] = set()

        def add_fact(key: tuple[Any, ...], fact: dict[str, Any]) -> None:
            # Scope deduplication to this analysis and to a single inventory
            # observation. Distinct pages, methods and form structures remain
            # distinct even when they happen to expose the same input.
            if key not in seen_facts:
                seen_facts.add(key)
                candidate_facts.append(fact)

        for path, item in inventory.items.items():
            clean_url = item.canonical_url.split("?")[0].split("#")[0]
            source_key = (item.source_observation_id, item.canonical_url, item.method)
            parsed_query = urllib.parse.urlsplit(item.path).query
            # Record query inputs on visited endpoint
            if parsed_query:
                for qk, qv in urllib.parse.parse_qsl(parsed_query, keep_blank_values=False):
                    add_fact((*source_key, "query", clean_url, str(qk)), {
                        "fact_id": f"FACT-PARAM-{uuid.uuid4().hex[:8]}",
                        "fact_type": "PARAMETER",
                        "subject": clean_url,
                        "value": str(qk),
                        "confidence": 0.85,
                    })
                    # An observed value that names a file/path is evidence the
                    # input carries a filesystem reference. Only a minimized
                    # marker is recorded; the value itself stays out of state.
                    from runtime.planners.web_planning_context import looks_like_path_value
                    if looks_like_path_value(qv):
                        marker_resource = urllib.parse.urlsplit(clean_url).path or "/"
                        if marker_resource != "/":
                            marker_resource = marker_resource.rstrip("/") or "/"
                        add_fact((*source_key, "query_path", clean_url, str(qk)), {
                            "fact_id": f"FACT-CAND-{uuid.uuid4().hex[:8]}",
                            "fact_type": "CANDIDATE_FINDING",
                            "subject": marker_resource,
                            "value": f"path_like_input_{qk}",
                            "confidence": 0.60,
                        })

            # Record form inputs with strict action and method provenance
            if item.forms:
                for form in item.forms:
                    raw_action = form.get("action", "").strip()
                    form_method = form.get("method", "GET").upper().strip()
                    form_target = urllib.parse.urljoin(item.canonical_url, raw_action) if raw_action else item.canonical_url
                    clean_form_target = form_target.split("?")[0].split("#")[0]
                    inputs = form.get("inputs", [])
                    is_credential_form = form_method == "POST" and any(
                        str(inp.get("type", "")).lower() == "password"
                        or any(part in str(inp.get("name", "")).lower()
                               for part in ("password", "passwd", "credential"))
                        for inp in inputs
                    )
                    # The whole observed form is part of the identity: two
                    # forms sharing an input name may carry different context.
                    form_key = json.dumps(form, sort_keys=True, ensure_ascii=True, separators=(",", ":"))

                    for inp in inputs:
                        inp_name = inp.get("name", "").strip()
                        if not inp_name:
                            continue
                        if form_method == "GET":
                            # Safe read-only query parameter input on actual form action endpoint
                            add_fact((*source_key, "form", clean_form_target, form_method, form_key, inp_name), {
                                "fact_id": f"FACT-PARAM-{uuid.uuid4().hex[:8]}",
                                "fact_type": "PARAMETER",
                                "subject": clean_form_target,
                                "value": str(inp_name),
                                "confidence": 0.85,
                            })
                        elif not is_credential_form:
                            # POST/mutating form input: record finding as CANDIDATE_FINDING (zero conversion to synthetic GET query parameter)
                            add_fact((*source_key, "form", clean_form_target, form_method, form_key, inp_name), {
                                "fact_id": f"FACT-CAND-{uuid.uuid4().hex[:8]}",
                                "fact_type": "CANDIDATE_FINDING",
                                "subject": clean_form_target,
                                "value": f"post_form_input_{inp_name}",
                                "confidence": 0.50,
                            })

                add_fact((*source_key, "form_summary", clean_url), {
                    "fact_id": f"FACT-CAND-{uuid.uuid4().hex[:8]}",
                    "fact_type": "CANDIDATE_FINDING",
                    "subject": clean_url,
                    "value": f"forms_inputs_count_{len(item.forms)}",
                    "confidence": 0.50,
                })

        if not candidate_facts:
            candidate_facts.append({
                "fact_id": f"FACT-NEG-{uuid.uuid4().hex[:8]}",
                "fact_type": "CONTROL",
                "subject": target_id,
                "value": "passive_clean_surface",
                "confidence": 0.90,
            })

        art = recorder.persist_phase_artifact("passive_scan_result", {
            "run_id": run_id,
            "target_id": target_id,
            "candidate_facts_count": len(candidate_facts),
        })

        return CapabilityExecutionResult(
            action_id="ACTION-SCAN-001",
            target_id=target_id,
            outcome="SUCCESS",
            classification="NEGATIVE",
            new_facts=candidate_facts,
            network_dispatch_count=0,
            result_evidence_id=art["evidence_id"],
            details={"candidate_facts_count": len(candidate_facts)},
        )


def _clean_form_target(item: InventoryItem, form: dict[str, Any]) -> str:
    target = urllib.parse.urljoin(item.canonical_url, form.get("action") or item.canonical_url)
    return urllib.parse.urlsplit(target).path.rstrip("/") or "/"


def _find_observed_form(
    inventory: InventoryStore,
    resource: str,
    parameter: str,
    method: str,
) -> tuple[InventoryItem, dict[str, Any]] | None:
    resource_path = urllib.parse.urlsplit(resource).path.rstrip("/") or "/"
    for item in inventory.items.values():
        for form in item.forms:
            if str(form.get("method", "GET")).upper() != method:
                continue
            if _clean_form_target(item, form) != resource_path:
                continue
            names = {str(inp.get("name", "")) for inp in form.get("inputs", [])}
            if parameter in names:
                return item, form
    return None


def _probe_form_method(
    inventory: InventoryStore,
    resource: str,
    parameter: str,
) -> str:
    """Pick the observation-proven method for one input.

    Provenance order: a query parameter on an observed GET URL, then a GET
    form, then a POST form. A query input therefore stays a GET probe even
    when the same resource also exposes an unrelated POST form with the same
    name. POST is only used when nothing GET-observable exposes the input.
    """
    if _observed_query_parameter(resource, parameter):
        return "GET"
    # The planner usually strips the query from resource_ref, so also look for
    # the parameter on URLs this run actually observed for the same path.
    if _observed_query_in_inventory(inventory, resource, parameter):
        return "GET"
    if _find_observed_form(inventory, resource, parameter, "GET") is not None:
        return "GET"
    if _find_observed_form(inventory, resource, parameter, "POST") is not None:
        return "POST"
    return "GET"


def _observed_query_in_inventory(
    inventory: InventoryStore,
    resource: str,
    parameter: str,
) -> bool:
    """True when a recorded GET URL for this path carried the parameter."""
    resource_path = urllib.parse.urlsplit(resource).path.rstrip("/") or "/"
    for item in inventory.items.values():
        if (urllib.parse.urlsplit(item.canonical_url).path.rstrip("/") or "/") != resource_path:
            continue
        query = urllib.parse.urlsplit(item.path).query
        if query and parameter in {name for name, _ in urllib.parse.parse_qsl(query)}:
            return True
    return False


def _observed_query_parameter(resource: str, parameter: str) -> bool:
    """True when the candidate URL itself carries this query parameter."""
    query = urllib.parse.urlsplit(resource).query
    if not query:
        return False
    return parameter in {name for name, _ in urllib.parse.parse_qsl(query)}


def observed_path_evidence(inventory: InventoryStore) -> set[tuple[str, str]]:
    """Collect (resource, parameter) pairs whose observed value looks like a path.

    The value is read from bounded inventory metadata that is already in memory.
    It is never copied into planner state or evidence; only membership leaves
    this function.
    """
    from runtime.planners.web_planning_context import looks_like_path_value

    evidence: set[tuple[str, str]] = set()
    for item in inventory.items.values():
        query = urllib.parse.urlsplit(item.path).query
        if not query:
            continue
        resource = urllib.parse.urlsplit(item.canonical_url).path or "/"
        if resource != "/":
            resource = resource.rstrip("/") or "/"
        for name, value in urllib.parse.parse_qsl(query, keep_blank_values=False):
            if looks_like_path_value(value):
                evidence.add((resource, name))
    return evidence


def _has_path_evidence(evidence: set[tuple[str, str]], resource: Any, parameter: Any) -> bool:
    """Match observed evidence for both relative and absolute resource forms."""
    from runtime.planners.web_planning_context import _canonical_resource

    canonical = _canonical_resource(resource)
    return (canonical, parameter) in evidence or (str(resource), parameter) in evidence


def _observed_get_baseline(
    inventory: InventoryStore,
    resource: str,
    parameter: str,
) -> str:
    # Prefer the value the target actually served for this input: a fabricated
    # baseline can turn a healthy endpoint into a 404 and mask every check.
    resource_path = urllib.parse.urlsplit(resource).path.rstrip("/") or "/"
    for item in inventory.items.values():
        if (urllib.parse.urlsplit(item.canonical_url).path.rstrip("/") or "/") != resource_path:
            continue
        for name, value in urllib.parse.parse_qsl(
                urllib.parse.urlsplit(item.path).query, keep_blank_values=False):
            if name == parameter and value:
                return value
    matched = _find_observed_form(inventory, resource, parameter, "GET")
    if matched is None:
        return "probe_test"
    _, form = matched
    for inp in form.get("inputs", []):
        if inp.get("name") != parameter:
            continue
        options = inp.get("options") or []
        selected = [str(opt.get("value", "")) for opt in options if opt.get("selected")]
        nonempty = [str(opt.get("value", "")) for opt in options if str(opt.get("value", ""))]
        if selected and selected[0]:
            return selected[0]
        if nonempty:
            return nonempty[0]
    return "probe_test"


def _prepare_observed_post_form(
    *,
    inventory: InventoryStore,
    resource: str,
    parameter: str,
    action_id: str,
    gate: CentralizedSafetyGate,
    run_id: str,
    target_id: str,
    approval: ApprovalToken | None,
) -> tuple[dict[str, str], dict[str, str], DispatchResponse | None, str | None]:
    """Refresh an observed form and keep its CSRF/session values in memory only."""
    matched = _find_observed_form(inventory, resource, parameter, "POST")
    if matched is None:
        return {}, {}, None, None
    item, metadata = matched
    response = gate.dispatch(DiscoveryRequest(
        run_id=run_id,
        target_id=target_id,
        action_id=action_id,
        url=item.canonical_url,
        method="GET",
        approval=approval,
    ))
    if (not response.durable_confirmed or response.outcome != "SUCCESS"
            or response.status_code != 200 or response.truncated or response.error_message):
        return {}, {}, response, "Observed POST form could not be refreshed safely"

    parsed = Forms(response.body)
    resource_path = urllib.parse.urlsplit(resource).path.rstrip("/") or "/"
    fields: dict[str, str] | None = None
    for form in parsed.forms:
        target = urllib.parse.urljoin(item.canonical_url, form.get("action") or item.canonical_url)
        target_path = urllib.parse.urlsplit(target).path.rstrip("/") or "/"
        candidate = {str(k): str(v) for k, v in form.get("fields", {}).items()}
        if form.get("method") == "POST" and target_path == resource_path and parameter in candidate:
            fields = candidate
            break
    if fields is None:
        return {}, {}, response, "Observed POST form changed before verification"

    input_types = {
        str(inp.get("name", "")): str(inp.get("type", "")).lower()
        for inp in metadata.get("inputs", [])
    }
    for name, value in list(fields.items()):
        if value:
            continue
        lowered = name.lower()
        if any(part in lowered for part in ("csrf", "token", "session", "secret")):
            return {}, {}, response, "Observed POST form control value is unavailable"
        if input_types.get(name) in {"number", "range", "hidden"} or lowered.endswith("_id") or lowered == "quantity":
            fields[name] = "1"
        else:
            fields[name] = "test"

    headers: dict[str, str] = {}
    cookie_header = response.headers.get("Set-Cookie") or response.headers.get("set-cookie") or ""
    if cookie_header:
        jar = SimpleCookie()
        try:
            jar.load(cookie_header)
        except Exception:
            return {}, {}, response, "Observed POST form session cookie is malformed"
        if "session" in jar and jar["session"].value:
            headers["Cookie"] = "session=" + jar["session"].value
    if any("csrf" in name.lower() for name in fields) and "Cookie" not in headers:
        return {}, {}, response, "Observed POST form session cookie is unavailable"
    return fields, headers, response, None


class SafeInputVerificationExecutor(BaseCapabilityExecutor):
    """Executor for ACTION-WEB-001 (Safe Input Injection / SQLi Verification).

    Enforces:
      - Bounded cyber-range test vectors only; zero arbitrary SQL generation.
      - Strictly dispatches through CentralizedSafetyGate.
      - Differential analysis: compares baseline response with syntax probe vectors.
      - Classification: NEGATIVE, SIGNAL, VERIFIED_IN_LAB, INCONCLUSIVE, REFUSED.
    """

    SQL_SYNTAX_ERROR_PATTERNS = [
        re.compile(r"syntax error", re.IGNORECASE),
        re.compile(r"sqlite3\.operationalerror", re.IGNORECASE),
        re.compile(r"unrecognized token", re.IGNORECASE),
        re.compile(r"sql logic error", re.IGNORECASE),
        re.compile(r"database error", re.IGNORECASE),
    ]

    def execute(
        self,
        proposal: dict[str, Any],
        gate: CentralizedSafetyGate,
        recorder: DurableEvidenceRecorder,
        run_id: str,
        target_id: str,
        inventory: InventoryStore,
        approval: ApprovalToken | None,
    ) -> CapabilityExecutionResult:
        resource = proposal.get("resource_ref", "/")
        param = proposal.get("parameter_name", "q")

        responses: dict[str, DispatchResponse] = {}
        last_intent_id = None
        result_ids: list[str] = []
        initial_dispatch_count = gate.network_dispatch_count
        dispatches_made = 0
        classification = "INCONCLUSIVE"
        reason = "Incomplete response set during bounded differential probe"

        is_post_form = _probe_form_method(inventory, resource, param) == "POST"
        default_form_fields: dict[str, str] = {}
        request_headers: dict[str, str] = {}
        can_probe = True
        if is_post_form:
            initial_artifact_count = len(recorder.artifacts)
            default_form_fields, request_headers, bootstrap, preparation_error = _prepare_observed_post_form(
                inventory=inventory,
                resource=resource,
                parameter=param,
                action_id="ACTION-WEB-001",
                gate=gate,
                run_id=run_id,
                target_id=target_id,
                approval=approval,
            )
            dispatches_made = gate.network_dispatch_count - initial_dispatch_count
            for artifact in recorder.artifacts[initial_artifact_count:]:
                evidence_id = artifact.get("evidence_id", "")
                if evidence_id.startswith("EV-RESULT-"):
                    result_ids.append(evidence_id)
                elif evidence_id.startswith("EV-INTENT-"):
                    last_intent_id = evidence_id
            if bootstrap is not None and (gate.halted_due_to_evidence or (
                not bootstrap.durable_confirmed and (
                    bootstrap.outcome != "DENIED" or "EVIDENCE" in (bootstrap.refusal_reason or "")
                )
            )):
                raise EvidenceFailure(bootstrap.refusal_reason or "Gate halted due to evidence failure")
            if preparation_error:
                can_probe = False
                if bootstrap is not None and (bootstrap.outcome == "DENIED" or bootstrap.refusal_reason):
                    classification = "REFUSED"
                    reason = "Safety Gate refused POST form refresh: " + (bootstrap.refusal_reason or bootstrap.outcome)
                else:
                    reason = preparation_error

        baseline_value = (
            default_form_fields.get(param, "test") if is_post_form
            else _observed_get_baseline(inventory, resource, param)
        )
        vectors = [
            ("baseline", baseline_value),
            ("quote", baseline_value + "'"),
            ("balance", baseline_value + "''"),
        ]

        for label, vector_val in vectors if can_probe else []:
            if is_post_form:
                form_payload = dict(default_form_fields)
                form_payload[param] = vector_val
                clean_path = urllib.parse.urlsplit(resource).path or "/"
                full_url = f"{gate.base_origin}{clean_path}"
                req = DiscoveryRequest(
                    run_id=run_id,
                    target_id=target_id,
                    action_id="ACTION-WEB-001",
                    url=full_url,
                    method="POST",
                    headers=request_headers,
                    form=form_payload,
                    approval=approval,
                )
            else:
                parsed = urllib.parse.urlsplit(resource)
                query_dict = dict(urllib.parse.parse_qsl(parsed.query))
                query_dict[param] = vector_val
                encoded_query = urllib.parse.urlencode(query_dict)
                full_path = f"{parsed.path}?{encoded_query}"
                full_url = f"{gate.base_origin}{full_path}"

                req = DiscoveryRequest(
                    run_id=run_id,
                    target_id=target_id,
                    action_id="ACTION-WEB-001",
                    url=full_url,
                    method="GET",
                    approval=approval,
                )
            initial_artifact_count = len(recorder.artifacts)
            resp = gate.dispatch(req)
            dispatches_made = gate.network_dispatch_count - initial_dispatch_count

            # A pre-dispatch refusal has no dispatched result to confirm durably.
            if gate.halted_due_to_evidence or (
                not resp.durable_confirmed and (
                    resp.outcome != "DENIED" or "EVIDENCE" in (resp.refusal_reason or "")
                )
            ):
                raise EvidenceFailure(resp.refusal_reason or "Gate halted due to evidence failure")

            responses[label] = resp

            # Each control/probe must refer to its own newly recorded evidence.
            for art in recorder.artifacts[initial_artifact_count:]:
                ev = art.get("evidence_id", "")
                if ev.startswith("EV-RESULT-"):
                    result_ids.append(ev)
                    last_result_id = ev
                elif ev.startswith("EV-INTENT-"):
                    last_intent_id = ev

            if resp.outcome == "DENIED" or resp.refusal_reason:
                classification = "REFUSED"
                reason = "Safety Gate refused bounded SQL syntax probe: " + (resp.refusal_reason or resp.outcome)
                break
            if resp.outcome not in {"SUCCESS", "FAILURE"} or resp.error_message or not 100 <= resp.status_code <= 599:
                reason = f"Incomplete {label} response during bounded SQL syntax probe"
                break
            if resp.truncated:
                reason = f"Truncated {label} response during bounded SQL syntax probe"
                break
            accepted_control_statuses = {200} if not is_post_form else {200, 201, 204, 302, 303}
            validation_rejected = resp.status_code in {400, 409, 422} and resp.outcome == "FAILURE"
            if label == "baseline":
                if resp.status_code not in accepted_control_statuses or resp.outcome != "SUCCESS" or any(
                    p.search(resp.body) for p in self.SQL_SYNTAX_ERROR_PATTERNS
                ):
                    reason = f"Invalid {label} control during bounded SQL syntax probe"
                    break
            elif label == "quote" and not (
                resp.status_code == 200 and resp.outcome == "SUCCESS"
                or 500 <= resp.status_code <= 599
                or validation_rejected
            ):
                reason = "Invalid quote response during bounded SQL syntax probe"
                break
            elif label == "balance" and not (
                resp.status_code in accepted_control_statuses
                and resp.outcome == "SUCCESS"
                and not any(pattern.search(resp.body) for pattern in self.SQL_SYNTAX_ERROR_PATTERNS)
                or validation_rejected and responses["quote"].status_code in {400, 409, 422}
            ):
                reason = "Invalid balance control during bounded SQL syntax probe"
                break
        else:
            if not can_probe:
                resp_quote = None
                quote_has_err = False
            else:
                # ponytail: verifies syntax-error differentials only; impact needs a separately approved capability.
                resp_quote = responses["quote"]
                quote_has_err = any(p.search(resp_quote.body) for p in self.SQL_SYNTAX_ERROR_PATTERNS)

            if not can_probe:
                pass
            elif (
                resp_quote.status_code in {400, 409, 422}
                and responses["balance"].status_code in {400, 409, 422}
            ):
                classification = "NEGATIVE"
                reason = "Bounded syntax vectors were rejected consistently by observed input validation"
            elif quote_has_err:
                classification = "VERIFIED_IN_LAB"
                reason = "Differential SQL syntax error observed on unescaped quote with recovery on balanced quote"
            elif resp_quote.status_code >= 500:
                classification = "SIGNAL"
                reason = "HTTP 5xx status differential observed on probe quote; syntax error signature unverified"
            else:
                # Bounded differential probe observed no syntax errors
                classification = "NEGATIVE"
                reason = "No SQL syntax anomaly observed for bounded syntax probe vectors (probe_test', probe_test'')"

        finding_id = f"FIND-SQLI-{uuid.uuid4().hex[:8]}"
        conf = 0.95 if classification == "VERIFIED_IN_LAB" else (0.60 if classification == "NEGATIVE" else 0.50)
        finding = VerificationFinding(
            finding_id=finding_id,
            family="SQL_INJECTION",
            classification=classification,
            resource_ref=resource,
            input_ref=param,
            source_observation_refs=proposal.get("evidence_refs", []),
            verification_action="ACTION-WEB-001",
            result_evidence_refs=result_ids,
            confidence=conf,
            limitations=[
                "Bounded differential probing with harmless syntax vectors only; zero arbitrary SQL execution",
                "Syntax-error differential only; does not demonstrate data access or authentication bypass",
            ],
            reason=reason,
        )

        fact = {
            "fact_id": f"FACT-SQLI-{uuid.uuid4().hex[:8]}",
            "fact_type": "ACTION_OUTCOME",
            "subject": f"ACTION-WEB-001:{resource}:{param}",
            "value": classification,
            "confidence": finding.confidence,
        }

        # Persist summary verification artifact
        art = recorder.persist_phase_artifact("action_web_001_verification", {
            "run_id": run_id,
            "target_id": target_id,
            "action_id": "ACTION-WEB-001",
            "resource": resource,
            "parameter": param,
            "classification": classification,
            "reason": reason,
            "finding": asdict(finding),
            "dispatches_made": dispatches_made,
        })

        return CapabilityExecutionResult(
            action_id="ACTION-WEB-001",
            target_id=target_id,
            outcome="DENIED" if classification == "REFUSED" else (
                "FAILURE" if classification == "INCONCLUSIVE" else "SUCCESS"
            ),
            classification=classification,
            findings=[finding],
            new_facts=[fact],
            network_dispatch_count=dispatches_made,
            intent_evidence_id=last_intent_id,
            result_evidence_id=art["evidence_id"],
            details={"reason": reason, "classification": classification},
        )


class SafeReflectionVerificationExecutor(BaseCapabilityExecutor):
    """Executor for ACTION-WEB-002 (Safe Script Injection / Reflection Verification).

    Enforces:
      - Harmless inert marker fixtures only; zero executable JS, zero cookie theft.
      - Evaluates reflection, context, and HTML output encoding.
      - Classification: NEGATIVE, SIGNAL, VERIFIED_IN_LAB, INCONCLUSIVE.
    """

    def execute(
        self,
        proposal: dict[str, Any],
        gate: CentralizedSafetyGate,
        recorder: DurableEvidenceRecorder,
        run_id: str,
        target_id: str,
        inventory: InventoryStore,
        approval: ApprovalToken | None,
    ) -> CapabilityExecutionResult:
        resource = proposal.get("resource_ref", "/")
        param = proposal.get("parameter_name", "q")

        # Inert markers
        marker_id = uuid.uuid4().hex[:8]
        inert_tag_marker = f"<shoplab_sentinel_{marker_id}>"
        escaped_tag_marker = f"&lt;shoplab_sentinel_{marker_id}&gt;"

        last_intent_id = None
        last_result_id = None
        result_ids: list[str] = []
        initial_dispatch_count = gate.network_dispatch_count
        dispatches_made = 0
        classification = "INCONCLUSIVE"
        reason = "Incomplete response during bounded reflection probe"

        # Check if input belongs to a discovered POST form
        is_post_form = _probe_form_method(inventory, resource, param) == "POST"
        default_form_fields: dict[str, str] = {}
        request_headers: dict[str, str] = {}
        can_probe = True
        preparation_error: str | None = None
        if is_post_form:
            initial_artifact_count = len(recorder.artifacts)
            default_form_fields, request_headers, bootstrap, preparation_error = _prepare_observed_post_form(
                inventory=inventory,
                resource=resource,
                parameter=param,
                action_id="ACTION-WEB-002",
                gate=gate,
                run_id=run_id,
                target_id=target_id,
                approval=approval,
            )
            dispatches_made = gate.network_dispatch_count - initial_dispatch_count
            for artifact in recorder.artifacts[initial_artifact_count:]:
                evidence_id = artifact.get("evidence_id", "")
                if evidence_id.startswith("EV-RESULT-"):
                    result_ids.append(evidence_id)
                    last_result_id = evidence_id
                elif evidence_id.startswith("EV-INTENT-"):
                    last_intent_id = evidence_id
            if bootstrap is not None and (gate.halted_due_to_evidence or (
                not bootstrap.durable_confirmed and (
                    bootstrap.outcome != "DENIED" or "EVIDENCE" in (bootstrap.refusal_reason or "")
                )
            )):
                raise EvidenceFailure(bootstrap.refusal_reason or "Gate halted due to evidence failure")
            if preparation_error:
                can_probe = False
                if bootstrap is not None and (bootstrap.outcome == "DENIED" or bootstrap.refusal_reason):
                    classification = "REFUSED"
                    reason = "Safety Gate refused POST form refresh: " + (bootstrap.refusal_reason or bootstrap.outcome)
                else:
                    reason = preparation_error

        if not can_probe:
            if bootstrap is not None and (bootstrap.outcome == "DENIED" or bootstrap.refusal_reason):
                classification = "REFUSED"
                reason = "Safety Gate refused POST form refresh: " + (bootstrap.refusal_reason or bootstrap.outcome)
            else:
                classification = "INCONCLUSIVE"
                reason = preparation_error or "Observed POST form could not be refreshed safely"
        else:
            if is_post_form:
                form_payload = dict(default_form_fields)
                form_payload[param] = inert_tag_marker
                clean_path = urllib.parse.urlsplit(resource).path or "/"
                full_url = f"{gate.base_origin}{clean_path}"
                req = DiscoveryRequest(
                    run_id=run_id,
                    target_id=target_id,
                    action_id="ACTION-WEB-002",
                    url=full_url,
                    method="POST",
                    headers=request_headers,
                    form=form_payload,
                    approval=approval,
                )
            else:
                parsed = urllib.parse.urlsplit(resource)
                query_dict = dict(urllib.parse.parse_qsl(parsed.query))
                query_dict[param] = inert_tag_marker
                encoded_query = urllib.parse.urlencode(query_dict)
                full_path = f"{parsed.path}?{encoded_query}"
                full_url = f"{gate.base_origin}{full_path}"

                req = DiscoveryRequest(
                    run_id=run_id,
                    target_id=target_id,
                    action_id="ACTION-WEB-002",
                    url=full_url,
                    method="GET",
                    approval=approval,
                )

            initial_artifact_count = len(recorder.artifacts)
            resp = gate.dispatch(req)
            dispatches_made = gate.network_dispatch_count - initial_dispatch_count
            if gate.halted_due_to_evidence or (
                not resp.durable_confirmed and (
                    resp.outcome != "DENIED" or "EVIDENCE" in (resp.refusal_reason or "")
                )
            ):
                raise EvidenceFailure(resp.refusal_reason or "Gate halted due to evidence failure")

            for art in recorder.artifacts[initial_artifact_count:]:
                ev = art.get("evidence_id", "")
                if ev.startswith("EV-RESULT-"):
                    result_ids.append(ev)
                    last_result_id = ev
                elif ev.startswith("EV-INTENT-"):
                    last_intent_id = ev

            body = resp.body or ""
            content_type = resp.headers.get("Content-Type") or resp.headers.get("content-type") or ""

            if resp.outcome == "DENIED" or resp.refusal_reason:
                classification = "REFUSED"
                reason = "Safety Gate refused bounded reflection probe: " + (resp.refusal_reason or resp.outcome)
            elif (
                resp.outcome not in {"SUCCESS", "FAILURE"}
                or resp.error_message
                or resp.truncated
                or not 100 <= resp.status_code <= 599
            ):
                classification = "INCONCLUSIVE"
                reason = "Incomplete response during bounded reflection probe"
            elif resp.status_code not in ({200, 201, 204, 302, 303} if is_post_form else {200}) and not (
                resp.status_code in {400, 409, 422} and resp.outcome == "FAILURE"
            ):
                classification = "INCONCLUSIVE"
                reason = f"Unexpected HTTP status {resp.status_code} during bounded reflection probe"
            elif inert_tag_marker in body and "text/html" in content_type.lower():
                # Raw unencoded tag marker reflected in HTML body
                classification = "VERIFIED_IN_LAB"
                reason = "Inert HTML sentinel reflected unescaped in HTML response body"
            elif escaped_tag_marker in body:
                # Safely HTML-escaped
                classification = "NEGATIVE"
                reason = "Inert sentinel is properly HTML-escaped (&lt;...&gt;) in observed response body context"
            elif marker_id in body:
                # Substring reflected in non-HTML or neutral text context
                classification = "SIGNAL"
                reason = "Inert marker reflected in response body without raw HTML tag execution context"
            elif resp.status_code in {400, 409, 422} and resp.outcome == "FAILURE":
                classification = "NEGATIVE"
                reason = "Inert probe marker was rejected by observed target input validation"
            else:
                # Marker not reflected
                classification = "NEGATIVE"
                reason = "Inert probe marker was not reflected in observed target response body"

        finding_id = f"FIND-XSS-{uuid.uuid4().hex[:8]}"
        conf = 0.95 if classification == "VERIFIED_IN_LAB" else (
            0.75 if "escaped" in reason else (0.50 if classification in {"INCONCLUSIVE", "REFUSED"} else 0.60)
        )
        finding = VerificationFinding(
            finding_id=finding_id,
            family="SCRIPT_INJECTION",
            classification=classification,
            resource_ref=resource,
            input_ref=param,
            source_observation_refs=proposal.get("evidence_refs", []),
            verification_action="ACTION-WEB-002",
            result_evidence_refs=result_ids if result_ids else ([last_result_id] if last_result_id else []),
            confidence=conf,
            limitations=["Inert marker fixtures only; zero executable JS, zero token extraction, zero browser takeover"],
            reason=reason,
        )

        fact = {
            "fact_id": f"FACT-XSS-{uuid.uuid4().hex[:8]}",
            "fact_type": "ACTION_OUTCOME",
            "subject": f"ACTION-WEB-002:{resource}:{param}",
            "value": classification,
            "confidence": finding.confidence,
        }

        art = recorder.persist_phase_artifact("action_web_002_verification", {
            "run_id": run_id,
            "target_id": target_id,
            "action_id": "ACTION-WEB-002",
            "resource": resource,
            "parameter": param,
            "classification": classification,
            "reason": reason,
            "finding": asdict(finding),
            "dispatches_made": dispatches_made,
        })

        return CapabilityExecutionResult(
            action_id="ACTION-WEB-002",
            target_id=target_id,
            outcome="DENIED" if classification == "REFUSED" else (
                "FAILURE" if classification == "INCONCLUSIVE" else "SUCCESS"
            ),
            classification=classification,
            findings=[finding],
            new_facts=[fact],
            network_dispatch_count=dispatches_made,
            intent_evidence_id=last_intent_id,
            result_evidence_id=art["evidence_id"],
            details={"reason": reason, "classification": classification},
        )


class SafePathFixtureVerificationExecutor(BaseCapabilityExecutor):
    """Executor for ACTION-WEB-003 (Safe Path Handling / Traversal Verification).

    Enforces:
      - NEVER reads /etc/passwd, win.ini, .env, SSH keys, credentials, or host filesystem.
      - Probes exclusively with approved lab fixture sentinel (LAB_TRAVERSAL_SENTINEL).
      - If sentinel fixture is unavailable or host files are required: CAPABILITY_BLOCKED.
      - Classification: NEGATIVE, SIGNAL, VERIFIED_IN_LAB, INCONCLUSIVE, REFUSED.
    """

    SAFE_SENTINEL = "LAB_TRAVERSAL_SENTINEL"

    def execute(
        self,
        proposal: dict[str, Any],
        gate: CentralizedSafetyGate,
        recorder: DurableEvidenceRecorder,
        run_id: str,
        target_id: str,
        inventory: InventoryStore,
        approval: ApprovalToken | None,
    ) -> CapabilityExecutionResult:
        resource = proposal.get("resource_ref", "/")
        param = proposal.get("parameter_name", "file")
        from runtime.planners.web_planning_context import is_path_like
        # Evidence comes from the observed inventory, not from the route name.
        # The raw value stays in memory; only a boolean is recorded.
        evidence = observed_path_evidence(inventory)
        if not is_path_like(str(resource), param, evidence=evidence):
            reason = "Observed input is not file/path-like; bounded path traversal verification was not dispatched"
            finding = VerificationFinding(
                finding_id=f"FIND-PATH-{uuid.uuid4().hex[:8]}", family="PATH_TRAVERSAL",
                classification="INCONCLUSIVE", resource_ref=resource, input_ref=param,
                source_observation_refs=proposal.get("evidence_refs", []),
                verification_action="ACTION-WEB-003", result_evidence_refs=[], confidence=0.3,
                limitations=["Requires an observed file/path-like input before dispatch"], reason=reason,
            )
            artifact = recorder.persist_phase_artifact("action_web_003_verification", {
                "run_id": run_id, "target_id": target_id, "action_id": "ACTION-WEB-003",
                "resource": resource, "parameter": param, "classification": "INCONCLUSIVE",
                "reason": reason, "finding": asdict(finding), "dispatches_made": 0,
            })
            finding.result_evidence_refs = [artifact["evidence_id"]]
            return CapabilityExecutionResult(
                action_id="ACTION-WEB-003", target_id=target_id, outcome="NOT_APPLICABLE",
                classification="INCONCLUSIVE", findings=[finding], network_dispatch_count=0,
                new_facts=[{"fact_id": f"FACT-PATH-{uuid.uuid4().hex[:8]}",
                            "fact_type": "ACTION_OUTCOME", "subject": f"ACTION-WEB-003:{resource}:{param}",
                            "value": "INCONCLUSIVE", "confidence": 1.0}],
                result_evidence_id=artifact["evidence_id"], details={"reason": reason},
            )

        # Construct bounded traversal probe using SAFE sentinel ONLY
        traversal_probe = f"../../../{self.SAFE_SENTINEL}"

        parsed = urllib.parse.urlsplit(resource)
        query_dict = dict(urllib.parse.parse_qsl(parsed.query))
        query_dict[param] = traversal_probe
        encoded_query = urllib.parse.urlencode(query_dict)
        full_path = f"{parsed.path}?{encoded_query}"
        full_url = f"{gate.base_origin}{full_path}"

        req = DiscoveryRequest(
            run_id=run_id,
            target_id=target_id,
            action_id="ACTION-WEB-003",
            url=full_url,
            method="GET",
            approval=approval,
        )
        initial_dispatch_count = gate.network_dispatch_count
        initial_artifact_count = len(recorder.artifacts)
        resp = gate.dispatch(req)
        dispatches_made = gate.network_dispatch_count - initial_dispatch_count
        if gate.halted_due_to_evidence or (
            not resp.durable_confirmed and "EVIDENCE" in (resp.refusal_reason or "")
        ):
            raise EvidenceFailure(resp.refusal_reason or "Gate halted due to evidence failure")

        last_intent_id = None
        last_result_id = None
        # Only artifacts created by this dispatch belong to this probe.
        for art in recorder.artifacts[initial_artifact_count:]:
            ev = art.get("evidence_id", "")
            if ev.startswith("EV-RESULT-"):
                last_result_id = ev
            elif ev.startswith("EV-INTENT-"):
                last_intent_id = ev

        body = resp.body or ""

        # A search page may echo the submitted traversal string. Treat that as
        # a signal only; confirmation requires the sentinel independently of
        # the supplied probe text.
        reflected_probe = traversal_probe in body or urllib.parse.quote(traversal_probe) in body
        # Every conclusion needs a usable control: the endpoint must have
        # answered the probe with HTTP 200. A 5xx, an unfollowed redirect, a
        # 4xx from an unproven control and a truncated body prove nothing, and
        # a sentinel inside such a body is not proof of traversal either.
        eligible_response = (
            resp.outcome == "SUCCESS" and resp.status_code == 200
            and not resp.error_message and not resp.truncated
        )
        if resp.outcome == "DENIED" or resp.refusal_reason:
            # A refusal before dispatch proves nothing about the input.
            classification = "REFUSED"
            reason = "Safety Gate refused bounded path traversal probe: " + (
                resp.refusal_reason or resp.outcome)
        elif (resp.outcome not in {"SUCCESS", "FAILURE"} or resp.error_message
              or not 100 <= resp.status_code <= 599):
            classification = "INCONCLUSIVE"
            reason = "Incomplete response during bounded path traversal probe"
        elif resp.truncated:
            classification = "INCONCLUSIVE"
            reason = "Truncated response during bounded path traversal probe"
        elif not eligible_response:
            classification = "INCONCLUSIVE"
            reason = f"Ineligible HTTP {resp.status_code} response during bounded path traversal probe"
        elif self.SAFE_SENTINEL in body and not reflected_probe:
            classification = "VERIFIED_IN_LAB"
            reason = "Approved lab traversal sentinel was successfully retrieved via traversal sequence"
        elif reflected_probe:
            classification = "SIGNAL"
            reason = "Traversal probe was reflected by the response; sentinel file retrieval was not demonstrated"
        else:
            classification = "NEGATIVE"
            reason = "No sentinel disclosure observed for bounded LAB_TRAVERSAL_SENTINEL fixture probe"

        finding_id = f"FIND-PATH-{uuid.uuid4().hex[:8]}"
        conf = (0.95 if classification == "VERIFIED_IN_LAB"
                else 0.60 if classification == "NEGATIVE" else 0.30)
        finding = VerificationFinding(
            finding_id=finding_id,
            family="PATH_TRAVERSAL",
            classification=classification,
            resource_ref=resource,
            input_ref=param,
            source_observation_refs=proposal.get("evidence_refs", []),
            verification_action="ACTION-WEB-003",
            result_evidence_refs=[last_result_id] if last_result_id else [],
            confidence=conf,
            limitations=["Harmless LAB_TRAVERSAL_SENTINEL probe only; zero host file access (/etc/passwd, win.ini forbidden)"],
            reason=reason,
            path_input_evidence=_has_path_evidence(evidence, resource, param),
        )

        fact = {
            "fact_id": f"FACT-PATH-{uuid.uuid4().hex[:8]}",
            "fact_type": "ACTION_OUTCOME",
            "subject": f"ACTION-WEB-003:{resource}:{param}",
            "value": classification,
            "confidence": finding.confidence,
        }

        art = recorder.persist_phase_artifact("action_web_003_verification", {
            "run_id": run_id,
            "target_id": target_id,
            "action_id": "ACTION-WEB-003",
            "resource": resource,
            "parameter": param,
            "classification": classification,
            "reason": reason,
            "finding": asdict(finding),
            "dispatches_made": dispatches_made,
            "path_input_evidence": _has_path_evidence(evidence, resource, param),
        })

        return CapabilityExecutionResult(
            action_id="ACTION-WEB-003",
            target_id=target_id,
            outcome="DENIED" if classification == "REFUSED" else (
                "FAILURE" if classification == "INCONCLUSIVE" else "SUCCESS"
            ),
            classification=classification,
            findings=[finding],
            new_facts=[fact],
            network_dispatch_count=dispatches_made,
            intent_evidence_id=last_intent_id,
            result_evidence_id=art["evidence_id"],
            details={"reason": reason, "classification": classification},
        )


class SafeBusinessLogicVerificationExecutor(BaseCapabilityExecutor):
    """Executor for ACTION-LOGIC-001 (Safe Business Logic & Transactional Verification).

    Enforces:
      - Bounded verification of business logic flaws:
        * Value tampering / numeric underflow (e.g. quantity = -1, zero, or float)
        * Idempotency & deduplication (replaying duplicate transaction tokens)
        * State consistency under sequential rapid probe
      - ZERO destructive payloads; zero arbitrary code/command injection.
      - All dispatches flow exclusively through CentralizedSafetyGate.
      - Classification: NEGATIVE, SIGNAL, VERIFIED_IN_LAB, INCONCLUSIVE, REFUSED.
    """

    def execute(
        self,
        proposal: dict[str, Any],
        gate: CentralizedSafetyGate,
        recorder: DurableEvidenceRecorder,
        run_id: str,
        target_id: str,
        inventory: InventoryStore,
        approval: ApprovalToken | None,
    ) -> CapabilityExecutionResult:
        resource = proposal.get("resource_ref", "/")
        param = proposal.get("parameter_name", "quantity")

        last_intent_id = None
        last_result_id = None
        result_ids: list[str] = []
        initial_dispatch_count = gate.network_dispatch_count
        dispatches_made = 0
        classification = "INCONCLUSIVE"
        reason = "Incomplete response set during business logic verification probe"

        is_post_form = _probe_form_method(inventory, resource, param) == "POST"
        default_form_fields: dict[str, str] = {}
        request_headers: dict[str, str] = {}
        can_probe = True

        if is_post_form:
            initial_artifact_count = len(recorder.artifacts)
            default_form_fields, request_headers, bootstrap, preparation_error = _prepare_observed_post_form(
                inventory=inventory,
                resource=resource,
                parameter=param,
                action_id="ACTION-LOGIC-001",
                gate=gate,
                run_id=run_id,
                target_id=target_id,
                approval=approval,
            )
            dispatches_made = gate.network_dispatch_count - initial_dispatch_count
            for artifact in recorder.artifacts[initial_artifact_count:]:
                evidence_id = artifact.get("evidence_id", "")
                if evidence_id.startswith("EV-RESULT-"):
                    result_ids.append(evidence_id)
                    last_result_id = evidence_id
                elif evidence_id.startswith("EV-INTENT-"):
                    last_intent_id = evidence_id

            if bootstrap is not None and (gate.halted_due_to_evidence or (
                not bootstrap.durable_confirmed and (
                    bootstrap.outcome != "DENIED" or "EVIDENCE" in (bootstrap.refusal_reason or "")
                )
            )):
                raise EvidenceFailure(bootstrap.refusal_reason or "Gate halted due to evidence failure")

            if preparation_error:
                can_probe = False
                if bootstrap is not None and (bootstrap.outcome == "DENIED" or bootstrap.refusal_reason):
                    classification = "REFUSED"
                    reason = "Safety Gate refused POST form refresh: " + (bootstrap.refusal_reason or bootstrap.outcome)
                else:
                    reason = preparation_error

        # Determine probe vectors based on parameter semantics
        p_lower = param.lower()
        is_numeric_or_quantity = any(k in p_lower for k in ("quantity", "qty", "amount", "count", "num", "balance", "price"))
        is_idempotency = any(k in p_lower for k in ("idempotency", "token", "nonce", "order_key", "ref"))

        vectors: list[tuple[str, str]] = []
        if is_numeric_or_quantity:
            # Boundary underflow & invalid type vectors
            vectors = [
                ("negative_boundary", "-1"),
                ("zero_boundary", "0"),
            ]
        elif is_idempotency:
            fixed_key = f"probe-idemp-{uuid.uuid4().hex[:8]}"
            vectors = [
                ("idempotency_first", fixed_key),
                ("idempotency_duplicate", fixed_key),
            ]
        else:
            # General business logic boundary check
            vectors = [
                ("tamper_boundary", "-1"),
                ("tamper_null", ""),
            ]

        responses: list[tuple[str, str, DispatchResponse]] = []
        for label, vector_val in vectors if can_probe else []:
            initial_count = len(recorder.artifacts)
            if is_post_form:
                payload = dict(default_form_fields)
                payload[param] = vector_val
                clean_path = urllib.parse.urlsplit(resource).path or "/"
                full_url = f"{gate.base_origin}{clean_path}"
                req = DiscoveryRequest(
                    run_id=run_id,
                    target_id=target_id,
                    action_id="ACTION-LOGIC-001",
                    url=full_url,
                    method="POST",
                    headers=request_headers,
                    form=payload,
                    approval=approval,
                )
            else:
                parsed = urllib.parse.urlsplit(resource)
                query_dict = dict(urllib.parse.parse_qsl(parsed.query))
                query_dict[param] = vector_val
                encoded_query = urllib.parse.urlencode(query_dict)
                full_path = f"{parsed.path}?{encoded_query}"
                full_url = f"{gate.base_origin}{full_path}"
                req = DiscoveryRequest(
                    run_id=run_id,
                    target_id=target_id,
                    action_id="ACTION-LOGIC-001",
                    url=full_url,
                    method="GET",
                    approval=approval,
                )

            resp = gate.dispatch(req)
            dispatches_made += 1
            for artifact in recorder.artifacts[initial_count:]:
                evidence_id = artifact.get("evidence_id", "")
                if evidence_id.startswith("EV-RESULT-"):
                    result_ids.append(evidence_id)
                    last_result_id = evidence_id
                elif evidence_id.startswith("EV-INTENT-"):
                    last_intent_id = evidence_id

            if gate.halted_due_to_evidence or (
                not resp.durable_confirmed and (
                    resp.outcome != "DENIED" or "EVIDENCE" in (resp.refusal_reason or "")
                )
            ):
                raise EvidenceFailure(resp.refusal_reason or "Gate halted due to evidence failure")

            responses.append((label, vector_val, resp))

        # Evaluate responses
        if can_probe and responses:
            statuses = [resp.status_code for _, _, resp in responses]

            if any(s == 500 for s in statuses):
                classification = "SIGNAL"
                reason = "Unhandled server error (HTTP 500) observed during business logic boundary probe"
            elif any(resp.outcome == "DENIED" for _, _, resp in responses):
                classification = "REFUSED"
                denied_resp = next(r for _, _, r in responses if r.outcome == "DENIED")
                reason = f"Safety Gate denied business logic probe: {denied_resp.refusal_reason}"
            elif is_numeric_or_quantity:
                # Check negative boundary response
                neg_resps = [r for lbl, _, r in responses if lbl == "negative_boundary"]
                if neg_resps:
                    neg_resp = neg_resps[0]
                    # If target returns success (200/302) and no validation error message
                    if neg_resp.status_code in {200, 302, 303} and not any(err in neg_resp.body.lower() for err in ("invalid", "error", "greater than", "positive", "cannot")):
                        classification = "VERIFIED_IN_LAB"
                        reason = f"Business logic flaw verified: target accepted negative value for parameter {param}"
                    elif neg_resp.status_code in {400, 409, 422} or any(err in neg_resp.body.lower() for err in ("invalid", "error", "must be", "greater than", "cannot")):
                        classification = "NEGATIVE"
                        reason = f"Target correctly validates parameter {param} and rejects negative/invalid boundary"
                    else:
                        classification = "NEGATIVE"
                        reason = f"Target responded with status {neg_resp.status_code} rejecting invalid logic state"
                else:
                    classification = "NEGATIVE"
                    reason = "Target handled numeric boundary values without state anomalies"
            elif is_idempotency:
                idemp_resps = [r for lbl, _, r in responses if lbl.startswith("idempotency_")]
                if len(idemp_resps) >= 2:
                    first, second = idemp_resps[0], idemp_resps[1]
                    first_loc = first.headers.get("location", "")
                    second_loc = second.headers.get("location", "")
                    # Both redirecting to the exact same order or second rejected 409/400
                    if (first_loc and first_loc == second_loc) or second.status_code in {400, 409, 422}:
                        classification = "NEGATIVE"
                        reason = "Idempotency verified: duplicate submission deduplicated to identical resource or rejected"
                    elif first.status_code in {200, 302} and second.status_code in {200, 302} and first_loc != second_loc:
                        classification = "VERIFIED_IN_LAB"
                        reason = f"Broken idempotency verified: identical idempotency key created distinct resources ({first_loc} vs {second_loc})"
                    else:
                        classification = "NEGATIVE"
                        reason = "Target handled duplicate idempotency token safely"
                else:
                    classification = "INCONCLUSIVE"
                    reason = "Insufficient responses to verify idempotency contract"
            else:
                classification = "NEGATIVE"
                reason = "Target enforced input and business logic boundaries safely"

        finding_id = f"FIND-LOGIC-{uuid.uuid4().hex[:8]}"
        conf = 0.95 if classification == "VERIFIED_IN_LAB" else (
            0.85 if classification == "NEGATIVE" else (0.50 if classification in {"INCONCLUSIVE", "REFUSED"} else 0.65)
        )
        finding = VerificationFinding(
            finding_id=finding_id,
            family="BUSINESS_LOGIC",
            classification=classification,
            resource_ref=resource,
            input_ref=param,
            source_observation_refs=proposal.get("evidence_refs", []),
            verification_action="ACTION-LOGIC-001",
            result_evidence_refs=result_ids if result_ids else ([last_result_id] if last_result_id else []),
            confidence=conf,
            limitations=["Bounded business logic verification; zero destructive payload, zero arbitrary code execution"],
            reason=reason,
        )

        fact = {
            "fact_id": f"FACT-LOGIC-{uuid.uuid4().hex[:8]}",
            "fact_type": "ACTION_OUTCOME",
            "subject": f"ACTION-LOGIC-001:{resource}:{param}",
            "value": classification,
            "confidence": finding.confidence,
        }

        art = recorder.persist_phase_artifact("action_logic_001_verification", {
            "run_id": run_id,
            "target_id": target_id,
            "action_id": "ACTION-LOGIC-001",
            "resource": resource,
            "parameter": param,
            "classification": classification,
            "reason": reason,
            "finding": asdict(finding),
            "dispatches_made": dispatches_made,
        })

        return CapabilityExecutionResult(
            action_id="ACTION-LOGIC-001",
            target_id=target_id,
            outcome="DENIED" if classification == "REFUSED" else (
                "FAILURE" if classification == "INCONCLUSIVE" else "SUCCESS"
            ),
            classification=classification,
            findings=[finding],
            new_facts=[fact],
            network_dispatch_count=dispatches_made,
            intent_evidence_id=last_intent_id,
            result_evidence_id=art["evidence_id"],
            details={"reason": reason, "classification": classification},
        )


class CapabilityRegistry:
    """Central registry dispatching action IDs strictly to authorized bounded capability executors."""

    def __init__(self) -> None:
        self._executors: dict[str, BaseCapabilityExecutor] = {
            "ACTION-RECON-001": ReconProbeExecutor(),
            "ACTION-SCAN-001":  PassiveSurfaceAnalyzer(),
            "ACTION-WEB-001":   SafeInputVerificationExecutor(),
            "ACTION-WEB-002":   SafeReflectionVerificationExecutor(),
            "ACTION-WEB-003":   SafePathFixtureVerificationExecutor(),
            "ACTION-LOGIC-001": SafeBusinessLogicVerificationExecutor(),
        }

    def register(self, action_id: str, executor: BaseCapabilityExecutor) -> None:
        self._executors[action_id] = executor

    def get_executor(self, action_id: str) -> BaseCapabilityExecutor | None:
        return self._executors.get(action_id)

    def is_executable(self, action_id: str) -> bool:
        return action_id in self._executors
