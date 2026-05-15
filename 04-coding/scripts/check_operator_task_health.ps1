param(
    [string]$TaskName = "VentureOperatorDailyDryRun"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$logPath = Join-Path $repoRoot "07-kpis\operator_execution_log.csv"
$gatePath = Join-Path $repoRoot "07-kpis\gate_status.json"
$pausePath = Join-Path $repoRoot "04-coding\state\operator_pause_state.json"

$issues = @()

try {
    $taskInfo = schtasks /Query /TN $TaskName /V /FO LIST
    $txt = ($taskInfo | Out-String)
    if ($txt -notmatch "Last Result:\s+0") {
        $issues += "scheduler_last_result_nonzero_or_unavailable"
    }
} catch {
    $issues += "scheduler_query_failed"
}

if (-not (Test-Path $logPath)) {
    $issues += "operator_log_missing"
} else {
    $last = Import-Csv $logPath | Select-Object -Last 1
    if (-not $last) {
        $issues += "operator_log_empty"
    } elseif ($last.date -ne (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd")) {
        $issues += "operator_log_not_updated_today"
    }
}

if (-not (Test-Path $gatePath)) {
    $issues += "gate_status_missing"
}

if ((Test-Path $pausePath)) {
    $pause = Get-Content -Raw -Encoding UTF8 $pausePath | ConvertFrom-Json
    if ($pause.paused -eq $true) {
        $issues += "operator_pause_active"
    }
}

if ($issues.Count -gt 0) {
    Write-Error ("Operator health check failed: " + ($issues -join ", "))
    exit 1
}

Write-Host "Operator health check OK."
