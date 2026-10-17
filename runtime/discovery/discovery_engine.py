"""Observation-driven web discovery engine with centralized safety gating.

Flow:
  approved seed
  -> observation
  -> discover candidate
  -> canonicalization
  -> safety/evidence gate
  -> bounded request
  -> normalized observation
  -> evidence
  -> inventory

Guarantees:
  - Zero bypass: all requests pass through CentralizedSafetyGate
  - Observation-driven: no hardcoded endpoint lists
  - Forms discovered as metadata only: zero form submissions
  - Strict same-origin enforcement: off-origin references recorded as refusal, zero dispatch
  - No library auto-follow: redirects gated individually, consuming budget
  - Bounded resource consumption: depth, pages, bytes, rate, timeouts
  - Evidence durable persistence before dispatch and before next scheduling
  - Feeds facts through ObservationNormalizer into StateManager
"""
from __future__ import annotations

import html.parser
import re
import urllib.parse
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

from agent.memory.state.state_manager import StateManager
from agent.perception.normalizers.observation_normalizer import ObservationNormalizer
from runtime.safety.discovery_gate import (
    ApprovalToken,
    CentralizedSafetyGate,
    DiscoveryRequest,
    DispatchResponse,
    _SENSITIVE_QUERY_PARAMS,
    redact_secrets,
)


@dataclass
class FormMetadata:
    action: str
    method: str
    inputs: list[dict[str, Any]]


@dataclass
class InventoryItem:
    canonical_url: str
    path: str
    method: str
    source_observation_id: str
    parent_url: str | None
    depth: int
    status_code: int
    content_type: str
    body_bytes: int
    truncated: bool
    forms: list[dict[str, Any]]
    links_found: list[str]
    redirect_to: str | None
    discovered_at_utc: str
    redacted: bool
    refusal_reason: str | None = None
    coverage_limitations: str = "Bounded discovery: unauthenticated public surface, depth-limited, zero form submissions"


class HTMLMetadataParser(html.parser.HTMLParser):
    """Safe, non-executing HTML metadata parser extracting links and form metadata."""

    def __init__(self, current_url: str) -> None:
        super().__init__()
        self.current_url = current_url
        self.links: list[str] = []
        self.forms: list[FormMetadata] = []
        self._current_form: FormMetadata | None = None
        self._current_select: dict[str, Any] | None = None
        self._disabled_optgroup = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        attr_dict = {k.lower(): (v or "") for k, v in attrs}

        if tag_lower == "a":
            href = attr_dict.get("href", "").strip()
            if href and not href.startswith("#"):
                self.links.append(href)

        elif tag_lower == "form":
            self._current_select = None
            action = attr_dict.get("action", "").strip()
            method = attr_dict.get("method", "GET").upper().strip()
            self._current_form = FormMetadata(
                action=action,
                method=method,
                inputs=[],
            )

        elif tag_lower in ("input", "textarea", "select", "button") and self._current_form is not None:
            if tag_lower == "select":
                self._current_select = None
                self._disabled_optgroup = False
            name = attr_dict.get("name", "").strip()
            input_type = attr_dict.get("type", "text" if tag_lower == "input" else tag_lower).strip()
            if name:
                self._current_form.inputs.append({
                    "name": name,
                    "type": input_type,
                })
                if tag_lower == "select":
                    sensitive = name.lower() in _SENSITIVE_QUERY_PARAMS or any(
                        part in name.lower() for part in ("token", "session", "password", "secret", "csrf"))
                    if self._current_form.method == "GET" and not sensitive and not {"disabled", "multiple"} & attr_dict.keys():
                        self._current_select = self._current_form.inputs[-1]
                        self._current_select["options"] = []

        elif tag_lower == "optgroup":
            self._disabled_optgroup = "disabled" in attr_dict
        elif tag_lower == "option" and self._current_select is not None:
            options = self._current_select["options"]
            value = attr_dict.get("value")
            # ponytail: explicit values only, 16 per select; label-derived and multi-select values need separate support.
            if ("disabled" not in attr_dict and not self._disabled_optgroup and value is not None
                    and len(value) <= 128
                    and not any(ord(c) < 32 or ord(c) == 127 for c in value)
                    and redact_secrets(value) == value):
                if len(options) < 16:
                    options.append({"value": value, "selected": "selected" in attr_dict})
                else:
                    self._current_select["options_truncated"] = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in ("select", "form"):
            self._current_select = None
        if tag.lower() == "optgroup":
            self._disabled_optgroup = False
        if tag.lower() == "form" and self._current_form is not None:
            self.forms.append(self._current_form)
            self._current_form = None


