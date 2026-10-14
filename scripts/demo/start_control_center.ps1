<#
.SYNOPSIS
    One-Command Launcher for Autonomous Cyber Range Control Center (Professor Demo Hardening).
.DESCRIPTION
    Performs prerequisite checks (Python, Node, Docker), verifies port availability,
    launches Backend & Frontend (with idempotency and PID tracking in .demo-session.json),
    polls system demo readiness via GET /api/demo/readiness, and launches the browser dashboard.
.PARAMETER NoBrowser
    Do not automatically open the default web browser.
.PARAMETER SkipDocker
    Do not attempt to start Docker containers if offline.
.PARAMETER BackendPort
    Port for FastAPI backend (default: 8000).
.PARAMETER FrontendPort
    Port for Vite frontend (default: 5173).
#>

[CmdletBinding()]
param (
    [switch]$NoBrowser,
    [switch]$SkipDocker,
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
$SessionFile = Join-Path $ProjectRoot ".demo-session.json"
$FrontendDir = Join-Path $ProjectRoot "dashboards\app\frontend"

Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "   AUTONOMOUS CYBER RANGE CONTROL CENTER - ONE-COMMAND DEMO LAUNCHER           " -ForegroundColor Yellow
Write-Host "   Bounded Autonomous Penetration Testing & Policy Enforcement Prototype       " -ForegroundColor Gray
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "[*] Project Root: $ProjectRoot" -ForegroundColor Gray
Write-Host "[*] Timestamp:    $([DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ'))" -ForegroundColor Gray
Write-Host ""

# ------------------------------------------------------------------------------
# 1. Prerequisite Validation
# ------------------------------------------------------------------------------
Write-Host "[1/5] Checking Environment Prerequisites..." -ForegroundColor Yellow

# Check Python
try {
    $pyVer = & python --version 2>&1
    Write-Host "  [+] Python: $pyVer" -ForegroundColor Green
} catch {
    Write-Error "[-] Python not found in PATH. Python >= 3.10 is required."
    exit 1
}

# Check Node.js
try {
    $nodeVer = & node --version 2>&1
    Write-Host "  [+] Node.js: $nodeVer" -ForegroundColor Green
} catch {
    Write-Error "[-] Node.js not found in PATH. Node >= 18 is required."
    exit 1
}

# Check Docker
$DockerAvailable = $false
try {
    $dockerVer = & docker --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        $DockerAvailable = $true
        Write-Host "  [+] Docker Engine: $dockerVer" -ForegroundColor Green
    } else {
        Write-Host "  [!] Docker CLI present but engine may be offline." -ForegroundColor DarkYellow
    }
} catch {
    Write-Host "  [!] Docker not detected. System will operate in Historical Replay & Offline Verification mode." -ForegroundColor DarkYellow
}

# ------------------------------------------------------------------------------
# 2. Port Collision & Idempotency Inspection
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "[2/5] Checking Port Status & Existing Project Services..." -ForegroundColor Yellow

$BackendRunning = $false
$FrontendRunning = $false
$BackendPID = $null
$FrontendPID = $null

# Inspect Backend Port
try {
    $bResp = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/api/status" -TimeoutSec 2 -ErrorAction Stop
    if ($bResp.api -eq "healthy") {
        $BackendRunning = $true
        Write-Host "  [+] Existing Project Backend is active & healthy on port $BackendPort (reusing instance)." -ForegroundColor Green
    }
} catch {
    # Check if port is occupied by unrelated process
    $occupied = Get-NetTCPConnection -LocalPort $BackendPort -State Listen -ErrorAction SilentlyContinue
    if ($occupied) {
        Write-Error "[-] Port $BackendPort is occupied by an unrelated non-project application (PID: $($occupied.OwningProcess)). Please free port $BackendPort."
        exit 1
    }
    Write-Host "  [*] Port $BackendPort is available for Backend." -ForegroundColor Gray
}

