# Operator Execution Sheet v1

This is the live 14-day protocol for early-stage venture lead generation.
No design changes during this cycle.

## Scope and constraints

- Max active pilots: `2`
- One ICP slice per pilot
- One outbound channel per pilot
- One variable change per pivot window (no exceptions)
- Duration: `14` calendar days

## Two-gate decision model

### Gate A: Governance integrity (system health)

Track daily:
- Pivot compliance (`Y/N`) - one variable only
- SLA compliance (`Y/N`) - client and operator response in agreed window
- Stop-loss compliance (`Y/N`) - no unlogged overrides
- Deliverability compliance (`Y/N`) - no ignored risk events
- Schema completeness (`0-100`) - required fields present in prospect + outreach + report artifacts

### Gate B: Market outcome (commercial signal)

Track daily:
- Delivered volume
- Positive replies
- Qualified conversations
- Meeting quality (high/medium/low), optional but recommended

## Frozen definitions for this cycle

- `Positive reply`: Any reply expressing interest, fit check, or next-step intent.
- `Qualified conversation`: Conversation with an ICP-fit contact that reaches a commercially relevant next step (problem context + authority or buying role + willingness to continue).
- `Stop-loss trigger`: Any pre-defined hard-fail event in this protocol; sends pause immediately.

Do not redefine terms during the 14-day run.

## Daily operating checklist

1. Run pipeline command (dry-run for safety rehearsal, live for approved pilots):
   - Dry-run full stack:
     - `python 04-coding/scripts/run_daily.py --generate-prospects --prospects-demo --execute-outbound --dry-run`
   - Live stack (only for approved pilot execution):
     - `python 04-coding/scripts/run_daily.py --generate-prospects --execute-outbound`
2. Verify `run_report.json` exists and records current `run_id`.
3. Log governance fields and outcome fields in the daily sheet.
4. If any stop-loss condition is hit, apply rollback immediately.

## Stop-loss conditions (hard)

Trigger immediate pause if any is true:
- Governance compliance < `80%` for a day
- 2 unlogged gate overrides in rolling 7 days
- Multi-variable pivot in one window
- Sends continue after a triggered stop-loss
- Schema completeness < `95%`

## Rollback protocol (hard)

When stop-loss triggers:
- Reduce volume by `50%`
- Revert to manual approval path
- Require `5` consecutive stable days before normal volume resumes

## Weekly pass/fail logic

Weekly pass requires both gates:

### Gate A threshold
- Governance integrity >= `90%` across weekly logs

### Gate B threshold
- At least one:
  - Non-zero qualified conversations
  - Positive reply rate above baseline threshold for that ICP/channel

If Gate A fails:
- System reset (do not optimize messaging first)

If Gate B fails for 2 consecutive evaluation windows:
- Treat ICP/offer/channel combo as invalid; pivot single variable only

If both fail:
- Stop current test and redesign inputs before resuming

## Google Sheets columns (copy/paste)

Use one row per day per pilot:

```text
date,pilot_id,client_name,icp_slice,channel,run_id,delivered_count,positive_replies,qualified_conversations,qualified_icp_fit,qualified_buyer_role,qualified_next_step,meeting_quality_notes,pivot_variable,pivot_compliant,sla_client_compliant,sla_operator_compliant,stop_loss_compliant,deliverability_compliant,schema_completeness_pct,gate_overrides_logged,stop_loss_triggered,action_taken
```

### Formula suggestions

- Governance score (%):
  - Average of boolean governance checks + normalized schema completeness
- Positive reply rate:
  - `positive_replies / delivered_count`
- Gate A pass:
  - `governance_score >= 0.90`
- Gate B pass:
  - `(qualified_conversations > 0) OR (positive_reply_rate >= baseline)`

## Weekly decision brief template (required)

Use this exact structure:

1. What changed this week (single-variable pivots only)
2. Gate A result (score + violations)
3. Gate B result (qualified conversations + reply rate vs baseline)
4. Decision (`persist`, `single-variable pivot`, `pause`)
5. Rationale in one paragraph (no narrative padding)

## Non-negotiable operating rule

Do not scale volume when Gate A fails, even if Gate B looks good.