class InventoryStore:
    """Traceable store for discovered web resources and refusal provenance."""

    def __init__(self) -> None:
        self.items: dict[str, InventoryItem] = {}
        self.refusals: list[dict[str, Any]] = []

    def record_item(self, item: InventoryItem) -> None:
        if item.canonical_url in self.items:
            # Merge links and forms if already visited from a different parent
            existing = self.items[item.canonical_url]
            for lnk in item.links_found:
                if lnk not in existing.links_found:
                    existing.links_found.append(lnk)
            for form in item.forms:
                if form not in existing.forms:
                    existing.forms.append(form)
        else:
            self.items[item.canonical_url] = item

    def record_refusal(
        self,
        candidate_url: str,
        reason: str,
        parent_url: str | None,
        depth: int,
        observation_id: str,
    ) -> None:
        self.refusals.append({
            "candidate_url": candidate_url,
            "refusal_reason": reason,
            "parent_url": parent_url,
            "depth": depth,
            "source_observation_id": observation_id,
            "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        })

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_count": len(self.items),
            "refusal_count": len(self.refusals),
            "items": [asdict(item) for item in self.items.values()],
            "refusals": list(self.refusals),
        }


@dataclass
class DiscoveryRunResult:
    run_id: str
    target_id: str
    seed_url: str
    inventory: InventoryStore
    normalized_observations: list[dict[str, Any]]
    final_state: dict[str, Any]
    network_dispatch_count: int
    forbidden_dispatch_count: int
    form_submission_count: int
    durable_confirmed: bool
    status: str
    stop_reason: str


class ObservationDrivenDiscovery:
    """Core discovery orchestrator executing observation-driven BFS crawl through the safety gate."""

    def __init__(
        self,
        gate: CentralizedSafetyGate,
        run_id: str,
        target_id: str,
        approval: ApprovalToken,
        action_id: str = "ACTION-RECON-002",
        normalizer: ObservationNormalizer | None = None,
        state_manager: StateManager | None = None,
    ) -> None:
        self.gate = gate
        self.run_id = run_id
        self.target_id = target_id
        self.approval = approval
        self.action_id = action_id
        self.normalizer = normalizer or ObservationNormalizer()
        self.state_manager = state_manager
        self.inventory = InventoryStore()
        self.observations: list[dict[str, Any]] = []

    def run(self, seed_path: str = "/") -> DiscoveryRunResult:
        """Run observation-driven discovery starting from approved seed."""
        # Initial canonical seed URL
        canon_seed = self.gate.canonicalizer.canonicalize(seed_path)
        if not canon_seed.is_valid:
            return DiscoveryRunResult(
                run_id=self.run_id,
                target_id=self.target_id,
                seed_url=seed_path,
                inventory=self.inventory,
                normalized_observations=[],
                final_state=self.state_manager.get_state() if self.state_manager is not None else {},
                network_dispatch_count=self.gate.network_dispatch_count,
                forbidden_dispatch_count=self.gate.forbidden_dispatch_count,
                form_submission_count=self.gate.form_submission_count,
                durable_confirmed=False,
                status="FAILED",
                stop_reason=f"INVALID_SEED: {canon_seed.reason}",
            )

        # Candidate queue: (url, depth, parent_url, redirect_hops)
        queue: list[tuple[str, int, str | None, int]] = [(canon_seed.canonical_url, 0, None, 0)]
        visited_urls: set[str] = set()
        durable_confirmed = True
        stop_reason = "QUEUE_EXHAUSTED"

        while queue:
            # Check gate halt flag (e.g. evidence writer failure)
            if self.gate.halted_due_to_evidence:
                durable_confirmed = False
                stop_reason = "HALTED_EVIDENCE_FAILURE"
                break

            # Check kill switch
            if self.gate.kill_switch.is_active():
                stop_reason = "KILL_SWITCH_ACTIVE"
                break

            # Check budget limits
            if not self.gate.budget_tracker.can_request() or self.gate.budget_tracker.pages_visited >= self.gate.budget_tracker.max_pages:
                stop_reason = "BUDGET_EXHAUSTED"
                break

            candidate_url, depth, parent_url, redirect_hops = queue.pop(0)

            # Deduplication
            if candidate_url in visited_urls:
                continue

            # Depth limit check
            if depth > self.gate.budget_tracker.max_depth:
                continue

            # Dispatch through centralized safety gate
            req = DiscoveryRequest(
                run_id=self.run_id,
                target_id=self.target_id,
                action_id=self.action_id,
                url=candidate_url,
                method="GET",
                approval=self.approval,
                depth=depth,
                redirect_hops=redirect_hops,
            )

            resp = self.gate.dispatch(req)
            obs_id = f"OBS-DISC-{uuid.uuid4().hex}"

            if not resp.durable_confirmed and resp.refusal_reason in ("INTENT_EVIDENCE_WRITE_FAILED", "RESULT_EVIDENCE_WRITE_FAILED"):
                durable_confirmed = False
                stop_reason = f"EVIDENCE_FAILURE: {resp.refusal_reason}"
                break

            # Handle gate refusal (e.g. off-origin, bad scheme)
            if resp.outcome == "DENIED":
                self.inventory.record_refusal(
                    candidate_url=candidate_url,
                    reason=resp.refusal_reason or "DENIED",
                    parent_url=parent_url,
                    depth=depth,
                    observation_id=obs_id,
                )
                continue

            # Mark visited
            visited_urls.add(candidate_url)
            self.gate.budget_tracker.pages_visited += 1

            # Parse path for inventory
            parsed = urllib.parse.urlsplit(resp.canonical_url)
            resource_path = parsed.path + (f"?{parsed.query}" if parsed.query else "")

            # Handle redirects (301, 302, 303, 307, 308)
            redirect_to = None
            if resp.status_code in (301, 302, 303, 307, 308):
                loc = resp.headers.get("Location") or resp.headers.get("location")
                if loc:
                    # Canonicalize redirect target
                    canon_loc = self.gate.canonicalizer.canonicalize(loc, current_url=candidate_url)
                    if canon_loc.is_same_origin and canon_loc.is_valid:
                        redirect_to = canon_loc.canonical_url
                        if redirect_hops + 1 <= self.gate.budget_tracker.max_redirect_hops:
                            # Prioritize redirect candidate at same depth with incremented hop counter
                            queue.insert(0, (canon_loc.canonical_url, depth, candidate_url, redirect_hops + 1))
                        else:
                            self.inventory.record_refusal(
                                candidate_url=canon_loc.canonical_url,
                                reason="REDIRECT_MAX_HOPS_EXHAUSTED",
                                parent_url=candidate_url,
                                depth=depth,
                                observation_id=obs_id,
                            )
                    else:
                        # Off-origin redirect or invalid redirect: record refusal, zero dispatch!
                        self.inventory.record_refusal(
                            candidate_url=loc,
                            reason=canon_loc.reason or "REFUSED_OFF_ORIGIN_REDIRECT",
                            parent_url=candidate_url,
                            depth=depth,
                            observation_id=obs_id,
                        )

            # Extract links and forms if HTML response
            content_type = resp.headers.get("Content-Type") or resp.headers.get("content-type") or ""
            links_extracted: list[str] = []
            forms_extracted: list[dict[str, Any]] = []

            if "text/html" in content_type.lower() and resp.body:
                parser = HTMLMetadataParser(current_url=candidate_url)
                try:
                    parser.feed(resp.body)
                except Exception:
                    pass  # Non-fatal HTML parsing irregularity

                # Process links
                for raw_link in parser.links:
                    canon_link = self.gate.canonicalizer.canonicalize(raw_link, current_url=candidate_url)
                    if canon_link.is_same_origin and canon_link.is_valid:
                        links_extracted.append(canon_link.canonical_url)
                        if (depth + 1 <= self.gate.budget_tracker.max_depth) and (canon_link.canonical_url not in visited_urls):
                            queue.append((canon_link.canonical_url, depth + 1, candidate_url, 0))
                    else:
                        # Off-origin link found in HTML: record refusal metadata, zero network dispatch!
                        self.inventory.record_refusal(
                            candidate_url=raw_link,
                            reason=canon_link.reason or "REFUSED_OFF_ORIGIN",
                            parent_url=candidate_url,
                            depth=depth + 1,
                            observation_id=obs_id,
                        )

                # Process forms (RECORD METADATA ONLY — NEVER SUBMIT)
                for form in parser.forms:
                    canon_action = self.gate.canonicalizer.canonicalize(form.action or candidate_url, current_url=candidate_url)
                    forms_extracted.append({
                        "action": canon_action.canonical_url if canon_action.is_valid else (form.action or candidate_url),
                        "method": form.method,
                        "inputs": form.inputs,
                        "is_same_origin": canon_action.is_same_origin,
                    })

            # Record item in inventory
            inv_item = InventoryItem(
                canonical_url=resp.canonical_url,
                path=resource_path,
                method=req.method,
                source_observation_id=obs_id,
                parent_url=parent_url,
                depth=depth,
                status_code=resp.status_code,
                content_type=content_type,
                body_bytes=resp.raw_bytes_len,
                truncated=resp.truncated,
                forms=forms_extracted,
                links_found=links_extracted,
                redirect_to=redirect_to,
                discovered_at_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                redacted=True,
                refusal_reason=None,
            )
            self.inventory.record_item(inv_item)

            # Normalize observation via ObservationNormalizer
            scanner_results = [{
                "source": "DISCOVERY",
                "target_id": self.target_id,
                "finding_type": "endpoint",
                "endpoint_id": resource_path,
                "confidence": 1.0,
            }]
            norm_obs = self.normalizer.normalize(
                scanner_results=scanner_results,
                run_id=self.run_id,
                action_id=self.action_id,
                observation_id=obs_id,
            )
            self.observations.append(norm_obs)

            # Ingest into StateManager ONLY if an explicit state_manager was provided
            # (e.g. standalone discovery callers).
            # When state_manager is None (coordinator/adapter-owned ingestion), discovery acts
            # strictly as an observation producer, leaving ingestion to PlannerStateAdapter.
            if self.state_manager is not None:
                self.state_manager.apply_observation(norm_obs)

        return DiscoveryRunResult(
            run_id=self.run_id,
            target_id=self.target_id,
            seed_url=canon_seed.canonical_url,
            inventory=self.inventory,
            normalized_observations=self.observations,
            final_state=self.state_manager.get_state() if self.state_manager is not None else {},
            network_dispatch_count=self.gate.network_dispatch_count,
            forbidden_dispatch_count=self.gate.forbidden_dispatch_count,
            form_submission_count=self.gate.form_submission_count,
            durable_confirmed=durable_confirmed,
            status=(
                "COMPLETED_BOUNDED" if (durable_confirmed and stop_reason == "BUDGET_EXHAUSTED")
                else "COMPLETED" if (durable_confirmed and stop_reason == "QUEUE_EXHAUSTED")
                else "STOPPED"
            ),
            stop_reason=stop_reason,
        )
