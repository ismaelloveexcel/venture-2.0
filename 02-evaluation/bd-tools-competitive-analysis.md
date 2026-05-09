# BD / sales intelligence tools — reference matrix

**Purpose:** Quick comparison of common platforms when you are building a **personal, composable outbound stack** (this repo) instead of buying a single vertical SaaS product.

Horizontal tools excel at breadth, CRM integrations, and scale. A custom stack adds **your** signals, workflows, and guardrails in code—see [venture-implementation-notes.md](../04-coding/venture-implementation-notes.md).

---

## 1. Scoring models

| Tool | Primary scoring dimensions | Uniqueness | Limitation |
|------|---------------------------|-----------|-----------|
| **ZoomInfo** | Firmographic + technographic + intent + revenue potential | AI prioritization; buying-committee views | Generic industries; you bring niche logic |
| **Apollo.io** | Company fit + intent + engagement + growth stage | Tied to outreach workflows | Coarse vs. role-specific nuance you encode yourself |
| **Seamless.ai** | Job changes + revenue growth + buying intent (100+ data points) | Real-time behavioral triggers | Broad intent topics |
| **RocketReach** | Technographics + intent + company stage | Stack mapping | Limited behavioral personalization |
| **Clearbit** | Role/seniority + industry (NAICS) + IP intent | Visitor intent | Passive vs. active buying behavior |
| **Salesforce** | Pipeline stage + forecast + custom weights | Highly customizable | Needs CRM discipline + enrichment |
| **Hunter.io** | Email verification + deliverability | Email quality | No full-funnel scoring |

**Custom stack gap (you fill):** Niche triggers, proprietary lists, and rules live in your configs and scripts—not in the vendor’s default model.

---

## 2. Contact intelligence

| Tool | Contact coverage | Decision-maker discovery | Job change tracking | Verification |
|------|-----------------|-------------------------|--------------------|--------------|
| **ZoomInfo** | Large global verified set | Org charts + buying groups | Exec moves | High |
| **Seamless.ai** | 1.6B+ emails, 448M+ phones | Rich profiles | Real-time alerts | Strong guarantees |
| **Apollo.io** | 230M+ contacts | Verified email + phone | Yes | High |
| **RocketReach** | 700M profiles | LinkedIn mapping | Alerts | 90–98% deliverability claim |
| **Hunter.io** | Domain + bulk | Company-wide domain search | Not core | High for email |
| **Clearbit** | Contact + account | Enrichment-led | Via API | High |
| **Salesforce** | CRM records | Manual + apps | Not native | Source-dependent |

---

## 3. Account intelligence

| Tool | Growth signals | Funding/news | Tech stack | Buying intent | Custom industry |
|------|---------------|--------------|------------|----------------|-----------------|
| **ZoomInfo** | Headcount, revenue | Funding, M&A, news | Technographics | Committee alerts | Firmographics |
| **Seamless.ai** | Revenue, employees | Funding + research | Tech detection | Many intent topics | Growth indicators |
| **Apollo.io** | Stage + growth | News | Limited | Intent signals | Size/stage tiers |
| **RocketReach** | Financials + stage | News + funding | Technographics | Emerging | Limited |
| **Clearbit** | Hierarchy, headcount | News | IP intelligence | Web intent | NAICS/GICS/SIC |
| **Salesforce** | CRM-logged | Integrations | Integrations | Custom | Custom |
| **Hunter.io** | — | — | — | — | — |

---

## 4. Personalization signals (outreach context)

| Tool | Press/news | Hiring | Partnerships | Financial events | Launches | Custom |
|------|------------|--------|--------------|------------------|----------|--------|
| **ZoomInfo** | ✓ | ✓ Org changes | ✓ | △ Funding-heavy | ✓ | △ Setup |
| **Seamless.ai** | ✓ Research | ✓ | ✓ | △ Growth | ✓ | ✓ Intent topics |
| **Apollo.io** | ✓ | ✓ | ✓ | △ | △ | △ |
| **RocketReach** | ✓ | ✓ | ✓ | △ | △ | △ |
| **Clearbit** | ✓ | ✓ Headcount | ✓ | ✓ Funding | △ | △ |
| **Salesforce** | Via integrations | Via integrations | Via integrations | Via integrations | Via integrations | ✓ |
| **Hunter.io** | — | — | — | — | — | — |

---

## 5. Outreach features

