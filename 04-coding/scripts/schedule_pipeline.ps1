# ─────────────────────────────────────────────────────────────────────────────
# Venture OS — Windows Task Scheduler Setup
# Registers a scheduled task to run the full pipeline automatically every week.
#
# Usage: Right-click this file → "Run with PowerShell" (as Administrator)
# Or: powershell -ExecutionPolicy Bypass -File ".\04-coding\scripts\schedule_pipeline.ps1"
#
# After running: the pipeline executes every Monday at 08:00 AM.
# To remove:     Unregister-ScheduledTask -TaskName "VentureOS Pipeline" -Confirm:$false
# ─────────────────────────────────────────────────────────────────────────────

$ErrorActionPreference = "Stop"

# ── Config ────────────────────────────────────────────────────────────────────
$WorkspaceRoot  = (Resolve-Path (Join-Path $PSScriptRoot "..\.." )).Path
$PythonExe      = Join-Path $WorkspaceRoot ".venv\Scripts\python.exe"
$RunnerScript   = Join-Path $WorkspaceRoot "04-coding\scripts\run_pipeline.ps1"
$LogDir         = Join-Path $WorkspaceRoot "logs"
$LogFile        = Join-Path $LogDir "pipeline-scheduled.log"
$TaskName       = "VentureOS Pipeline"
$RunDay         = "Monday"
$RunTime        = "08:00"

# ── Validate paths ────────────────────────────────────────────────────────────
if (-not (Test-Path $PythonExe)) {
    Write-Error "Python not found at: $PythonExe"
    Write-Host "Make sure you're in the right workspace and the .venv exists."
    exit 1
}
if (-not (Test-Path $RunnerScript)) {
    Write-Error "Runner script not found at: $RunnerScript"
    exit 1
}
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

# ── Build the action ──────────────────────────────────────────────────────────
# Runs: powershell -File run_pipeline.ps1 -Mode live >> logs/pipeline-scheduled.log
$ActionArgs  = "-NoProfile -ExecutionPolicy Bypass -File `"$RunnerScript`" -Mode live >> `"$LogFile`" 2>&1"
$Action      = New-ScheduledTaskAction `
    -Execute  "powershell.exe" `
    -Argument $ActionArgs `
    -WorkingDirectory $WorkspaceRoot

# ── Weekly trigger ────────────────────────────────────────────────────────────
$Trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek $RunDay `
    -At $RunTime

# ── Run as current user, only when logged in ──────────────────────────────────
$Principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Limited

# ── Settings ──────────────────────────────────────────────────────────────────
$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -StartWhenAvailable  # run ASAP if the machine was off at trigger time

# ── Register (or update if already exists) ────────────────────────────────────
$Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
try {
    if ($Existing) {
        Set-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings | Out-Null
        Write-Host "[ok] Updated existing scheduled task: $TaskName"
    } else {
        Register-ScheduledTask `
            -TaskName  $TaskName `
            -Action    $Action `
            -Trigger   $Trigger `
            -Principal $Principal `
            -Settings  $Settings `
            -Description "Venture OS: weekly outreach + follow-up + Notion sync + KPI digest" | Out-Null
        Write-Host "[ok] Registered new scheduled task: $TaskName"
    }
}
catch {
    Write-Host "[warn] Scheduled task registration needs additional permission in this shell."
    Write-Host "[info] Re-run this script once in an elevated PowerShell to complete scheduler setup."
    Write-Host "[info] Error: $($_.Exception.Message)"
}

Write-Host ""
Write-Host "  Schedule : Every $RunDay at $RunTime"
Write-Host "  Log file : $LogFile"
Write-Host "  To test  : Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "  To view  : Get-ScheduledTaskInfo -TaskName '$TaskName'"
Write-Host "  To remove: Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
Write-Host ""
