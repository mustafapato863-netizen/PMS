# PMS Dashboard - one-command local run.
#
# Usage:
#   .\run.ps1                 # start backend + worker + frontend (dev mode)
#   .\run.ps1 -NoWorker       # skip the background worker
#   .\run.ps1 -NoInstall      # skip dependency checks/installs
#   .\run.ps1 -NoBrowser      # do not open the browser automatically
#   .\run.ps1 -Stop           # stop everything started by .\run.ps1
#
# If Windows blocks the script, run:
#   powershell -ExecutionPolicy Bypass -File .\run.ps1
#
# What it starts:
#   Backend   http://127.0.0.1:8000  (FastAPI via uvicorn, from Backend/)
#   Worker    durable processing worker (Backend/worker.py, needs Postgres)
#   Frontend  http://localhost:5173   (Vite dev, pointed at the local backend)
#
# The backend reads Backend/.env.local automatically (Postgres, CORS, ...).
# The frontend's .env.local points at production, so this script overrides
# VITE_API_BASE_URL (+ socket URL) via process env for the dev server only.

param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [switch]$NoWorker,
    [switch]$NoInstall,
    [switch]$NoBrowser,
    [switch]$Stop
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path ([System.IO.Path]::GetTempPath()) 'pms-run-pids.json'

function Get-ListenerPid {
    param([int]$Port)
    $line = netstat -ano | Select-String 'LISTENING' | Select-String ":$Port " | Select-Object -First 1
    if ($line -and ($line -match '(\d+)\s*$')) { return [int]$Matches[1] }
    return $null
}

function Stop-RunningStack {
    if (Test-Path $PidFile) {
        $pids = Get-Content $PidFile -Raw | ConvertFrom-Json
        foreach ($id in $pids) {
            try {
                $proc = Get-Process -Id $id -ErrorAction Stop
                Write-Host "Stopping $($proc.ProcessName) (PID $id)..." -ForegroundColor Gray
                Stop-Process -Id $id -Force
            } catch {
                Write-Host "PID $id already gone." -ForegroundColor Gray
            }
        }
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    }
    # Belt and braces: free the ports too (covers orphaned child servers).
    # Only touch processes that look like ours (stale PIDs can be recycled
    # by the OS for unrelated processes, so never kill blindly by PID).
    $safeNames = @('powershell', 'pwsh', 'python', 'pythonw', 'node', 'cmd', 'npm')
    foreach ($port in @($BackendPort, $FrontendPort)) {
        $listenerPid = Get-ListenerPid -Port $port
        if ($listenerPid) {
            try {
                $proc = Get-Process -Id $listenerPid -ErrorAction Stop
                if ($safeNames -contains $proc.ProcessName) {
                    Write-Host "Freeing port $port ($($proc.ProcessName), PID $listenerPid)..." -ForegroundColor Gray
                    Stop-Process -Id $listenerPid -Force
                } else {
                    Write-Warning "Port $port is held by $($proc.ProcessName) (PID $listenerPid) - leaving it alone."
                }
            } catch { }
        }
    }
    Write-Host 'Stopped.' -ForegroundColor Green
}

if ($Stop) {
    Stop-RunningStack
    exit 0
}

# If a previous stack is still tracked, stop it first so ports are free.
if (Test-Path $PidFile) {
    Write-Host 'A previous stack is still tracked - stopping it first...' -ForegroundColor Yellow
    Stop-RunningStack
}

