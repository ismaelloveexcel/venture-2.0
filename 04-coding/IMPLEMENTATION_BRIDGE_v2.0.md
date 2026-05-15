# 🚀 IMPLEMENTATION BRIDGE DOCUMENT (v2.0)

## System Observability Dashboard — Complete Execution Contract

This document defines **all runtime, file, and execution mechanics** required for deterministic agent implementation.

---

# 1. RUN REPORT GENERATION PIPELINE

## Source of Truth Generator

```text
venture_pipeline.py
```

This is the **ONLY script responsible** for producing `run_report.json`.

---

## Execution Timing

* Runs pipeline end-to-end
* Collects all component metrics from execution logs
* THEN writes final snapshot to disk

```text
Pipeline Execution Flow:

start pipeline
→ execute stage_1 → stage_2 → ... → stage_7
→ collect metrics from each stage (from logs/DB)
→ calculate system_score + category scores
→ identify top 3 issues
→ build complete run_report.json
→ overwrite previous file
→ append run_history (trim to 10)
→ exit
```

---

## Write Mode (CRITICAL RULE)

* run_report.json is **fully overwritten per run**
* NOT incrementally updated
* NOT streamed

```text
WRITE STRATEGY:
OVERWRITE ENTIRE FILE AFTER PIPELINE COMPLETES
(New structure replaces old; run_history preserved via append logic)
```

---

# 2. METRICS POPULATION SOURCE (CRITICAL)

## Per-Component Metric Calculation

All metrics are sourced from pipeline execution logs. Python calculates these BEFORE writing JSON.

### success_count
```
Source: venture_jobs.db → block_logs (WHERE block_id = component_id AND status = 'SUCCESS')
Calculation: COUNT(successful operations)
Type: Integer (0+)
```

### failure_count
```
Source: venture_jobs.db → block_logs (WHERE block_id = component_id AND status = 'FAILED')
Calculation: COUNT(failed operations)
Type: Integer (0+)
```

### total_count
```
Calculation: success_count + failure_count
Type: Integer (0+)
```

### error_rate
```
Calculation: failure_count / total_count (if total_count > 0, else 0)
Range: 0.0 to 1.0 (decimal, NOT percentage)
Example: 5 failures / 100 attempts = 0.05
```

### latency_ms
```
Source: venture_jobs.db → block_logs (timestamp deltas per operation)
Calculation: AVG(end_timestamp - start_timestamp) for this component
Type: Integer (milliseconds)
Range: 0+
```

### output_summary
```
Populated by: Python code after stage completion (hardcoded or log-based)
Format: Plain English summary, 1-2 sentences
Examples:
  - "3,240 companies found; 2,890 enriched; 250 scored"
  - "2,890 enriched profiles generated; 45 parse errors"
  - "250 prospects shortlisted; 18 below threshold"
Type: String
```

---

## Metrics Write Rule

```
✅ All metrics pre-calculated in Python
✅ Written once to run_report.json per run
✅ HTML is read-only (no calculations)
```

---

# 3. COMPONENT ERROR FIELD SPECIFICATION

## When to Set error.has_error = true

```
Condition: Component status = FAILED
Source: venture_jobs.db → block_logs (severity = 'HARD' or 'SOFT')
```

---

## error.error_type (REQUIRED)

```
Calculated from: block_logs.error_type
Valid values (enum):
  - "rate_limit"      (API rate limit hit)
  - "api_failure"     (API returned error)
  - "timeout"         (Operation exceeded timeout)
  - "auth_failure"    (Authentication/authorization failed)
  - "parsing_error"   (Data parsing/validation failed)
  - "unknown"         (Error type could not be determined)

Rule: Must be one of the above; no free-form strings
```

---

## error.error_message (REQUIRED)

```
Calculated from: block_logs.error_message
Format: First 200 characters of error string
Type: String
Example: "Hunter.io API returned 429: Rate limit exceeded (100/min)"
```

---

## error.retry_status (REQUIRED)

