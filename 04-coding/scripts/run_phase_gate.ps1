<#
.SYNOPSIS
  Deterministic gate: optional phase expectation + pytest + validate_repo_contract.

.DESCRIPTION
  Use after local work or before opening a PHASE REVIEWER Task. Does not run LLM review.
  After PHASE_PASS, run: .venv\Scripts\python 04-coding\scripts\advance_venture_phase.py P3

.PARAMETER ExpectCurrentPhase
  If set, must match .venture_phase_state.json "current_phase" or exit 2.

#>
param(
    [string] $ExpectCurrentPhase = "",
    [switch] $SkipPhaseCheck
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$StatePath = Join-Path $RepoRoot "04-coding\.venture_phase_state.json"
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }

function Read-PhaseState {
    $raw = Get-Content -LiteralPath $StatePath -Raw -Encoding utf8
    return $raw | ConvertFrom-Json
}

if (-not (Test-Path $StatePath)) {
    Write-Error "Missing $StatePath"
    exit 2
}

if ($ExpectCurrentPhase -and -not $SkipPhaseCheck) {
    $st = Read-PhaseState
    if ($st.current_phase -ne $ExpectCurrentPhase) {
        Write-Error "Phase check: expected current_phase='$ExpectCurrentPhase', got '$($st.current_phase)'"
        exit 2
    }
}

Push-Location $RepoRoot
try {
    & $Python -m pytest tests -q
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $Python (Join-Path $RepoRoot "04-coding\scripts\validate_repo_contract.py")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}

Write-Host "run_phase_gate: OK"
