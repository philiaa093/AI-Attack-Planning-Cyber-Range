"""ZAP adapter — bounded OWASP ZAP scanning for lab targets.

Handles:
- ACTION-SCAN-001: ZAP active/passive scan

Rate limiting, request budget enforcement, lab target pinning.
Parser converts ZAP XML/JSON output to scanner-result.schema.json.
"""

from tools.adapters.base import BaseAdapter, build_observation, build_scanner_result, load_request_budget


class ZapAdapter(BaseAdapter):
    ADAPTER_SOURCE = "ZAP"
    ALLOWED_ACTIONS = {
        "ACTION-SCAN-001": "SCAN",
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
        return self._zap_scan(target_id, run_id)

    def _zap_scan(self, target_id, run_id):
        """Simulate ZAP scan. In production, wraps ZAP API/CLI."""
        # ponytail: simulated results; swap for zap-cli/API wrapper when runtime authorized
        from tools.parsers.zap_parser import parse_zap_results

        simulated_zap_output = {
            "site": [
                {
                    "host": target_id,
                    "alerts": [
                        {
                            "alert": "SQL Injection",
                            "riskcode": "3",
                            "confidence": "2",
                            "uri": f"http://{target_id}/login",
                            "param": "username",
                        },
                        {
                            "alert": "Cross Site Scripting",
                            "riskcode": "2",
                            "confidence": "2",
                            "uri": f"http://{target_id}/search",
                            "param": "q",
                        },
                    ],
                }
            ]
        }

        scanner_results = parse_zap_results(simulated_zap_output, target_id)

        facts = []
        for i, sr in enumerate(scanner_results):
            facts.append({
                "fact_id": f"FACT-ZAP-{target_id}-{i:03d}",
                "fact_type": "CANDIDATE_FINDING",
                "subject": target_id,
                "value": sr["finding_type"],
                "confidence": sr["confidence"],
            })

        return build_observation(
            observation_id=f"OBS-SCAN-001-{run_id}",
            run_id=run_id,
            action_id="ACTION-SCAN-001",
            outcome="SUCCESS",
            new_facts=facts,
        ), scanner_results
