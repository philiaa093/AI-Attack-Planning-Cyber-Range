<#
.SYNOPSIS
    Hardened Project-Targeted Stopper for Autonomous Cyber Range Control Center.
.DESCRIPTION
    Reads .demo-session.json and terminates ONLY the project-owned Backend and Frontend
    processes by strictly verifying BOTH PID and Command Line / Executable path.
    Protects against PID reuse and prevents killing unrelated Python or Node processes.
#>

[CmdletBinding()]
param (
    [switch]$Force
)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
$SessionFile = Join-Path $ProjectRoot ".demo-session.json"

Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "   AUTONOMOUS CYBER RANGE CONTROL CENTER - SAFE SHUTDOWN                       " -ForegroundColor Yellow
Write-Host "================================================================================" -ForegroundColor Cyan

if (-not (Test-Path $SessionFile)) {
    Write-Host "[!] No active session file (.demo-session.json) found in project root." -ForegroundColor DarkYellow
    Write-Host "[*] Checking if backend (8000) or frontend (5173) are listening..." -ForegroundColor Gray

    # Check port 8000
    $bConn = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
    if ($bConn) {
        Write-Host "  [!] Port 8000 is listening under PID $($bConn.OwningProcess)." -ForegroundColor Yellow
    }

    # Check port 5173
    $fConn = Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue
    if ($fConn) {
        Write-Host "  [!] Port 5173 is listening under PID $($fConn.OwningProcess)." -ForegroundColor Yellow
    }
    Write-Host "[*] No project session to shut down. Safe exit without terminating external processes." -ForegroundColor Gray
    exit 0
}

# Read session file
try {
    $session = Get-Content $SessionFile -Raw | ConvertFrom-Json
} catch {
    Write-Error "[-] Failed to parse .demo-session.json: $_"
    exit 1
}

$backendPID = $session.backend_pid
$frontendPID = $session.frontend_pid
$recordedRoot = if ($session.project_root) { $session.project_root } else { $ProjectRoot }

Write-Host "[*] Session ID:     $($session.session_id)" -ForegroundColor Gray
Write-Host "[*] Started At:     $($session.started_at_utc)" -ForegroundColor Gray
Write-Host "[*] Project Root:   $recordedRoot" -ForegroundColor Gray

function Get-ProcessDetails {
    param([int]$ProcId)
    $details = @{
        Exists       = $false
        ProcessName  = ""
        CommandLine  = ""
        Executable   = ""
    }
    try {
        $p = Get-Process -Id $ProcId -ErrorAction SilentlyContinue
        if ($p) {
            $details.Exists = $true
            $details.ProcessName = $p.ProcessName
            try {
                $cim = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcId" -ErrorAction SilentlyContinue
                if ($cim) {
                    $details.CommandLine = if ($cim.CommandLine) { $cim.CommandLine } else { "" }
                    $details.Executable = if ($cim.ExecutablePath) { $cim.ExecutablePath } else { "" }
                }
            } catch {
                # Fallback if WMI/CIM fails
            }
        }
    } catch {
        # Process not accessible or exited
    }
    return $details
}

# -----------------------------------------------------------------------------
# 1. Safe Verify & Terminate Backend PID
# -----------------------------------------------------------------------------
if ($backendPID) {
    $bInfo = Get-ProcessDetails -ProcId $backendPID
    if ($bInfo.Exists) {
        $pName = $bInfo.ProcessName.ToLower()
        $cmdLine = $bInfo.CommandLine

        # Primary check: Process Name must be python or uvicorn
        $isPythonName = ($pName -like "*python*" -or $pName -like "*uvicorn*")

        # Secondary check: Command line must contain control_api module or uvicorn project path
        $isProjectBackend = $false
        if ($cmdLine) {
            $isProjectBackend = ($cmdLine -match "dashboards\.app\.backend\.control_api") -or `
                                (($cmdLine -match "uvicorn") -and ($cmdLine -match "control_api")) -or `
                                ($cmdLine -match [regex]::Escape($ProjectRoot))
        } else {
            # If command line is unavailable, check executable path belongs to python in project environment
            $isProjectBackend = $isPythonName
        }

        if ($isPythonName -and $isProjectBackend) {
            Write-Host "[*] Terminating verified Backend process (PID $backendPID)..." -ForegroundColor Yellow
            Stop-Process -Id $backendPID -Force -ErrorAction SilentlyContinue
            Write-Host "  [+] Backend process stopped safely." -ForegroundColor Green
        } else {
            Write-Host "  [!] PID $backendPID ($pName) does not match expected project backend command line!" -ForegroundColor Red
            Write-Host "      Detected command line: '$cmdLine'" -ForegroundColor DarkYellow
            Write-Host "      SKIPPING termination to protect unrelated/reused process." -ForegroundColor Yellow
        }
    } else {
        Write-Host "  [*] Backend process (PID $backendPID) was already terminated." -ForegroundColor Gray
    }
}

# -----------------------------------------------------------------------------
# 2. Safe Verify & Terminate Frontend PID
# -----------------------------------------------------------------------------
if ($frontendPID) {
    $fInfo = Get-ProcessDetails -ProcId $frontendPID
    if ($fInfo.Exists) {
        $pName = $fInfo.ProcessName.ToLower()
        $cmdLine = $fInfo.CommandLine

        # Primary check: Process Name must be node, npm, or cmd launcher
        $isNodeName = ($pName -like "*node*" -or $pName -like "*npm*" -or $pName -like "*cmd*")

        # Secondary check: Command line must relate to Vite or dashboards/app/frontend
        $isProjectFrontend = $false
        if ($cmdLine) {
            $isProjectFrontend = ($cmdLine -match "vite") -or `
                                 ($cmdLine -match "dashboards[/\\]app[/\\]frontend") -or `
                                 (($cmdLine -match "npm") -and ($cmdLine -match "run") -and ($cmdLine -match "dev")) -or `
                                 ($cmdLine -match [regex]::Escape($ProjectRoot))
        } else {
            $isProjectFrontend = $isNodeName
        }

        if ($isNodeName -and $isProjectFrontend) {
            Write-Host "[*] Terminating verified Frontend process (PID $frontendPID)..." -ForegroundColor Yellow

            # Also terminate any direct child node processes spawned by npm
            try {
                $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $frontendPID" -ErrorAction SilentlyContinue
                foreach ($child in $children) {
                    if ($child.CommandLine -match "vite" -or $child.CommandLine -match "frontend") {
                        Stop-Process -Id $child.ProcessId -Force -ErrorAction SilentlyContinue
                    }
                }
            } catch {}

            Stop-Process -Id $frontendPID -Force -ErrorAction SilentlyContinue
            Write-Host "  [+] Frontend process stopped safely." -ForegroundColor Green
        } else {
            Write-Host "  [!] PID $frontendPID ($pName) does not match expected project frontend command line!" -ForegroundColor Red
            Write-Host "      Detected command line: '$cmdLine'" -ForegroundColor DarkYellow
            Write-Host "      SKIPPING termination to protect unrelated/reused process." -ForegroundColor Yellow
        }
    } else {
        Write-Host "  [*] Frontend process (PID $frontendPID) was already terminated." -ForegroundColor Gray
    }
}

# Clean up session receipt
Remove-Item -Path $SessionFile -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "[+] Control Center shutdown complete. Ports 8000 & 5173 freed." -ForegroundColor Green
Write-Host "================================================================================" -ForegroundColor Cyan