| Tool | Templates | Sequences | AI drafting | Warm intros | Multi-channel | Response tracking |
|-----|-----------|-----------|------------|-------------|---------------|-------------------|
| **Apollo.io** | ✓ + AI | ✓ Workflows | ✓ | △ | ✓ Email + LI | ✓ |
| **Seamless.ai** | ✓ | ✓ Automation | ✓ | △ | ✓ | ✓ |
| **ZoomInfo** | ✓ | Via Outreach/Salesloft | ✓ Copilot | ✓ | ✓ | ✓ |
| **Salesforce** | ✓ | Einstein | ✓ | △ | ✓ | ✓ |
| **RocketReach** | ✓ | ✓ Autopilot | ✓ | ✗ | ✓ Limited | ✓ |
| **Hunter.io** | ✓ | ✓ | △ | ✗ | ✓ Email | ✓ |

---

## 6. Integrations

| Tool | Salesforce | HubSpot | Outreach/Salesloft | Slack | Zapier | API |
|-----|-----------|---------|-------------------|-------|--------|-----|
| **Apollo.io** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ Full |
| **ZoomInfo** | ✓ | ✓ | ✓ | ✓ | ✓ | △ Limited |
| **Seamless.ai** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ Full |
| **Salesforce** | N/A | — | ✓ | ✓ | ✗ | ✓ |
| **RocketReach** | ✓ | ✓ | △ | △ Zapier | ✓ | ✓ |
| **Hunter.io** | ✓ | ✓ | △ | △ | ✓ | ✓ |
| **Clearbit** | ✓ | ✓ | △ | △ | ✓ | ✓ |

---

## 7. Analytics & reporting

| Tool | Email metrics | Segment reply rates | Call insights | Deal velocity | Dashboards | AI summaries |
|-----|--------------|---------------------|---------------|---------------|------------|--------------|
| **Apollo.io** | ✓ | ✓ | △ Integrations | ✓ | ✓ Basic | △ |
| **ZoomInfo** | ✓ | ✓ Intent | ✓ Copilot | ✓ | ✓ GTM Studio | ✓ |
| **Seamless.ai** | ✓ | ✓ Intent | ✓ | ✓ | ✓ | ✓ Agent |
| **Salesforce** | △ Einstein | ✓ | ✓ Gong etc. | ✓ | ✓ Tableau | ✓ Einstein |
| **RocketReach** | ✓ | △ | ✗ | △ | ✓ Basic | ✗ |
| **Hunter.io** | ✓ | △ | ✗ | ✗ | ✓ Basic | ✗ |
| **Databox** | Aggregates | ✓ | ✗ | ✓ Queries | ✓ Templates | ✓ |

---

## Best-in-class by dimension (opinionated)

| Dimension | Strong options | Notes for a custom stack |
|-----------|------------------|---------------------------|
| Scoring | ZoomInfo, Seamless | You own niche features + weights in code/config |
| Contact intel | Seamless, Apollo | Often pair with Hunter for email-only workflows |
| Account intel | ZoomInfo, Seamless | Augment with your own research + CSVs |
| Personalization data | Seamless, ZoomInfo | Pipeline logs + webhook events close the loop locally |
| Outreach | Apollo | This repo adds gates, queue, and replayable lifecycle |
| Integrations | Apollo, Seamless | Airtable/Notion/webhooks as lightweight CRM |
| Analytics | ZoomInfo, Salesforce, Databox | `funnel_health_snapshots` + your BI of choice |

---

## Pricing (indicative — verify with vendors)

| Tool | Model | Typical cost | Best for |
|------|-------|--------------|----------|
| **Apollo.io** | Per user/mo | $49–120/user | SMB/mid-market outbound |
| **ZoomInfo** | Enterprise | $2K–10K/mo (quoted) | Enterprise ABM |
| **Seamless.ai** | User + credits | $100–500/user | High-volume outbound |
| **Salesforce Sales Cloud** | Per user/mo | $25–350/user | Teams already on SF |
| **RocketReach** | User + credits | $99–300/user | Contact discovery |
| **Hunter.io** | Free + usage | ~$99–500/mo team | Lean email workflows |
| **Clearbit** | API credits | $200–1K/mo | Marketing enrichment |
| **Databox** | Per user/mo | $199–999/mo | Centralized KPI views |

---

## This workspace (Venture OS)

You are not positioning a separate commercial “vertical BD” product here. **Venture OS** composes APIs (e.g. Hunter, OpenAI, Resend), JSON contracts under `04-coding/venture-engine/config/`, and Python scripts with SQLite state. For architecture and ops details, start at the repository [README](../README.md).

---

## Appendix

Detailed numeric-style scoring: [bd-tools-scoring-matrix.csv](bd-tools-scoring-matrix.csv).

*Research refreshed: May 2026 — neutral reference for personal tooling.*