```
Calculated from: block_logs.retry_count and job_state.retry_scheduled_at

Valid values:
  "none"         → No retries attempted yet
  "scheduled"    → Retry queued, scheduled for < 1 hour
  "in_progress"  → Retry running right now
  "exhausted"    → Max retries reached, will not retry again

Logic:
  if retry_count == 0:
    retry_status = "none"
  else if retry_scheduled_at and retry_scheduled_at < (now + 1 hour):
    retry_status = "scheduled"
  else if retry_count > max_retries:
    retry_status = "exhausted"
  else:
    retry_status = "in_progress"
```

---

## When to Clear error (has_error = false)

```
Condition: Component status = COMPLETED
Action: Set error.has_error = false, clear all error.* fields
```

---

## Error Persistence Rule

```
Errors are KEPT in run_history (not deleted after successful retry)

Example run_history entry:
{
  "run_id": "cycle_9",
  "system_score": 75,
  "component_failures": {
    "stage_2_enrichment": {
      "has_error": false,  ← Success, but history shows...
      "prior_errors": ["rate_limit", "timeout", "rate_limit"]  ← ...it failed 3x before succeeding
    }
  }
}

Operator benefit: Can see "Stage 2 FAILED 3x, finally succeeded"
```

---

# 4. COMPONENT REGISTRY (SOURCE OF TRUTH)

## Location

```text
Embedded in HTML (JavaScript constant)
No external file. No backend lookup.
```

---

## Structure

```javascript
const COMPONENT_REGISTRY = {
  stage_1_prospecting: {
    name: "Finding Companies",
    input_source: "Apollo.io + Hunter.io + Web search APIs",
    processing_method: "Entity discovery + filtering",
    hard_dependencies: [],
    soft_dependencies: []
  },

  stage_2_enrichment: {
    name: "Company Intelligence Enrichment",
    input_source: "Stage 1 output",
    processing_method: "Website scraping + API enrichment",
    hard_dependencies: ["stage_1_prospecting"],
    soft_dependencies: []
  },

  stage_3_scoring: {
    name: "Filtering & Scoring Leads",
    input_source: "Stage 2 output",
    processing_method: "ICP matching + intent signals + maturity filters",
    hard_dependencies: ["stage_2_enrichment"],
    soft_dependencies: []
  }

  // ... stage 4-7
};
```

---

## RULES

* Registry is IMMUTABLE during runtime
* Only edited by developer (not pipeline)
* Component IDs NEVER change once defined
* Hard/soft dependencies are static per component

---

# 5. DEPENDENCY MODEL & FAILURE PROPAGATION

## Dependency Types

### Hard Dependency
```
If parent FAILED → child is BLOCKED (cannot execute)
Example: Stage 2 enrichment fails → Stage 3 scoring BLOCKED
```

### Soft Dependency
```
If parent FAILED → child runs using cached parent data
Result: Child marked DEGRADED (not FAILED)
Example: Stage 6 tracking fails → Stage 7 analytics runs with cached tracking data
```

---

## Component Status Calculation During Execution

**Responsibility: Python (venture_pipeline.py)**

Status is determined BEFORE/DURING execution, not in HTML.

```
After each component execution:

  if execution succeeded:
    component.status = "COMPLETED"
    component.error.has_error = false
    
  else if execution failed:
    component.status = "FAILED"
    component.error = { has_error: true, error_type: "...", ... }
    
  else if hard dependency parent FAILED:
    component.status = "BLOCKED"
    component.error.has_error = false  ← Not an error, just blocked
    (don't execute this component at all)
    
  else if soft dependency parent FAILED:
    component.status = "DEGRADED"
    component.error.has_error = false
    (execute with cached data)
    
  else if operator flagged for review:
    component.status = "NEEDS_REVIEW"
    component.error.has_error = false
```

---

## HTML Responsibility

```
✅ Read component.status from JSON
✅ Render visual state (no recalculation)
✅ Show propagation chain visualization:
   "Stage 2 FAILED → Stages 3,4,5,6,7 BLOCKED"
❌ Do NOT recalculate status
❌ Do NOT re-run dependency logic
```

---

# 6. STALENESS RULES + SCORING IMPACT

## Calculation

```text
staleness_minutes = (now - last_updated) in minutes
```

