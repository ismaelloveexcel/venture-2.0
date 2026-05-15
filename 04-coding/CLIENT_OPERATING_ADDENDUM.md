# Client Operating Addendum (Governed Outbound)

This addendum applies to all governed outbound pilot engagements.

## 1) Stop-loss and pause authority

- Operator may pause outbound immediately when stop-loss conditions trigger.
- Stop-loss triggers include governance integrity violations, deliverability risk, or data-integrity failures.
- Pauses are protective controls, not performance defaults.

## 2) SLA as system input

- Client response SLA (24-48h) is required for reliable outcome attribution.
- Missed SLA may move campaign state to amber/red and can pause scaling decisions.

## 3) Decision cadence

- Weekly decision brief is mandatory.
- Allowed decisions: `persist`, `single-variable pivot`, `pause`.
- Multi-variable pivots in one cycle are not allowed.

## 4) Data integrity

- Prospect and outreach schema fields must remain complete and auditable.
- Qualified conversation claims require verifier fields:
  - ICP fit
  - Buyer role
  - Next step

## 5) Scaling constraint

- Volume scaling is blocked when governance integrity fails, regardless of short-term outcomes.

## 6) Override policy

- Any gate override must be logged with reason and timestamp.
- Repeated unlogged overrides are treated as system failure and trigger reset.
