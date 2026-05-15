param(
    [switch]$Live,
    [switch]$ProspectsDemo = $true,
    [string]$PilotId = "pilot_1",
    [string]$ClientName = "internal_run",
    [string]$IcpSlice = "early_stage_b2b_founders",
    [string]$Channel = "cold_email",
    [string]$ConfirmLive = "",
    [switch]$OverridePause
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$runDaily = Join-Path $repoRoot "04-coding\scripts\run_daily.py"
$gateCalc = Join-Path $repoRoot "04-coding\scripts\calculate_gate_scores.py"
$reportPath = Join-Path $repoRoot "run_report.json"
$logPath = Join-Path $repoRoot "07-kpis\operator_execution_log.csv"
$pausePath = Join-Path $repoRoot "04-coding\state\operator_pause_state.json"
$archiveRoot = Join-Path $repoRoot "logs\run-reports"
$gatesPath = Join-Path $repoRoot "04-coding\config\gates.json"

if (-not (Test-Path $python)) {
    throw "Missing venv python at $python"
}
if (-not (Test-Path $gatesPath)) {
    throw "Missing thresholds config at $gatesPath"
}

if ($Live) {
    if ($ConfirmLive -ne "I_UNDERSTAND_LIVE_SENDS") {
        throw "Live run requires -ConfirmLive I_UNDERSTAND_LIVE_SENDS"
    }
    $liveEnv = if ($null -ne $env:VENTURE_ENABLE_LIVE_SENDS) { $env:VENTURE_ENABLE_LIVE_SENDS } else { "" }
    if ($liveEnv.ToUpperInvariant() -ne "1") {
        throw "Set VENTURE_ENABLE_LIVE_SENDS=1 to allow live operator run"
    }
}

if ((Test-Path $pausePath) -and (-not $OverridePause)) {
    $pause = Get-Content -Raw -Encoding UTF8 $pausePath | ConvertFrom-Json
    if ($pause.paused -eq $true) {
        throw "Operator pause is active. Use -OverridePause only after reviewing reasons in $pausePath"
    }
}

$args = @($runDaily, "--generate-prospects", "--execute", "--report-path", $reportPath)
if ($ProspectsDemo) { $args += "--prospects-demo" }
if (-not $Live) { $args += "--dry-run" }
$env:VENTURE_CANONICAL_ENTRY = "1"
& $python @args
if ($LASTEXITCODE -ne 0) {
    throw "run_daily failed with exit code $LASTEXITCODE"
}

$report = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
$pb = $report.outbound.prospect_batch

# Archive run_report by run_id for immutable history.
$archiveDir = Join-Path $archiveRoot ((Get-Date).ToUniversalTime().ToString("yyyy-MM-dd"))
if (-not (Test-Path $archiveDir)) { New-Item -ItemType Directory -Path $archiveDir | Out-Null }
$archiveFile = Join-Path $archiveDir ("run_{0}.json" -f $report.run_id)
Copy-Item -Path $reportPath -Destination $archiveFile -Force

$row = [ordered]@{
    date                    = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd")
    pilot_id                = $PilotId
    client_name             = $ClientName
    icp_slice               = $IcpSlice
    channel                 = $Channel
    run_id                  = $report.run_id
    delivered_count         = [string]($pb.approved_pass_rows)
    positive_replies        = "0"
    qualified_conversations = "0"
    qualified_icp_fit       = ""
    qualified_buyer_role    = ""
    qualified_next_step     = ""
    meeting_quality_notes   = "n/a_auto_log"
    pivot_variable          = "none"
    pivot_compliant         = "Y"
    sla_client_compliant    = "Y"
    sla_operator_compliant  = "Y"
    stop_loss_compliant     = "Y"
    deliverability_compliant= "Y"
    schema_completeness_pct = "100"
    gate_overrides_logged   = "0"
    stop_loss_triggered     = "N"
    action_taken            = $(if ($Live) { "live_full_stack_success" } else { "dry_run_full_stack_success" })
}

$logDir = Split-Path -Parent $logPath
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }

$exists = Test-Path $logPath
$schema = @(
    "date","pilot_id","client_name","icp_slice","channel","run_id","delivered_count",
    "positive_replies","qualified_conversations","qualified_icp_fit","qualified_buyer_role",
    "qualified_next_step","meeting_quality_notes","pivot_variable","pivot_compliant",
    "sla_client_compliant","sla_operator_compliant","stop_loss_compliant",
    "deliverability_compliant","schema_completeness_pct","gate_overrides_logged",
    "stop_loss_triggered","action_taken"
)
if ($exists) {
    $rows = Import-Csv -Path $logPath
    if ($rows.Count -gt 0) {
        $currentCols = $rows[0].PSObject.Properties.Name
        $missingCols = @($schema | Where-Object { $_ -notin $currentCols })
        if ($missingCols.Count -gt 0) {
            $migrated = @()
            foreach ($r in $rows) {
                $obj = [ordered]@{}
                foreach ($c in $schema) {
                    $obj[$c] = if ($r.PSObject.Properties.Name -contains $c) { $r.$c } else { "" }
                }
                $migrated += [PSCustomObject]$obj
            }
            $migrated | Export-Csv -Path $logPath -NoTypeInformation -Encoding UTF8
        }
    }
}

$csvRow = [PSCustomObject]([ordered]@{})
foreach ($c in $schema) { $csvRow | Add-Member -NotePropertyName $c -NotePropertyValue ($row[$c]) }
if (Test-Path $logPath) {
    $csvRow | Export-Csv -Path $logPath -Append -NoTypeInformation -Encoding UTF8
} else {
    $csvRow | Export-Csv -Path $logPath -NoTypeInformation -Encoding UTF8
}

# Schema + qualified conversation verifier enforcement on latest row.
$latest = Import-Csv -Path $logPath | Select-Object -Last 1
$required = $schema
foreach ($k in $required) {
    if (-not ($latest.PSObject.Properties.Name -contains $k)) {
        throw "Schema validation failed: missing column $k"
    }
}
if ([int]($latest.qualified_conversations) -gt 0) {
    if ([string]::IsNullOrWhiteSpace($latest.qualified_icp_fit) -or [string]::IsNullOrWhiteSpace($latest.qualified_buyer_role) -or [string]::IsNullOrWhiteSpace($latest.qualified_next_step)) {
        throw "Qualified conversation verifier fields are required when qualified_conversations > 0"
    }
}

# Calculate Gate A/B status and update pause state.
& $python $gateCalc | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Gate score calculator failed"
}

Write-Host "Logged operator row: $logPath"
Write-Host "Archived report: $archiveFile"

Write-Host "Operator day run complete."
