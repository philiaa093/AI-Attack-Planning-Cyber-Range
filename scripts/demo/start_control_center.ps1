<#
.SYNOPSIS
    Launch checkout-bound backend and frontend processes with verifiable birth identities.
#>
[CmdletBinding()]
param (
    [switch]$NoBrowser,
    [switch]$SkipDocker,
    [ValidateRange(1, 65535)][int]$BackendPort = 8000,
    [ValidateRange(1, 65535)][int]$FrontendPort = 5173
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path.TrimEnd('\', '/')
$SessionFile = Join-Path $ProjectRoot '.demo-session.json'
$FrontendDir = Join-Path $ProjectRoot 'dashboards\app\frontend'
$ViteScript = Join-Path $FrontendDir 'node_modules\vite\bin\vite.js'
$mutex = $null
$lockHeld = $false
$sessionData = $null
$script:expectedSession = $null

function Write-SessionCheckpoint {
    if (Test-Path -LiteralPath $SessionFile) {
        if ([IO.File]::ReadAllText($SessionFile) -cne $script:expectedSession) {
            throw 'Session changed during startup.'
        }
    } elseif ($null -ne $script:expectedSession) { throw 'Session disappeared during startup.' }
    $text = $sessionData | ConvertTo-Json -Depth 5
    $pending = Join-Path $ProjectRoot ('.demo-session.' + [guid]::NewGuid().ToString('N') + '.tmp')
    try {
        $stream = [IO.File]::Open($pending, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try {
            $bytes = [Text.UTF8Encoding]::new($false).GetBytes($text)
            $stream.Write($bytes, 0, $bytes.Length)
            $stream.Flush($true)
        } finally { $stream.Dispose() }
        if (Test-Path -LiteralPath $SessionFile) { [IO.File]::Replace($pending, $SessionFile, [System.Management.Automation.Language.NullString]::Value, $true) }
        else { [IO.File]::Move($pending, $SessionFile) }
        $script:expectedSession = $text
    } catch {
        if (Test-Path -LiteralPath $pending) { Write-Host "Unpublished session checkpoint retained: $pending" }
        throw
    }
}

function Get-PortListeners([int]$Port) {
    return @(Get-NetTCPConnection -ErrorAction Stop | Where-Object {
        $_.State -eq 'Listen' -and $_.LocalPort -eq $Port
    })
}

function Test-OwnedListener([int]$Port, $Process) {
    if ($Process.HasExited) { throw 'Recorded process exited during startup.' }
    $listeners = @(Get-PortListeners $Port)
    return $listeners.Count -gt 0 -and -not @($listeners | Where-Object {
        $_.OwningProcess -ne $Process.Id -or $_.LocalAddress -notin @('127.0.0.1', '::1')
    }).Count
}

try {
    if ($BackendPort -eq $FrontendPort) { throw 'Backend and frontend ports must differ.' }
    $python = (Get-Command python.exe -CommandType Application -ErrorAction Stop).Source
    $node = (Get-Command node.exe -CommandType Application -ErrorAction Stop).Source
    foreach ($path in @($ProjectRoot, $python, $node, $ViteScript, $FrontendDir)) {
        if ($path -notmatch '^[A-Za-z]:[\\/]' -or $path -match '["\x00-\x1f]' -or $path -match '[^\S \t]') {
            throw 'Unsupported executable or project path.'
        }
    }
    foreach ($path in @($python, $node, $ViteScript)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required local file is missing: $path" }
    }
    # A linked Vite installation could resolve to another checkout.
    $directory = Get-Item -LiteralPath $ViteScript
    while ($directory.FullName -ne $ProjectRoot) {
        if ($directory.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked Vite paths are unsupported.' }
        $directory = Get-Item -LiteralPath (Split-Path -Parent $directory.FullName)
    }
    $rootKey = [IO.Path]::GetFullPath($ProjectRoot).ToLowerInvariant()
    $hash = [Security.Cryptography.SHA256]::Create()
    try { $key = [BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($rootKey))).Replace('-', '') }
    finally { $hash.Dispose() }
    $mutex = [Threading.Mutex]::new($false, "Local\PBL6-ControlCenter-$key")
    try { $lockHeld = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $lockHeld = $true }
    if (-not $lockHeld) { throw 'Another control operation is active.' }
    if (@(Get-ChildItem -LiteralPath $ProjectRoot -Filter '.demo-session.*.tmp' -File -ErrorAction Stop).Count) {
        throw 'Unpublished session checkpoints require recovery before startup.'
    }

    $backend = $null
    $frontend = $null
    $reuse = $false
    if (Test-Path -LiteralPath $SessionFile) {
        if ((Get-Item -LiteralPath $SessionFile).Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw 'Linked session files are unsupported.'
        }
        $script:expectedSession = [IO.File]::ReadAllText($SessionFile)
        $ownership = & (Join-Path $PSScriptRoot 'stop_control_center.ps1') -VerifyOnly
        if ($LASTEXITCODE -ne 0 -or $null -eq $ownership) { throw 'Existing session ownership could not be verified.' }
        $backend = $ownership.backend
        $frontend = $ownership.frontend
        if (($null -ne $backend) -ne ($null -ne $frontend)) { throw 'Existing session is partially active; stop it before restarting.' }
        $reuse = $null -ne $backend
    }

    if ($reuse) {
        $previous = $script:expectedSession | ConvertFrom-Json
        if ($previous.backend_url -cne "http://127.0.0.1:$BackendPort" -or
            $previous.frontend_url -cne "http://127.0.0.1:$FrontendPort") {
            throw 'Existing session URLs do not match the requested loopback ports.'
        }
        if (-not (Test-OwnedListener $BackendPort $backend) -or -not (Test-OwnedListener $FrontendPort $frontend)) {
            throw 'Existing session does not own the requested loopback listeners.'
        }
        Write-Host 'Reusing verified processes; existing session identity is unchanged.'
    } else {
        if (@(Get-PortListeners $BackendPort).Count -or @(Get-PortListeners $FrontendPort).Count) {
            throw 'Requested port is occupied by an unowned process.'
        }
        $sessionData = @{
            session_id = 'DEMO-SES-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
            backend_pid = $null; backend_started_at_utc = $null
            frontend_pid = $null; frontend_started_at_utc = $null
            backend_url = "http://127.0.0.1:$BackendPort"
            frontend_url = "http://127.0.0.1:$FrontendPort"
            gateway_url = 'http://127.0.0.1:18088'
            started_at_utc = [datetime]::UtcNow.ToString('o')
            project_root = $ProjectRoot; status = 'INITIALIZING'
        }
        Write-SessionCheckpoint
        foreach ($role in @('backend', 'frontend')) {
            if ($role -eq 'backend') {
                $arguments = '-m uvicorn dashboards.app.backend.control_api:app --app-dir "' + $ProjectRoot + '" --host 127.0.0.1 --port ' + $BackendPort
                $process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $ProjectRoot -PassThru -WindowStyle Hidden
                $backend = $process
            } else {
                $arguments = '"' + $ViteScript + '" "' + $FrontendDir + '" --host 127.0.0.1 --port ' + $FrontendPort
                $process = Start-Process -FilePath $node -ArgumentList $arguments -WorkingDirectory $FrontendDir -PassThru -WindowStyle Hidden
                $frontend = $process
            }
            $sessionData["${role}_pid"] = $process.Id
            Write-Host "Started $role PID $($process.Id); capturing its birth identity."
            $handle = $process.Handle
            if ($null -eq $handle -or $handle -eq [IntPtr]::Zero) { throw 'Process handle is unavailable.' }
            $sessionData["${role}_started_at_utc"] = $process.StartTime.ToUniversalTime().ToString('o')
            Write-Host "Owned $role PID $($process.Id), birth $($sessionData["${role}_started_at_utc"])."
            Write-SessionCheckpoint
            if ($process.HasExited) { throw "$role exited before readiness." }
        }
    }

    $readiness = $null
    for ($elapsed = 0; $elapsed -lt 30; $elapsed++) {
        $backendReady = Test-OwnedListener $BackendPort $backend
        $frontendReady = Test-OwnedListener $FrontendPort $frontend
        try {
            if ($backendReady) {
                $readiness = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/api/demo/readiness" -MaximumRedirection 0 -TimeoutSec 2 -ErrorAction Stop
                $backendReady = $readiness.overall_status -in @('READY', 'DEGRADED')
            }
            if ($frontendReady) {
                $response = Invoke-WebRequest -Uri "http://127.0.0.1:$FrontendPort" -UseBasicParsing -MaximumRedirection 0 -TimeoutSec 2 -ErrorAction Stop
                $frontendReady = $response.StatusCode -eq 200
            }
        } catch { $backendReady = $false; $frontendReady = $false }
        if ($backendReady -and $frontendReady) { break }
        Start-Sleep -Seconds 1
    }
    if (-not $backendReady -or -not $frontendReady) { throw 'Control Center did not reach verified readiness after 30 readiness checks.' }
    if (-not $reuse) { $sessionData.status = $readiness.overall_status; Write-SessionCheckpoint }
    Write-Host "Control Center $($readiness.overall_status): http://127.0.0.1:$FrontendPort/#overview"
    if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$FrontendPort/#overview" }
    exit 0
} catch {
    if ($null -ne $sessionData) {
        $sessionData.status = 'FAILED'
        try { Write-SessionCheckpoint } catch { Write-Host "Session checkpoint failed; prior receipt retained: $($_.Exception.Message)" }
    }
    Write-Host "Startup refused or incomplete: $($_.Exception.Message)"
    exit 1
} finally {
    if ($lockHeld) { $mutex.ReleaseMutex() }
    if ($null -ne $mutex) { $mutex.Dispose() }
}
