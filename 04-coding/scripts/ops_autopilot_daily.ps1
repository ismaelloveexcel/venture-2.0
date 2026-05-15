#Requires -Version 5.1
<#
.SYNOPSIS
  Daily autonomous operations runner: status gate + policy refresh + health guard.

.DESCRIPTION
  Executes in this order:
    1) ops_daily.ps1 (compliance + DLQ hard checks)
    2) autopilot_health_guard.ps1 (snapshot + policy + anomalies)
    3) policy.json readback for final mode

  Exit code:
    0 = healthy and policy mode allows sends
    1 = operator attention required (ops_daily failed OR SAFE_MODE/paused)

  Logs one summary line to logs/ops-autopilot.log
#>

$ErrorActionPreference = "Stop"

$ScriptDir = $PSScriptRoot
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
$LogDir = Join-Path $RepoRoot "logs"
$LogFile = Join-Path $LogDir "ops-autopilot.log"
$DailyScript = Join-Path $ScriptDir "ops_daily.ps1"
$GuardScript = Join-Path $ScriptDir "autopilot_health_guard.ps1"
$PolicyFile = Join-Path $RepoRoot "04-coding\venture-engine\config\policy.json"
$VerdictScript = Join-Path $ScriptDir "operator_verdict.py"
$RunDailyScript = Join-Path $ScriptDir "run_daily.py"

function Resolve-Python {
  $candidates = @(
    (Join-Path $RepoRoot ".venv\Scripts\python.exe"),
    (Join-Path $RepoRoot ".venv-test\Scripts\python.exe")
  )
  foreach ($c in $candidates) {
    if (Test-Path $c) { return $c }
  }
  return "python"
}

$Python = Resolve-Python

$autoRunRaw = [string]$env:VENTURE_AUTOPILOT_RUN_PIPELINE_ON_GO
if ([string]::IsNullOrWhiteSpace($autoRunRaw)) {
  $autoRunRaw = "true"
}
$autoRunRaw = $autoRunRaw.ToLower().Trim()
$autoRunPipelineOnGo = @("1", "true", "yes", "on") -contains $autoRunRaw

$allowDryRunRaw = [string]$env:VENTURE_AUTOPILOT_ALLOW_DRY_RUN_ON_MISSING_CONFIG
if ([string]::IsNullOrWhiteSpace($allowDryRunRaw)) {
  $allowDryRunRaw = "true"
}
$allowDryRunRaw = $allowDryRunRaw.ToLower().Trim()
$allowDryRunOnMissingConfig = @("1", "true", "yes", "on") -contains $allowDryRunRaw

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

# 1) Daily hard checks
$dailyExit = 0
try {
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $DailyScript | Out-Null
  $dailyExit = $LASTEXITCODE
}
catch {
  $dailyExit = 1
}

# 2) Autopilot guard run (best effort, keeps exit 0 by design)
$guardExit = 0
try {
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $GuardScript | Out-Null
  $guardExit = $LASTEXITCODE
}
catch {
  $guardExit = 1
}

# 3) Read policy mode
$policyMode = "UNKNOWN"
$sendVelocity = "unknown"
if (Test-Path $PolicyFile) {
  try {
    $p = Get-Content -Raw -Path $PolicyFile | ConvertFrom-Json
    if ($p.mode) { $policyMode = [string]$p.mode }
    if ($p.send_velocity) { $sendVelocity = [string]$p.send_velocity }
  }
  catch {
    $policyMode = "INVALID_JSON"
  }
}

$policyBlocked = ($policyMode -eq "SAFE_MODE") -or ($sendVelocity -eq "paused")

# 4) Compute a single GO/HOLD operator verdict
$verdict = "HOLD"
$verdictScore = 0
$verdictReasons = "verdict_unavailable"
try {
  $vraw = & $Python $VerdictScript --daily-exit $dailyExit --guard-exit $guardExit 2>&1 | Out-String
  $vobj = $vraw | ConvertFrom-Json -ErrorAction Stop
  $verdict = [string]($vobj.verdict)
  $verdictScore = [int]($vobj.score)
  $verdictReasons = [string](($vobj.reasons -join ","))
}
catch {
  $verdict = "HOLD"
  $verdictScore = 0
  $verdictReasons = "verdict_parse_failed"
}

$fail = ($dailyExit -ne 0) -or ($policyBlocked) -or ($verdict -ne "GO")

# 5) Optional autonomous pipeline run after GO verdict.
$pipelineTriggered = $false
$pipelineExit = -1
$pipelineMode = "none"
$missingLiveConfig = @()
$requiredLiveEnv = @("OPENAI_API_KEY", "HUNTER_API_KEY", "NOTION_API_KEY")
foreach ($k in $requiredLiveEnv) {
  $v = [string](Get-Item -Path ("Env:" + $k) -ErrorAction SilentlyContinue).Value
  if ([string]::IsNullOrWhiteSpace($v)) {
    $missingLiveConfig += $k
  }
}

if ((-not $fail) -and $autoRunPipelineOnGo) {
  if (($missingLiveConfig.Count -gt 0) -and (-not $allowDryRunOnMissingConfig)) {
    $fail = $true
  }
  else {
    $pipelineTriggered = $true
    $pipelineArgs = @()
    if ($missingLiveConfig.Count -gt 0) {
      $pipelineMode = "dry_run"
      $pipelineArgs += "--dry-run"
    }
    else {
      $pipelineMode = "live"
    }

    try {
      $env:VENTURE_CANONICAL_ENTRY = "1"
      $runDailyArgs = @($RunDailyScript, "--execute")
      if ($pipelineArgs -contains "--dry-run") {
        $runDailyArgs += "--dry-run"
      }
      & $Python $runDailyArgs | Out-Null
      $pipelineExit = $LASTEXITCODE
    }
    catch {
      $pipelineExit = 1
    }
    if ($pipelineExit -ne 0) {
      $fail = $true
    }
  }
}

$missingConfigSummary = "none"
if ($missingLiveConfig.Count -gt 0) {
  $missingConfigSummary = ($missingLiveConfig -join ",")
}

$summary = "${timestamp}  ops_autopilot  ops_daily_exit=$dailyExit  guard_exit=$guardExit  policy_mode=$policyMode  velocity=$sendVelocity  verdict=$verdict  score=$verdictScore  reasons=$verdictReasons  pipeline_triggered=$pipelineTriggered  pipeline_mode=$pipelineMode  missing_live_config=$missingConfigSummary  pipeline_exit=$pipelineExit  exit=$([int]$fail)"
Add-Content -Path $LogFile -Value $summary
Write-Output $summary

if ($fail) {
  if ($dailyExit -ne 0) {
    Write-Error "ops_daily failed; check logs/ops-daily.log"
  }
  if ($policyBlocked) {
    Write-Error "Policy is blocking sends (mode=$policyMode, velocity=$sendVelocity)."
  }
  if ($verdict -ne "GO") {
    Write-Error "Operator verdict is HOLD (score=$verdictScore; reasons=$verdictReasons)."
  }
  if ((-not $pipelineTriggered) -and ($missingLiveConfig.Count -gt 0) -and (-not $allowDryRunOnMissingConfig)) {
    Write-Error "Missing live config prevents autonomous pipeline run: $($missingLiveConfig -join ',')."
  }
  if ($pipelineTriggered -and $pipelineExit -ne 0) {
    Write-Error "Autonomous pipeline run failed (exit=$pipelineExit)."
  }
  exit 1
}

exit 0
