@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "FRONTEND=%ROOT%\dashboards\app\frontend"
set "STATE_DIR=%LOCALAPPDATA%\PBL6_FINAL\demo-runtime"
set "BACKEND_STATE=%STATE_DIR%\backend.json"
set "FRONTEND_STATE=%STATE_DIR%\frontend.json"
set "BACKEND_URL=http://127.0.0.1:8000/api/runs/current"
set "FRONTEND_URL=http://127.0.0.1:5173/"

if "%~1"=="" goto menu
if /I "%~1"=="start" goto start
if /I "%~1"=="restart" goto restart
if /I "%~1"=="stop" goto stop
if /I "%~1"=="status" goto status
if /I "%~1"=="open" goto open
if /I "%~1"=="help" goto usage

echo [ERROR] Unknown command: %~1
goto usage_error

:menu
cls
echo PBL6 Demo Launcher
echo =================
echo 1. Start
echo 2. Restart
echo 3. Stop
echo 4. Status
echo 5. Open dashboard
echo 6. Exit
choice /C 123456 /N /M "Choose [1-6]: "
set "selection=%errorlevel%"
if "%selection%"=="6" exit /b 0
if "%selection%"=="5" call "%~f0" open
if "%selection%"=="4" call "%~f0" status
if "%selection%"=="3" call "%~f0" stop
if "%selection%"=="2" call "%~f0" restart
if "%selection%"=="1" call "%~f0" start
echo.
pause
goto menu

:start
if not exist "%STATE_DIR%" mkdir "%STATE_DIR%" >nul 2>&1

where python >nul 2>&1 || (
  echo [ERROR] Python is not available in PATH.
  exit /b 1
)
where npm >nul 2>&1 || (
  echo [ERROR] npm is not available in PATH.
  exit /b 1
)

python -c "import fastapi,uvicorn" >nul 2>&1 || (
  echo [ERROR] Backend dependencies are missing.
  echo Install them with: python -m pip install -r dashboards\app\backend\requirements.txt
  exit /b 1
)

powershell -NoProfile -Command "$t=[Environment]::GetEnvironmentVariable('SHOPLAB_GNS3_CONTROL_TOKEN','User'); if([string]::IsNullOrWhiteSpace($t) -or $t.Length -lt 32){exit 1}" >nul 2>&1 || (
  echo [ERROR] SHOPLAB_GNS3_CONTROL_TOKEN is missing or invalid in User environment.
  exit /b 1
)

if not exist "%FRONTEND%\node_modules\vite\bin\vite.js" (
  echo [INFO] Installing frontend dependencies...
  pushd "%FRONTEND%"
  call npm install
  if errorlevel 1 (
    popd
    echo [ERROR] Frontend dependency installation failed.
    exit /b 1
  )
  popd
)

call :url_ready "%BACKEND_URL%"
if errorlevel 1 (
  echo [INFO] Starting backend...
  powershell -NoProfile -Command "$ErrorActionPreference='Stop'; $token=[Environment]::GetEnvironmentVariable('SHOPLAB_GNS3_CONTROL_TOKEN','User'); $env:SHOPLAB_GNS3_CONTROL_TOKEN=$token; $stamp=Get-Date -Format 'yyyyMMdd-HHmmss'; $out=Join-Path '%STATE_DIR%' ('backend-'+$stamp+'.out.log'); $err=Join-Path '%STATE_DIR%' ('backend-'+$stamp+'.err.log'); $p=Start-Process -FilePath 'python' -ArgumentList @('-B','-m','uvicorn','dashboards.app.backend.control_api:app','--host','127.0.0.1','--port','8000') -WorkingDirectory '%ROOT%' -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err -PassThru; @{pid=$p.Id;started=$p.StartTime.ToUniversalTime().Ticks;stdout=$out;stderr=$err}|ConvertTo-Json|Set-Content -LiteralPath '%BACKEND_STATE%' -Encoding UTF8" || exit /b 1
) else (
  echo [INFO] Backend is already reachable; it was not replaced.
)

