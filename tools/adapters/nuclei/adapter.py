"""Nuclei adapter — bounded template scanning for lab targets.

Handles:
- ACTION-SCAN-002: Nuclei template scan

Template allowlist: only SQLi, XSS, Path Traversal templates.
Rate limiting enforcement. Parser converts Nuclei JSON to scanner-result.schema.json.
"""

from tools.adapters.base import BaseAdapter, build_observation, build_scanner_result, load_request_budget


# Only these template categories are permitted
TEMPLATE_ALLOWLIST = frozenset([
    "sqli",
    "xss",
    "path-traversal",
])


class NucleiAdapter(BaseAdapter):
    ADAPTER_SOURCE = "NUCLEI"
    ALLOWED_ACTIONS = {
        "ACTION-SCAN-002": "SCAN",
    }

    def __init__(self):
        super().__init__()
        budget = load_request_budget()
        self._max_requests = budget["max_requests"]
        self._request_count = 0

    def _check_budget(self):
        if self._request_count >= self._max_requests:
            raise RuntimeError(f"request budget exhausted ({self._max_requests})")
        self._request_count += 1

    def _run(self, action_id, target_id, run_id, parameters):
        self._check_budget()
        templates = parameters.get("templates", list(TEMPLATE_ALLOWLIST))
        self._validate_templates(templates)
        return self._nuclei_scan(target_id, run_id, templates)

    @staticmethod
    def _validate_templates(templates):
        """Reject any template not in the allowlist."""
        for t in templates:
            if t not in TEMPLATE_ALLOWLIST:
                raise ValueError(f"template '{t}' not in allowlist; allowed: {sorted(TEMPLATE_ALLOWLIST)}")

    def _nuclei_scan(self, target_id, run_id, templates):
        """Simulate Nuclei scan. In production, wraps nuclei CLI."""
        # ponytail: simulated results; swap for subprocess nuclei wrapper when runtime authorized
        from tools.parsers.nuclei_parser import parse_nuclei_results

        simulated_nuclei_output = [
            {
                "template-id": "sqli-error-based",
                "type": "http",
                "host": target_id,
                "matched-at": f"http://{target_id}/login?id=1",
                "severity": "high",
                "tags": ["sqli"],
            },
            {
                "template-id": "xss-reflected",
                "type": "http",
                "host": target_id,
                "matched-at": f"http://{target_id}/search?q=test",
                "severity": "medium",
                "tags": ["xss"],
            },
        ]

        # Filter to only requested templates
        filtered = [r for r in simulated_nuclei_output if any(t in r.get("tags", []) for t in templates)]
        scanner_results = parse_nuclei_results(filtered, target_id)

        facts = []
        for i, sr in enumerate(scanner_results):
            facts.append({
                "fact_id": f"FACT-NUCLEI-{target_id}-{i:03d}",
                "fact_type": "CANDIDATE_FINDING",
                "subject": target_id,
                "value": sr["finding_type"],
                "confidence": sr["confidence"],
            })

        return build_observation(
            observation_id=f"OBS-SCAN-002-{run_id}",
            run_id=run_id,
            action_id="ACTION-SCAN-002",
            outcome="SUCCESS",
            new_facts=facts,
        ), scanner_results
