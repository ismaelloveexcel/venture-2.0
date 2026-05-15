param(
    [string]$TaskName = "VentureOperatorDailyDryRun",
    [string]$Time = "08:30",
    [switch]$Live,
    [switch]$ProspectsDemo = $true,
    [string]$ConfirmLive = ""
)

$ErrorActionPreference = "Stop"

if ($Live -and $ConfirmLive -ne "I_UNDERSTAND_LIVE_SENDS") {
    throw "Live scheduling requires -ConfirmLive I_UNDERSTAND_LIVE_SENDS"
}

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$runner = Join-Path $repoRoot "04-coding\scripts\run_operator_day.ps1"
$powershellExe = (Get-Command powershell).Source

if (-not (Test-Path $runner)) {
    throw "Missing runner script: $runner"
}

$argList = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$runner`""
)

if ($Live) {
    $argList += "-Live"
}
if ($ProspectsDemo) {
    $argList += "-ProspectsDemo"
}

$action = New-ScheduledTaskAction -Execute $powershellExe -Argument ($argList -join " ")
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -StartWhenAvailable

# Register in current user context (non-elevated) to minimize setup friction.
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Venture OS daily operator run" `
    -Force | Out-Null

Write-Host "Scheduled task registered:"
Write-Host "  Name: $TaskName"
Write-Host "  Time: $Time (daily)"
Write-Host "  Mode: $(if ($Live) { 'LIVE' } else { 'DRY-RUN' })"
