"""Isolated scanner processes with a serialized, fail-closed stdio gate relay."""
from __future__ import annotations

import hashlib
import copy
import json
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid
from pathlib import Path

from runtime.evidence.discovery_recorder import EvidenceFailure
from runtime.lab.capability_registry import CapabilityExecutionResult, VerificationFinding
from runtime.safety.discovery_gate import DiscoveryRequest
from scripts.validation.validate_scaffold import ROOT
from tools.parsers.nuclei_parser import parse_nuclei_results, _unique_object, _reject_constant
from tools.parsers.zap_parser import parse_zap_results

TOOLS = {"zap-passive", "zap-active", "nuclei"}
TEMPLATES = {"lab-sql-error": "sqli", "lab-sentinel-disclosure": "path-traversal"}
FAMILIES = {"sqli": "SQL_INJECTION", "xss": "SCRIPT_INJECTION", "path-traversal": "PATH_TRAVERSAL"}
ASSETS = ROOT / "tools" / "scanners"
LIMITATIONS = ["Unauthenticated observed GET/HEAD surface only; no POST or authenticated workflows",
              "Scanner candidates require independent verification; no confirmed vulnerability claim",
              "ZAP active rules: 40012,40018 only; Nuclei: SQL-error and lab-sentinel HTTP checks only"]


