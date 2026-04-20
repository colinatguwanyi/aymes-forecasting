# Local dev: opens API in a new window, then runs Vite in this window.
# Requires: MySQL running (see docs/MYSQL_SETUP.md), backend/.env configured.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

$apiCmd = @"
Set-Location '$backend'
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
Write-Host 'API: http://127.0.0.1:8000/docs' -ForegroundColor Green
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
"@
Start-Process powershell -ArgumentList "-NoExit", "-Command", $apiCmd
Start-Sleep -Seconds 2
Set-Location $frontend
Write-Host 'App: http://localhost:5173 (proxies /api to :8000)' -ForegroundColor Green
npm run dev