call :url_ready "%FRONTEND_URL%"
if errorlevel 1 (
  echo [INFO] Starting frontend...
  powershell -NoProfile -Command "$ErrorActionPreference='Stop'; $stamp=Get-Date -Format 'yyyyMMdd-HHmmss'; $out=Join-Path '%STATE_DIR%' ('frontend-'+$stamp+'.out.log'); $err=Join-Path '%STATE_DIR%' ('frontend-'+$stamp+'.err.log'); $p=Start-Process -FilePath 'cmd.exe' -ArgumentList @('/d','/s','/c','npm run dev -- --host 127.0.0.1') -WorkingDirectory '%FRONTEND%' -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err -PassThru; @{pid=$p.Id;started=$p.StartTime.ToUniversalTime().Ticks;stdout=$out;stderr=$err}|ConvertTo-Json|Set-Content -LiteralPath '%FRONTEND_STATE%' -Encoding UTF8" || exit /b 1
) else (
  echo [INFO] Frontend is already reachable; it was not replaced.
)

call :wait_url "%BACKEND_URL%" 30
if errorlevel 1 (
  echo [ERROR] Backend did not become ready. Check %STATE_DIR%\backend-*.err.log
  exit /b 1
)
call :wait_url "%FRONTEND_URL%" 30
if errorlevel 1 (
  echo [ERROR] Frontend did not become ready. Check %STATE_DIR%\frontend-*.err.log
  exit /b 1
)

echo [OK] Local demo services are ready.
call :status
exit /b %errorlevel%

:restart
call "%~f0" stop
if errorlevel 1 exit /b 1
call "%~f0" start
exit /b %errorlevel%

:stop
echo [INFO] Stopping launcher-owned frontend...
call :stop_owned "%FRONTEND_STATE%"
if errorlevel 2 exit /b 1
echo [INFO] Stopping launcher-owned backend...
call :stop_owned "%BACKEND_STATE%"
if errorlevel 2 exit /b 1
echo [OK] Launcher-owned local services are stopped.
exit /b 0

:status
powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; function TestUrl([string]$name,[string]$url,[hashtable]$headers=@{}){try{$r=Invoke-WebRequest -UseBasicParsing -Uri $url -Headers $headers -TimeoutSec 4; Write-Host ('[OK]   '+$name+' HTTP '+[int]$r.StatusCode); return $true}catch{Write-Host ('[DOWN] '+$name); return $false}}; $backend=TestUrl 'Backend 127.0.0.1:8000' '%BACKEND_URL%'; $frontend=TestUrl 'Frontend 127.0.0.1:5173' '%FRONTEND_URL%'; $shop=TestUrl 'Shop 10.0.0.2:8080' 'http://10.0.0.2:8080/health'; $token=[Environment]::GetEnvironmentVariable('SHOPLAB_GNS3_CONTROL_TOKEN','User'); if([string]::IsNullOrWhiteSpace($token)){Write-Host '[DOWN] Control 10.0.0.2:8081 (User token missing)'}else{[void](TestUrl 'Control 10.0.0.2:8081' 'http://10.0.0.2:8081/control/v1/health' @{Authorization=('Bearer '+$token)})}; if(-not ($backend -and $frontend)){exit 1}"
exit /b %errorlevel%

:open
start "" "%FRONTEND_URL%"
echo [OK] Dashboard open request sent.
exit /b 0

:url_ready
powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; try{Invoke-WebRequest -UseBasicParsing -Uri '%~1' -TimeoutSec 2|Out-Null; exit 0}catch{exit 1}" >nul 2>&1
exit /b %errorlevel%

:wait_url
powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; $deadline=(Get-Date).AddSeconds(%~2); do{try{Invoke-WebRequest -UseBasicParsing -Uri '%~1' -TimeoutSec 2|Out-Null; exit 0}catch{Start-Sleep -Milliseconds 500}}while((Get-Date)-lt $deadline); exit 1" >nul 2>&1
exit /b %errorlevel%

:stop_owned
if not exist "%~1" (
  echo [INFO] No launcher state found; no process was stopped.
  exit /b 0
)
powershell -NoProfile -Command "$ErrorActionPreference='Stop'; $state=Get-Content -Raw -LiteralPath '%~1'|ConvertFrom-Json; $p=Get-Process -Id ([int]$state.pid) -ErrorAction SilentlyContinue; if($null -eq $p){Remove-Item -LiteralPath '%~1' -Force; exit 0}; if($p.StartTime.ToUniversalTime().Ticks -ne [long]$state.started){Write-Host '[ERROR] PID was reused; refusing to stop an unrelated process.'; exit 2}; taskkill.exe /PID $p.Id /T /F | Out-Null; Remove-Item -LiteralPath '%~1' -Force; exit 0"
exit /b %errorlevel%

:usage
echo Usage: demo.bat ^<start^|restart^|stop^|status^|open^>
exit /b 0

:usage_error
echo Usage: demo.bat ^<start^|restart^|stop^|status^|open^>
exit /b 2