---

## Thresholds

| Condition  | State    | Score Impact | UI Visual |
| ---------- | -------- | ------------ | --------- |
| < 30 min   | OK       | Included     | Green     |
| 30–120 min | STALE    | Included     | Yellow    |
| > 6 hours  | UNKNOWN  | EXCLUDED     | Red       |
| > 24 hours | DISABLED | EXCLUDED     | Grayed    |

---

## Scoring Rule (CRITICAL)

When calculating system_score in Python:

```
execution_health = calculate_health_from_all_components()

BUT:
- If component.staleness_minutes > 360 (6 hours):
    Exclude from calculation
  
- If component.staleness_minutes > 1440 (24 hours):
    Ignore completely (as if component doesn't exist)

Example:
  Stage 1: OK (included)
  Stage 2: STALE (included)
  Stage 3: UNKNOWN (excluded)
  Stage 4: DISABLED (ignored)
  
  system_score = weighted_avg(Stage_1, Stage_2) × 100
  (Stages 3, 4 don't contribute)
```

---

## UI Display Rule

```
Component card shows staleness badge:
  < 30 min: No badge (normal green)
  30–120 min: Yellow "STALE" badge + timestamp
  > 6 hours: Red "UNKNOWN" badge
  > 24 hours: Gray "DISABLED" badge (dimmed entire card)

Operator can [Refresh Component] to force re-run.
```

---

# 7. SCORE DELTA & TREND DETECTION

## Previous Score Retrieval

```
To calculate delta:

current_score = (calculated in this run)
previous_score = run_history[-2].system_score (from JSON, second-to-last run)

delta = current_score - previous_score

if abs(delta) > 15:
  Trigger NEEDS_REVIEW flag for operator awareness
```

---

## Trend Visualization (Last 10 Runs)

```
Calculate from run_history array:

avg_3_runs = avg(run_history[-3:].system_score)
current = run_history[-1].system_score

if current > avg_3_runs:
  trend_label = "↑ IMPROVING"
  trend_color = green
  
else if current < (avg_3_runs - 10):
  trend_label = "↓ DEGRADING"
  trend_color = red
  
else:
  trend_label = "→ STABLE"
  trend_color = blue

Display: "Score: {current} {trend_label}"
```

---

## Score Delta Display (Operator View)

```
If delta >= 0:
  "Score: 78 ↑ +5pts" (green)

else:
  "Score: 72 ↓ -8pts" (red)

Condition: Show delta only if current run exists and previous run exists
```

---

# 8. RUN_HISTORY MANAGEMENT

## Location

```text
Inside run_report.json → run_history[]
(NOT a separate file)
```

---

## Data Structure

```json
{
  "run_id": "cycle_9",
  "timestamp": "2026-05-15T14:32:10Z",
  "system_score": 75,
  
  "execution_health": 22,
  "data_quality": 18,
  "messaging_health": 20,
  "infrastructure_health": 15
}
```

---

## Lifecycle (FIFO: First In, First Out)

```
1. Load previous run_report.json
2. Append current run metrics to run_history array
3. If run_history length > 10:
     Remove oldest entry (index 0)
4. Write updated run_report.json

Example:
  Before run 11: run_history has 10 entries [cycle_1...cycle_10]
  After run 11: append cycle_11 → [cycle_2...cycle_11] (cycle_1 deleted)
```

---

## Retention Rule

```
Keep ONLY last 10 runs
Old entries are DELETED (not archived)

Sufficient for:
  - 10-run trend visualization
  - Cycle-over-cycle comparison
  - Anomaly detection (runs trending down/up)
```

---

# 9. NEEDS_REVIEW STATE LOGIC

## Trigger Conditions (Choose ONE per use case)

### Option A — Score Anomaly (Default)

```
if abs(current_score - previous_score) > 15:
  component.status = "NEEDS_REVIEW"
  component.needs_review_reason = "Score jumped ±15 points"
```

---

### Option B — Manual Operator Flag

```
Operator clicks "Flag for Review" button in UI
  component.status = "NEEDS_REVIEW"
  component.needs_review_reason = "Operator flagged manually"
```