def load_config():
    config = json.loads((ROOT / "configs/tools/scanners.json").read_text(encoding="utf-8"))
    for key in ("bridge_image", "zap_image", "nuclei_image"):
        if not isinstance(config.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", config[key]):
            raise ValueError("Invalid scanner image configuration")
    if type(config.get("timeout_seconds")) is not int or not 1 <= config["timeout_seconds"] <= 600:
        raise ValueError("Invalid scanner timeout")
    if type(config.get("max_report_bytes")) is not int or not 1024 <= config["max_report_bytes"] <= 1048576:
        raise ValueError("Invalid scanner report limit")
    return config


def image_identity(image):
    result = subprocess.run(["docker", "image", "inspect", image, "--format", "{{json .}}"],
                            capture_output=True, text=True, timeout=10, check=False)
    if result.returncode:
        raise ValueError(f"SCANNER_IMAGE_UNAVAILABLE: {image}")
    data = json.loads(result.stdout)
    identity = data.get("Id", "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", identity) or identity != "sha256:" + image:
        raise ValueError("SCANNER_IMAGE_ID_INVALID")
    return {"id": identity, "digests": data.get("RepoDigests", []), "reference": image}


def preflight(selected):
    if type(selected) not in (list, tuple) or any(type(tool) is not str or tool not in TOOLS for tool in selected):
        raise ValueError("Unknown scanner selection")
    if len(set(selected)) != len(selected) or len(selected) > 2 or {"zap-passive", "zap-active"} <= set(selected):
        raise ValueError("Choose one ZAP mode and/or Nuclei")
    if not selected:
        return {}
    config = load_config()
    keys = {"bridge_image"} | {"nuclei_image" if t == "nuclei" else "zap_image" for t in selected}
    return {key: image_identity(config[key]) for key in sorted(keys)}


class ScannerRelay:
    def __init__(self, gate, recorder, run_id, target_id, inventory, approval, action_id, cancelled):
        self.gate, self.recorder = gate, recorder
        self.run_id, self.target_id, self.approval = run_id, target_id, approval
        self.action_id, self.cancelled = action_id, cancelled
        self.origin = "http://" + target_id
        self.paths = {}
        self.seed_urls = set()
        self.refusals = 0
        self.executed_urls = set()
        for item in inventory.items.values():
            parsed = urllib.parse.urlsplit(item.canonical_url)
            canon = gate.canonicalizer.canonicalize(item.canonical_url)
            if not canon.is_valid or item.refusal_reason:
                continue
            self.paths.setdefault(parsed.path or "/", set()).update(
                key for key, _ in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
            self.seed_urls.add(self.origin + (parsed.path or "/") + ("?" + parsed.query if parsed.query else ""))
        for item in inventory.items.values():
            if item.refusal_reason or not gate.canonicalizer.canonicalize(item.canonical_url).is_valid:
                continue
            for form in item.forms:
                if form.get("method", "GET").upper() != "GET":
                    continue
                url = urllib.parse.urljoin(item.canonical_url, form.get("action") or item.canonical_url)
                if not gate.canonicalizer.canonicalize(url).is_valid:
                    continue
                path = urllib.parse.urlsplit(url).path or "/"
                if path in self.paths:
                    self.paths[path].update(i["name"] for i in form.get("inputs", []) if i.get("name"))
                    query = urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query, keep_blank_values=True)
                    defaults = list(query)
                    for field in form.get("inputs", []):
                        if field.get("type") != "select" or not field.get("name"):
                            continue
                        options = field.get("options", [])
                        if type(options) is not list:
                            continue
                        values = [option for option in options[:16] if type(option) is dict
                                  and type(option.get("value")) is str and 0 < len(option["value"]) <= 128
                                  and not any(ord(c) < 32 or ord(c) == 127 for c in option["value"])]
                        if values and field["name"] not in {key for key, _ in defaults}:
                            chosen = next((option for option in values if option.get("selected") is True), values[0])
                            defaults.append((field["name"], chosen["value"]))
                    if defaults != query:
                        candidate = self.origin + path + "?" + urllib.parse.urlencode(defaults)
                        checked = gate.canonicalizer.canonicalize(gate.base_origin + path + "?" + urllib.parse.urlencode(defaults))
                        if checked.is_valid and not checked.redacted:
                            self.seed_urls.add(candidate)
                    for field in form.get("inputs", []):
                        if field.get("name") and field.get("type", "text").lower() in ("text", "search"):
                            query = list(defaults)
                            if field["name"] not in {key for key, _ in query}:
                                query.append((field["name"], ""))
                            checked = gate.canonicalizer.canonicalize(gate.base_origin + path + "?" + urllib.parse.urlencode(query))
                            if checked.is_valid and not checked.redacted:
                                self.seed_urls.add(self.origin + path + "?" + urllib.parse.urlencode(query))

    def check(self):
        if self.cancelled() or self.gate.kill_switch.is_active():
            raise RuntimeError("SCANNER_CANCELLED")
        if self.gate.halted_due_to_evidence:
            raise EvidenceFailure("SCANNER_EVIDENCE_HALTED")
        if not self.gate.lab_mode or self.target_id not in self.gate.effective_targets:
            raise RuntimeError("SCANNER_TARGET_REVOKED")
        origin = urllib.parse.urlsplit(self.gate.base_origin)
        registered = self.gate.target_registry.get(self.target_id, {})
        if (origin.scheme != "http" or origin.hostname != "127.0.0.1"
                or origin.port != registered.get("port") or origin.username is not None
                or origin.password is not None or origin.path or origin.query or origin.fragment):
            raise RuntimeError("SCANNER_GATE_ORIGIN_MISMATCH")
        if self.action_id not in self.gate.effective_actions:
            raise RuntimeError("SCANNER_ACTION_REVOKED")
        if (self.approval is None or not self.approval.is_valid()[0] or self.approval.run_id != self.run_id
                or self.approval.target_id != self.target_id or self.approval.action_id not in ("*", self.action_id)):
            raise RuntimeError("SCANNER_APPROVAL_INVALID")
        if not self.gate.budget_tracker.can_request():
            raise RuntimeError("SCANNER_BUDGET_EXHAUSTED")

    def urls(self):
        return sorted(self.seed_urls)[:100]

    def dispatch(self, message):
        self.check()
        reason = "SCANNER_REQUEST_OUT_OF_SCOPE"
        valid = type(message) is dict and set(message) == {"url", "method"}
        url, method = (message.get("url"), message.get("method")) if valid else (None, None)
        # Parse only bounded strings. Neither headers, bodies nor arbitrary ports cross this boundary.
        valid = valid and type(url) is str and len(url) <= 8192 and method in ("GET", "HEAD")
        if valid:
            try:
                parsed = urllib.parse.urlsplit(url)
                keys = {k for k, _ in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)}
                valid = (parsed.scheme == "http" and parsed.netloc in (self.target_id, self.target_id + ":80") and not parsed.fragment
                         and parsed.path in self.paths and keys <= self.paths[parsed.path]
                         and not any(ord(c) < 33 or ord(c) == 127 for c in url) and "\\" not in url)
                mapped = self.gate.base_origin + parsed.path + ("?" + parsed.query if parsed.query else "")
                valid = valid and self.gate.canonicalizer.canonicalize(mapped).is_valid
            except ValueError:
                valid = False
        if not valid:
            self.refusals += 1
            self.recorder.persist_phase_artifact("scanner_refusal", {"run_id": self.run_id,
                "source": "SCANNER_RELAY", "reason": reason, "request_sha256": hashlib.sha256(
                    json.dumps(message, sort_keys=True).encode()).hexdigest()})
            if self.refusals >= 32:
                raise RuntimeError("SCANNER_REFUSAL_LIMIT")
            return {"status": 403, "headers": {}, "body": reason}
        response = self.gate.dispatch(DiscoveryRequest(run_id=self.run_id, target_id=self.target_id,
            action_id=self.action_id, url=mapped, method=method, approval=self.approval))
        if self.gate.halted_due_to_evidence or not response.durable_confirmed:
            if self.gate.halted_due_to_evidence:
                raise EvidenceFailure("SCANNER_DISPATCH_EVIDENCE_FAILED")
            raise RuntimeError(response.refusal_reason or "SCANNER_DISPATCH_FAILED")
        if not response.status_code or response.truncated:
            raise RuntimeError("SCANNER_RESPONSE_INCOMPLETE")
        if any(key.lower() == "content-encoding" and value.lower() not in ("", "identity")
               for key, value in response.headers.items()):
            raise RuntimeError("SCANNER_COMPRESSED_RESPONSE_UNSUPPORTED")
        self.executed_urls.add(self.origin + parsed.path + ("?" + parsed.query if parsed.query else ""))
        headers = {}
        for key, value in response.headers.items():
            if key.lower() in ("content-type", "location", "x-content-type-options", "content-security-policy",
                               "x-frame-options", "cache-control") and "\r" not in value and "\n" not in value:
                headers[key] = value.replace(self.gate.base_origin, self.origin)
        return {"status": response.status_code, "headers": headers, "body": response.body}


