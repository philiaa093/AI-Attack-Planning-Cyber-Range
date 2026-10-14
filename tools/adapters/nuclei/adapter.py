"""Offline Nuclei report wrapper; scanner execution is always denied."""

import re
from threading import Lock
from uuid import uuid4

from tools.adapters.base import BaseAdapter, build_observation, load_request_budget
from tools.parsers.nuclei_parser import (
    parse_nuclei_jsonl,
    parse_nuclei_results,
    validate_lab_target,
    validate_template_manifest,
)


class NucleiAdapter(BaseAdapter):
    ADAPTER_SOURCE = "NUCLEI"
    ALLOWED_ACTIONS = {"ACTION-SCAN-002": "SCAN"}

    def __init__(self, *, allowed_templates=None):
        super().__init__()
        self._allowed_templates = validate_template_manifest(allowed_templates)
        self._max_imports = load_request_budget()["max_actions"]
        if type(self._max_imports) is not int or not 1 <= self._max_imports <= 100:
            raise ValueError("Invalid offline import budget")
        self._import_count = 0
        self._import_lock = Lock()

    def validate_request(self, action_id, target_id, run_id):
        validate_lab_target(target_id)
        if type(action_id) is not str or action_id not in self.ALLOWED_ACTIONS:
            raise ValueError("Unsupported Nuclei action")
        if type(run_id) is not str or not re.fullmatch(r"RUN-[A-Za-z0-9_-]{1,120}", run_id):
            raise ValueError("Invalid run ID")
        super().validate_request(action_id, target_id, run_id)

    def execute(self, action_id, target_id, run_id, parameters=None):
        if parameters is not None and (type(parameters) is not dict or parameters):
            raise ValueError("Offline wrapper accepts no execution parameters")
        return super().execute(action_id, target_id, run_id, parameters)

    def _run(self, action_id, target_id, run_id, parameters):
        return build_observation(
            observation_id=f"OBS-SCAN-002-{run_id}-{uuid4().hex}",
            run_id=run_id,
            action_id=action_id,
            outcome="DENIED",
            new_facts=[],
            evidence_refs=[],
        ), []

    def import_report(self, report, *, target_id):
        """Return candidates only; caller owns evidence and normalization.

        Accept decoded lists or JSONL text. Quotas are per adapter instance,
        count attempts including malformed imports, and are not network budgets.
        """
        validate_lab_target(target_id)
        with self._import_lock:
            if self._import_count >= self._max_imports:
                raise RuntimeError("Offline import budget exhausted")
            self._rate_limiter.acquire("OFFLINE-NUCLEI-IMPORT", target_id)
            self._import_count += 1
        parser = parse_nuclei_jsonl if type(report) is str else parse_nuclei_results
        return parser(report, target_id, allowed_templates=self._allowed_templates)
