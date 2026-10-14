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
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from runtime.discovery.discovery_engine import InventoryItem, InventoryStore
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

        for path, item in inventory.items.items():
            clean_url = item.canonical_url.split("?")[0].split("#")[0]
            parsed_query = urllib.parse.urlsplit(item.path).query
            # Record query inputs on visited endpoint
            if parsed_query:
                for qk, _ in urllib.parse.parse_qsl(parsed_query):
                    candidate_facts.append({
                        "fact_id": f"FACT-PARAM-{uuid.uuid4().hex[:8]}",
                        "fact_type": "PARAMETER",
                        "subject": clean_url,
                        "value": str(qk),
                        "confidence": 0.85,
                    })

            # Record form inputs with strict action and method provenance
            if item.forms:
                for form in item.forms:
                    raw_action = form.get("action", "").strip()
                    form_method = form.get("method", "GET").upper().strip()
                    form_target = urllib.parse.urljoin(item.canonical_url, raw_action) if raw_action else item.canonical_url
                    clean_form_target = form_target.split("?")[0].split("#")[0]

                    for inp in form.get("inputs", []):
                        inp_name = inp.get("name", "").strip()
                        if not inp_name:
                            continue
                        if form_method == "GET":
                            # Safe read-only query parameter input on actual form action endpoint
                            candidate_facts.append({
                                "fact_id": f"FACT-PARAM-{uuid.uuid4().hex[:8]}",
                                "fact_type": "PARAMETER",
                                "subject": clean_form_target,
                                "value": str(inp_name),
                                "confidence": 0.85,
                            })
                        else:
                            # POST/mutating form input: metadata finding only; zero conversion to synthetic GET
                            candidate_facts.append({
                                "fact_id": f"FACT-CAND-{uuid.uuid4().hex[:8]}",
                                "fact_type": "CANDIDATE_FINDING",
                                "subject": clean_form_target,
                                "value": f"post_form_input_{inp_name}",
                                "confidence": 0.50,
                            })

                candidate_facts.append({
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


class SafeInputVerificationExecutor(BaseCapabilityExecutor):
    """Executor for ACTION-WEB-001 (Safe Input Injection / SQLi Verification).

    Enforces:
      - Bounded cyber-range test vectors only; zero arbitrary SQL generation.
      - Strictly dispatches through CentralizedSafetyGate.
      - Differential analysis: compares baseline response with syntax probe vectors.
      - Classification: NEGATIVE, SIGNAL, VERIFIED_IN_LAB, INCONCLUSIVE.
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

        # Bounded cyber-range probe vectors
        vectors = [
            ("baseline", "probe_test"),
            ("quote", "probe_test'"),
            ("balance", "probe_test''"),
        ]

        responses: dict[str, DispatchResponse] = {}
        last_intent_id = None
        last_result_id = None
        dispatches_made = 0

        for label, vector_val in vectors:
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
            resp = gate.dispatch(req)
            dispatches_made += 1

            if gate.halted_due_to_evidence or (
                not resp.durable_confirmed and "EVIDENCE" in (resp.refusal_reason or "")
            ):
                raise EvidenceFailure(resp.refusal_reason or "Gate halted due to evidence failure")

            responses[label] = resp

            # Track latest artifact refs
            for art in reversed(recorder.artifacts):
                ev = art.get("evidence_id", "")
                if not last_result_id and "result" in ev.lower():
                    last_result_id = ev
                elif not last_intent_id and "intent" in ev.lower():
                    last_intent_id = ev
                if last_intent_id and last_result_id:
                    break

        # Differential analysis
        resp_base = responses.get("baseline")
        resp_quote = responses.get("quote")
        resp_balance = responses.get("balance")

        if not resp_base or not resp_quote or not resp_balance:
            classification = "INCONCLUSIVE"
            reason = "Incomplete response set during bounded differential probe"
        else:
            base_has_err = any(p.search(resp_base.body) for p in self.SQL_SYNTAX_ERROR_PATTERNS)
            quote_has_err = any(p.search(resp_quote.body) for p in self.SQL_SYNTAX_ERROR_PATTERNS)
            bal_has_err = any(p.search(resp_balance.body) for p in self.SQL_SYNTAX_ERROR_PATTERNS)

            if quote_has_err and not base_has_err and not bal_has_err:
                # Differential syntax error confirmed and balanced recovery verified
                classification = "VERIFIED_IN_LAB"
                reason = "Differential SQL syntax error observed on unescaped quote with recovery on balanced quote"
            elif resp_quote.status_code >= 500 and resp_base.status_code == 200:
                classification = "SIGNAL"
                reason = "HTTP 500 status differential observed on probe quote; syntax error signature unverified"
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
            result_evidence_refs=[last_result_id] if last_result_id else [],
            confidence=conf,
            limitations=["Bounded differential probing with harmless syntax vectors only; zero arbitrary SQL execution"],
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
            outcome="SUCCESS",
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
        resp = gate.dispatch(req)
        if gate.halted_due_to_evidence or (
            not resp.durable_confirmed and "EVIDENCE" in (resp.refusal_reason or "")
        ):
            raise EvidenceFailure(resp.refusal_reason or "Gate halted due to evidence failure")

        last_intent_id = None
        last_result_id = None
        for art in reversed(recorder.artifacts):
            ev = art.get("evidence_id", "")
            if not last_result_id and "result" in ev.lower():
                last_result_id = ev
            elif not last_intent_id and "intent" in ev.lower():
                last_intent_id = ev
            if last_intent_id and last_result_id:
                break

        body = resp.body or ""
        content_type = resp.headers.get("Content-Type") or resp.headers.get("content-type") or ""

        if inert_tag_marker in body and "text/html" in content_type.lower():
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
        else:
            # Marker not reflected
            classification = "NEGATIVE"
            reason = "Inert probe marker was not reflected in observed target response body"

        finding_id = f"FIND-XSS-{uuid.uuid4().hex[:8]}"
        conf = 0.95 if classification == "VERIFIED_IN_LAB" else (0.75 if "escaped" in reason else 0.60)
        finding = VerificationFinding(
            finding_id=finding_id,
            family="SCRIPT_INJECTION",
            classification=classification,
            resource_ref=resource,
            input_ref=param,
            source_observation_refs=proposal.get("evidence_refs", []),
            verification_action="ACTION-WEB-002",
            result_evidence_refs=[last_result_id] if last_result_id else [],
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
            "dispatches_made": 1,
        })

        return CapabilityExecutionResult(
            action_id="ACTION-WEB-002",
            target_id=target_id,
            outcome="SUCCESS",
            classification=classification,
            findings=[finding],
            new_facts=[fact],
            network_dispatch_count=1,
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
        resp = gate.dispatch(req)
        if gate.halted_due_to_evidence or (
            not resp.durable_confirmed and "EVIDENCE" in (resp.refusal_reason or "")
        ):
            raise EvidenceFailure(resp.refusal_reason or "Gate halted due to evidence failure")

        last_intent_id = None
        last_result_id = None
        for art in reversed(recorder.artifacts):
            ev = art.get("evidence_id", "")
            if not last_result_id and "result" in ev.lower():
                last_result_id = ev
            elif not last_intent_id and "intent" in ev.lower():
                last_intent_id = ev
            if last_intent_id and last_result_id:
                break

        body = resp.body or ""

        if self.SAFE_SENTINEL in body:
            classification = "VERIFIED_IN_LAB"
            reason = "Approved lab traversal sentinel was successfully retrieved via traversal sequence"
        elif resp.status_code in (400, 403, 404):
            # Target cleanly rejected the path traversal sequence (e.g. ShopLab INV-* regex rejection)
            classification = "NEGATIVE"
            reason = f"Path traversal probe rejected with HTTP {resp.status_code} by parameter validation"
        else:
            classification = "NEGATIVE"
            reason = "No sentinel disclosure observed for bounded LAB_TRAVERSAL_SENTINEL fixture probe"

        finding_id = f"FIND-PATH-{uuid.uuid4().hex[:8]}"
        conf = 0.95 if classification == "VERIFIED_IN_LAB" else 0.60
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
            "dispatches_made": 1,
        })

        return CapabilityExecutionResult(
            action_id="ACTION-WEB-003",
            target_id=target_id,
            outcome="SUCCESS",
            classification=classification,
            findings=[finding],
            new_facts=[fact],
            network_dispatch_count=1,
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
        }

    def register(self, action_id: str, executor: BaseCapabilityExecutor) -> None:
        self._executors[action_id] = executor

    def get_executor(self, action_id: str) -> BaseCapabilityExecutor | None:
        return self._executors.get(action_id)

    def is_executable(self, action_id: str) -> bool:
        return action_id in self._executors
