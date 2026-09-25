"""Observation normalizer — ingest scanner-result, emit canonical observation facts.

Ingests scanner-result dicts from Discovery, ZAP, Nuclei adapters.
Normalizes to canonical facts per observation.schema.json.
Deduplicates by (fact_type, subject, value).
Standardizes confidence scores to [0,1].

Isolation: planner sees only observation.schema.json output.
"""

import hashlib
import re
from datetime import datetime, timezone


# Canonical finding type mapping (unified across all scanner sources)
_CANONICAL_FINDING_TYPES = {
    "sqli": "sqli",
    "sql_injection": "sqli",
    "xss": "xss",
    "cross_site_scripting": "xss",
    "path-traversal": "path-traversal",
    "path_traversal": "path-traversal",
    "lfi": "path-traversal",
    "rfi": "path-traversal",
    "directory_browsing": "path-traversal",
    "open_port": "open_port",
}

# scanner source → default fact_type for findings
_SOURCE_FACT_TYPE = {
    "DISCOVERY": "SERVICE",
    "ZAP": "CANDIDATE_FINDING",
    "NUCLEI": "CANDIDATE_FINDING",
}

_ACTION_ID_PATTERN = re.compile(r"^ACTION-[A-Z]+-[0-9]{3}$")


def _clamp_confidence(c):
    """Clamp confidence to [0, 1]."""
    if not isinstance(c, (int, float)):
        return 0.5
    return max(0.0, min(1.0, float(c)))


def _make_fact_id(fact_type, subject, value):
    """Deterministic fact_id from content hash."""
    raw = f"{fact_type}:{subject}:{value}"
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"FACT-{fact_type[:4]}-{h}"


class ObservationNormalizer:
    """Normalize scanner-results into canonical observation facts.

    Usage:
        normalizer = ObservationNormalizer()
        observation = normalizer.normalize(
            scanner_results=[...],
            run_id="RUN-001",
            action_id="ACTION-RECON-001",
        )
    """

    def __init__(self):
        self._seen = {}  # dedup key → fact dict

    def reset(self):
        """Clear deduplication state between runs."""
        self._seen.clear()

    def normalize(self, scanner_results, run_id, action_id, observation_id=None):
        """Normalize list of scanner-result dicts → single observation dict.

        Args:
            scanner_results: list of scanner-result.schema.json dicts
            run_id: current run identifier
            action_id: ACTION-*-NNN that produced these results
            observation_id: optional; auto-generated if omitted

        Returns:
            dict conforming to observation.schema.json
        """
        if not _ACTION_ID_PATTERN.match(action_id):
            raise ValueError(f"action_id '{action_id}' invalid format")

        facts = []
        for sr in scanner_results:
            new_facts = self._scanner_result_to_facts(sr)
            facts.extend(new_facts)

        # Deduplicate
        deduped = self._deduplicate(facts)

        if observation_id is None:
            observation_id = f"OBS-NORM-{action_id}-{run_id}"

        return {
            "observation_id": observation_id,
            "run_id": run_id,
            "action_id": action_id,
            "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "outcome": "SUCCESS" if deduped else "PARTIAL",
            "new_facts": deduped,
        }

    def normalize_observation(self, observation):
        """Normalize an existing observation dict (from adapter output).

        Deduplicates and standardizes facts within the observation.
        Returns new observation with cleaned facts.
        """
        if "new_facts" not in observation:
            return dict(observation)

        cleaned_facts = []
        for fact in observation["new_facts"]:
            fact = dict(fact)
            fact["confidence"] = _clamp_confidence(fact.get("confidence", 0.5))
            cleaned_facts.append(fact)

        deduped = self._deduplicate(cleaned_facts)
        result = dict(observation)
        result["new_facts"] = deduped
        return result

    def _scanner_result_to_facts(self, sr):
        """Convert one scanner-result dict to list of fact dicts."""
        source = sr.get("source", "UNKNOWN")
        target_id = sr.get("target_id", "")
        finding_type_raw = sr.get("finding_type", "unknown")
        confidence = _clamp_confidence(sr.get("confidence", 0.5))
        endpoint_id = sr.get("endpoint_id")

        # Canonicalize finding type
        finding_type = _CANONICAL_FINDING_TYPES.get(finding_type_raw, finding_type_raw)

        # Determine fact_type from source and finding
        fact_type = _SOURCE_FACT_TYPE.get(source, "CANDIDATE_FINDING")

        # For discovery open_port results, use SERVICE type
        if finding_type == "open_port":
            fact_type = "SERVICE"

        facts = []

        # Main finding fact
        fact_value = finding_type
        if endpoint_id:
            fact_value = f"{finding_type}@{endpoint_id}"

        facts.append({
            "fact_id": _make_fact_id(fact_type, target_id, fact_value),
            "fact_type": fact_type,
            "subject": target_id,
            "value": fact_value,
            "confidence": confidence,
        })

        # If endpoint_id present, also emit ENDPOINT fact
        if endpoint_id:
            facts.append({
                "fact_id": _make_fact_id("ENDPOINT", target_id, endpoint_id),
                "fact_type": "ENDPOINT",
                "subject": target_id,
                "value": endpoint_id,
                "confidence": 1.0,
            })

        return facts

    def _deduplicate(self, facts):
        """Deduplicate facts by (fact_type, subject, value). Keep highest confidence."""
        seen = {}
        for fact in facts:
            key = (fact["fact_type"], fact["subject"], fact["value"])
            if key in seen:
                if fact["confidence"] > seen[key]["confidence"]:
                    seen[key] = fact
            else:
                seen[key] = fact
        return list(seen.values())
