"""Shared metadata for the existing bounded 13-action planner catalog."""

ACTION_CATALOG = {
    "ACTION-RECON-001": {"name": "DISCOVER_TARGET",      "class": "RECON"},
    "ACTION-RECON-002": {"name": "DISCOVER_WEB_SURFACE", "class": "RECON"},
    "ACTION-SCAN-001":  {"name": "PASSIVE_WEB_SCAN",     "class": "SCAN"},
    "ACTION-SCAN-002":  {"name": "ACTIVE_WEB_SCAN",      "class": "SCAN"},
    "ACTION-WEB-001":   {"name": "TEST_SQLI_CLASS",      "class": "WEB_TEST"},
    "ACTION-WEB-002":   {"name": "TEST_XSS_CLASS",       "class": "WEB_TEST"},
    "ACTION-WEB-003":   {"name": "TEST_PATH_TRAVERSAL",  "class": "WEB_TEST"},
    "ACTION-PLAN-001":  {"name": "CHANGE_TARGET",        "class": "PLAN"},
    "ACTION-PLAN-002":  {"name": "CHANGE_HYPOTHESIS",    "class": "PLAN"},
    "ACTION-PLAN-003":  {"name": "REVISIT_EVIDENCE",     "class": "PLAN"},
    "ACTION-END-001":   {"name": "STOP_SUCCESS",         "class": "STOP"},
    "ACTION-END-002":   {"name": "STOP_BUDGET",          "class": "STOP"},
    "ACTION-END-003":   {"name": "STOP_NO_PROGRESS",     "class": "STOP"},
}

