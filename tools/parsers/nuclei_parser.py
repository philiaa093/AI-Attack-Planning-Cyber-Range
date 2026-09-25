"""Nuclei output parser — converts Nuclei JSON output to scanner-result.schema.json."""

from tools.adapters.base import build_scanner_result

# Nuclei severity → confidence float
_SEVERITY_MAP = {
    "info": 0.2,
    "low": 0.4,
    "medium": 0.7,
    "high": 0.9,
    "critical": 0.95,
}

# Tag → canonical finding_type
_TAG_FINDING_MAP = {
    "sqli": "sqli",
    "xss": "xss",
    "path-traversal": "path-traversal",
    "lfi": "path-traversal",
    "rfi": "path-traversal",
}


def parse_nuclei_results(nuclei_output, target_id):
    """Parse Nuclei JSON list → list of scanner-result dicts.

    Args:
        nuclei_output: list of Nuclei JSON result dicts
        target_id: lab-* target ID

    Returns:
        list of scanner-result conforming dicts
    """
    results = []
    for item in nuclei_output:
        severity = item.get("severity", "info")
        confidence = _SEVERITY_MAP.get(severity, 0.3)
        endpoint_id = item.get("matched-at")

        # Determine finding_type from tags
        finding_type = "unknown"
        for tag in item.get("tags", []):
            if tag in _TAG_FINDING_MAP:
                finding_type = _TAG_FINDING_MAP[tag]
                break

        results.append(build_scanner_result(
            source="NUCLEI",
            target_id=target_id,
            finding_type=finding_type,
            confidence=confidence,
            endpoint_id=endpoint_id,
        ))
    return results
