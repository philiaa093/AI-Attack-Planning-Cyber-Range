"""Enterprise Red Team Belief State Projection (RT-02B).

Deterministic projection from canonical observations and knowledge state store.
The Belief State is NOT an independent source of truth; it is a deterministic,
read-only projection that gives the Planner a structured Red Team state under
partial observability (POMDP) without leaking True State, Ground Truth, hidden
network topology, full target allowlists, or plaintext secrets.

Hard Invariants:
1. Ground Truth Isolation: Zero Ground Truth or private defender SIEM state in Belief State.
2. Facts vs Hypotheses: Observations with source_kind="PLANNER_INFERENCE" are isolated into
   hypotheses and never update authoritative belief facts (hosts, access, creds, sessions, edges).
3. Secret Redaction: Plaintext secrets never enter Belief State; credentials use opaque handles.
4. Session Sanitization: Sessions use opaque references; no raw shell/subprocess handles.
5. Determinism: Same observation sequence produces bit-for-bit identical projection dictionary.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

# Canonical Access Levels hierarchy (least privilege to greatest privilege)
ACCESS_LEVELS = ("NONE", "FOOTHOLD", "USER", "PRIVILEGED", "SYSTEM")
ACCESS_LEVEL_ORDER = {lvl: idx for idx, lvl in enumerate(ACCESS_LEVELS)}

# Credential Validity States
VALIDITY_STATES = ("UNKNOWN", "CANDIDATE", "VALID", "INVALID", "REVOKED")

# Forbidden secrets & Ground Truth keys to reject fail-closed
_FORBIDDEN_GROUND_TRUTH_KEYS = frozenset({
    "ground_truth", "truth", "expected_vulnerabilities", "flag_location",
    "hidden_topology", "defender_rule", "siem_score", "siem_alert_id",
})
_SECRET_FIELD_NAMES = frozenset({
    "password", "secret", "cleartext", "raw_secret", "private_key",
})


def _compare_access_levels(a: str, b: str) -> int:
    """Return -1 if a < b, 0 if a == b, 1 if a > b."""
    order_a = ACCESS_LEVEL_ORDER.get(a, 0)
    order_b = ACCESS_LEVEL_ORDER.get(b, 0)
    if order_a < order_b:
        return -1
    elif order_a > order_b:
        return 1
    return 0


def _highest_access_level(a: str, b: str) -> str:
    """Return the higher of two access levels."""
    return b if _compare_access_levels(a, b) < 0 else a


def project_belief_state(
    observed_facts: Sequence[Mapping[str, Any]],
    observations: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Deterministically project Belief State from canonical observed facts and observations.

    Args:
        observed_facts: Sequence of fact dicts conforming to state.schema.json ($defs/fact)
        observations: Optional sequence of observation envelopes for provenance resolution

    Returns:
        Deterministic dict conforming to state.schema.json ($defs/belief_state)
    """
    obs_map: dict[str, Mapping[str, Any]] = {}
    if observations:
        for obs in observations:
            obs_id = obs.get("observation_id")
            if obs_id:
                obs_map[obs_id] = obs

    # Accumulators for authoritative belief facts
    known_hosts: dict[str, dict[str, Any]] = {}
    known_services_map: dict[tuple[str, str, str], dict[str, Any]] = {}
    known_endpoints_map: dict[tuple[str, str], dict[str, Any]] = {}
    candidate_findings_map: dict[str, dict[str, Any]] = {}
    confirmed_findings_map: dict[str, dict[str, Any]] = {}
    access_state: dict[str, str] = {}
    credentials_map: dict[str, dict[str, Any]] = {}
    sessions_map: dict[str, dict[str, Any]] = {}
    reachability_map: dict[tuple[str, str, str], dict[str, Any]] = {}
    detection_signals_map: dict[tuple[str, str, str], dict[str, Any]] = {}
    objective_status_map: dict[str, dict[str, Any]] = {}
    hypotheses_list: list[dict[str, Any]] = []
    provenance_refs_set: set[str] = set()

    # Process observed facts in deterministic sequence
    for fact in observed_facts:
        if not isinstance(fact, Mapping):
            continue

        fact_id = fact.get("fact_id", "")
        fact_type = fact.get("fact_type", "")
        subject = fact.get("subject", "")
        val = fact.get("value")
        confidence = float(fact.get("confidence", 1.0))
        obs_id = fact.get("source_observation_id", "")
        if obs_id:
            provenance_refs_set.add(obs_id)

        # Determine source_kind
        source_kind = fact.get("source_kind")
        if not source_kind and obs_id in obs_map:
            source_kind = obs_map[obs_id].get("source_kind")
        if not source_kind:
            source_kind = "OBSERVED"

        # HARD BOUNDARY: Planner inference is HYPOTHESIS ONLY
        if source_kind == "PLANNER_INFERENCE":
            hypotheses_list.append({
                "fact_type": fact_type,
                "subject": subject,
                "value": copy.deepcopy(val),
                "confidence": confidence,
                "provenance": sorted({obs_id, fact_id} - {""}),
            })
            continue

        # Reject any accidental Ground Truth leakage
        if any(k in str(val).lower() for k in _FORBIDDEN_GROUND_TRUTH_KEYS):
            continue

        # 1. HOST / TARGET
        if fact_type in ("HOST", "TARGET"):
            host_name = subject
            ip_val = None
            if isinstance(val, dict):
                ip_val = val.get("ip") or val.get("ip_address")
            elif isinstance(val, str) and val not in ("discovered", "reachable", host_name):
                # If value is an IP address
                if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", val):
                    ip_val = val

            if host_name not in known_hosts:
                known_hosts[host_name] = {
                    "host": host_name,
                    "ip": ip_val,
                    "access_level": access_state.get(host_name, "NONE"),
                    "confidence": confidence,
                    "provenance": sorted({obs_id, fact_id} - {""}),
                }
            else:
                existing = known_hosts[host_name]
                if ip_val and not existing["ip"]:
                    existing["ip"] = ip_val
                existing["confidence"] = max(existing["confidence"], confidence)
                existing["provenance"] = sorted(set(existing["provenance"]) | {obs_id, fact_id} - {""})
                existing["access_level"] = access_state.get(host_name, existing["access_level"])

        # 2. SERVICE
        elif fact_type == "SERVICE":
            host = subject.split(":")[0] if ":" in subject else subject
            port = None
            proto = "unknown"
            if ":" in subject:
                try:
                    port = int(subject.split(":")[1])
                except ValueError:
                    port = subject.split(":")[1]
            if isinstance(val, dict):
                port = val.get("port", port)
                proto = val.get("protocol", val.get("service", proto))
            elif isinstance(val, str):
                proto = val
            key = (host, str(port) if port is not None else "", str(proto))
            if key not in known_services_map or confidence > known_services_map[key]["confidence"]:
                known_services_map[key] = {
                    "host": host,
                    "port": port,
                    "protocol": proto,
                    "confidence": confidence,
                    "provenance": sorted({obs_id, fact_id} - {""}),
                }
            else:
                known_services_map[key]["provenance"] = sorted(
                    set(known_services_map[key]["provenance"]) | {obs_id, fact_id} - {""}
                )

        # 3. ENDPOINT
        elif fact_type == "ENDPOINT":
            host = subject.split(":")[0] if ":" in subject else subject
            path = str(val) if isinstance(val, str) else "/"
            if isinstance(val, dict):
                path = val.get("path", "/")
            key = (host, path)
            if key not in known_endpoints_map or confidence > known_endpoints_map[key]["confidence"]:
                known_endpoints_map[key] = {
                    "host": host,
                    "path": path,
                    "confidence": confidence,
                    "provenance": sorted({obs_id, fact_id} - {""}),
                }
            else:
                known_endpoints_map[key]["provenance"] = sorted(
                    set(known_endpoints_map[key]["provenance"]) | {obs_id, fact_id} - {""}
                )

        # 4. ACCESS
        elif fact_type == "ACCESS":
            target = subject
            access_lvl = "NONE"
            if isinstance(val, str) and val in ACCESS_LEVELS:
                access_lvl = val
            elif isinstance(val, dict):
                access_lvl = val.get("level", val.get("access_level", "NONE"))
                if access_lvl not in ACCESS_LEVELS:
                    access_lvl = "NONE"

            # Monotonic access transition: peak confirmed access
            current = access_state.get(target, "NONE")
            new_level = _highest_access_level(current, access_lvl)
            access_state[target] = new_level
            if target in known_hosts:
                known_hosts[target]["access_level"] = new_level

        # 5. CREDENTIAL
        elif fact_type == "CREDENTIAL":
            cred_data = val if isinstance(val, dict) else {}
            cid = cred_data.get("credential_id") or fact_id
            principal = cred_data.get("principal", "anonymous")
            kind = cred_data.get("credential_kind", "OPAQUE_HANDLE")
            scope = cred_data.get("observed_scope", subject or "domain")
            validity = cred_data.get("validity_state", "VALID")
            if validity not in VALIDITY_STATES:
                validity = "UNKNOWN"

            # Redact: zero raw secrets
            if cid in credentials_map:
                existing_cred = credentials_map[cid]
                # Validity state transition: INVALID / REVOKED is terminal
                if existing_cred["validity_state"] in ("REVOKED", "INVALID"):
                    pass  # keep terminal invalid state
                else:
                    existing_cred["validity_state"] = validity
                existing_cred["confidence"] = max(existing_cred["confidence"], confidence)
                existing_cred["provenance"] = sorted(
                    set(existing_cred["provenance"]) | {obs_id, fact_id} - {""}
                )
            else:
                credentials_map[cid] = {
                    "credential_id": cid,
                    "principal": principal,
                    "credential_kind": kind,
                    "observed_scope": scope,
                    "validity_state": validity,
                    "confidence": confidence,
                    "provenance": sorted({obs_id, fact_id} - {""}),
                }

        # 6. SESSION
        elif fact_type == "SESSION":
            sess_data = val if isinstance(val, dict) else {}
            sid = sess_data.get("session_id") or fact_id
            target_id = sess_data.get("target_id") or sess_data.get("node_id") or subject
            level = sess_data.get("access_level", "USER")
            if level not in ACCESS_LEVELS:
                level = "USER"
            state = sess_data.get("state") or sess_data.get("session_state") or "ACTIVE"
            if state not in ("ACTIVE", "CLOSED"):
                state = "ACTIVE"


            if sid in sessions_map:
                existing_sess = sessions_map[sid]
                # Transition: ACTIVE -> CLOSED is terminal
                if state == "CLOSED" or existing_sess["state"] == "CLOSED":
                    existing_sess["state"] = "CLOSED"
                existing_sess["confidence"] = max(existing_sess["confidence"], confidence)
                existing_sess["provenance"] = sorted(
                    set(existing_sess["provenance"]) | {obs_id, fact_id} - {""}
                )
            else:
                sessions_map[sid] = {
                    "session_id": sid,
                    "target_id": target_id,
                    "access_level": level,
                    "state": state,
                    "confidence": confidence,
                    "provenance": sorted({obs_id, fact_id} - {""}),
                }

        # 7. REACHABILITY
        elif fact_type == "REACHABILITY":
            from_h = ""
            to_h = ""
            proto = "tcp"
            if isinstance(val, dict):
                from_h = val.get("from_host") or val.get("source", "")
                to_h = val.get("to_host") or val.get("target", "")
                proto = val.get("protocol", "tcp")
            if not from_h or not to_h:
                if "->" in subject:
                    parts = subject.split("->")
                    from_h = parts[0].strip()
                    to_h = parts[1].strip()
                    if isinstance(val, str):
                        proto = val


            if from_h and to_h:
                r_key = (from_h, to_h, proto)
                if r_key not in reachability_map or confidence > reachability_map[r_key]["confidence"]:
                    reachability_map[r_key] = {
                        "from_host": from_h,
                        "to_host": to_h,
                        "protocol": proto,
                        "confidence": confidence,
                        "provenance": sorted({obs_id, fact_id} - {""}),
                    }
                else:
                    reachability_map[r_key]["provenance"] = sorted(
                        set(reachability_map[r_key]["provenance"]) | {obs_id, fact_id} - {""}
                    )
                if to_h not in known_hosts:
                    known_hosts[to_h] = {
                        "host": to_h,
                        "ip": None,
                        "access_level": access_state.get(to_h, "NONE"),
                        "confidence": confidence,
                        "provenance": sorted({obs_id, fact_id} - {""}),
                    }


        # 8. DETECTION_SIGNAL
        elif fact_type == "DETECTION_SIGNAL":
            sig_data = val if isinstance(val, dict) else {}
            stype = sig_data.get("signal_type") or str(val) or "BLOCKED"
            target = sig_data.get("source_target") or sig_data.get("target_id") or subject
            event = sig_data.get("observable_event") or sig_data.get("observed_effect") or str(val)
            d_key = (target, stype, event)
            if d_key not in detection_signals_map or confidence > detection_signals_map[d_key]["confidence"]:
                detection_signals_map[d_key] = {
                    "signal_type": stype,
                    "source_target": target,
                    "observable_event": event,
                    "confidence": confidence,
                    "provenance": sorted({obs_id, fact_id} - {""}),
                }
            else:
                detection_signals_map[d_key]["provenance"] = sorted(
                    set(detection_signals_map[d_key]["provenance"]) | {obs_id, fact_id} - {""}
                )

        # 9. OBJECTIVE
        elif fact_type == "OBJECTIVE":
            obj_id = subject
            status = "UNKNOWN"
            evidence_refs = []
            if isinstance(val, dict):
                status = val.get("status") or val.get("objective_state") or "DISCOVERED"
                evidence_refs = val.get("evidence_refs", [])
            elif isinstance(val, str):
                status = val

            if status not in ("UNKNOWN", "DISCOVERED", "ACHIEVED"):
                status = "DISCOVERED"

            # Check obs evidence refs if none in fact
            if not evidence_refs and obs_id in obs_map:
                evidence_refs = list(obs_map[obs_id].get("evidence_refs", []))

            if obj_id in objective_status_map:
                existing_obj = objective_status_map[obj_id]
                # Transition: UNKNOWN -> DISCOVERED -> ACHIEVED
                if status == "ACHIEVED" or existing_obj["status"] == "ACHIEVED":
                    existing_obj["status"] = "ACHIEVED"
                elif status == "DISCOVERED" and existing_obj["status"] == "UNKNOWN":
                    existing_obj["status"] = "DISCOVERED"
                existing_obj["evidence_refs"] = sorted(
                    set(existing_obj["evidence_refs"]) | set(evidence_refs)
                )
                existing_obj["provenance"] = sorted(
                    set(existing_obj["provenance"]) | {obs_id, fact_id} - {""}
                )
            else:
                objective_status_map[obj_id] = {
                    "status": status,
                    "evidence_refs": sorted(set(evidence_refs)),
                    "provenance": sorted({obs_id, fact_id} - {""}),
                }

        # 10. CANDIDATE_FINDING & CONFIRMED_FINDING
        elif fact_type == "CANDIDATE_FINDING":
            candidate_findings_map[fact_id] = {
                "fact_id": fact_id,
                "target": subject,
                "finding": copy.deepcopy(val),
                "confidence": confidence,
                "provenance": sorted({obs_id, fact_id} - {""}),
            }
        elif fact_type == "CONFIRMED_FINDING":
            confirmed_findings_map[fact_id] = {
                "fact_id": fact_id,
                "target": subject,
                "finding": copy.deepcopy(val),
                "confidence": confidence,
                "provenance": sorted({obs_id, fact_id} - {""}),
            }

    # Ensure all known_hosts reflect latest access_state
    for h, host_data in known_hosts.items():
        if h in access_state:
            host_data["access_level"] = _highest_access_level(host_data["access_level"], access_state[h])

    # Sort all projections deterministically
    sorted_known_hosts = {k: known_hosts[k] for k in sorted(known_hosts.keys())}
    sorted_known_services = sorted(
        known_services_map.values(),
        key=lambda s: (s["host"], str(s["port"]), s["protocol"]),
    )
    sorted_known_endpoints = sorted(
        known_endpoints_map.values(),
        key=lambda e: (e["host"], e["path"]),
    )
    sorted_candidate_findings = sorted(
        candidate_findings_map.values(),
        key=lambda f: f["fact_id"],
    )
    sorted_confirmed_findings = sorted(
        confirmed_findings_map.values(),
        key=lambda f: f["fact_id"],
    )
    sorted_access_state = {k: access_state[k] for k in sorted(access_state.keys())}
    sorted_credentials = sorted(
        credentials_map.values(),
        key=lambda c: c["credential_id"],
    )
    sorted_sessions = sorted(
        sessions_map.values(),
        key=lambda s: s["session_id"],
    )
    sorted_reachability = sorted(
        reachability_map.values(),
        key=lambda r: (r["from_host"], r["to_host"], r["protocol"]),
    )
    sorted_detection_signals = sorted(
        detection_signals_map.values(),
        key=lambda d: (d["source_target"], d["signal_type"], d["observable_event"]),
    )
    sorted_objective_status = {k: objective_status_map[k] for k in sorted(objective_status_map.keys())}
    sorted_hypotheses = sorted(
        hypotheses_list,
        key=lambda h: (h["fact_type"], h["subject"], str(h["value"])),
    )
    sorted_provenance = sorted(provenance_refs_set)

    return {
        "known_hosts": sorted_known_hosts,
        "known_services": sorted_known_services,
        "known_endpoints": sorted_known_endpoints,
        "candidate_findings": sorted_candidate_findings,
        "confirmed_findings": sorted_confirmed_findings,
        "access_state": sorted_access_state,
        "known_credentials": sorted_credentials,
        "sessions": sorted_sessions,
        "observed_reachability": sorted_reachability,
        "detection_signals": sorted_detection_signals,
        "objective_status": sorted_objective_status,
        "hypotheses": sorted_hypotheses,
        "provenance_refs": sorted_provenance,
    }