---

### Option C — Component-Specific Rule

```
Some components always require review:
  stage_4_message_generation.always_review = true

Hardcoded in COMPONENT_REGISTRY:

const COMPONENT_REGISTRY = {
  stage_4_message_generation: {
    name: "Generating Personalized Messages",
    always_review: true,
    ...
  }
}

If always_review: true:
  component.status = "NEEDS_REVIEW" after execution
```

---

## Approval/Rejection Workflow

| Operator Action | Result | Next State |
| --------------- | ------ | ---------- |
| Clicks [Approve] | Recorded in audit log | RUNNING |
| Clicks [Reject] | Recorded in audit log | PENDING (reset) |
| No action for 30 min | Auto-approve (configurable) | RUNNING |

---

## Audit Trail

```
component.approval_log = [
  {
    timestamp: "2026-05-15T14:32:10Z",
    operator: "human_email@example.com" or "system_auto",
    decision: "APPROVED" or "REJECTED",
    reason: "Operator comment (optional)"
  }
]
```

---

# 10. JSON FIELD → UI ELEMENT MAPPING

## run_report.json Structure (Complete)

```json
{
  "run_id": "cycle_9",
  "timestamp": "2026-05-15T14:32:10Z",
  "system_score": 75,
  
  "execution_health": 22,
  "data_quality": 18,
  "messaging_health": 20,
  "infrastructure_health": 15,
  
  "top_issues": [
    {
      "id": "stage_2_enrichment",
      "impact_score": 42,
      "description": "Hunter.io rate limit hit 3 times, affecting 890 enrichments"
    },
    {
      "id": "stage_4_personalization",
      "impact_score": 35,
      "description": "Low message variance detected (85% duplicate templates)"
    },
    {
      "id": "stage_5_delivery",
      "impact_score": 28,
      "description": "5 unconfirmed bounces; manual review needed"
    }
  ],
  
  "components": [
    {
      "id": "stage_1_prospecting",
      "name": "Finding Companies",
      "status": "COMPLETED",
      "last_updated": "2026-05-15T14:15:00Z",
      "staleness_minutes": 17,
      
      "input_source": "Apollo.io + Hunter.io + Web search APIs",
      "processing_method": "Entity discovery + filtering",
      
      "metrics": {
        "success_count": 3240,
        "failure_count": 2,
        "total_count": 3242,
        "error_rate": 0.0006,
        "latency_ms": 4521
      },
      
      "output_summary": "3,240 companies found",
      
      "risk_level": "LOW",
      
      "dependencies": {
        "hard": [],
        "soft": []
      },
      
      "error": {
        "has_error": false,
        "error_type": null,
        "error_message": null,
        "retry_status": null
      }
    },
    
    {
      "id": "stage_2_enrichment",
      "name": "Company Intelligence Enrichment",
      "status": "FAILED",
      "last_updated": "2026-05-15T14:20:00Z",
      "staleness_minutes": 12,
      
      "input_source": "Stage 1 output",
      "processing_method": "Website scraping + API enrichment",
      
      "metrics": {
        "success_count": 2890,
        "failure_count": 45,
        "total_count": 2935,
        "error_rate": 0.0153,
        "latency_ms": 6821
      },
      
      "output_summary": "2,890 enriched profiles; 45 failures",
      
      "risk_level": "HIGH",
      
      "dependencies": {
        "hard": ["stage_1_prospecting"],
        "soft": []
      },
      
      "error": {
        "has_error": true,
        "error_type": "rate_limit",
        "error_message": "Hunter.io: 100/min exceeded at 14:19:55",
        "retry_status": "scheduled"
      }
    }
    
    // ... stage 3-7
  ],
  
  "run_history": [
    {
      "run_id": "cycle_1",
      "timestamp": "2026-05-01T10:00:00Z",
      "system_score": 62,
      "execution_health": 18,
      "data_quality": 14,
      "messaging_health": 15,
      "infrastructure_health": 15
    },
    
    // ... cycle_2 through cycle_8 ...
    
    {
      "run_id": "cycle_9",
      "timestamp": "2026-05-15T14:32:10Z",
      "system_score": 75,
      "execution_health": 22,
      "data_quality": 18,
      "messaging_health": 20,
      "infrastructure_health": 15
    }
  ]
}
```