# Inspect Frontend Port
try {
    $fResp = Invoke-WebRequest -Uri "http://127.0.0.1:$FrontendPort" -TimeoutSec 2 -ErrorAction Stop
    if ($fResp.StatusCode -eq 200) {
        $FrontendRunning = $true
        Write-Host "  [+] Existing Frontend server is active on port $FrontendPort (reusing instance)." -ForegroundColor Green
    }
} catch {
    # Check if port is occupied by unrelated process
    $occupied = Get-NetTCPConnection -LocalPort $FrontendPort -State Listen -ErrorAction SilentlyContinue
    if ($occupied) {
        Write-Error "[-] Port $FrontendPort is occupied by an unrelated non-project application (PID: $($occupied.OwningProcess)). Please free port $FrontendPort."
        exit 1
    }
    Write-Host "  [*] Port $FrontendPort is available for Frontend." -ForegroundColor Gray
}

# ------------------------------------------------------------------------------
# 3. Launching Services
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "[3/5] Starting Control Center Services..." -ForegroundColor Yellow

# Read existing session if present
$ExistingSession = @{}
if (Test-Path $SessionFile) {
    try {
        $ExistingSession = Get-Content $SessionFile -Raw | ConvertFrom-Json -AsHashtable
    } catch {
        $ExistingSession = @{}
    }
}

# Spawn Backend if not running
if (-not $BackendRunning) {
    Write-Host "  [*] Spawning Backend (uvicorn FastAPI on 127.0.0.1:$BackendPort)..." -ForegroundColor Cyan
    $bProc = Start-Process -FilePath "python" `
        -ArgumentList "-m", "uvicorn", "dashboards.app.backend.control_api:app", "--host", "127.0.0.1", "--port", "$BackendPort" `
        -WorkingDirectory $ProjectRoot `
        -PassThru -WindowStyle Hidden
    $BackendPID = $bProc.Id
    Write-Host "  [+] Backend launched with PID: $BackendPID" -ForegroundColor Green
} else {
    $BackendPID = $ExistingSession["backend_pid"]
}

# Spawn Frontend if not running
if (-not $FrontendRunning) {
    Write-Host "  [*] Spawning Frontend (Vite dev server on 127.0.0.1:$FrontendPort)..." -ForegroundColor Cyan
    $fProc = Start-Process -FilePath "npm.cmd" `
        -ArgumentList "run", "dev", "--", "--host", "127.0.0.1", "--port", "$FrontendPort" `
        -WorkingDirectory $FrontendDir `
        -PassThru -WindowStyle Hidden
    $FrontendPID = $fProc.Id
    Write-Host "  [+] Frontend launched with PID: $FrontendPID" -ForegroundColor Green
} else {
    $FrontendPID = $ExistingSession["frontend_pid"]
}

# Record session manifest for safe targeted termination
$SessionData = @{
    session_id      = "DEMO-SES-" + [System.Guid]::NewGuid().ToString("N").Substring(0, 8)
    backend_pid     = $BackendPID
    frontend_pid    = $FrontendPID
    backend_url     = "http://127.0.0.1:$BackendPort"
    frontend_url    = "http://127.0.0.1:$FrontendPort"
    gateway_url     = "http://127.0.0.1:18088"
    started_at_utc  = [DateTime]::UtcNow.ToString("o")
    project_root    = $ProjectRoot
    status          = "INITIALIZING"
}

[System.IO.File]::WriteAllText($SessionFile, ($SessionData | ConvertTo-Json -Depth 5), [System.Text.UTF8Encoding]::new($false))

# ------------------------------------------------------------------------------
# 4. Polling System Readiness & Health
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "[4/5] Polling Unified Readiness & System Health..." -ForegroundColor Yellow

$MaxWaitSeconds = 30
$PollInterval = 1
$Elapsed = 0
$BackendReady = $false
$FrontendReady = $false
$ReadinessData = $null

