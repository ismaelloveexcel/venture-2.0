$ErrorActionPreference = "Stop"

$WorkspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\.." )).Path
$VenvPython = Join-Path $WorkspaceRoot ".venv\Scripts\python.exe"
$Requirements = Join-Path $WorkspaceRoot "requirements.txt"

if (-not (Test-Path $VenvPython)) {
    Write-Host "[info] Creating virtual environment..."
    python -m venv (Join-Path $WorkspaceRoot ".venv")
}

if (-not (Test-Path $VenvPython)) {
    Write-Host "[fail] Could not create/find .venv Python at $VenvPython"
    exit 1
}

Write-Host "[info] Upgrading pip..."
& $VenvPython -m pip install --upgrade pip

if (Test-Path $Requirements) {
    Write-Host "[info] Installing dependencies from requirements.txt..."
    & $VenvPython -m pip install -r $Requirements
}

Write-Host "[ok] Bootstrap complete."
Write-Host "[info] Run dry-run:  .\04-coding\scripts\run_pipeline.ps1 -Mode dry-run"
Write-Host "[info] Run live:     .\04-coding\scripts\run_pipeline.ps1 -Mode live"
Write-Host "[info] Dashboard:    .\04-coding\scripts\start_dashboard.ps1"