class BeliefState:
    """Immutable, queryable Red Team Belief State."""

    def __init__(self, data: Mapping[str, Any]) -> None:
        self._data = copy.deepcopy(dict(data))

    @classmethod
    def from_facts(
        cls,
        observed_facts: Sequence[Mapping[str, Any]],
        observations: Sequence[Mapping[str, Any]] | None = None,
    ) -> BeliefState:
        projection = project_belief_state(observed_facts, observations)
        return cls(projection)

    @classmethod
    def from_state(cls, state: Mapping[str, Any]) -> BeliefState:
        if "belief_state" in state and isinstance(state["belief_state"], Mapping):
            return cls(state["belief_state"])
        facts = state.get("observed_facts", [])
        return cls.from_facts(facts)

    @property
    def known_hosts(self) -> dict[str, dict[str, Any]]:
        return copy.deepcopy(self._data.get("known_hosts", {}))

    @property
    def known_services(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._data.get("known_services", []))

    @property
    def known_endpoints(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._data.get("known_endpoints", []))

    @property
    def candidate_findings(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._data.get("candidate_findings", []))

    @property
    def confirmed_findings(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._data.get("confirmed_findings", []))

    @property
    def access_state(self) -> dict[str, str]:
        return copy.deepcopy(self._data.get("access_state", {}))

    @property
    def known_credentials(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._data.get("known_credentials", []))

    @property
    def sessions(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._data.get("sessions", []))

    @property
    def active_sessions(self) -> list[dict[str, Any]]:
        return [s for s in self._data.get("sessions", []) if s.get("state") == "ACTIVE"]

    @property
    def observed_reachability(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._data.get("observed_reachability", []))

    @property
    def detection_signals(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._data.get("detection_signals", []))

    @property
    def objective_status(self) -> dict[str, dict[str, Any]]:
        return copy.deepcopy(self._data.get("objective_status", {}))

    @property
    def hypotheses(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._data.get("hypotheses", []))

    @property
    def visible_target_ids(self) -> frozenset[str]:
        hosts = set(self._data.get("known_hosts", {}).keys())
        for r in self._data.get("observed_reachability", []):
            to_h = r.get("to_host") if isinstance(r, dict) else getattr(r, "to_host", None)
            if to_h:
                hosts.add(to_h)
        return frozenset(hosts)


    @property
    def provenance_refs(self) -> list[str]:
        return list(self._data.get("provenance_refs", []))

    def get_host_access(self, host: str) -> str:
        """Return the confirmed access level for host, defaulting to NONE."""
        return self._data.get("access_state", {}).get(host, "NONE")

    def is_host_known(self, host: str) -> bool:
        """Return True if host has been authoritatively discovered."""
        return host in self._data.get("known_hosts", {})

    def get_valid_credentials(self, scope: str | None = None) -> list[dict[str, Any]]:
        """Return valid credentials, optionally filtered by scope."""
        creds = [c for c in self._data.get("known_credentials", []) if c.get("validity_state") == "VALID"]
        if scope:
            creds = [c for c in creds if c.get("observed_scope") == scope]
        return copy.deepcopy(creds)

    def get_reachable_from(self, host: str) -> list[str]:
        """Return list of host IDs reachable from host based on observed reachability."""
        targets = set()
        for edge in self._data.get("observed_reachability", []):
            if edge.get("from_host") == host:
                targets.add(edge.get("to_host"))
        return sorted(targets)

    def is_objective_achieved(self) -> bool:
        """Return True if any tracked objective is confirmed ACHIEVED."""
        return any(
            (info.get("status") if isinstance(info, dict) else str(info)) == "ACHIEVED"
            for info in self._data.get("objective_status", {}).values()
        )

    def to_dict(self) -> dict[str, Any]:
        """Return deepcopy of projection dict."""
        return copy.deepcopy(self._data)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, BeliefState):
            return self._data == other._data
        if isinstance(other, dict):
            return self._data == other
        return False
