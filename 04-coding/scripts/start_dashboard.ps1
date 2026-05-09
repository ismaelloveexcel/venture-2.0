$ErrorActionPreference = "Stop"

$WorkspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\.." )).Path
$PythonExe = Join-Path $WorkspaceRoot ".venv\Scripts\python.exe"
$Dashboard = Join-Path $WorkspaceRoot "04-coding\scripts\dashboard.py"

if (-not (Test-Path $PythonExe)) {
    Write-Host "[fail] Python not found at $PythonExe"
    exit 1
}

if (-not (Test-Path $Dashboard)) {
    Write-Host "[fail] dashboard.py not found at $Dashboard"
    exit 1
}

Write-Host "[info] Starting Venture OS dashboard..."
& $PythonExe $Dashboard
