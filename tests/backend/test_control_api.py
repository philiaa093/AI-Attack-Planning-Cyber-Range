"""Unit and Integration tests for Dashboard Control API and RunManager."""
from __future__ import annotations

import json
import base64
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from dashboards.app.backend.control_api import app, run_manager, range_controller, event_sink
from dashboards.app.backend.models import AgentState, RangeState, StepState


class TestControlAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        event_sink.clear()

    def test_get_status(self):
        """Verify GET /api/status returns structured SystemStatus without crashing."""
        resp = self.client.get("/api/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["api"], "healthy")
        self.assertIn("range", data)
        self.assertIn("run", data)
        self.assertIn("agent", data)
        self.assertIn("safety", data)
        self.assertIn("evidence", data)
        self.assertIn("pipeline", data)

        # Range must report structured status
        self.assertIn(data["range"]["status"], [s.value for s in RangeState])
        self.assertEqual(data["range"]["target_id"], "lab-ecommerce")

    def test_get_range_status(self):
        """Verify GET /api/range/status returns genuine Docker/services state."""
        resp = self.client.get("/api/range/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("status", data)
        self.assertIn("checked_at_utc", data)

    def test_range_stop_when_no_owned_services(self):
        """Verify POST /api/range/stop is a safe no-op when no services are owned."""
        resp = self.client.post("/api/range/stop")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["message"], "No owned services to stop")

    def test_preflight_real_validation(self):
        """Verify POST /api/demo/preflight returns genuine check items and blockers."""
        resp = self.client.post("/api/demo/preflight")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("passed", data)
        self.assertIn("outcome", data)
        self.assertIsInstance(data["checks"], list)
        self.assertIsInstance(data["blockers"], list)
        self.assertTrue(len(data["checks"]) > 0)

        check_names = [c["name"] for c in data["checks"]]
        self.assertIn("DOCKER_AVAILABLE", check_names)
        self.assertIn("CANONICAL_POLICY", check_names)

    def test_event_sink_thread_safety(self):
        """Verify EventSink handles concurrent multi-threaded publishing."""
        run_id = "RUN-TEST-" + uuid.uuid4().hex
        threads = []

        def publisher(idx):
            for i in range(10):
                event_sink.publish({
                    "run_id": run_id,
                    "type": f"TEST_EVENT_{idx}_{i}",
                    "payload": {"idx": idx, "i": i},
                })

        for t_idx in range(5):
            t = threading.Thread(target=publisher, args=(t_idx,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        history = event_sink.get_history(run_id=run_id, limit=100)
        self.assertEqual(len(history), 50)

    def test_deny_demo_execution_flow(self):
        """Verify POST /api/runs with mode='deny-demo' executes zero-dispatch safety denial."""
        req_payload = {
            "mode": "deny-demo",
            "planner": "rule",
            "allow_fallback": True,
            "target": "lab-ecommerce",
            "approve_read_only": True,
        }
        resp = self.client.post("/api/runs", json=req_payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        run_id = data["run_id"]

        # Wait briefly for background worker to complete deny case
        for _ in range(50):
            time.sleep(0.1)
            curr = self.client.get("/api/runs/current").json()
            if curr["run"]["state"] in ("COMPLETED", "FAILED"):
                break

        final_curr = self.client.get("/api/runs/current").json()
        self.assertEqual(final_curr["run"]["state"], "COMPLETED")
        self.assertEqual(final_curr["run"]["stop_reason"], "DENY_DEMO_COMPLETED")
        self.assertEqual(final_curr["safety"]["network_dispatches"], 0)
        self.assertGreaterEqual(final_curr["safety"]["denials_count"], 1)

    def test_prevent_duplicate_active_runs(self):
        """Verify system forbids starting a new run while another run is active."""
        req_payload = {
            "mode": "deny-demo",
            "planner": "rule",
        }
        with run_manager._lock:
            run_manager._run_status.state = AgentState.RUNNING
            run_manager._active_run_id = "RUN-ACTIVE-TEST"

        try:
            resp = self.client.post("/api/runs", json=req_payload)
            self.assertEqual(resp.status_code, 409)
            self.assertIn("Another run is currently active", resp.json()["detail"])
        finally:
            with run_manager._lock:
                run_manager._run_status.state = AgentState.IDLE
                run_manager._active_run_id = None

    def test_emergency_stop_halts_active_state(self):
        """Verify POST /api/emergency-stop activates kill switch and halts dispatches."""
        resp = self.client.post("/api/emergency-stop")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])

        # Check status reflects blocked/kill switch
        curr = self.client.get("/api/runs/current").json()
        self.assertEqual(curr["run"]["state"], "BLOCKED")
        self.assertEqual(curr["run"]["stop_reason"], "EMERGENCY_KILL_SWITCH_ACTIVATED")

    def test_evidence_and_findings_endpoints(self):
        """Verify GET /api/runs/{run_id}/evidence, /findings, /summary against real run data."""
        # Check if there is an existing run in demo-output
        sample_runs = list(run_manager.output_root.glob("RUN-*"))
        if not sample_runs:
            return  # Skip if no runs recorded yet

        run_id = sample_runs[0].name
        # 1. Evidence list
        ev_resp = self.client.get(f"/api/runs/{run_id}/evidence")
        self.assertEqual(ev_resp.status_code, 200)
        ev_data = ev_resp.json()
        self.assertIn("items", ev_data)
        self.assertIn("integrity_status", ev_data)
        self.assertGreaterEqual(ev_data["evidence_count"], 1)

        # 2. Evidence detail
        first_ev_id = ev_data["items"][0]["evidence_id"]
        det_resp = self.client.get(f"/api/runs/{run_id}/evidence/{first_ev_id}")
        self.assertEqual(det_resp.status_code, 200)
        det_data = det_resp.json()
        self.assertEqual(det_data["evidence_id"], first_ev_id)
        self.assertTrue(det_data["verified"])
        self.assertIsNotNone(det_data["content"])

        # 3. Findings list
        fnd_resp = self.client.get(f"/api/runs/{run_id}/findings")
        self.assertEqual(fnd_resp.status_code, 200)
        fnd_data = fnd_resp.json()
        self.assertIn("items", fnd_data)
        self.assertIn("findings_count", fnd_data)

        # 4. Run Summary
        sum_resp = self.client.get(f"/api/runs/{run_id}/summary")
        self.assertEqual(sum_resp.status_code, 200)
        sum_data = sum_resp.json()
        self.assertEqual(sum_data["run_id"], run_id)
        self.assertIn("integrity_status", sum_data)
        self.assertIn("network_dispatches", sum_data)

    def test_path_traversal_protection(self):
        """Verify strict path traversal protection across all run inspection endpoints."""
        traversal_payloads = [
            "..",
            "../..",
            "..%2F..",
            "....//....//",
            "C:\\Windows\\System32",
            "/etc/passwd",
            "RUN-ID/../../secret",
        ]
        for bad_id in traversal_payloads:
            r1 = self.client.get(f"/api/runs/{bad_id}/evidence")
            self.assertIn(r1.status_code, (400, 404))

            r2 = self.client.get(f"/api/runs/{bad_id}/findings")
            self.assertIn(r2.status_code, (400, 404))

            r3 = self.client.get(f"/api/runs/{bad_id}/summary")
            self.assertIn(r3.status_code, (400, 404))

            r4 = self.client.get(f"/api/runs/{bad_id}/evidence/{bad_id}")
            self.assertIn(r4.status_code, (400, 404))

        # Unknown but valid syntax run_id should 404
        r_unk = self.client.get("/api/runs/RUN-NONEXISTENT-999999/evidence")
        self.assertEqual(r_unk.status_code, 404)

    def test_pause_and_resume_api_endpoints(self):
        """Verify POST /api/runs/{run_id}/pause and resume endpoints."""
        # Non-existent run -> 400 or 404
        p_resp = self.client.post("/api/runs/RUN-NONEXISTENT/pause")
        self.assertIn(p_resp.status_code, (400, 404))

        r_resp = self.client.post("/api/runs/RUN-NONEXISTENT/resume")
        self.assertIn(r_resp.status_code, (400, 404))

    def test_approval_and_rejection_api_security(self):
        """Verify POST /api/runs/{run_id}/proposals/{proposal_id}/approve and reject."""
        # Non-existent run -> 400 or 404
        app_resp = self.client.post("/api/runs/RUN-NONEXISTENT/proposals/PROP-01/approve")
        self.assertIn(app_resp.status_code, (400, 404))

        rej_resp = self.client.post(
            "/api/runs/RUN-NONEXISTENT/proposals/PROP-01/reject",
            json={"reason": "Operator denied"},
        )
        self.assertIn(rej_resp.status_code, (400, 404))

    def test_demo_readiness_endpoint(self):
        """Verify GET /api/demo/readiness separates REQUIRED vs OPTIONAL and reports honest LLM status."""
        resp = self.client.get("/api/demo/readiness")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn(data["overall_status"], ["READY", "DEGRADED", "BLOCKED"])
        self.assertIn("summary", data)
        self.assertIn("checks", data)
        self.assertIn("details", data)

        check_map = {c["name"]: c for c in data["checks"]}
        self.assertIn("BACKEND_API", check_map)
        self.assertEqual(check_map["BACKEND_API"]["category"], "REQUIRED")
        self.assertTrue(check_map["BACKEND_API"]["passed"])

        self.assertIn("SAFETY_POLICY", check_map)
        self.assertEqual(check_map["SAFETY_POLICY"]["category"], "REQUIRED")
        self.assertTrue(check_map["SAFETY_POLICY"]["passed"])

        self.assertIn("EVIDENCE_VAULT", check_map)
        self.assertEqual(check_map["EVIDENCE_VAULT"]["category"], "REQUIRED")
        self.assertTrue(check_map["EVIDENCE_VAULT"]["passed"])

        self.assertIn("LLM_PROVIDER", check_map)
        self.assertEqual(check_map["LLM_PROVIDER"]["category"], "OPTIONAL")
        # Missing LLM key must NEVER be in blockers
        self.assertNotIn("LLM_PROVIDER", data["blockers"])

        # Details must disclose fallback and offline replay capabilities
        self.assertTrue(data["details"]["llm_fallback_ready"])
        self.assertTrue(data["details"]["offline_replay_available"])
        self.assertIn("ports", data["details"])
        self.assertEqual(data["details"]["ports"]["backend"], 8000)
        self.assertEqual(data["details"]["ports"]["frontend"], 5173)


class TestControlCenterStop(unittest.TestCase):
    """Execute a temporary script copy with every process operation mocked."""

    def run_stop(self, case, shell="powershell"):
        executable = shutil.which(shell)
        if not executable:
            self.skipTest(f"{shell} is unavailable")
        directory = Path(tempfile.gettempdir()) / ("control-stop-" + uuid.uuid4().hex)
        directory.mkdir(mode=0o755)
        directory = directory.resolve()
        self.assertEqual(directory.parent, Path(tempfile.gettempdir()).resolve())
        self.addCleanup(shutil.rmtree, directory)
        project = Path(directory) / "project with spaces"
        script = project / "scripts" / "demo" / "stop_control_center.ps1"
        script.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / "scripts/demo/stop_control_center.ps1", script)
        role = case.get("role", "backend")
        process_name = "python" if role == "backend" else "node"
        process_exe = str(project / ".venv/Scripts/python.exe") if role == "backend" else r"C:\Program Files\nodejs\node.exe"
        command = (f'"{process_exe}" -m uvicorn dashboards.app.backend.control_api:app --app-dir "{project}"' if role == "backend" else
                   f'"{process_exe}" "{project}/dashboards/app/frontend/node_modules/vite/bin/vite.js" "{project}/dashboards/app/frontend"')
        fixture = {
            "id": 42420, "process_name": process_name, "executable": process_exe,
            "command": command, "created": "2026-10-13T00:59:59Z", **case.get("process", {}),
        }
        for key in ("command", "executable"):
            if isinstance(fixture[key], str):
                fixture[key] = fixture[key].replace("{root}", str(project)).replace("{other}", str(project) + "-other")
        session = {
            "session_id": "TEST-STOP", "started_at_utc": "2026-10-13T01:00:00Z",
            "backend_pid": None, "frontend_pid": None, "project_root": str(project),
            "backend_started_at_utc": None, "frontend_started_at_utc": None,
            f"{role}_started_at_utc": "2026-10-13T00:59:59Z",
            f"{role}_pid": fixture["id"], **case.get("session", {}),
        }
        session_file = project / ".demo-session.json"
        before = case.get("raw_session", json.dumps(session))
        if not case.get("no_session"):
            session_file.write_text(before, encoding="utf-8")
        (project / "fixture.json").write_text(json.dumps(fixture), encoding="utf-8")
        wrapper = r'''
$ErrorActionPreference = 'Stop'
$testRoot = '__ROOT__'
$global:stopTestFixture = Get-Content -LiteralPath (Join-Path $testRoot 'fixture.json') -Raw | ConvertFrom-Json
$global:stopTestStopped = @()
$global:stopTestProcesses = @()
if (-not $global:stopTestFixture.absent) {
$mock = [pscustomobject]@{
    Id = $global:stopTestFixture.id; ProcessName = $global:stopTestFixture.process_name;
    Handle = if ($global:stopTestFixture.handle_missing) { $null } elseif ($null -ne $global:stopTestFixture.handle) { $global:stopTestFixture.handle } else { 123 };
        StartTime = if ($global:stopTestFixture.created -is [datetime]) { $global:stopTestFixture.created.ToUniversalTime() }
            elseif ($global:stopTestFixture.created) { [DateTimeOffset]::Parse($global:stopTestFixture.created, [Globalization.CultureInfo]::InvariantCulture).UtcDateTime }
            else { $null };
    HasExited = [bool]$global:stopTestFixture.exited; MockProcess = $true
}
$mock | Add-Member ScriptMethod WaitForExit { param($timeout) return $this.HasExited }
$global:stopTestProcesses = @($mock)
}
function Get-Process {
param($ErrorAction)
if ($global:stopTestFixture.process_error) { throw 'Mock process lookup denied' }
return $global:stopTestProcesses
}
function Get-CimInstance {
param($ClassName, $Filter, $ErrorAction)
if ($Filter -notmatch '^ProcessId = [0-9]+$') { throw 'Unexpected child lookup' }
if ($global:stopTestFixture.cim_error) { throw 'Mock CIM unavailable' }
if ($global:stopTestFixture.cim_missing) { return $null }
return [pscustomobject]@{ ProcessId = $global:stopTestFixture.id; CommandLine = $global:stopTestFixture.command; ExecutablePath = $global:stopTestFixture.executable }
}
function Stop-Process {
param($InputObject, [switch]$Force, $ErrorAction)
if (-not $InputObject.MockProcess -or -not [object]::ReferenceEquals($InputObject, $global:stopTestProcesses[0])) {
    throw 'Unmocked termination rejected'
}
if ($global:stopTestFixture.stop_error) { throw 'Mock termination denied' }
$global:stopTestStopped += $InputObject.Id
$InputObject.HasExited = -not [bool]$global:stopTestFixture.stop_unconfirmed
if ($global:stopTestFixture.replace_session) {
    Set-Content -LiteralPath (Join-Path $testRoot '.demo-session.json') -Value '{"replacement":true}'
}
}
function Get-NetTCPConnection { throw 'Live port inspection rejected' }
& (Join-Path $testRoot 'scripts/demo/stop_control_center.ps1') -Force
$result = $LASTEXITCODE
Write-Output ('MOCK_STOPS=' + (ConvertTo-Json -InputObject @($global:stopTestStopped) -Compress))
exit $result
'''.replace("__ROOT__", str(project).replace("'", "''"))
        encoded = base64.b64encode(wrapper.encode("utf-16-le")).decode("ascii")
        result = subprocess.run(
            [executable, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
            cwd=project, capture_output=True, text=True, timeout=20,
        )
        output = result.stdout + result.stderr
        stops = next((json.loads(line.removeprefix("MOCK_STOPS=")) for line in result.stdout.splitlines()
                      if line.startswith("MOCK_STOPS=")), None)
        self.assertIsNotNone(stops, output)
        self.assertEqual(result.returncode, case.get("exit", 1), output)
        self.assertEqual(stops, case.get("stops", []), output)
        if case.get("retained", True):
            self.assertTrue(session_file.exists(), output)
            if not fixture.get("replace_session"):
                self.assertEqual(session_file.read_text(encoding="utf-8"), before)
        else:
            self.assertFalse(session_file.exists(), output)
        self.assertNotIn("Ports 8000 & 5173 freed", output)

    def test_verified_processes_and_absent_session(self):
        for case in (
            {"exit": 0, "stops": [42420]},
            {"role": "frontend", "exit": 0, "stops": [42420]},
            {"no_session": True, "exit": 0, "retained": False},
            {"process": {"absent": True}, "exit": 0},
            {"process": {"executable": r"C:\Python\python.exe", "command": '"C:\\Python\\python.exe" -m uvicorn dashboards.app.backend.control_api:app --app-dir "{root}"'},
             "exit": 0, "stops": [42420]},
            {"process": {"command": '"{root}\\.venv\\Scripts\\python.exe" -m uvicorn dashboards.app.backend.control_api:app --app-dir "{root}" --host 127.0.0.1 --port 8000'},
             "exit": 0, "stops": [42420]},
            {"role": "frontend", "process": {"command": '"C:\\Program Files\\nodejs\\node.exe" "{root}\\dashboards\\app\\frontend\\node_modules\\vite\\bin\\vite.js" "{root}\\dashboards\\app\\frontend" --host 127.0.0.1 --port 5173'},
             "exit": 0, "stops": [42420]},
        ):
            with self.subTest(case=case):
                self.run_stop(case)

    def test_unverified_processes_never_terminate(self):
        for role in ("backend", "frontend"):
            for change in (
                {"cim_error": True}, {"cim_missing": True}, {"command": ""}, {"command": " "},
                {"handle_missing": True}, {"handle": 0},
                {"created": None}, {"created": "2026-10-13T01:00:01Z"}, {"process_error": True},
                {"exited": True}, {"process_name": "unrelated"}, {"executable": r"C:\other.exe"},
                {"command": '"C:\\Python\\python.exe" -m uvicorn dashboards.app.backend.control_api:app'},
                {"command": '"{root}\\.venv\\Scripts\\python.exe" -m uvicorn dashboards.app.backend.control_api:app'},
                {"command": '"C:\\Program Files\\nodejs\\node.exe" "{root}\\dashboards\\app\\frontend\\node_modules\\vite\\bin\\vite.js"'},
                {"command": '"{root}\\.venv\\Scripts\\python.exe" -c "-m uvicorn dashboards.app.backend.control_api:app"'},
                {"command": '"{root}\\.venv\\Scripts\\python.exe" -m uvicorn dashboards.app.backend.control_api:app --app-dir "{other}"'},
                {"command": '"{root}\\.venv\\Scripts\\python.exe" -m uvicorn dashboards.app.backend.control_api:app --app-dir="{other}"'},
                {"command": '"{root}\\.venv\\Scripts\\python.exe" -m uvicorn dashboards.app.backend.control_api:app --app-dir "{root}\\"'},
                {"command": '"C:\\Program Files\\nodejs\\node.exe" --eval "{root}\\dashboards\\app\\frontend\\node_modules\\vite\\bin\\vite.js"'},
                {"command": '"C:\\Program Files\\nodejs\\node.exe" "{other}\\dashboards\\app\\frontend\\node_modules\\vite\\bin\\vite.js"'},
                {"command": '"C:\\Program Files\\nodejs\\node.exe" "{root}\\dashboards\\app\\frontend\\node_modules\\vite\\bin\\vite.js" --root "{other}"'},
                {"command": '"C:\\Program Files\\nodejs\\node.exe" "{root}\\dashboards\\app\\frontend\\node_modules\\vite\\bin\\vite.js" "{other}"'},
                {"command": '"C:\\Program Files\\nodejs\\node.exe" "{root}\\dashboards\\app\\frontend\\node_modules\\vite\\bin\\vite.js" "{root}\\dashboards\\app\\frontend\\"'},
                {"command": '"unterminated'},
            ):
                with self.subTest(role=role, change=change):
                    self.run_stop({"role": role, "process": change})

    def test_malformed_session_never_terminates(self):
        for change in (
            {"backend_pid": True}, {"backend_pid": "42420"}, {"backend_pid": -1},
            {"backend_pid": 0}, {"backend_pid": 2147483648}, {"frontend_pid": 42420},
            {"project_root": None}, {"project_root": "."}, {"project_root": r"C:\other"},
            {"started_at_utc": "invalid"}, {"started_at_utc": "2026-10-13T01:00:00"},
            {"started_at_utc": "2999-10-13T01:00:00Z"}, {"started_at_utc": "2026-10-13T01:00:00+07:00"},
            {"backend_started_at_utc": None}, {"backend_started_at_utc": "2026-10-13T00:59:58Z"},
            {"backend_started_at_utc": "invalid"}, {"backend_started_at_utc": 123},
        ):
            with self.subTest(change=change):
                self.run_stop({"session": change})
        self.run_stop({"raw_session": "{invalid json"})
        self.run_stop({"raw_session": '{"project_root":"C:\\\\other"}'})

    def test_failed_stop_or_replaced_session_preserves_receipt(self):
        self.run_stop({"process": {"stop_error": True}})
        self.run_stop({"process": {"stop_unconfirmed": True}, "stops": [42420]})
        self.run_stop({"process": {"replace_session": True}, "stops": [42420]})

    def test_powershell_core_compatibility(self):
        self.run_stop({"exit": 0, "stops": [42420]}, shell="pwsh")

    def test_non_windows_whitespace_never_terminates(self):
        for case in (
            {"process": {"command": '"{root}\\.venv\\Scripts\\python.exe" -m uvicorn dashboards.app.backend.control_api:app --app-dir "{root}"\u00a0'}},
            {"role": "frontend", "process": {"command": '"C:\\Program Files\\nodejs\\node.exe" "{root}\\dashboards\\app\\frontend\\node_modules\\vite\\bin\\vite.js" "{root}\\dashboards\\app\\frontend"\u00a0'}},
            {"process": {"command": '"{root}\\.venv\\Scripts\\python.exe" -m uvicorn dashboards.app.backend.control_api:app\u00a0--app-dir "{root}"'}},
        ):
            with self.subTest(case=case):
                self.run_stop(case)


class TestControlCenterLaunch(unittest.TestCase):
    """Run copied launcher/stopper scripts without services or network requests."""

    def run_launch(self, case, shell="powershell"):
        executable = shutil.which(shell)
        if not executable:
            self.skipTest(f"{shell} is unavailable")
        directory = Path(tempfile.gettempdir()) / ("control-launch-" + uuid.uuid4().hex)
        directory.mkdir(mode=0o755)
        directory = directory.resolve()
        self.assertEqual(directory.parent, Path(tempfile.gettempdir()).resolve())
        self.addCleanup(shutil.rmtree, directory)
        project = directory / "project with spaces"
        scripts = project / "scripts/demo"
        scripts.mkdir(parents=True)
        for name in ("start_control_center.ps1", "stop_control_center.ps1"):
            shutil.copyfile(ROOT / "scripts/demo" / name, scripts / name)
        for name in ("python.exe", "node.exe"):
            path = project / "tools" / name
            path.parent.mkdir(exist_ok=True)
            path.touch()
        vite = project / "dashboards/app/frontend/node_modules/vite/bin/vite.js"
        vite.parent.mkdir(parents=True)
        if not case.get("missing_vite"):
            vite.touch()
        (project / "fixture.json").write_text(json.dumps(case), encoding="utf-8")
        wrapper = r'''
$ErrorActionPreference = 'Stop'
$global:launchRoot = '__ROOT__'
$global:launchFixture = Get-Content -LiteralPath (Join-Path $global:launchRoot 'fixture.json') -Raw | ConvertFrom-Json
$global:launchProcesses = @(); $global:launchStarts = @(); $global:launchAttempts = @(); $global:launchStops = @(); $global:launchHttp = @()
$global:launchCheckpointLock = $null; $global:launchInitialCheckpoint = $null
function New-TestProcess($role, $file, $arguments) {
    $processId = if ($role -eq 'backend') { 42420 } else { 42421 }
    $mock = [pscustomobject]@{
        Id = $processId; ProcessName = [IO.Path]::GetFileNameWithoutExtension($file); Handle = 123;
        StartTime = [DateTimeOffset]::Parse('2026-10-13T00:59:59Z').UtcDateTime;
        HasExited = $false; MockProcess = $true; Role = $role; Executable = $file; Command = '"' + $file + '" ' + $arguments
    }
    $mock | Add-Member ScriptMethod WaitForExit { param($timeout) return $this.HasExited }
    return $mock
}
$python = Join-Path $global:launchRoot 'tools/python.exe'
$node = Join-Path $global:launchRoot 'tools/node.exe'
$frontend = Join-Path $global:launchRoot 'dashboards/app/frontend'
$vite = Join-Path $frontend 'node_modules/vite/bin/vite.js'
$backendArgs = '-m uvicorn dashboards.app.backend.control_api:app --app-dir "' + $global:launchRoot + '" --host 127.0.0.1 --port 8000'
$frontendArgs = '"' + $vite + '" "' + $frontend + '" --host 127.0.0.1 --port 5173'
$sessionFile = Join-Path $global:launchRoot '.demo-session.json'
if ($global:launchFixture.existing) {
    $old = @{
        session_id = 'EXISTING-SESSION'; project_root = $global:launchRoot; status = 'READY'; started_at_utc = '2026-10-13T01:00:00Z';
        backend_pid = 42420; frontend_pid = 42421; backend_started_at_utc = '2026-10-13T00:59:59Z'; frontend_started_at_utc = '2026-10-13T00:59:59Z';
        backend_url = 'http://127.0.0.1:8000'; frontend_url = 'http://127.0.0.1:5173'
    }
    $global:launchProcesses = @((New-TestProcess 'backend' $python $backendArgs), (New-TestProcess 'frontend' $node $frontendArgs))
    switch ($global:launchFixture.existing) {
        'reused_pid' { $global:launchProcesses[0].StartTime = $global:launchProcesses[0].StartTime.AddSeconds(1) }
        'legacy' { $old.Remove('backend_started_at_utc') }
        'partial' { $global:launchProcesses = @($global:launchProcesses[0]) }
        'absent' { $global:launchProcesses = @() }
        'wrong_root' { $old.project_root += '-other' }
        'wrong_url' { $old.backend_url = 'http://127.0.0.1:9000' }
    }
    [IO.File]::WriteAllText($sessionFile, ($old | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
}
$before = if (Test-Path -LiteralPath $sessionFile) { [IO.File]::ReadAllText($sessionFile) } else { $null }
function Get-Command {
    param($Name, $CommandType, $ErrorAction)
    if ($Name -eq 'python.exe') { return [pscustomobject]@{ Source = Join-Path $global:launchRoot 'tools/python.exe' } }
    if ($Name -eq 'node.exe') { return [pscustomobject]@{ Source = Join-Path $global:launchRoot 'tools/node.exe' } }
    return Microsoft.PowerShell.Core\Get-Command @PSBoundParameters
}
function Start-Process {
    param($FilePath, $ArgumentList, $WorkingDirectory, [switch]$PassThru, $WindowStyle)
    $role = if ($FilePath -eq (Join-Path $global:launchRoot 'tools/python.exe')) { 'backend' }
        elseif ($FilePath -eq (Join-Path $global:launchRoot 'tools/node.exe')) { 'frontend' }
        else { throw 'Unmocked process launch rejected' }
    if (-not $PassThru -or $WindowStyle -ne 'Hidden') { throw 'Unsafe launch options' }
    $expectedDirectory = if ($role -eq 'backend') { $global:launchRoot } else { Join-Path $global:launchRoot 'dashboards/app/frontend' }
    if ($WorkingDirectory -ne $expectedDirectory) { throw 'Unexpected working directory' }
    $global:launchAttempts += $role
    if ($role -eq 'backend' -and $global:launchFixture.checkpoint_failure) {
        $path = Join-Path $global:launchRoot '.demo-session.json'
        $global:launchInitialCheckpoint = [IO.File]::ReadAllText($path)
        $global:launchCheckpointLock = [IO.File]::Open($path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    }
    if ($role -eq 'frontend') {
        $checkpoint = Get-Content -LiteralPath (Join-Path $global:launchRoot '.demo-session.json') -Raw | ConvertFrom-Json
        if ($checkpoint.backend_pid -ne 42420 -or -not $checkpoint.backend_started_at_utc) { throw 'Backend identity was not checkpointed' }
        if ($global:launchFixture.fail_frontend) { throw 'Mock frontend startup failed' }
    }
    $mock = New-TestProcess $role $FilePath $ArgumentList
    if ($global:launchFixture.handle_error -and $role -eq 'backend') {
        $mock.PSObject.Properties.Remove('Handle')
        $mock | Add-Member ScriptProperty Handle { throw 'Mock handle inaccessible' }
    }
    $global:launchProcesses += $mock
    $global:launchStarts += @{ role = $role; file = $FilePath; arguments = $ArgumentList }
    return $mock
}
function Get-Process { param($ErrorAction) return @($global:launchProcesses | Where-Object { -not $_.HasExited }) }
function Get-CimInstance {
    param($ClassName, $Filter, $ErrorAction)
    if ($Filter -notmatch '^ProcessId = ([0-9]+)$') { throw 'Unmocked CIM lookup rejected' }
    $lookupId = [int]$Matches[1]
    $mock = @($global:launchProcesses | Where-Object Id -EQ $lookupId)[0]
    return [pscustomobject]@{ ProcessId = $mock.Id; CommandLine = $mock.Command; ExecutablePath = $mock.Executable }
}
function Stop-Process {
    param($InputObject, [switch]$Force, $ErrorAction)
    if (-not $InputObject.MockProcess -or -not @($global:launchProcesses | Where-Object { [object]::ReferenceEquals($_, $InputObject) }).Count) {
        throw 'Unmocked termination rejected'
    }
    $global:launchStops += $InputObject.Id
    $InputObject.HasExited = $true
}
function Get-NetTCPConnection {
    param($ErrorAction)
    if ($global:launchFixture.foreign_listener) { return [pscustomobject]@{ State = 'Listen'; LocalPort = 8000; LocalAddress = '127.0.0.1'; OwningProcess = 99999 } }
    foreach ($mock in $global:launchProcesses) {
        if ($mock.HasExited) { continue }
        $port = if ($mock.Role -eq 'backend') { 8000 } else { 5173 }
        if ($global:launchFixture.port_mismatch -and $mock.Role -eq 'backend') { $port = 9000 }
        [pscustomobject]@{ State = 'Listen'; LocalPort = $port; LocalAddress = '127.0.0.1'; OwningProcess = $mock.Id }
    }
}
function Invoke-RestMethod {
    param($Uri, $TimeoutSec, $MaximumRedirection, $ErrorAction)
    if ($Uri -ne 'http://127.0.0.1:8000/api/demo/readiness' -or $null -eq $MaximumRedirection -or $MaximumRedirection -ne 0) { throw 'Unmocked or redirecting HTTP rejected' }
    $global:launchHttp += $Uri
    if ($global:launchFixture.health_failure) { throw 'Mock readiness unavailable' }
    return [pscustomobject]@{ overall_status = 'READY' }
}
function Invoke-WebRequest {
    param($Uri, [switch]$UseBasicParsing, $TimeoutSec, $MaximumRedirection, $ErrorAction)
    if ($Uri -ne 'http://127.0.0.1:5173' -or $null -eq $MaximumRedirection -or $MaximumRedirection -ne 0) { throw 'Unmocked or redirecting HTTP rejected' }
    $global:launchHttp += $Uri
    return [pscustomobject]@{ StatusCode = 200 }
}
function Start-Sleep { param($Seconds) }
$parameters = @{ NoBrowser = $true; SkipDocker = $true }
if ($null -ne $global:launchFixture.backend_port) { $parameters.BackendPort = $global:launchFixture.backend_port }
if ($null -ne $global:launchFixture.frontend_port) { $parameters.FrontendPort = $global:launchFixture.frontend_port }
try { & (Join-Path $global:launchRoot 'scripts/demo/start_control_center.ps1') @parameters; $startExit = $LASTEXITCODE }
catch { $startExit = 1 }
finally { if ($null -ne $global:launchCheckpointLock) { $global:launchCheckpointLock.Dispose() } }
$retryExit = $null
if ($global:launchFixture.retry_after_failure) {
    & (Join-Path $global:launchRoot 'scripts/demo/start_control_center.ps1') @parameters
    $retryExit = $LASTEXITCODE
}
$stopExit = $null
if ($global:launchFixture.stop_after) { & (Join-Path $global:launchRoot 'scripts/demo/stop_control_center.ps1'); $stopExit = $LASTEXITCODE }
$after = if (Test-Path -LiteralPath $sessionFile) { [IO.File]::ReadAllText($sessionFile) } else { $null }
$pending = @(Get-ChildItem -LiteralPath $global:launchRoot -Filter '.demo-session.*.tmp' -File | ForEach-Object { [IO.File]::ReadAllText($_.FullName) })
$result = @{ start_exit = $startExit; stop_exit = $stopExit; retry_exit = $retryExit; initial_checkpoint = $global:launchInitialCheckpoint; pending = $pending; before = $before; after = $after; starts = @($global:launchStarts); attempts = @($global:launchAttempts); stops = @($global:launchStops); http = @($global:launchHttp) }
Write-Output ('MOCK_RESULT=' + (ConvertTo-Json -InputObject $result -Depth 8 -Compress))
'''.replace("__ROOT__", str(project).replace("'", "''"))
        encoded = base64.b64encode(wrapper.encode("utf-16-le")).decode("ascii")
        response = subprocess.run(
            [executable, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
            cwd=project, capture_output=True, text=True, timeout=20,
        )
        output = response.stdout + response.stderr
        data = next((json.loads(line.removeprefix("MOCK_RESULT=")) for line in response.stdout.splitlines()
                     if line.startswith("MOCK_RESULT=")), None)
        self.assertIsNotNone(data, output)
        self.assertEqual(response.returncode, 0, output)
        self.assertEqual(data["start_exit"], case.get("exit", 0), output)
        self.assertEqual([item["role"] for item in data["starts"]], case.get("starts", ["backend", "frontend"]), output)
        self.assertEqual(data["stops"], case.get("stops", []), output)
        if case.get("preserve"):
            self.assertEqual(data["before"], data["after"], output)
        if case.get("stop_after"):
            self.assertEqual(data["stop_exit"], 0, output)
        if case.get("exit", 0) == 0:
            session = json.loads(data["after"])
            self.assertTrue(session["backend_started_at_utc"])
            self.assertTrue(session["frontend_started_at_utc"])
            for item in data["starts"]:
                self.assertIn('"' + str(project), item["arguments"])
        if case.get("fail_frontend") or case.get("handle_error"):
            session = json.loads(data["after"])
            self.assertEqual(session["backend_pid"], 42420)
            self.assertIsNone(session["frontend_pid"])
            self.assertEqual(session["status"], "FAILED")
            self.assertEqual(bool(session["backend_started_at_utc"]), not bool(case.get("handle_error")))
        if case.get("health_failure") and not case.get("existing"):
            session = json.loads(data["after"])
            self.assertEqual(session["status"], "FAILED")
            self.assertEqual((session["backend_pid"], session["frontend_pid"]), (42420, 42421))
            self.assertTrue(session["backend_started_at_utc"])
            self.assertTrue(session["frontend_started_at_utc"])
        if case.get("checkpoint_failure"):
            self.assertEqual(data["attempts"], ["backend"], output)
            self.assertEqual(data["initial_checkpoint"], data["after"], output)
            self.assertTrue(data["pending"], output)
            for pending in data["pending"]:
                record = json.loads(pending)
                self.assertEqual(record["backend_pid"], 42420)
                self.assertEqual(record["backend_started_at_utc"], "2026-10-13T00:59:59.0000000Z")
                self.assertIsNone(record["frontend_pid"])
            if case.get("retry_after_failure"):
                self.assertEqual(data["retry_exit"], 1, output)

    def test_fresh_launch_stop_and_reuse(self):
        for case in (
            {"stop_after": True, "stops": [42420, 42421]},
            {"existing": "valid", "starts": [], "preserve": True, "stop_after": True, "stops": [42420, 42421]},
            {"existing": "absent", "stop_after": True, "stops": [42420, 42421]},
        ):
            with self.subTest(case=case):
                self.run_launch(case)

    def test_unowned_or_inconsistent_session_is_not_adopted(self):
        for case in (
            {"existing": "reused_pid"}, {"existing": "legacy"}, {"existing": "partial"},
            {"existing": "wrong_root"}, {"existing": "wrong_url"},
            {"existing": "valid", "port_mismatch": True}, {"existing": "valid", "foreign_listener": True},
            {"existing": "valid", "health_failure": True},
        ):
            with self.subTest(case=case):
                self.run_launch({**case, "exit": 1, "starts": [], "preserve": True})

    def test_startup_failures_preserve_owned_process_identity(self):
        self.run_launch({"fail_frontend": True, "exit": 1, "starts": ["backend"], "stop_after": True, "stops": [42420]})
        self.run_launch({"handle_error": True, "exit": 1, "starts": ["backend"]})
        self.run_launch({"health_failure": True, "exit": 1})

    def test_failed_checkpoint_retains_identity_and_blocks_retry(self):
        self.run_launch({"checkpoint_failure": True, "retry_after_failure": True, "exit": 1, "starts": ["backend"]})

    def test_prerequisites_fail_before_spawning(self):
        for case in (
            {"missing_vite": True}, {"backend_port": 0}, {"frontend_port": 65536},
            {"backend_port": 5173}, {"foreign_listener": True},
        ):
            with self.subTest(case=case):
                self.run_launch({**case, "exit": 1, "starts": [], "preserve": True})

    def test_powershell_core_launch_stop(self):
        self.run_launch({"stop_after": True, "stops": [42420, 42421]}, shell="pwsh")


if __name__ == "__main__":
    unittest.main()
