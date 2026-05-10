#Requires -Version 5.1
<#
.SYNOPSIS
  Weekly maintenance: replay_audit, DLQ dry-run sample, append summary to logs.

.EXIT
  0 always (summary records replay_audit exit code for triage).
#>
$ErrorActionPreference = "Stop"

$ScriptDir = $PSScriptRoot
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
$LogDir = Join-Path $RepoRoot "logs"
$LogFile = Join-Path $LogDir "ops-weekly.log"
$Replay = Join-Path $RepoRoot "04-coding\scripts\replay_audit.py"
$Dlq = Join-Path $RepoRoot "04-coding\scripts\dlq_replay.py"

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

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$replayOut = & $Python $Replay 2>&1 | Out-String
$replayExit = $LASTEXITCODE

$dlqOut = ""
try {
    $dlqOut = & $Python $Dlq --limit 30 2>&1 | Out-String
} catch {
    $dlqOut = "dlq_replay failed: $_"
}

function Get-Tail([string]$text, [int]$maxLen) {
    if ([string]::IsNullOrEmpty($text)) { return "" }
    $start = [Math]::Max(0, $text.Length - $maxLen)
    return $text.Substring($start)
}

$dlqSummary = "dlq_replay_dry_run_lines=" + (($dlqOut -split "`n").Count)
$line = "${timestamp}  ops_weekly  replay_audit_exit=$replayExit  $dlqSummary"
Add-Content -Path $LogFile -Value $line
Add-Content -Path $LogFile -Value "--- replay_audit (tail) ---"
Add-Content -Path $LogFile -Value (Get-Tail $replayOut 4000)
Add-Content -Path $LogFile -Value "--- dlq_replay dry-run (tail) ---"
Add-Content -Path $LogFile -Value (Get-Tail $dlqOut 2000)
Add-Content -Path $LogFile -Value "========"

Write-Output $line
Write-Output "(full detail appended to $LogFile)"
exit 0
