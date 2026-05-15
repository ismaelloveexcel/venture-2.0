# Campaign Reconstruction Report

**Purpose:** Show a prospect or operator exactly what happened in a campaign—one readable artifact.  
**Status:** SAMPLE DATA ONLY — replace every `SAMPLE_*` field with production exports.

---

## Campaign Overview

| Field | SAMPLE value |
|--------|----------------|
| Campaign / cohort ID | `SAMPLE_COHORT_2026_01` |
| Date range | `SAMPLE_START` → `SAMPLE_END` |
| Channel | `SAMPLE_EMAIL` |
| Owner / operator | `SAMPLE_OPERATOR_NAME` |
| Objective (one line) | `SAMPLE_OBJECTIVE_LINE` |

---

## Prospect Eligibility Log

*Who was allowed into the campaign and why.*

| Prospect ID | Company | Email (redacted) | Eligibility decision | Reason / rule set | Timestamp (UTC) |
|-------------|---------|------------------|------------------------|-------------------|-----------------|
| `SAMPLE_P001` | `SAMPLE_CO_A` | `f***@sample-agency.io` | ELIGIBLE | `SAMPLE_RULE_PACK_V1` | `SAMPLE_TS_1` |
| `SAMPLE_P002` | `SAMPLE_CO_B` | `j***@sample-outbound.co` | ELIGIBLE | `SAMPLE_RULE_PACK_V1` | `SAMPLE_TS_2` |
| `SAMPLE_P003` | `SAMPLE_CO_C` | — | NOT ELIGIBLE | `SAMPLE_SUPPRESSION_DOMAIN` | `SAMPLE_TS_3` |

---

## Send Log

*What sent, when, to whom (operational truth).*

| Send ID | Timestamp (UTC) | Recipient | Subject fingerprint | Message hash | Provider status | Batch / lock ref |
|---------|-----------------|-----------|----------------------|--------------|-----------------|------------------|
| `SAMPLE_S001` | `SAMPLE_TS_S1` | `SAMPLE_EMAIL_A` | `SAMPLE_SUBJ_FP` | `SAMPLE_MSG_HASH_1` | `SAMPLE_SENT` | `SAMPLE_LOCK_ID` |
| `SAMPLE_S002` | `SAMPLE_TS_S2` | `SAMPLE_EMAIL_B` | `SAMPLE_SUBJ_FP` | `SAMPLE_MSG_HASH_2` | `SAMPLE_SENT` | `SAMPLE_LOCK_ID` |

---

## Decision Trail

*Why each contacted prospect was in scope (human + system).*

| Prospect ID | Decision | Approver | Notes | Timestamp (UTC) |
|-------------|----------|----------|-------|-------------------|
| `SAMPLE_P001` | APPROVED_SEND | `SAMPLE_OPERATOR` | `SAMPLE_NOTE_ICP_MATCH` | `SAMPLE_TS_D1` |
| `SAMPLE_P002` | APPROVED_SEND | `SAMPLE_OPERATOR` | `SAMPLE_NOTE_REVIEW_OK` | `SAMPLE_TS_D2` |

---

## Outcome Summary

| Metric | SAMPLE value |
|--------|----------------|
| Planned sends | `SAMPLE_N_PLANNED` |
| Confirmed sent | `SAMPLE_N_SENT` |
| Replies (tracked) | `SAMPLE_N_REPLIES` |
| Unsubscribe / complaint | `SAMPLE_N_COMPLAINTS` |
| Open questions | `SAMPLE_FOLLOWUPS` |

---

*Attach: raw CSV exports from your tooling (redacted), plus `run_report.json` excerpt if using Venture OS.*