def parse_runtime_nuclei(raw, relay):
    records = []
    for line in raw.decode("utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        if type(record) is not dict or record.get("matched-at") not in relay.executed_urls:
            raise ValueError("SCANNER_UNBOUND_REPORT_URL")
        # Nuclei 3.4.10 through an HTTP proxy omits host and emits a malformed diagnostic url.
        # Bind matches to actual gated requests, then feed the existing strict candidate parser.
        records.append({"template-id": record.get("template-id"), "type": record.get("type"),
                        "matcher-status": record.get("matcher-status"), "info": record.get("info"),
                        "host": record.get("host", relay.origin), "matched-at": record["matched-at"],
                        "error": record.get("error", "")})
    return parse_nuclei_results(records, relay.target_id, allowed_templates=TEMPLATES)


def parse_runtime_zap(report, relay):
    # Validate the entire untrusted report, including alerts outside the research families.
    parse_zap_results(report, relay.target_id)
    bounded = copy.deepcopy(report)
    for site in bounded["site"]:
        retained = []
        for alert in site["alerts"]:
            instances = alert.get("instances", [{"uri": alert.get("uri")}])
            matched = []
            for instance in instances:
                parsed = urllib.parse.urlsplit(instance["uri"])
                normalized = urllib.parse.urlunsplit((parsed.scheme, parsed.hostname, parsed.path, parsed.query, ""))
                if parsed.port not in (None, 80) or normalized not in relay.executed_urls:
                    continue
                matched.append(instance)
            if matched:
                alert.pop("uri", None)
                alert["instances"] = matched
                retained.append(alert)
        site["alerts"] = retained
    return parse_zap_results(bounded, relay.target_id)


def _pump(stream, messages, limit):
    try:
        while True:
            line = stream.readline(limit + 1)
            if not line:
                messages.put(None, timeout=1)
                return
            if len(line) > limit:
                messages.put(ValueError("SCANNER_OUTPUT_LIMIT"), timeout=1)
                return
            messages.put(line, timeout=1)
    except (OSError, ValueError, queue.Full):
        return


def isolated_scan(tool, relay, identities, config):
    """No host shell, host port, Docker socket mount, target network, or implicit image pull."""
    nonce = uuid.uuid4().hex
    bridge_name, scanner_name = "lab-relay-" + nonce, "lab-scanner-" + nonce
    common = ["docker", "run", "--rm", "--pull=never", "--read-only", "--cap-drop=ALL",
              "--security-opt=no-new-privileges", "--pids-limit=256", "--memory=2g", "--cpus=1",
              "--tmpfs", "/tmp:rw,nosuid,size=512m", "--user", "1000:1000"]
    mount = ["--mount", f"type=bind,source={ASSETS},target=/scanner,readonly"]
    bridge_cmd = common + ["--name", bridge_name, "--network=none", "-i"] + mount + [
        "--entrypoint", "python", identities["bridge_image"]["id"], "-B", "-u", "/scanner/stdio_proxy.py"]
    scanner_cmd = common + ["--name", scanner_name, "--network", "container:" + bridge_name] + mount
    if tool == "nuclei":
        scanner_cmd += ["-i", "-e", "HOME=/tmp", "--entrypoint", "/usr/local/bin/nuclei",
                        identities["nuclei_image"]["id"], "-list", "/dev/stdin", "-jsonl", "-silent", "-nc",
                        "-duc", "-ni", "-or", "-ot", "-c", "1", "-bs", "1", "-rl", "1", "-retries", "0",
                        "-timeout", "10", "-proxy", "http://127.0.0.1:8081", "-proxy-internal"]
        for name in TEMPLATES:
            scanner_cmd += ["-t", "/scanner/templates/" + name + ".yaml"]
        job = "\n".join(relay.urls()) + "\n"
    else:
        scanner_cmd += ["-i", "-e", "HOME=/tmp", "--entrypoint", "python3", identities["zap_image"]["id"],
                        "-B", "/scanner/zap_worker.py"]
        job = json.dumps({"active": tool == "zap-active", "urls": relay.urls()})
    bridge = scanner = None
    output = bytearray()
    deadline = time.monotonic() + config["timeout_seconds"]
    requests, reports = queue.Queue(4), queue.Queue(4)
    try:
        relay.check()
        bridge = subprocess.Popen(bridge_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        threading.Thread(target=_pump, args=(bridge.stdout, requests, 32768), daemon=True).start()
        ready = False
        while time.monotonic() < deadline:
            relay.check()
            try:
                request = requests.get(timeout=0.1)
            except queue.Empty:
                request = b""
            if isinstance(request, Exception):
                raise request
            if request is None:
                raise RuntimeError("SCANNER_RELAY_EXITED")
            if request:
                message = json.loads(request)
                if not ready:
                    if message != {"ready": True}:
                        raise ValueError("SCANNER_RELAY_HANDSHAKE_FAILED")
                    ready = True
                    scanner = subprocess.Popen(scanner_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                               stderr=subprocess.DEVNULL)
                    threading.Thread(target=_pump, args=(scanner.stdout, reports, config["max_report_bytes"]),
                                     daemon=True).start()
                    scanner.stdin.write(job.encode())
                    scanner.stdin.close()
                else:
                    response = relay.dispatch(message)
                    bridge.stdin.write(json.dumps(response).encode() + b"\n")
                    bridge.stdin.flush()
            try:
                while True:
                    line = reports.get_nowait()
                    if isinstance(line, Exception):
                        raise line
                    if line is None:
                        if scanner.wait(timeout=5) != 0:
                            raise RuntimeError("SCANNER_PROCESS_FAILED")
                        return bytes(output)
                    output.extend(line)
                    if len(output) > config["max_report_bytes"]:
                        raise ValueError("SCANNER_OUTPUT_LIMIT")
            except queue.Empty:
                pass
        raise RuntimeError("SCANNER_TIMEOUT")
    finally:
        cleanup_errors = []
        for name in (scanner_name, bridge_name):
            try:
                result = subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=10)
                if result.returncode and b"No such container" not in result.stderr:
                    cleanup_errors.append(name)
            except (OSError, subprocess.TimeoutExpired):
                cleanup_errors.append(name)
        for process in (scanner, bridge):
            if process:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
                for stream in (process.stdin, process.stdout):
                    if stream and not stream.closed:
                        stream.close()
        if cleanup_errors and sys.exc_info()[0] is None:
            raise RuntimeError("SCANNER_CLEANUP_FAILED:" + ",".join(cleanup_errors))


class ExternalScannerExecutor:
    def __init__(self, selected, cancelled=lambda: False, event_hook=None):
        self.selected = tuple(selected)
        self.cancelled = cancelled
        self.event_hook = event_hook or (lambda *args, **kwargs: None)
        self.results = []

    def execute(self, proposal, gate, recorder, run_id, target_id, inventory, approval):
        action = proposal["action_id"]
        if self.results:
            raise ValueError("SCANNER_BATCH_ALREADY_EXECUTED")
        before = gate.network_dispatch_count
        findings, facts = [], []
        result_ids = []
        for tool in self.selected:
            tool_before = gate.network_dispatch_count
            relay = ScannerRelay(gate, recorder, run_id, target_id, inventory, approval, action, self.cancelled)
            summary = {"tool": tool, "status": "ERROR", "limitations": LIMITATIONS, "run_id": run_id}
            self.event_hook("SCANNER_STARTED", action_id=action, payload={"tool": tool, "status": "RUNNING"})
            try:
                relay.check()
                if not relay.paths:
                    raise RuntimeError("SCANNER_NO_OBSERVED_SURFACE")
                identities = preflight([tool])
                assets = {str(p.relative_to(ASSETS)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in [ASSETS / "stdio_proxy.py", ASSETS / "zap_worker.py",
                                    *(ASSETS / "templates" / (n + ".yaml") for n in TEMPLATES)]}
                summary.update({"images": identities, "asset_hashes": assets, "scope_urls_count": len(relay.urls())})
                recorder.persist_phase_artifact("scanner_intent", {**summary, "expected_state": "SCANNER_COMPLETED",
                                                                     "observed_state": "SCANNER_REQUESTED"})
                raw = isolated_scan(tool, relay, identities, load_config())
                summary["report_sha256"] = hashlib.sha256(raw).hexdigest()
                if gate.network_dispatch_count == tool_before:
                    raise RuntimeError("SCANNER_NO_TARGET_REQUESTS")
                if tool == "nuclei":
                    candidates = parse_runtime_nuclei(raw, relay)
                else:
                    envelope = json.loads(raw)
                    summary["version"] = envelope["version"]
                    candidates = parse_runtime_zap(envelope["report"], relay)
                summary.update({"status": "COMPLETED", "candidate_count": len(candidates), "candidates": candidates,
                                "refused_requests": relay.refusals,
                                "coverage": "PARTIAL" if relay.refusals else "BOUNDED"})
            except EvidenceFailure:
                raise
            except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
                # Record fixed error categories, never provider output or raw target responses.
                summary["reason"] = str(exc) if str(exc).startswith("SCANNER_") else type(exc).__name__
                summary["coverage"] = "INCOMPLETE"
                candidates = []
            artifact = recorder.persist_phase_artifact("scanner_result", summary)
            summary["evidence_id"] = artifact["evidence_id"]
            result_ids.append(artifact["evidence_id"])
            self.results.append(summary)
            self.event_hook("SCANNER_COMPLETED", action_id=action, payload=summary)
            for candidate in candidates:
                findings.append(VerificationFinding(finding_id="FND-" + uuid.uuid4().hex,
                    family=FAMILIES[candidate["finding_type"]], classification="CANDIDATE",
                    resource_ref=target_id, input_ref="", source_observation_refs=[], verification_action=action,
                    result_evidence_refs=[artifact["evidence_id"]], confidence=candidate["confidence"],
                    limitations=LIMITATIONS, reason=tool + ": unconfirmed " + candidate["finding_type"]))
            facts.append({"fact_id": "FACT-SCANNER-" + uuid.uuid4().hex, "fact_type": "ACTION_OUTCOME",
                          "subject": action + ":" + tool, "value": summary["status"], "confidence": 1.0})
            for family in sorted({candidate["finding_type"] for candidate in candidates}):
                facts.append({"fact_id": "FACT-SCANNER-" + uuid.uuid4().hex, "fact_type": "ACTION_OUTCOME",
                              "subject": action + ":" + tool + ":" + family,
                              "value": "UNCONFIRMED_CANDIDATE", "confidence": 0.0})
            if summary["status"] != "COMPLETED":
                break
        aggregate = recorder.persist_phase_artifact("scanner_batch", {"run_id": run_id,
            "results": self.results, "result_evidence_refs": result_ids}, derived_from=result_ids)
        success = len(self.results) == len(self.selected) and all(r["status"] == "COMPLETED" for r in self.results)
        return CapabilityExecutionResult(action_id=action, target_id=target_id,
            outcome="SUCCESS" if success else "FAILURE", classification="SIGNAL" if findings else "INCONCLUSIVE",
            findings=findings, new_facts=facts, network_dispatch_count=gate.network_dispatch_count - before,
            result_evidence_id=aggregate["evidence_id"], details={"scanners": self.results})
