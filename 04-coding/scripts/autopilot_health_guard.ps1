#Requires -Version 5.1
<#
.SYNOPSIS
  Autopilot Health Guard: autonomous anomaly detection + guardrail enforcement.

.DESCRIPTION
  Runs system_state_snapshot + policy_engine to detect anomalies.
  
  If anomalies detected (DLQ spike, failures, etc.), automatically:
  1. Triggers policy engine re-evaluation
  2. Enters SAFE_MODE if critical
  3. Logs all actions to ops-health-guard.log
  4. Updates system_state.json mirror for dashboard visibility

  Exit code: always 0 (logging is best-effort; errors are recorded, not failed)

.NOTES
  This is the autonomous anomaly reactor. It should run after ops_daily.ps1
  or as part of batch monitoring. It observes and corrects, not intervenes manually.
#>

$ErrorActionPreference = "Stop"

$ScriptDir = $PSScriptRoot
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
$LogDir = Join-Path $RepoRoot "logs"
$LogFile = Join-Path $LogDir "ops-health-guard.log"

$ScriptsDir = Join-Path $RepoRoot "04-coding\scripts"
$StateFile = Join-Path $RepoRoot "04-coding\venture-engine\config\system_state.json"
$PolicyFile = Join-Path $RepoRoot "04-coding\venture-engine\config\policy.json"

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
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
if (-not (Test-Path (Split-Path -Parent $StateFile))) {
  New-Item -ItemType Directory -Path (Split-Path -Parent $StateFile) | Out-Null
}

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

# Run snapshot
$snapshotJson = & $Python (Join-Path $ScriptsDir "system_state_snapshot.py") 2>&1 | Out-String
$snapshot = $snapshotJson | ConvertFrom-Json -ErrorAction SilentlyContinue

if (-not $snapshot) {
  $line = "${timestamp}  ERROR: snapshot failed"
  Add-Content -Path $LogFile -Value $line
  Write-Output $line
  exit 0
}

# Always run policy engine so policy.json stays fresh for every guard cycle.
$policyOutput = & $Python (Join-Path $ScriptsDir "policy_engine.py") 2>&1 | Out-String
$policyMode = "UNKNOWN"
$policyReason = ""
if ($policyOutput -match "POLICY DECISION: (\S+)") {
  $policyMode = $Matches[1]
}
if (Test-Path $PolicyFile) {
  try {
    $policyJson = Get-Content -Raw -Path $PolicyFile | ConvertFrom-Json
    if ($policyJson.mode) { $policyMode = [string]$policyJson.mode }
    if ($policyJson.reason) { $policyReason = [string]$policyJson.reason }
  }
  catch {
    # keep parsed mode from stdout if file read fails
  }
}

# Analyze for anomalies
$anomalies = @()

# DLQ spike: new entries in last 24h > 3
if ($snapshot.dlq_growth_24h -gt 3) {
  $anomalies += "DLQ_SPIKE (growth_24h=$($snapshot.dlq_growth_24h))"
}

# DLQ backlog critical
if ($snapshot.dlq_count -ge 10) {
  $anomalies += "DLQ_CRITICAL (count=$($snapshot.dlq_count))"
}

# Failure spike
if ($snapshot.failure_rate_24h -ge 15) {
  $anomalies += "FAILURE_RATE_HIGH (rate=$($snapshot.failure_rate_24h)%)"
}

# Data integrity
if ($snapshot.orphan_outbound_events -gt 0) {
  $anomalies += "ORPHAN_EVENTS (count=$($snapshot.orphan_outbound_events))"
}

if ($snapshot.duplicate_initial_sends -gt 0) {
  $anomalies += "DUPLICATE_SENDS (count=$($snapshot.duplicate_initial_sends))"
}

# Compliance violations
if ($snapshot.cooldown_violations_24h -gt 5) {
  $anomalies += "COOLDOWN_VIOLATIONS (count=$($snapshot.cooldown_violations_24h))"
}

# Mirror the latest snapshot into system_state.json with policy mode included.
try {
  $snapshot.system_mode = $policyMode
  ($snapshot | ConvertTo-Json -Depth 10) | Set-Content -Path $StateFile -Encoding UTF8
}
catch {
  Add-Content -Path $LogFile -Value "${timestamp}  WARN: failed to update system_state.json: $_"
}

# Log current state
$stateLog = "${timestamp}  health=$($snapshot.health_emoji)  dlq=$($snapshot.dlq_count)  failures=$($snapshot.failure_rate_24h)%  mode=$policyMode"

if ($anomalies.Count -gt 0) {
  $anomalyStr = ($anomalies -join " | ")
  $stateLog += "  ANOMALIES: $anomalyStr"
}

if ($policyReason) {
  $stateLog += "  policy_reason=`"$policyReason`""
}

Add-Content -Path $LogFile -Value $stateLog
Write-Output $stateLog

# If anomalies detected, surface policy result in logs for fast triage.
if ($anomalies.Count -gt 0) {
  $policyLog = "${timestamp}  POLICY_ENGINE_RESULT: $policyMode"
  if ($policyMode -eq "SAFE_MODE") {
    $policyLog += " [CRITICAL: sends paused]"
  }
  elseif ($policyMode -eq "RESTRICTED") {
    $policyLog += " [sends throttled]"
  }
  Add-Content -Path $LogFile -Value $policyLog
  Write-Output $policyLog
}

exit 0
