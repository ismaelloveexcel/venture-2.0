# Operator launch readiness — Auditbound / Venture OS

Use this checklist **before** the first live cohort send. Mark items `[x]` only when verified.  
`launch_day_executor.py --outbound-go` (live) treats any remaining `- [ ]` item as a **preflight failure** unless you pass `--skip-checklist` (emergency only).

---

## A. DNS and SPF / DKIM / DMARC (abtmail.co)

- [ ] Add SPF record to abtmail.co DNS: `v=spf1 include:sendingdomain.resend.dev ~all`
- [ ] Add DKIM record to abtmail.co DNS (copy values from Resend dashboard for this domain)
- [ ] Add DMARC record: `v=DMARC1; p=quarantine; rua=mailto:dmarc@abtmail.co`
- [ ] Test SPF, DKIM, and DMARC at [MXToolbox](https://mxtoolbox.com) (or equivalent) — all green before live send

---

## B. Inbox placement testing (use your Calendly booking email as the test recipient)

- [ ] Gmail inbox (desktop, mobile, dark mode) — check preview div, body, footer links
- [ ] Gmail Promotions tab — if mail lands here, adjust sender, subject, or body copy and retest
- [ ] Outlook inbox — same checks
- [ ] Proton inbox — same checks
- [ ] iCloud inbox — same checks
- [ ] Spam folder test — send to a disposable / test inbox; confirm message is **not** caught as spam
- [ ] Reply test — confirm you can reply to the test thread and threading looks correct

---

## C. Service configuration

- [ ] Calendly: production URL is set in `EMAIL_SIGNATURE_HTML` (not a staging link)
- [ ] Calendly: time zone matches the operator’s time zone
- [ ] Resend: sending domain verified in Resend; track warmup in `.env` (e.g. `DOMAIN_WARMUP_STAGE=cold` for a new domain)
- [ ] `.env`: `SEND_HOURLY_CAP` and `SEND_DAILY_CAP` set to planned rates (example: 6/hr, 40/day)
- [ ] `.env`: `ENABLE_SUPPRESSION_CHECKS=true`
- [ ] `.env`: `ENABLE_LIST_UNSUBSCRIBE=true` (when policy requires it)
- [ ] `.env`: `ALLOW_OPERATOR_OVERRIDE=false` (safety lock for launch window)

---

## Sign-off

When every item above is `[x]`, run:

`python 04-coding/scripts/preflight_safety_check.py --quick` (expect VERDICT: PASS with your real `.env`),

then a final rehearsal:

`python 04-coding/scripts/launch_day_executor.py --outbound-go --dry-run`

Then proceed per `LAUNCH_DAY_2026-05-18_FINAL_RUNBOOK.md`.
