"""Read-only checks for completed synthetic evaluation artifacts.

A caller-supplied manifest pin detects changed bytes. It does not authenticate
the producer, rerun experiments, restore history or certify statistical claims.
"""
import hashlib
from pathlib import Path
import re

from runtime.evidence.evidence_readonly import bounded_bytes, read_object


def verify_evaluation_package(directory: Path, expected_manifest_sha256: str) -> dict:
    if type(expected_manifest_sha256) is not str or not re.fullmatch(r"[a-f0-9]{64}", expected_manifest_sha256):
        raise ValueError("explicit manifest pin required")
    directory = Path(directory).absolute()
    data = bounded_bytes(directory / "manifest.json", directory)
    if hashlib.sha256(data).hexdigest() != expected_manifest_sha256:
        raise ValueError("evaluation manifest hash mismatch")
    manifest = read_object(directory / "manifest.json", directory)
    if (manifest.get("run_id") != directory.name or manifest.get("schema_version") != 2 or
            manifest.get("source") != "SIMULATED_FIXTURE"):
        raise ValueError("unsupported evaluation identity or provenance")
    observed = manifest.get("observed_state", {})
    if observed.get("pipeline") != "COMPLETED_OFFLINE":
        raise ValueError("evaluation package is incomplete")
    refs = observed.get("artifacts")
    if type(refs) is not list or len(refs) != 11:
        raise ValueError("complete artifact inventory required")
    expected = {"configuration.json", "analysis.json", "report.md"}
    expected |= {f"{split}-{candidate}.{kind}.json" for split in ("validation", "test")
                 for candidate in ("synthetic-review", "synthetic-random") for kind in ("log", "metrics")}
    names = set()
    for ref in refs:
        if type(ref) is not dict or set(ref) != {"name", "sha256"} or ref["name"] not in expected:
            raise ValueError("unexpected evaluation artifact reference")
        name = ref["name"]
        if name in names:
            raise ValueError("duplicate evaluation artifact reference")
        names.add(name)
        content = bounded_bytes(directory / name, directory)
        if hashlib.sha256(content).hexdigest() != ref["sha256"]:
            raise ValueError("evaluation artifact digest mismatch")
        if name.endswith(".json"):
            envelope = read_object(directory / name, directory)
            if envelope.get("run_id") != directory.name or envelope.get("source") != "SIMULATED_FIXTURE":
                raise ValueError("evaluation artifact provenance mismatch")
    if names != expected:
        raise ValueError("missing evaluation artifact")
    configuration = read_object(directory / "configuration.json", directory)["observed_state"]
    if observed.get("configuration") != configuration:
        raise ValueError("evaluation configuration conflict")
    return dict(run_id=directory.name, verified_artifacts=len(names),
                manifest_sha256=expected_manifest_sha256,
                integrity_scope="ARTIFACT_HASHES_AND_ENVELOPES",
                protocol_sha256=configuration["protocol_sha256"],
                experimental_claims="UNRESOLVED", independent_review="UNRESOLVED")
