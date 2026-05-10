param(
    [ValidateSet("dry-run", "live")]
    [string]$Mode = "dry-run"
)

$ErrorActionPreference = "Stop"

$WorkspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\.." )).Path
$PythonExe = Join-Path $WorkspaceRoot ".venv\Scripts\python.exe"
$Preflight = Join-Path $WorkspaceRoot "04-coding\scripts\pre_send_check.py"
$Pipeline = Join-Path $WorkspaceRoot "04-coding\scripts\venture_pipeline.py"

if (-not (Test-Path $PythonExe)) {
    Write-Host "[fail] Python not found at $PythonExe"
    exit 1
}

if (-not (Test-Path $Preflight)) {
    Write-Host "[fail] preflight_check.py not found at $Preflight"
    exit 1
}

if (-not (Test-Path $Pipeline)) {
    Write-Host "[fail] venture_pipeline.py not found at $Pipeline"
    exit 1
}

Write-Host "[info] Workspace: $WorkspaceRoot"
Write-Host "[info] Running preflight checks..."
& $PythonExe $Preflight --mode $Mode
if ($LASTEXITCODE -ne 0) {
    if ($Mode -eq "live") {
        Write-Host "[fail] Live preflight failed. Pipeline run aborted."
        exit $LASTEXITCODE
    }
    Write-Host "[warn] Dry-run pre-send gate is not armed yet; continuing dry-run pipeline."
}

Write-Host "[info] Running operator status snapshot..."
& $PythonExe $Pipeline --status
if ($LASTEXITCODE -ne 0) {
    Write-Host "[fail] Status snapshot failed. Pipeline run aborted."
    exit $LASTEXITCODE
}

Write-Host "[info] Starting pipeline mode: $Mode"
$prevErrPref = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
if ($Mode -eq "dry-run") {
    cmd /c "`"$PythonExe`" `"$Pipeline`" --dry-run"
}
else {
    cmd /c "`"$PythonExe`" `"$Pipeline`""
}
$ErrorActionPreference = $prevErrPref

exit $LASTEXITCODE