while ($Elapsed -lt $MaxWaitSeconds) {
    # Check Backend Readiness endpoint
    if (-not $BackendReady) {
        try {
            $rResp = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/api/demo/readiness" -TimeoutSec 2 -ErrorAction Stop
            if ($rResp.overall_status -in @("READY", "DEGRADED")) {
                $BackendReady = $true
                $ReadinessData = $rResp
            }
        } catch {
            # Still warming up
        }
    }

    # Check Frontend
    if (-not $FrontendReady) {
        try {
            $fResp = Invoke-WebRequest -Uri "http://127.0.0.1:$FrontendPort" -TimeoutSec 2 -ErrorAction Stop
            if ($fResp.StatusCode -eq 200) {
                $FrontendReady = $true
            }
        } catch {
            # Still warming up
        }
    }

    if ($BackendReady -and $FrontendReady) {
        break
    }

    Start-Sleep -Seconds $PollInterval
    $Elapsed += $PollInterval
    Write-Host "  [*] Waiting for services to respond ($Elapsed/${MaxWaitSeconds}s)..." -ForegroundColor Gray
}

if (-not $BackendReady) {
    Write-Error "[-] Backend failed to reach ready state within $MaxWaitSeconds seconds."
    exit 1
}

if (-not $FrontendReady) {
    Write-Error "[-] Frontend failed to respond within $MaxWaitSeconds seconds."
    exit 1
}

# Update session manifest to ACTIVE
$SessionData["status"] = $ReadinessData.overall_status
[System.IO.File]::WriteAllText($SessionFile, ($SessionData | ConvertTo-Json -Depth 5), [System.Text.UTF8Encoding]::new($false))

# ------------------------------------------------------------------------------
# 5. Presentation Summary & Ready Banner
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "[5/5] Control Center Ready for Professor Demonstration!" -ForegroundColor Green
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "   OVERALL SYSTEM STATUS: " -NoNewline
if ($ReadinessData.overall_status -eq "READY") {
    Write-Host "READY (DEMO READY)" -ForegroundColor Green
} else {
    Write-Host "$($ReadinessData.overall_status) (DEGRADED / HISTORICAL REPLAY AVAILABLE)" -ForegroundColor Yellow
}
Write-Host "   Summary: $($ReadinessData.summary)" -ForegroundColor Gray
Write-Host "--------------------------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "   Frontend Dashboard URL:  http://127.0.0.1:$FrontendPort" -ForegroundColor Cyan
Write-Host "   Backend API URL:         http://127.0.0.1:$BackendPort/docs" -ForegroundColor Cyan
Write-Host "   Readiness Endpoint:      http://127.0.0.1:$BackendPort/api/demo/readiness" -ForegroundColor Cyan
Write-Host "   Cyber Range Gateway:     http://127.0.0.1:18088" -ForegroundColor Gray
Write-Host "--------------------------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "   [HONEST LLM PROVENANCE DISCLOSURE]" -ForegroundColor Cyan
Write-Host "   Provider Status:         $($ReadinessData.details.llm_status)" -ForegroundColor Yellow
Write-Host "   Provenance Disclosure:   $($ReadinessData.details.llm_provenance_disclosure)" -ForegroundColor Yellow
Write-Host "   RULE Baseline Fallback:  $($ReadinessData.details.rule_baseline_ready)" -ForegroundColor Green
Write-Host "   Zero Network Dispatch:   ENFORCED BY CENTRALIZED SAFETY GATE" -ForegroundColor Green
Write-Host "--------------------------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "   To safely stop the Control Center:" -ForegroundColor Gray
Write-Host "   powershell -File .\scripts\demo\stop_control_center.ps1" -ForegroundColor Yellow
Write-Host "================================================================================" -ForegroundColor Cyan

# Open Browser unless -NoBrowser
if (-not $NoBrowser) {
    Write-Host "[*] Launching browser to http://127.0.0.1:$FrontendPort/#overview..." -ForegroundColor Green
    Start-Process "http://127.0.0.1:$FrontendPort/#overview"
}
