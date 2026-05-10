# Credibility Launch System

Status: locked for validation. Do not refine before the first 50 sends.

## Offer

Make your company look credible, active, and sales-ready before prospects check you.
Delivered in 72 hours.

## ICP

Founder-led B2B service firms with:

- 2-20 employees
- Decent website
- Weak or underbuilt LinkedIn presence
- Founder still involved in sales

Hard exclusions:

- Freelancers
- Influencers or coaches
- Consumer brands
- Ecommerce
- Companies with already strong LinkedIn presence

## Scope

- LinkedIn company page rebuild: positioning and structure
- Founder profile polish: headline, about section, positioning
- Messaging alignment: what they do and who it is for
- Visual cleanup: banner direction and consistency
- First content set: 3-5 posts
- Prospect-view audit: what a buyer sees before replying

## Pricing

- Lite: GBP 500-700, profile and positioning only
- Core: GBP 1,000-1,500, full system and content

No custom tiers during validation.

## Lead Qualification: 60-Second Rule

Use a pressure-first filter before any LinkedIn review:

```text
motion signal detection -> revenue model classification -> distribution gap scoring -> urgency proxy scoring -> binary LinkedIn check
```

LinkedIn is a verification tool, not a discovery tool. Inspect only the top-ranked motion candidates, usually the top 20% of a batch.

For each company, confirm:

- Website is solid
- LinkedIn company page is weak, missing, inactive, or underbuilt
- Founder is visible and plausibly involved in sales
- The company is actively trying to grow or look credible now

The filter is not company age. It is moment of visibility gap:

```text
new or established + active growth pressure + underdeveloped credibility layer
```

Primary pressure types:

- Revenue pressure
- Scaling pressure
- Acquisition pressure
- Visibility pressure
- Talent pressure

Avoid idea-stage companies with no team, no traction, or no visible growth pressure.

## Pre-Send Decision Table

Use [credibility-launch-leads.csv](credibility-launch-leads.csv) as the only review table.

Use [credibility-launch-signal-lab.csv](credibility-launch-signal-lab.csv) for borderline 5-6 score learning leads. Do not send Signal Lab rows.

Columns are locked to:

```text
company
website
first_name
role
industry
employee_count
location
trigger
linkedin_url
website_quality
linkedin_quality
fit_score
message_version
service_angle
status
notes
```

Allowed values:

- `trigger`: `revenue_pressure`, `scaling_pressure`, `acquisition_pressure`, `visibility_pressure`, `talent_pressure`
- `website_quality`: `strong`, `average`, `weak`
- `linkedin_quality`: `unknown`, `strong`, `weak`, `missing`
- `fit_score`: `0` to `10`
- `message_version`: `credibility_v1`
- `service_angle`: `credibility_gap`, `linkedin_rebuild`, `founder_positioning`, `content_start`
- `status`: `VALIDATED`, `SENT`, `REPLIED`, `CLOSED`, `LEARNING`

Use [credibility-launch-scoring.md](credibility-launch-scoring.md) to assign `fit_score`.

LinkedIn presence must be verified before scoring a send opportunity:

| LinkedIn status | Meaning | Action |
|---|---|---|
| `unknown` | Not directly checked yet | Signal Lab only |
| `weak` | Verified weak, inactive, generic, underbuilt, or absent | Send Pool candidate |
| `strong` | Active company brand/content presence exists | Discard for this offer |

Send only rows with `fit_score >= 7` after human review confirms the website, verified weak or missing LinkedIn presence, founder, and contact details. Do not score uncertainty as opportunity.

Put rows with `fit_score` of `5` or `6` into Signal Lab with `status=LEARNING`. These are for pattern discovery, not outreach.

To generate a pre-filtered Signal Lab batch from a structured export, use:

```powershell
.\.venv\Scripts\python.exe .\04-coding\scripts\credibility_candidate_generator.py --input .\06-sales\credibility-candidate-source-template.csv
```

The generator scores buying pressure proxies only and writes `linkedin_quality=unknown`. No generated row is send-ready until the LinkedIn check is completed manually and classified as weak or missing.

If automated lead generation is added, it must output [credibility-launch-lead-schema.json](credibility-launch-lead-schema.json).

## Initial Outreach

Subject: quick one

```text
Hi {{first_name}},

Quick one - {{company}} looks solid, but your LinkedIn presence doesn't yet reflect the quality of the offer.

That can quietly hurt trust when prospects check you before replying or booking.

I help founder-led B2B service firms fix that in 72 hours: positioning, profile cleanup, and first content so the company looks credible and active.

Want me to send the 3 things I'd change for {{company}}?

Best,
Ismael Sudally
ReplyPilot AI
```

Use one version only until 50 sends are complete.

## Positive Reply Response

```text
Sure - quick look:

1. [one positioning gap]
2. [one credibility gap]
3. [one content/activity gap]

Happy to walk you through how I'd fix this in 72 hours - does a 15-min call work this week?
```

Keep this manual. Do not systemize before there is reply signal.

## Call Objective

Diagnose the trust gap, show the credibility gap, position the Core offer, and close GBP 1,000-1,500.

Transition line into the main offer:

```text
Fixing LinkedIn improves trust.

But the real constraint is still predictable conversations.

That's where the outbound system comes in.
```

## Daily Loop

Build 20, send 20, process replies.

Time cap: 90 minutes per batch.

## Success Criteria

After 50 sends:

- 3-8 replies: signal exists
- 1-3 calls: viable
- 0 calls: reposition or kill

## Do Not Do

- Do not add Instagram by default
- Do not sell social media management
- Do not offer free audits beyond 3 bullets
- Do not customize heavily per lead
- Do not add links in the first email
- Do not over-explain the service

## Strategic Role

This is a front-end wedge, not the core business.

Credibility Launch, then outbound system, then ongoing ops.