Push-Location $Root
try {
    # ---------- 1. Prerequisites ----------
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) { Write-Error 'python not found on PATH. Install Python 3.12+ first.' }
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npm) { Write-Error 'npm not found on PATH. Install Node.js 20+ first.' }
    Write-Host "python: $(python --version 2>&1)" -ForegroundColor Gray
    Write-Host "node:   $(node --version 2>&1)" -ForegroundColor Gray

    # Prefer the repo venv when present, otherwise the current python.
    $VenvPython = Join-Path $Root 'Backend\.venv\Scripts\python.exe'
    $BackendPython = if (Test-Path $VenvPython) { $VenvPython } else { 'python' }
    Write-Host "backend python: $BackendPython" -ForegroundColor Gray

    if (-not $NoInstall) {
        # Backend deps
        $hasDeps = & $BackendPython -c 'import fastapi, uvicorn' 2>$null; $hasDepsOk = ($LASTEXITCODE -eq 0)
        if (-not $hasDepsOk) {
            Write-Host 'Installing backend requirements...' -ForegroundColor Yellow
            if (-not (Test-Path $VenvPython)) {
                Write-Host 'Creating Backend/.venv...' -ForegroundColor Gray
                & python -m venv (Join-Path $Root 'Backend\.venv')
                $BackendPython = $VenvPython
            }
            & $BackendPython -m pip install -r (Join-Path $Root 'Backend\requirements.txt')
        } else {
            Write-Host 'Backend deps OK.' -ForegroundColor Gray
        }
        # Frontend deps
        if (-not (Test-Path (Join-Path $Root 'Frontend\node_modules'))) {
            Write-Host 'Installing frontend packages (npm install)...' -ForegroundColor Yellow
            Push-Location (Join-Path $Root 'Frontend')
            try { npm install } finally { Pop-Location }
        } else {
            Write-Host 'Frontend deps OK.' -ForegroundColor Gray
        }
    }

    # ---------- 2. Postgres reachability (backend + worker need it) ----------    $dbUp = $false
    try {
        $tcp = New-Object Net.Sockets.TcpClient
        $iar = $tcp.BeginConnect('127.0.0.1', 5432, $null, $null)
        $dbUp = $iar.AsyncWaitHandle.WaitOne(1500)
        $tcp.Close()
    } catch { $dbUp = $false }
    if (-not $dbUp) {
        Write-Warning 'Postgres is not reachable at 127.0.0.1:5432. The backend/worker need DATABASE_URL from Backend/.env.local - start Postgres, then re-run.'
    }

    # ---------- 3. Port availability (fail fast with a clear message) ----------
    foreach ($port in @($BackendPort, $FrontendPort)) {
        $listener = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback, $port)
        try {
            $listener.Start()
            $listener.Stop()
        } catch {
            Write-Error "Port $port is already in use (another server running?). Free it or pick another: .\run.ps1 -BackendPort 8010 -FrontendPort 5199"
        } finally {
            $listener.Stop()
        }
    }

    # ---------- 4. Launch ----------
    $BackendUrl = "http://127.0.0.1:$BackendPort"
    $FrontendUrl = "http://localhost:$FrontendPort"
    $started = @()

    $backendCmd = "`$Host.UI.RawUI.WindowTitle='PMS backend'; `$env:PORT='$BackendPort'; & '$BackendPython' -m uvicorn app:app --host 127.0.0.1 --port $BackendPort --reload"
    $p = Start-Process powershell -ArgumentList @('-NoExit', '-Command', "cd '$Root\Backend'; $backendCmd") -WorkingDirectory "$Root\Backend" -PassThru
    $started += $p.Id
    Write-Host "Backend starting (PID $($p.Id)) -> $BackendUrl" -ForegroundColor Cyan

    if (-not $NoWorker) {
        $p = Start-Process powershell -ArgumentList @('-NoExit', '-Command', "cd '$Root\Backend'; `$Host.UI.RawUI.WindowTitle='PMS worker'; & '$BackendPython' worker.py") -WorkingDirectory "$Root\Backend" -PassThru
        $started += $p.Id
        Write-Host "Worker starting (PID $($p.Id))..." -ForegroundColor Cyan
    }

    $frontendEnv = "`$env:VITE_API_BASE_URL='$BackendUrl'; `$env:VITE_SOCKET_URL='ws://127.0.0.1:$BackendPort'; `$env:PORT='$FrontendPort'"
    $p = Start-Process powershell -ArgumentList @('-NoExit', '-Command', "cd '$Root\Frontend'; `$Host.UI.RawUI.WindowTitle='PMS frontend'; $frontendEnv; npm run dev -- --port $FrontendPort --strictPort") -WorkingDirectory "$Root\Frontend" -PassThru
    $started += $p.Id
    Write-Host "Frontend starting (PID $($p.Id)) -> $FrontendUrl" -ForegroundColor Cyan

    $started | ConvertTo-Json | Set-Content $PidFile
    if ($FrontendPort -ne 5173) {
        Write-Warning "Frontend port is $FrontendPort but Backend/.env.local CORS_ORIGINS only allows 5173 - update CORS_ORIGINS or use the default port."
    }

    Write-Host ''
    Write-Host 'PMS Dashboard is starting:' -ForegroundColor Green
    Write-Host "  Frontend  $FrontendUrl" -ForegroundColor White
    Write-Host "  Backend   $BackendUrl/docs" -ForegroundColor White
    if (-not $NoWorker) { Write-Host '  Worker    polling Postgres for jobs' -ForegroundColor White }
    Write-Host '  Stop all: .\run.ps1 -Stop' -ForegroundColor White

    if (-not $NoBrowser) {
        Start-Sleep -Seconds 4
        Start-Process $FrontendUrl | Out-Null
    }
} finally {
    Pop-Location
}
