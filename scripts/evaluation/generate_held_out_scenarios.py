"""Generates and validates 12 held-out evaluation scenarios (H1–H12) for RT-05D / RT-07.

Ensures:
1. 3 scenarios per family:
   - Straight: H1 (SCN-HELD-001), H2 (SCN-HELD-002), H3 (SCN-HELD-003)
   - Decoy: H4 (SCN-HELD-004), H5 (SCN-HELD-005), H6 (SCN-HELD-006)
   - Blocked/Replan: H7 (SCN-HELD-007), H8 (SCN-HELD-008), H9 (SCN-HELD-009)
   - Clean-Control: H10 (SCN-HELD-010), H11 (SCN-HELD-011), H12 (SCN-HELD-012)
2. Every scenario strictly adheres to Draft 2020-12 closed-schema contracts and referential integrity.
3. Every scenario has distinct node IDs, IPs, hostnames, credentials, and topology from development scenarios S1–S4.
4. Generates evaluator manifest with zero leak of family labels or hidden targets to planner context.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.simulation.loader import ScenarioLoader

HELD_OUT_DIR = ROOT / "evaluation" / "datasets" / "held_out"


def _build_straight_scenario(
    scenario_id: str,
    name: str,
    description: str,
    random_seed: int,
    entry_id: str,
    entry_ip: str,
    entry_host: str,
    app_id: str,
    app_ip: str,
    app_host: str,
    db_id: str,
    db_ip: str,
    db_host: str,
    cred_app: str,
    cred_db: str,
    obj_id: str,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "scenario_id": scenario_id,
        "name": name,
        "description": description,
        "random_seed": random_seed,
        "entry_seed": entry_id,
        "hidden_nodes": [
            {
                "node_id": entry_id,
                "node_kind": "ENTRY",
                "network_zone": "PERIMETER",
                "ip": entry_ip,
                "hostname": entry_host,
                "is_decoy": False,
                "initial_access_level": "NONE",
                "services": [
                    {
                        "service_id": f"svc-{entry_id}-80",
                        "port": 80,
                        "protocol": "HTTP",
                        "service_type": "HTTP",
                        "capabilities": ["WEB_HOSTING", "REST_API"],
                    }
                ],
                "vulnerabilities": [
                    {
                        "vulnerability_id": f"VULN-{scenario_id}-001",
                        "vulnerability_family": "SQLI",
                        "severity": "HIGH",
                        "target_service_id": f"svc-{entry_id}-80",
                    }
                ],
                "credentials_present": [cred_app],
            },
            {
                "node_id": app_id,
                "node_kind": "INTERNAL_HOST",
                "network_zone": "INTERNAL_APP",
                "ip": app_ip,
                "hostname": app_host,
                "is_decoy": False,
                "initial_access_level": "NONE",
                "services": [
                    {
                        "service_id": f"svc-{app_id}-22",
                        "port": 22,
                        "protocol": "SSH",
                        "service_type": "SSH",
                        "capabilities": ["REMOTE_SHELL", "PIVOT"],
                    },
                    {
                        "service_id": f"svc-{app_id}-8080",
                        "port": 8080,
                        "protocol": "HTTP",
                        "service_type": "HTTP",
                        "capabilities": ["BACKEND_API"],
                    },
                ],
                "vulnerabilities": [
                    {
                        "vulnerability_id": f"VULN-{scenario_id}-002",
                        "vulnerability_family": "MISCONFIGURATION",
                        "severity": "MEDIUM",
                        "target_service_id": f"svc-{app_id}-8080",
                    }
                ],
                "credentials_present": [cred_db],
            },
            {
                "node_id": db_id,
                "node_kind": "DATABASE",
                "network_zone": "SECURE_DATA",
                "ip": db_ip,
                "hostname": db_host,
                "is_decoy": False,
                "initial_access_level": "NONE",
                "services": [
                    {
                        "service_id": f"svc-{db_id}-5432",
                        "port": 5432,
                        "protocol": "TCP",
                        "service_type": "DATABASE",
                        "capabilities": ["DATA_STORAGE", "CONFIDENTIAL_RECORDS"],
                    }
                ],
                "vulnerabilities": [],
                "credentials_present": [],
            },
        ],
        "hidden_topology": {
            "edges": [
                {
                    "edge_id": f"edge-{entry_id}-to-{app_id}",
                    "source": entry_id,
                    "target": app_id,
                    "protocol": "TCP",
                    "port": 22,
                    "bidirectional": False,
                    "is_blocked": False,
                },
                {
                    "edge_id": f"edge-{app_id}-to-{db_id}",
                    "source": app_id,
                    "target": db_id,
                    "protocol": "TCP",
                    "port": 5432,
                    "bidirectional": False,
                    "is_blocked": False,
                },
            ]
        },
        "hidden_credentials": [
            {
                "credential_id": cred_app,
                "principal": f"{app_id}_svc",
                "credential_kind": "SSH_KEY",
                "valid_nodes": [app_id],
                "granted_access_level": "USER",
                "validity_state": "VALID",
                "is_decoy": False,
            },
            {
                "credential_id": cred_db,
                "principal": f"{db_id}_admin",
                "credential_kind": "PASSWORD",
                "valid_nodes": [db_id],
                "granted_access_level": "PRIVILEGED",
                "validity_state": "VALID",
                "is_decoy": False,
            },
        ],
        "objective": {
            "objective_id": obj_id,
            "target_node_id": db_id,
            "target_artifact": "vault_records.enc",
            "required_access_level": "PRIVILEGED",
            "completion_condition": "ACCESS",
            "description": f"Held-out objective for {scenario_id}",
        },
        "detection_model": {
            "noise_threshold": 12.0,
            "alert_threshold": 22.0,
            "containment_threshold": 32.0,
            "initial_detection_state": "QUIET",
        },
        "transitions": [
            {
                "transition_id": f"TRANS-{scenario_id}-RECON-ENTRY",
                "action_id": "ACTION-RECON-001",
                "match_conditions": {"target_node_id": entry_id, "require_active_session": False, "require_reachability": False},
                "success_probability": 1.0,
                "noise_delta": 0.5,
                "success_outcome": {
                    "mutations": {},
                    "observations": [
                        {
                            "fact_type": "SERVICE",
                            "emit_on": "SUCCESS",
                            "probability": 1.0,
                            "confidence": 0.95,
                            "source_kind": "SIMULATED",
                            "subject_template": f"{entry_id}:80",
                            "value_template": {"port": 80, "protocol": "HTTP", "service_type": "HTTP"},
                        }
                    ],
                },
                "failure_outcome": {"mutations": {}, "observations": []},
            },
            {
                "transition_id": f"TRANS-{scenario_id}-SCAN-ENTRY",
                "action_id": "ACTION-SCAN-001",
                "match_conditions": {"target_node_id": entry_id, "require_active_session": False, "require_reachability": False},
                "success_probability": 1.0,
                "noise_delta": 1.0,
                "success_outcome": {
                    "mutations": {},
                    "observations": [
                        {
                            "fact_type": "CONFIRMED_FINDING",
                            "emit_on": "SUCCESS",
                            "probability": 1.0,
                            "confidence": 0.9,
                            "source_kind": "SIMULATED",
                            "subject_template": entry_id,
                            "value_template": {"finding_id": f"FIND-{scenario_id}-01", "vulnerability_id": f"VULN-{scenario_id}-001"},
                        }
                    ],
                },
                "failure_outcome": {"mutations": {}, "observations": []},
            },
            {
                "transition_id": f"TRANS-{scenario_id}-FOOTHOLD-ENTRY",
                "action_id": "ACTION-WEB-001",
                "match_conditions": {"target_node_id": entry_id, "require_active_session": False, "require_reachability": False},
                "success_probability": 1.0,
                "noise_delta": 2.0,
                "success_outcome": {
                    "mutations": {
                        "grant_access_level": "FOOTHOLD",
                        "create_session": True,
                    },
                    "observations": [
                        {
                            "fact_type": "ACCESS",
                            "emit_on": "SUCCESS",
                            "probability": 1.0,
                            "confidence": 1.0,
                            "source_kind": "SIMULATED",
                            "subject_template": entry_id,
                            "value_template": {"access_level": "FOOTHOLD"},
                        },
                        {
                            "fact_type": "SESSION",
                            "emit_on": "SUCCESS",
                            "probability": 1.0,
                            "confidence": 1.0,
                            "source_kind": "SIMULATED",
                            "subject_template": f"sess-{entry_id}-01",
                            "value_template": {"node_id": entry_id, "session_state": "ACTIVE"},
                        },
                    ],
                },
                "failure_outcome": {"mutations": {}, "observations": []},
            },
            {
                "transition_id": f"TRANS-{scenario_id}-HOSTRECON-ENTRY",
                "action_id": "ACTION-HOSTRECON-001",
                "match_conditions": {"target_node_id": entry_id, "require_active_session": True, "require_reachability": False},
                "success_probability": 1.0,
                "noise_delta": 0.5,
                "success_outcome": {
                    "mutations": {},
                    "observations": [
                        {
                            "fact_type": "REACHABILITY",
                            "emit_on": "SUCCESS",
                            "probability": 1.0,
                            "confidence": 0.9,
                            "source_kind": "SIMULATED",
                            "subject_template": f"{entry_id}->{app_id}",
                            "value_template": {"source": entry_id, "target": app_id, "reachable": True},
                        }
                    ],
                },
                "failure_outcome": {"mutations": {}, "observations": []},
            },
            {
                "transition_id": f"TRANS-{scenario_id}-CREDS-ENTRY",
                "action_id": "ACTION-AUTH-001",
                "match_conditions": {"target_node_id": entry_id, "require_active_session": True, "require_reachability": False},
                "success_probability": 1.0,
                "noise_delta": 1.0,
                "success_outcome": {
                    "mutations": {
                        "reveal_credentials": [cred_app],
                    },
                    "observations": [
                        {
                            "fact_type": "CREDENTIAL",
                            "emit_on": "SUCCESS",
                            "probability": 1.0,
                            "confidence": 0.95,
                            "source_kind": "SIMULATED",
                            "subject_template": cred_app,
                            "value_template": {"credential_id": cred_app, "principal": f"{app_id}_svc", "kind": "SSH_KEY"},
                        }
                    ],
                },
                "failure_outcome": {"mutations": {}, "observations": []},
            },
            {
                "transition_id": f"TRANS-{scenario_id}-PIVOT-APP",
                "action_id": "ACTION-FLOW-001",
                "match_conditions": {"target_node_id": app_id, "require_active_session": False, "require_reachability": True},
                "success_probability": 1.0,
                "noise_delta": 1.5,
                "success_outcome": {
                    "mutations": {
                        "grant_access_level": "USER",
                        "create_session": True,
                    },
                    "observations": [
                        {
                            "fact_type": "ACCESS",
                            "emit_on": "SUCCESS",
                            "probability": 1.0,
                            "confidence": 1.0,
                            "source_kind": "SIMULATED",
                            "subject_template": app_id,
                            "value_template": {"access_level": "USER"},
                        },
                        {
                            "fact_type": "SESSION",
                            "emit_on": "SUCCESS",
                            "probability": 1.0,
                            "confidence": 1.0,
                            "source_kind": "SIMULATED",
                            "subject_template": f"sess-{app_id}-01",
                            "value_template": {"node_id": app_id, "session_state": "ACTIVE"},
                        },
                    ],
                },
                "failure_outcome": {"mutations": {}, "observations": []},
            },
            {
                "transition_id": f"TRANS-{scenario_id}-HOSTRECON-APP",
                "action_id": "ACTION-HOSTRECON-001",
                "match_conditions": {"target_node_id": app_id, "require_active_session": True, "require_reachability": False},
                "success_probability": 1.0,
                "noise_delta": 0.5,
                "success_outcome": {
                    "mutations": {},
                    "observations": [
                        {
                            "fact_type": "REACHABILITY",
                            "emit_on": "SUCCESS",
                            "probability": 1.0,
                            "confidence": 0.9,
                            "source_kind": "SIMULATED",
                            "subject_template": f"{app_id}->{db_id}",
                            "value_template": {"source": app_id, "target": db_id, "reachable": True},
                        }
                    ],
                },
                "failure_outcome": {"mutations": {}, "observations": []},
            },
            {
                "transition_id": f"TRANS-{scenario_id}-CREDS-APP",
                "action_id": "ACTION-AUTH-001",
                "match_conditions": {"target_node_id": app_id, "require_active_session": True, "require_reachability": False},
                "success_probability": 1.0,
                "noise_delta": 1.0,
                "success_outcome": {
                    "mutations": {
                        "reveal_credentials": [cred_db],
                    },
                    "observations": [
                        {
                            "fact_type": "CREDENTIAL",
                            "emit_on": "SUCCESS",
                            "probability": 1.0,
                            "confidence": 0.95,
                            "source_kind": "SIMULATED",
                            "subject_template": cred_db,
                            "value_template": {"credential_id": cred_db, "principal": f"{db_id}_admin", "kind": "PASSWORD"},
                        }
                    ],
                },
                "failure_outcome": {"mutations": {}, "observations": []},
            },
            {
                "transition_id": f"TRANS-{scenario_id}-PIVOT-DB",
                "action_id": "ACTION-FLOW-001",
                "match_conditions": {"target_node_id": db_id, "require_active_session": False, "require_reachability": True},
                "success_probability": 1.0,
                "noise_delta": 1.5,
                "success_outcome": {
                    "mutations": {
                        "grant_access_level": "PRIVILEGED",
                        "create_session": True,
                    },
                    "observations": [
                        {
                            "fact_type": "ACCESS",
                            "emit_on": "SUCCESS",
                            "probability": 1.0,
                            "confidence": 1.0,
                            "source_kind": "SIMULATED",
                            "subject_template": db_id,
                            "value_template": {"access_level": "PRIVILEGED"},
                        },
                        {
                            "fact_type": "SESSION",
                            "emit_on": "SUCCESS",
                            "probability": 1.0,
                            "confidence": 1.0,
                            "source_kind": "SIMULATED",
                            "subject_template": f"sess-{db_id}-01",
                            "value_template": {"node_id": db_id, "session_state": "ACTIVE"},
                        },
                    ],
                },
                "failure_outcome": {"mutations": {}, "observations": []},
            },
            {
                "transition_id": f"TRANS-{scenario_id}-OBJECTIVE",
                "action_id": "ACTION-FLOW-002",
                "match_conditions": {"target_node_id": db_id, "require_active_session": True, "require_reachability": False},
                "success_probability": 1.0,
                "noise_delta": 1.0,
                "success_outcome": {
                    "mutations": {
                        "set_objective_achieved": True,
                    },
                    "observations": [
                        {
                            "fact_type": "OBJECTIVE",
                            "emit_on": "SUCCESS",
                            "probability": 1.0,
                            "confidence": 1.0,
                            "source_kind": "SIMULATED",
                            "subject_template": db_id,
                            "value_template": {"objective_id": obj_id, "objective_state": "ACHIEVED"},
                        }
                    ],
                },
                "failure_outcome": {"mutations": {}, "observations": []},
            },
            {
                "transition_id": f"TRANS-{scenario_id}-STOP",
                "action_id": "ACTION-END-001",
                "match_conditions": {"target_node_id": "ANY", "require_active_session": False, "require_reachability": False},
                "success_probability": 1.0,
                "noise_delta": 0.0,
                "success_outcome": {"mutations": {}, "observations": []},
                "failure_outcome": {"mutations": {}, "observations": []},
            },
        ],
    }


def _build_decoy_scenario(
    scenario_id: str,
    name: str,
    description: str,
    random_seed: int,
    entry_id: str,
    entry_ip: str,
    entry_host: str,
    app_id: str,
    app_ip: str,
    app_host: str,
    db_id: str,
    db_ip: str,
    db_host: str,
    decoy_id: str,
    decoy_ip: str,
    decoy_host: str,
    decoy_trap_type: str,
    cred_app: str,
    cred_db: str,
    obj_id: str,
) -> dict[str, Any]:
    base = _build_straight_scenario(
        scenario_id=scenario_id,
        name=name,
        description=description,
        random_seed=random_seed,
        entry_id=entry_id,
        entry_ip=entry_ip,
        entry_host=entry_host,
        app_id=app_id,
        app_ip=app_ip,
        app_host=app_host,
        db_id=db_id,
        db_ip=db_ip,
        db_host=db_host,
        cred_app=cred_app,
        cred_db=cred_db,
        obj_id=obj_id,
    )
    decoy_node = {
        "node_id": decoy_id,
        "node_kind": "DECOY",
        "network_zone": "INTERNAL_DECOY",
        "ip": decoy_ip,
        "hostname": decoy_host,
        "is_decoy": True,
        "decoy_metadata": {"trap_type": decoy_trap_type, "tripwire_alarm": True},
        "initial_access_level": "NONE",
        "services": [
            {
                "service_id": f"svc-{decoy_id}-trap",
                "port": 8888,
                "protocol": "TCP",
                "service_type": "HTTP",
                "capabilities": ["TRAP_SERVICE"],
            }
        ],
        "vulnerabilities": [
            {
                "vulnerability_id": f"VULN-{scenario_id}-DECOY",
                "vulnerability_family": "MISCONFIGURATION",
                "severity": "LOW",
                "target_service_id": f"svc-{decoy_id}-trap",
            }
        ],
        "credentials_present": [],
    }
    base["hidden_nodes"].append(decoy_node)
    base["hidden_topology"]["edges"].append(
        {
            "edge_id": f"edge-{app_id}-to-{decoy_id}",
            "source": app_id,
            "target": decoy_id,
            "protocol": "TCP",
            "port": 8888,
            "bidirectional": False,
            "is_blocked": False,
        }
    )
    for trans in base["transitions"]:
        if trans["transition_id"] == f"TRANS-{scenario_id}-HOSTRECON-APP":
            trans["success_outcome"]["observations"].append(
                {
                    "fact_type": "REACHABILITY",
                    "emit_on": "SUCCESS",
                    "probability": 1.0,
                    "confidence": 0.9,
                    "source_kind": "SIMULATED",
                    "subject_template": f"{app_id}->{decoy_id}",
                    "value_template": {"source": app_id, "target": decoy_id, "reachable": True},
                }
            )
    base["transitions"].append(
        {
            "transition_id": f"TRANS-{scenario_id}-PIVOT-DECOY",
            "action_id": "ACTION-FLOW-001",
            "match_conditions": {"target_node_id": decoy_id, "require_active_session": False, "require_reachability": True},
            "success_probability": 0.0,
            "noise_delta": 15.0,
            "success_outcome": {"mutations": {}, "observations": []},
            "failure_outcome": {
                "mutations": {},
                "observations": [],
            },
        }
    )
    return base


def _build_blocked_scenario(
    scenario_id: str,
    name: str,
    description: str,
    random_seed: int,
    entry_id: str,
    entry_ip: str,
    entry_host: str,
    app_id: str,
    app_ip: str,
    app_host: str,
    jump_id: str,
    jump_ip: str,
    jump_host: str,
    db_id: str,
    db_ip: str,
    db_host: str,
    cred_app: str,
    cred_jump: str,
    cred_db: str,
    obj_id: str,
) -> dict[str, Any]:
    base = _build_straight_scenario(
        scenario_id=scenario_id,
        name=name,
        description=description,
        random_seed=random_seed,
        entry_id=entry_id,
        entry_ip=entry_ip,
        entry_host=entry_host,
        app_id=app_id,
        app_ip=app_ip,
        app_host=app_host,
        db_id=db_id,
        db_ip=db_ip,
        db_host=db_host,
        cred_app=cred_app,
        cred_db=cred_db,
        obj_id=obj_id,
    )
    for edge in base["hidden_topology"]["edges"]:
        if edge["source"] == app_id and edge["target"] == db_id:
            edge["is_blocked"] = True
            edge["edge_id"] = f"edge-{app_id}-to-{db_id}-blocked"

    jump_node = {
        "node_id": jump_id,
        "node_kind": "INTERNAL_HOST",
        "network_zone": "INTERNAL_OPS",
        "ip": jump_ip,
        "hostname": jump_host,
        "is_decoy": False,
        "initial_access_level": "NONE",
        "services": [
            {
                "service_id": f"svc-{jump_id}-22",
                "port": 22,
                "protocol": "SSH",
                "service_type": "SSH",
                "capabilities": ["REMOTE_SHELL", "PIVOT"],
            }
        ],
        "vulnerabilities": [],
        "credentials_present": [cred_db],
    }
    base["hidden_nodes"].append(jump_node)
    base["hidden_credentials"].append(
        {
            "credential_id": cred_jump,
            "principal": f"{jump_id}_ops",
            "credential_kind": "SSH_KEY",
            "valid_nodes": [jump_id],
            "granted_access_level": "USER",
            "validity_state": "VALID",
            "is_decoy": False,
        }
    )
    base["hidden_topology"]["edges"].append(
        {
            "edge_id": f"edge-{app_id}-to-{jump_id}",
            "source": app_id,
            "target": jump_id,
            "protocol": "TCP",
            "port": 22,
            "bidirectional": False,
            "is_blocked": False,
        }
    )
    base["hidden_topology"]["edges"].append(
        {
            "edge_id": f"edge-{jump_id}-to-{db_id}",
            "source": jump_id,
            "target": db_id,
            "protocol": "TCP",
            "port": 5432,
            "bidirectional": False,
            "is_blocked": False,
        }
    )
    for node in base["hidden_nodes"]:
        if node["node_id"] == app_id:
            node["credentials_present"].append(cred_jump)

    for trans in base["transitions"]:
        if trans["transition_id"] == f"TRANS-{scenario_id}-PIVOT-DB":
            trans["success_probability"] = 0.0
            trans["success_outcome"] = {"mutations": {}, "observations": []}
            trans["failure_outcome"] = {"mutations": {}, "observations": []}
        if trans["transition_id"] == f"TRANS-{scenario_id}-HOSTRECON-APP":
            trans["success_outcome"]["observations"].append(
                {
                    "fact_type": "REACHABILITY",
                    "emit_on": "SUCCESS",
                    "probability": 1.0,
                    "confidence": 0.9,
                    "source_kind": "SIMULATED",
                    "subject_template": f"{app_id}->{jump_id}",
                    "value_template": {"source": app_id, "target": jump_id, "reachable": True},
                }
            )

    base["transitions"].extend([
        {
            "transition_id": f"TRANS-{scenario_id}-PIVOT-JUMP",
            "action_id": "ACTION-FLOW-001",
            "match_conditions": {"target_node_id": jump_id, "require_active_session": False, "require_reachability": True},
            "success_probability": 1.0,
            "noise_delta": 1.0,
            "success_outcome": {
                "mutations": {
                    "grant_access_level": "USER",
                    "create_session": True,
                },
                "observations": [
                    {
                        "fact_type": "ACCESS",
                        "emit_on": "SUCCESS",
                        "probability": 1.0,
                        "confidence": 1.0,
                        "source_kind": "SIMULATED",
                        "subject_template": jump_id,
                        "value_template": {"access_level": "USER"},
                    },
                    {
                        "fact_type": "SESSION",
                        "emit_on": "SUCCESS",
                        "probability": 1.0,
                        "confidence": 1.0,
                        "source_kind": "SIMULATED",
                        "subject_template": f"sess-{jump_id}-01",
                        "value_template": {"node_id": jump_id, "session_state": "ACTIVE"},
                    },
                ],
            },
            "failure_outcome": {"mutations": {}, "observations": []},
        },
        {
            "transition_id": f"TRANS-{scenario_id}-HOSTRECON-JUMP",
            "action_id": "ACTION-HOSTRECON-001",
            "match_conditions": {"target_node_id": jump_id, "require_active_session": True, "require_reachability": False},
            "success_probability": 1.0,
            "noise_delta": 0.5,
            "success_outcome": {
                "mutations": {},
                "observations": [
                    {
                        "fact_type": "REACHABILITY",
                        "emit_on": "SUCCESS",
                        "probability": 1.0,
                        "confidence": 0.9,
                        "source_kind": "SIMULATED",
                        "subject_template": f"{jump_id}->{db_id}",
                        "value_template": {"source": jump_id, "target": db_id, "reachable": True},
                    }
                ],
            },
            "failure_outcome": {"mutations": {}, "observations": []},
        },
        {
            "transition_id": f"TRANS-{scenario_id}-PIVOT-JUMP-TO-DB",
            "action_id": "ACTION-FLOW-001",
            "match_conditions": {"target_node_id": db_id, "require_active_session": False, "require_reachability": True},
            "success_probability": 1.0,
            "noise_delta": 1.5,
            "success_outcome": {
                "mutations": {
                    "grant_access_level": "PRIVILEGED",
                    "create_session": True,
                },
                "observations": [
                    {
                        "fact_type": "ACCESS",
                        "emit_on": "SUCCESS",
                        "probability": 1.0,
                        "confidence": 1.0,
                        "source_kind": "SIMULATED",
                        "subject_template": db_id,
                        "value_template": {"access_level": "PRIVILEGED"},
                    },
                    {
                        "fact_type": "SESSION",
                        "emit_on": "SUCCESS",
                        "probability": 1.0,
                        "confidence": 1.0,
                        "source_kind": "SIMULATED",
                        "subject_template": f"sess-{db_id}-01",
                        "value_template": {"node_id": db_id, "session_state": "ACTIVE"},
                    },
                ],
            },
            "failure_outcome": {"mutations": {}, "observations": []},
        },
    ])
    return base


def _build_clean_scenario(
    scenario_id: str,
    name: str,
    description: str,
    random_seed: int,
    entry_id: str,
    entry_ip: str,
    entry_host: str,
    isolated_id: str,
    isolated_ip: str,
    isolated_host: str,
    obj_id: str,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "scenario_id": scenario_id,
        "name": name,
        "description": description,
        "random_seed": random_seed,
        "entry_seed": entry_id,
        "hidden_nodes": [
            {
                "node_id": entry_id,
                "node_kind": "ENTRY",
                "network_zone": "HARDENED_DMZ",
                "ip": entry_ip,
                "hostname": entry_host,
                "is_decoy": False,
                "initial_access_level": "NONE",
                "services": [
                    {
                        "service_id": f"svc-{entry_id}-443",
                        "port": 443,
                        "protocol": "HTTPS",
                        "service_type": "HTTP",
                        "capabilities": ["TLS_SECURED_PORTAL"],
                    }
                ],
                "vulnerabilities": [],
                "credentials_present": [],
            },
            {
                "node_id": isolated_id,
                "node_kind": "INTERNAL_HOST",
                "network_zone": "INTERNAL_SECURE",
                "ip": isolated_ip,
                "hostname": isolated_host,
                "is_decoy": False,
                "initial_access_level": "NONE",
                "services": [],
                "vulnerabilities": [],
                "credentials_present": [],
            },
        ],
        "hidden_topology": {
            "edges": [
                {
                    "edge_id": f"edge-{entry_id}-to-{isolated_id}-blocked",
                    "source": entry_id,
                    "target": isolated_id,
                    "protocol": "TCP",
                    "port": 443,
                    "bidirectional": False,
                    "is_blocked": True,
                }
            ]
        },
        "hidden_credentials": [],
        "objective": {
            "objective_id": obj_id,
            "target_node_id": isolated_id,
            "target_artifact": "sealed_audit_report.pdf",
            "required_access_level": "SYSTEM",
            "completion_condition": "ACCESS",
            "description": "Clean control objective: no unpatched or exploitable progression path exists",
        },
        "detection_model": {
            "noise_threshold": 15.0,
            "alert_threshold": 25.0,
            "containment_threshold": 35.0,
            "initial_detection_state": "QUIET",
        },
        "transitions": [
            {
                "transition_id": f"TRANS-{scenario_id}-RECON",
                "action_id": "ACTION-RECON-001",
                "match_conditions": {"target_node_id": entry_id, "require_active_session": False, "require_reachability": False},
                "success_probability": 1.0,
                "noise_delta": 0.2,
                "success_outcome": {
                    "mutations": {},
                    "observations": [
                        {
                            "fact_type": "SERVICE",
                            "emit_on": "SUCCESS",
                            "probability": 1.0,
                            "confidence": 0.98,
                            "source_kind": "SIMULATED",
                            "subject_template": f"{entry_id}:443",
                            "value_template": {"port": 443, "protocol": "HTTPS", "service_type": "HTTP"},
                        }
                    ],
                },
                "failure_outcome": {"mutations": {}, "observations": []},
            },
            {
                "transition_id": f"TRANS-{scenario_id}-STOP",
                "action_id": "ACTION-END-001",
                "match_conditions": {"target_node_id": "ANY", "require_active_session": False, "require_reachability": False},
                "success_probability": 1.0,
                "noise_delta": 0.0,
                "success_outcome": {"mutations": {}, "observations": []},
                "failure_outcome": {"mutations": {}, "observations": []},
            },
        ],
    }


def generate_all_held_out_scenarios() -> list[dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []

    # Straight Family (H1-H3)
    scenarios.append(_build_straight_scenario(
        "SCN-HELD-001", "H1 Straight Enterprise Path A", "Linear 3-tier enterprise path A",
        2001, "held-gw-edge", "10.10.1.5", "edge-gw.corp.net",
        "held-app-core", "10.10.2.15", "core-app.corp.net",
        "held-vault-sec", "10.10.3.25", "vault-db.corp.net",
        "cred-held-001-app", "cred-held-001-db", "OBJ-HELD-001",
    ))
    scenarios.append(_build_straight_scenario(
        "SCN-HELD-002", "H2 Straight Enterprise Path B", "Linear 3-tier enterprise path B",
        2002, "held-pub-ingress", "172.16.1.10", "pub-ingress.fin.net",
        "held-srv-worker", "172.16.2.20", "worker-srv.fin.net",
        "held-db-ledger", "172.16.3.30", "ledger-db.fin.net",
        "cred-held-002-app", "cred-held-002-db", "OBJ-HELD-002",
    ))
    scenarios.append(_build_straight_scenario(
        "SCN-HELD-003", "H3 Straight Enterprise Path C", "Linear 3-tier enterprise path C",
        2003, "held-api-proxy", "192.168.10.2", "api-proxy.cloud.net",
        "held-backend-svc", "192.168.20.4", "backend-svc.cloud.net",
        "held-datastore", "192.168.30.6", "datastore.cloud.net",
        "cred-held-003-app", "cred-held-003-db", "OBJ-HELD-003",
    ))

    # Decoy Family (H4-H6)
    scenarios.append(_build_decoy_scenario(
        "SCN-HELD-004", "H4 Decoy Enterprise Path A", "Enterprise path with deceptive honeypot trap A",
        2004, "held-dmz-front", "10.20.1.10", "front-dmz.secure.net",
        "held-mid-app", "10.20.2.20", "mid-app.secure.net",
        "held-prod-db", "10.20.3.30", "prod-db.secure.net",
        "held-decoy-trapdb", "10.20.2.99", "backup-trap.secure.net", "HONEYPOT_DATABASE",
        "cred-held-004-app", "cred-held-004-db", "OBJ-HELD-004",
    ))
    scenarios.append(_build_decoy_scenario(
        "SCN-HELD-005", "H5 Decoy Enterprise Path B", "Enterprise path with deceptive portal trap B",
        2005, "held-web-portal", "172.20.1.10", "portal-web.enterprise.net",
        "held-task-worker", "172.20.2.20", "worker-task.enterprise.net",
        "held-secret-store", "172.20.3.30", "store-secret.enterprise.net",
        "held-fake-admin", "172.20.2.88", "admin-console.enterprise.net", "HONEYPOT_PORTAL",
        "cred-held-005-app", "cred-held-005-db", "OBJ-HELD-005",
    ))
    scenarios.append(_build_decoy_scenario(
        "SCN-HELD-006", "H6 Decoy Enterprise Path C", "Enterprise path with deceptive storage trap C",
        2006, "held-edge-gateway", "192.168.50.2", "gateway-edge.corp.net",
        "held-int-host", "192.168.50.20", "int-host.corp.net",
        "held-crown-records", "192.168.60.30", "records-db.corp.net",
        "held-honey-smb", "192.168.50.90", "smb-share.corp.net", "HONEYPOT_SMB",
        "cred-held-006-app", "cred-held-006-db", "OBJ-HELD-006",
    ))

    # Blocked / Replan Family (H7-H9)
    scenarios.append(_build_blocked_scenario(
        "SCN-HELD-007", "H7 Blocked Path & Re-planning A", "Direct route blocked, recovery requires jump box pivot A",
        2007, "held-entry-portal", "10.30.1.10", "portal-entry.grid.net",
        "held-app-staging", "10.30.2.20", "staging-app.grid.net",
        "held-ops-jump", "10.30.2.50", "jump-ops.grid.net",
        "held-target-db", "10.30.3.30", "target-db.grid.net",
        "cred-held-007-app", "cred-held-007-jump", "cred-held-007-db", "OBJ-HELD-007",
    ))
    scenarios.append(_build_blocked_scenario(
        "SCN-HELD-008", "H8 Blocked Path & Re-planning B", "Direct route blocked, recovery requires backup host pivot B",
        2008, "held-ingress-node", "172.30.1.10", "ingress-node.infra.net",
        "held-cluster-master", "172.30.2.20", "cluster-master.infra.net",
        "held-backup-host", "172.30.2.60", "backup-host.infra.net",
        "held-cluster-db", "172.30.3.30", "cluster-db.infra.net",
        "cred-held-008-app", "cred-held-008-jump", "cred-held-008-db", "OBJ-HELD-008",
    ))
    scenarios.append(_build_blocked_scenario(
        "SCN-HELD-009", "H9 Blocked Path & Re-planning C", "Direct route blocked, recovery requires security gateway pivot C",
        2009, "held-gw-router", "192.168.70.2", "router-gw.sys.net",
        "held-compute-srv", "192.168.70.20", "compute-srv.sys.net",
        "held-sec-gateway", "192.168.70.70", "sec-gw.sys.net",
        "held-crown-node", "192.168.80.30", "crown-node.sys.net",
        "cred-held-009-app", "cred-held-009-jump", "cred-held-009-db", "OBJ-HELD-009",
    ))

    # Clean-Control Family (H10-H12)
    scenarios.append(_build_clean_scenario(
        "SCN-HELD-010", "H10 Clean Control Target A", "Hardened baseline corporate network with zero vulnerabilities A",
        2010, "held-hardened-portal", "10.40.1.10", "portal-hardened.firm.net",
        "held-isolated-archive", "10.40.2.100", "archive-isolated.firm.net",
        "OBJ-HELD-010",
    ))
    scenarios.append(_build_clean_scenario(
        "SCN-HELD-011", "H11 Clean Control Target B", "Hardened baseline corporate network with zero vulnerabilities B",
        2011, "held-firewall-ext", "172.40.1.10", "firewall-ext.bank.net",
        "held-core-vault-locked", "172.40.2.100", "vault-locked.bank.net",
        "OBJ-HELD-011",
    ))
    scenarios.append(_build_clean_scenario(
        "SCN-HELD-012", "H12 Clean Control Target C", "Hardened baseline corporate network with zero vulnerabilities C",
        2012, "held-cdn-perimeter", "192.168.90.2", "cdn-perimeter.cloud.net",
        "held-internal-sealed", "192.168.90.100", "internal-sealed.cloud.net",
        "OBJ-HELD-012",
    ))

    return scenarios


def write_and_validate_all() -> None:
    HELD_OUT_DIR.mkdir(parents=True, exist_ok=True)
    loader = ScenarioLoader()
    scenarios = generate_all_held_out_scenarios()

    manifest_entries = []
    file_mapping = {
        "SCN-HELD-001": ("scenario_h01_straight.json", "Straight"),
        "SCN-HELD-002": ("scenario_h02_straight.json", "Straight"),
        "SCN-HELD-003": ("scenario_h03_straight.json", "Straight"),
        "SCN-HELD-004": ("scenario_h04_decoy.json", "Decoy"),
        "SCN-HELD-005": ("scenario_h05_decoy.json", "Decoy"),
        "SCN-HELD-006": ("scenario_h06_decoy.json", "Decoy"),
        "SCN-HELD-007": ("scenario_h07_blocked.json", "Blocked/Replan"),
        "SCN-HELD-008": ("scenario_h08_blocked.json", "Blocked/Replan"),
        "SCN-HELD-009": ("scenario_h09_blocked.json", "Blocked/Replan"),
        "SCN-HELD-010": ("scenario_h10_clean.json", "Clean Control"),
        "SCN-HELD-011": ("scenario_h11_clean.json", "Clean Control"),
        "SCN-HELD-012": ("scenario_h12_clean.json", "Clean Control"),
    }

    for scn in scenarios:
        scn_id = scn["scenario_id"]
        filename, family = file_mapping[scn_id]
        out_path = HELD_OUT_DIR / filename

        # 1. Validate with ScenarioLoader
        errors = loader.validate_scenario_data(scn)
        if errors:
            raise ValueError(f"Scenario {scn_id} failed validation: {errors}")

        # 2. Write formatted JSON
        json_bytes = json.dumps(scn, indent=2).encode("utf-8")
        out_path.write_bytes(json_bytes)
        file_sha256 = hashlib.sha256(json_bytes).hexdigest()
        print(f"Validated and written: {out_path.name} (SHA-256: {file_sha256[:12]}...)")

        # 3. Add to manifest
        manifest_entries.append({
            "scenario_id": scn_id,
            "filename": filename,
            "sha256": file_sha256,
            "family": family,
            "name": scn["name"],
            "entry_seed": scn["entry_seed"],
            "target_node_id": scn["objective"]["target_node_id"],
            "is_clean_control": family == "Clean Control",
            "has_decoy": family == "Decoy",
            "has_blocked_path": family == "Blocked/Replan",
        })

    # Write manifest
    manifest = {
        "schema_version": "1.1.0",
        "dataset_id": "HELD_OUT_EVALUATION_DATASET_V1",
        "status": "IMPLEMENTED",
        "seal_state": "SEALED",
        "benchmark_protocol_version": "BENCHMARK_PROTOCOL_FREEZE_V1",
        "created_for": "RT-05D / RT-07 Comparative Evaluation",
        "manifest_invariant": "evaluation uses manifest-pinned scenario bytes",
        "description": "12 held-out evaluation scenarios (H1-H12) partitioned into Straight, Decoy, Blocked/Replan, and Clean Control families with pinned SHA-256 byte digests.",
        "scenarios": manifest_entries,
    }
    manifest_path = HELD_OUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Written manifest: {manifest_path.name}")


if __name__ == "__main__":
    write_and_validate_all()
