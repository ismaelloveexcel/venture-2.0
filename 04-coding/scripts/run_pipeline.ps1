param(
    [ValidateSet("dry-run", "live")]
    [string]$Mode = "dry-run"
)

$ErrorActionPreference = "Stop"

$WorkspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\.." )).Path
$PythonExe = Join-Path $WorkspaceRoot ".venv\Scripts\python.exe"
$Preflight = Join-Path $WorkspaceRoot "04-coding\scripts\pre_send_check.py"
$RunDaily = Join-Path $WorkspaceRoot "04-coding\scripts\run_daily.py"

if (-not (Test-Path $PythonExe)) {
    Write-Host "[fail] Python not found at $PythonExe"
    exit 1
}

if (-not (Test-Path $Preflight)) {
    Write-Host "[fail] preflight_check.py not found at $Preflight"
    exit 1
}

if (-not (Test-Path $RunDaily)) {
    Write-Host "[fail] run_daily.py not found at $RunDaily"
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
$env:VENTURE_CANONICAL_ENTRY = "1"
& $PythonExe $RunDaily bridge status
if ($LASTEXITCODE -ne 0) {
    Write-Host "[fail] Status snapshot failed. Pipeline run aborted."
    exit $LASTEXITCODE
}

Write-Host "[info] Starting canonical mode via run_daily: $Mode"
$prevErrPref = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
$args = @($RunDaily, "--execute")
if ($Mode -eq "dry-run") {
    $args += "--dry-run"
}
cmd /c "`"$PythonExe`" `"$($args[0])`" $($args[1..($args.Length-1)] -join ' ')"
$ErrorActionPreference = $prevErrPref

exit $LASTEXITCODE
