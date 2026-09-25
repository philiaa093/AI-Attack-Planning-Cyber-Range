"""Discovery adapter — bounded reconnaissance for lab targets.

Handles:
- ACTION-RECON-001: Port scanning (simulated nmap-style)
- ACTION-RECON-002: Endpoint discovery + tech fingerprinting

No arbitrary shell. All targets must be in lab-* allowlist.
Output conforms to observation.schema.json and scanner-result.schema.json.
"""

from tools.adapters.base import BaseAdapter, build_observation, build_scanner_result


class DiscoveryAdapter(BaseAdapter):
    ADAPTER_SOURCE = "DISCOVERY"
    ALLOWED_ACTIONS = {
        "ACTION-RECON-001": "RECON",
        "ACTION-RECON-002": "RECON",
    }

    def _run(self, action_id, target_id, run_id, parameters):
        if action_id == "ACTION-RECON-001":
            return self._port_scan(target_id, run_id)
        elif action_id == "ACTION-RECON-002":
            return self._endpoint_discovery(target_id, run_id)

    def _port_scan(self, target_id, run_id):
        """Simulate port scan. In production, wraps nmap with fixed args."""
        # ponytail: simulated results; swap for subprocess nmap wrapper when runtime authorized
        facts = [
            {
                "fact_id": f"FACT-PORT-{target_id}-80",
                "fact_type": "SERVICE",
                "subject": target_id,
                "value": "http/80",
                "confidence": 0.95,
            },
            {
                "fact_id": f"FACT-PORT-{target_id}-443",
                "fact_type": "SERVICE",
                "subject": target_id,
                "value": "https/443",
                "confidence": 0.95,
            },
        ]
        return build_observation(
            observation_id=f"OBS-RECON-001-{run_id}",
            run_id=run_id,
            action_id="ACTION-RECON-001",
            outcome="SUCCESS",
            new_facts=facts,
        )

    def _endpoint_discovery(self, target_id, run_id):
        """Simulate endpoint discovery + tech fingerprinting."""
        # ponytail: simulated; swap for httpx/whatweb wrapper when runtime authorized
        facts = [
            {
                "fact_id": f"FACT-ENDPOINT-{target_id}-root",
                "fact_type": "ENDPOINT",
                "subject": target_id,
                "value": "/",
                "confidence": 1.0,
            },
            {
                "fact_id": f"FACT-TECH-{target_id}-server",
                "fact_type": "SERVICE",
                "subject": target_id,
                "value": "nginx",
                "confidence": 0.8,
            },
        ]
        scanner_results = [
            build_scanner_result(
                source="DISCOVERY",
                target_id=target_id,
                finding_type="open_port",
                confidence=0.95,
                endpoint_id=None,
            ),
        ]
        return build_observation(
            observation_id=f"OBS-RECON-002-{run_id}",
            run_id=run_id,
            action_id="ACTION-RECON-002",
            outcome="SUCCESS",
            new_facts=facts,
        ), scanner_results