---

## UI Rendering Responsibility

### Python Calculates:
```
✅ system_score, 4 category scores
✅ top_issues (ranked by impact_score)
✅ all component metrics (from logs)
✅ component error fields
✅ component status (COMPLETED/FAILED/BLOCKED/etc)
✅ run_history (last 10)
```

### HTML Calculates On-Demand:
```
✅ Dependency graph visualization (from COMPONENT_REGISTRY + status)
✅ Failure propagation chain ("Stage 2 failed → 3,4,5,6,7 blocked")
✅ Trend direction ("IMPROVING" vs "DEGRADING")
✅ Trend visualization (arrows, line graph)
✅ Staleness badges (< 30 min / 30-120 min / > 6 hours / > 24 hours)
```

---

# 11. HTML DATA LOADING STRATEGY

## File Access Method

```text
fetch('./run_report.json')
```

---

## Load Behavior

### On Page Load

```javascript
fetch('./run_report.json')
  .then(r => r.json())
  .then(data => {
    renderOperatorView(data);
    renderClientView(data);
  })
  .catch(err => showErrorState("run_report.json not found"));
```

---

### Manual Refresh

```html
<button onclick="refreshData()">Refresh Now</button>

function refreshData() {
  fetch('./run_report.json?cache=' + Date.now())  // Bypass cache
    .then(r => r.json())
    .then(data => {
      updateDashboard(data);
      showNotification("Dashboard updated");
    })
    .catch(err => showErrorState("Cannot refresh: " + err.message));
}
```

---

## No Auto-Polling

```
❌ No setInterval() for auto-refresh
❌ No WebSocket streaming
❌ No background sync
```

User is responsible for clicking [Refresh Now] to get latest data.

---

## Error Handling

| Condition     | UI Response                                |
| ------------- | ------------------------------------------ |
| File missing  | "Run the pipeline to generate data"        |
| Invalid JSON  | "run_report.json is corrupted"             |
| Network error | "Cannot load system state; check network"  |
| Stale data    | "Data is 8h old; click Refresh for latest" |

---

# 12. FINAL CONTRACT SUMMARY

## What Python (venture_pipeline.py) MUST Do

```
✅ Calculate all component metrics from logs
✅ Determine component status (COMPLETED/FAILED/BLOCKED/DEGRADED/NEEDS_REVIEW)
✅ Populate error fields (type, message, retry_status)
✅ Calculate system_score + 4 category scores
✅ Identify top 3 issues (ranked by impact)
✅ Append to run_history (trim to 10)
✅ Write complete run_report.json
```

---

## What HTML (JavaScript) MUST Do

```
✅ Fetch run_report.json on page load
✅ Render components from JSON (read-only)
✅ Calculate dependency graph visualization
✅ Show failure propagation chain
✅ Display trend visualization
✅ Provide manual [Refresh Now] button
✅ Toggle between Operator and Client views
```

---

## What Agent SHOULD NOT Do

```
❌ Calculate scoring in JavaScript (pre-calculated in JSON)
❌ Determine component status (pre-determined in JSON)
❌ Build/populate error fields (pre-populated in JSON)
❌ Auto-poll for updates (user triggers manual refresh)
❌ Query databases (all data comes from run_report.json)
❌ Execute pipeline logic (that's venture_pipeline.py's job)
```

---

# 13. RESULT: FULLY DETERMINISTIC SYSTEM

With this bridge document, the agent can:

```
✅ Build HTML UI from deterministic JSON schema
✅ Implement state machine from explicit rules
✅ Visualize dependencies + failure propagation
✅ Render scoring breakdown without calculation
✅ Handle error fields unambiguously
✅ Manage component status without guessing
✅ Display run history trends correctly
✅ Provide debug info in < 2 minutes
```

---

# END OF BRIDGE DOCUMENT v2.0

**Status**: Ready for agent implementation

**Next step**: Hand this + Master Prompt to agent. No additional clarifications needed.
