# Local build and deploy: build frontend, then run backend (serves API + built app)
# Run from project root. Requires: Node, npm, Python, Postgres (for DB).

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

Write-Host "Building frontend..." -ForegroundColor Cyan
Set-Location frontend
npm run build
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Set-Location ..

Write-Host "Frontend built to frontend/dist" -ForegroundColor Green
Write-Host ""
Write-Host "To run the app (backend serves API + frontend):" -ForegroundColor Cyan
Write-Host "  cd backend" -ForegroundColor White
Write-Host "  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000" -ForegroundColor White
Write-Host ""
Write-Host "Then open: http://localhost:8000" -ForegroundColor Green
Write-Host "API docs: http://localhost:8000/docs" -ForegroundColor Green
