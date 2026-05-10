#Requires -Version 5.1
<#
.SYNOPSIS
  Daily health: venture_pipeline --status, fail on compliance BLOCKED or DLQ over threshold.

.DESCRIPTION
  Exit 0 = healthy. Exit 1 = operator attention (compliance policy blocked, or DLQ count > threshold).

  Environment:
    VENTURE_OPS_DLQ_THRESHOLD  (default 0)  Fail when DLQ count is STRICTLY GREATER than this value.
                              Use 0 to fail on any DLQ row (count >= 1).

  Logs one line to repo logs/ops-daily.log
#>
$ErrorActionPreference = "Stop"

$ScriptDir = $PSScriptRoot
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
$LogDir = Join-Path $RepoRoot "logs"
$LogFile = Join-Path $LogDir "ops-daily.log"
$Pipeline = Join-Path $RepoRoot "04-coding\scripts\venture_pipeline.py"

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
$threshold = 0
if ($env:VENTURE_OPS_DLQ_THRESHOLD -match '^\d+$') {
    $threshold = [int]$env:VENTURE_OPS_DLQ_THRESHOLD
}

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$output = & $Python $Pipeline --status 2>&1 | Out-String

$blocked = $output -match "cooldown:\s+BLOCKED"
$dlqCount = 0
if ($output -match "webhook_dlq:\s*(\d+)\s+row") {
    $dlqCount = [int]$Matches[1]
}

$dlqFail = $dlqCount -gt $threshold
$fail = $blocked -or $dlqFail

$summary = "${timestamp}  ops_daily  compliance_blocked=$blocked  dlq_count=$dlqCount  threshold=$threshold  exit=$([int]$fail)"
Add-Content -Path $LogFile -Value $summary

Write-Output $output
Write-Output ""
Write-Output $summary

if ($fail) {
    if ($blocked) { Write-Error "Compliance policy is BLOCKED (fix compliance.config.json)." }
    if ($dlqFail) { Write-Error "DLQ count $dlqCount exceeds threshold $threshold (replay with dlq_replay.py)." }
    exit 1
}
exit 0
