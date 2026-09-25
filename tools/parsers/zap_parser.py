"""ZAP output parser — converts ZAP JSON/XML-style dict to scanner-result.schema.json."""

from tools.adapters.base import build_scanner_result

# ZAP confidence mapping: riskcode string → float
_CONFIDENCE_MAP = {
    "0": 0.1,   # informational
    "1": 0.4,   # low
    "2": 0.7,   # medium
    "3": 0.9,   # high
}

# ZAP alert name → canonical finding_type
_FINDING_TYPE_MAP = {
    "SQL Injection": "sqli",
    "Cross Site Scripting": "xss",
    "Path Traversal": "path-traversal",
    "Cross Site Scripting (Reflected)": "xss",
    "Cross Site Scripting (Persistent)": "xss",
    "SQL Injection - MySQL": "sqli",
    "SQL Injection - PostgreSQL": "sqli",
    "Remote File Inclusion": "path-traversal",
    "Directory Browsing": "path-traversal",
}


def parse_zap_results(zap_output, target_id):
    """Parse ZAP JSON report dict → list of scanner-result dicts.

    Args:
        zap_output: dict with "site" key containing alerts
        target_id: lab-* target ID for the result

    Returns:
        list of scanner-result conforming dicts
    """
    results = []
    for site in zap_output.get("site", []):
        for alert in site.get("alerts", []):
            finding_type = _FINDING_TYPE_MAP.get(alert.get("alert"), alert.get("alert", "unknown"))
            confidence = _CONFIDENCE_MAP.get(str(alert.get("confidence", alert.get("riskcode", "1"))), 0.5)
            endpoint_id = alert.get("uri")
            results.append(build_scanner_result(
                source="ZAP",
                target_id=target_id,
                finding_type=finding_type,
                confidence=confidence,
                endpoint_id=endpoint_id,
            ))
    return results
