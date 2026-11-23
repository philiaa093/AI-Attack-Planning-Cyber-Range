<#
.SYNOPSIS
    Stop only processes whose identity and checkout can be verified.
#>
[CmdletBinding()]
param ([switch]$Force, [switch]$VerifyOnly)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
$SessionFile = Join-Path $ProjectRoot ".demo-session.json"

function Get-AbsolutePathKey($Value) {
    if ($Value -isnot [string] -or $Value -notmatch '^[A-Za-z]:[\\/]') {
        throw "Expected an absolute local path."
    }
    return [IO.Path]::GetFullPath($Value).TrimEnd('\', '/').ToLowerInvariant()
}

function Get-CommandArguments([string]$CommandLine) {
    if ($CommandLine -match '[^\S \t]') { throw "Unsupported command-line whitespace." }
    $tokens = @([regex]::Matches($CommandLine, '\G\s*(?:"([^"]*)"|([^\s"]+))(?=\s|$)'))
    if (-not $tokens.Count -or
        ($tokens[-1].Index + $tokens[-1].Length) -ne $CommandLine.TrimEnd().Length) {
        throw "Unsupported command line."
    }
    foreach ($token in $tokens) {
        if ($token.Groups[1].Success -and $token.Groups[1].Value.EndsWith('\')) {
            throw "Escaped closing quotes are unsupported."
        }
    }
    return ,@($tokens | ForEach-Object {
        if ($_.Groups[1].Success) { $_.Groups[1].Value } else { $_.Groups[2].Value }
    })
}

function Test-ServerArguments($CommandArgs, [int]$Start, [bool]$AllowAppDir) {
    $seen = @{}
    for ($index = $Start; $index -lt $CommandArgs.Count; $index += 2) {
        $option = $CommandArgs[$index]
        if ($seen.ContainsKey($option) -or $index + 1 -ge $CommandArgs.Count) { return $false }
        $seen[$option] = $true
        $value = $CommandArgs[$index + 1]
        switch ($option) {
            '--host' { if ($value -notin @('127.0.0.1', '::1', 'localhost')) { return $false } }
            '--port' { if ($value -notmatch '^\d{1,5}$' -or [int]$value -lt 1 -or [int]$value -gt 65535) { return $false } }
            '--app-dir' { if (-not $AllowAppDir -or (Get-AbsolutePathKey $value) -ne $rootKey) { return $false } }
            default { return $false }
        }
    }
    return $true
}

function ConvertTo-UtcTimestamp($Value) {
    if ($Value -isnot [string] -or
        $Value -notmatch '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,7})?(?:Z|\+00:00)$') {
        throw "Process/session timestamp must be UTC."
    }
    $parsed = [DateTimeOffset]::Parse($Value, [Globalization.CultureInfo]::InvariantCulture).UtcDateTime
    if ($parsed -gt [datetime]::UtcNow) { throw "Process/session timestamp is in the future." }
    return $parsed
}

$mutex = $null
$lockHeld = $false
try {
if (-not $VerifyOnly) {
    $hash = [Security.Cryptography.SHA256]::Create()
    try { $key = [BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes((Get-AbsolutePathKey $ProjectRoot)))).Replace('-', '') }
    finally { $hash.Dispose() }
    $mutex = [Threading.Mutex]::new($false, "Local\PBL6-ControlCenter-$key")
    try { $lockHeld = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $lockHeld = $true }
    if (-not $lockHeld) { Write-Host "Another control operation is active; session retained."; exit 1 }
}

if (-not (Test-Path -LiteralPath $SessionFile)) {
    Write-Host "No project session to shut down; no processes were terminated."
    exit 0
}

try {
    $sessionText = Get-Content -LiteralPath $SessionFile -Raw
    if ((Get-Command ConvertFrom-Json).Parameters.ContainsKey('DateKind')) {
        $session = $sessionText | ConvertFrom-Json -DateKind String
    } else { $session = $sessionText | ConvertFrom-Json }
    if ($session -isnot [pscustomobject] -or
        'backend_pid' -notin $session.PSObject.Properties.Name -or
        'frontend_pid' -notin $session.PSObject.Properties.Name) {
        throw "Session must explicitly record both process roles."
    }
    $rootKey = Get-AbsolutePathKey $ProjectRoot
    if ((Get-AbsolutePathKey $session.project_root) -ne $rootKey) {
        throw "Session project root does not match this checkout."
    }
    $null = ConvertTo-UtcTimestamp $session.started_at_utc
    $births = @{}
    foreach ($role in @('backend', 'frontend')) {
        $recordedPid = $session."${role}_pid"
        if ($null -ne $recordedPid -and
            (($recordedPid -isnot [int] -and $recordedPid -isnot [long]) -or
             $recordedPid -le 0 -or $recordedPid -gt [int]::MaxValue)) {
            throw "Invalid $role PID."
        }
        if ($null -ne $recordedPid) {
            $births[$role] = ConvertTo-UtcTimestamp $session."${role}_started_at_utc"
        }
    }
    if ($session.backend_pid -and $session.backend_pid -eq $session.frontend_pid) {
        throw "Backend and frontend PIDs must differ."
    }
} catch {
    Write-Host "Shutdown refused; session retained: $($_.Exception.Message)"
    exit 1
}

$incomplete = $false
$verified = @{ backend = $null; frontend = $null }
foreach ($role in @('backend', 'frontend')) {
    $recordedPid = $session."${role}_pid"
    if ($null -eq $recordedPid) { continue }
    try {
        # Enumerating an exact PID distinguishes an absent process from lookup errors.
        $process = @(Get-Process -ErrorAction Stop | Where-Object Id -EQ $recordedPid)
        if (-not $process.Count) { continue }
        if ($process.Count -ne 1) { throw "Ambiguous process lookup." }
        $process = $process[0]
        $handle = $process.Handle
        if ($null -eq $handle -or $handle -eq [IntPtr]::Zero) { throw "Process handle is unavailable." }
        $created = $process.StartTime.ToUniversalTime()
        if ($process.HasExited -or $created -ne $births[$role]) {
            throw "Process identity is stale or PID has been reused."
        }
        $cim = Get-CimInstance Win32_Process -Filter "ProcessId = $recordedPid" -ErrorAction Stop
        if (-not $cim -or $cim.ProcessId -ne $recordedPid -or
            [string]::IsNullOrWhiteSpace($cim.CommandLine)) {
            throw "Process command line is unavailable."
        }
        $commandArgs = Get-CommandArguments $cim.CommandLine
        $executable = Get-AbsolutePathKey $cim.ExecutablePath
        if ((Get-AbsolutePathKey $commandArgs[0]) -ne $executable -or
            [IO.Path]::GetFileNameWithoutExtension($executable) -ne $process.ProcessName) {
            throw "Executable and process name do not match."
        }
        $owned = $false
        if ($role -eq 'backend' -and $process.ProcessName -match '^(?:python(?:\d+(?:\.\d+)*)?|uvicorn)$' -and
            $commandArgs.Count -ge 4 -and $commandArgs[1] -eq '-m' -and
            $commandArgs[2] -eq 'uvicorn' -and $commandArgs[3] -eq 'dashboards.app.backend.control_api:app') {
            $owned = (Test-ServerArguments $commandArgs 4 $true) -and '--app-dir' -in $commandArgs
        } elseif ($role -eq 'frontend' -and $process.ProcessName -eq 'node' -and $commandArgs.Count -ge 3) {
            $vitePath = Join-Path $ProjectRoot 'dashboards\app\frontend\node_modules\vite\bin\vite.js'
            $frontendRoot = Join-Path $ProjectRoot 'dashboards\app\frontend'
            $owned = (Get-AbsolutePathKey $commandArgs[1]) -eq (Get-AbsolutePathKey $vitePath) -and
                (Get-AbsolutePathKey $commandArgs[2]) -eq (Get-AbsolutePathKey $frontendRoot) -and
                (Test-ServerArguments $commandArgs 3 $false)
        }
        # ponytail: legacy receipts without exact birth/app-root identity are refused; recreate them through the current launcher.
        if (-not $owned -or $process.HasExited -or $process.StartTime.ToUniversalTime() -ne $created) {
            throw "Cannot verify $role ownership for this checkout."
        }
        $verified[$role] = $process
        if ($VerifyOnly) { continue }
        Stop-Process -InputObject $process -Force -ErrorAction Stop
        if (-not $process.WaitForExit(5000)) { throw "Process termination was not confirmed." }
        Write-Host "Verified $role process stopped (PID $recordedPid)."
        # Children are not terminated without their own verified identity.
    } catch {
        $incomplete = $true
        Write-Host "SKIPPING unverified or failed $role shutdown; session retained: $($_.Exception.Message)"
    }
}

if ($incomplete) { exit 1 }
try {
    if ((Get-Content -LiteralPath $SessionFile -Raw) -cne $sessionText) {
        throw "Session changed during shutdown."
    }
} catch {
    Write-Host "Session retained: $($_.Exception.Message)"
    exit 1
}
if ($VerifyOnly) { Write-Output ([pscustomobject]$verified); exit 0 }
Write-Host "Recorded processes are stopped or absent; session receipt retained. Unverified children and port state were not checked."
exit 0
} finally {
    if ($lockHeld) { $mutex.ReleaseMutex() }
    if ($null -ne $mutex) { $mutex.Dispose() }
}
