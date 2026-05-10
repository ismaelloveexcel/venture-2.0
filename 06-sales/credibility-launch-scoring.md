# Credibility Launch Lead Scoring

Use this to decide send vs no-send. Do not score company age directly. Score the moment of visibility gap.

## Purpose

This is a motion-first candidate filter plus a final LinkedIn verification gate for B2B trust-based selling.

Do not optimize for perfect precision yet. For the first 50-100 evaluated leads, use high recall with controlled quality:

- Candidate Pool / Signal Lab: high-motion companies that may deserve LinkedIn inspection
- Send Pool: verified credibility-gap leads only

Pipeline order:

```text
structured source export -> motion pre-score -> Signal Lab shortlist -> binary LinkedIn check -> Send Pool
```

Do not use LinkedIn as a discovery source. Use LinkedIn only as the final binary verification gate.

## Send-Ready Rule

A row is send-ready only if all are true:

- Website is filled and checked
- First name is correct
- Role is founder, owner, managing director, partner, or CEO
- LinkedIn URL is confirmed
- LinkedIn company presence is verified weak or missing, not merely unchecked
- Trigger is observed, not assumed
- `fit_score >= 7`

If any required field is missing, do not send.

## Motion Pre-Score

Use motion pre-score before any LinkedIn inspection. This score answers: "is this company in motion right now?"

| Proxy Signal | Points |
|---|---:|
| Founder-led decision-maker is visible in source data | 2 |
| B2B service, SaaS, enterprise, professional, legal, accounting, staffing, or sales category | 2 |
| 2-20 employees | 1 |
| Hiring signal or open jobs | 2 |
| YC / launch / demo-day / Product Hunt signal | 2 |
| Funding or credible growth news | 2 |
| Founder visibility or building publicly signal | 1 |
| Website present | 1 |
| Strong website quality proxy | 1 |

Top-ranked rows go to Signal Lab with `linkedin_quality=unknown`. Only inspect the top 20% manually.

## 0-10 Fit Score After LinkedIn Verification

Start at 0. Add points only for observed evidence.

| Signal | Points |
|---|---:|
| Founder-led B2B service or SaaS business | 2 |
| 2-20 employees | 1 |
| Website is strong or clearly better than verified LinkedIn presence | 2 |
| LinkedIn company page is verified weak, missing, inactive, or generic | 2 |
| Founder is active, selling, posting, hiring, launching, or visibly building | 2 |
| Clear service offer and likely need for prospect trust | 1 |

## Decision

Do not score missing validation as opportunity. LinkedIn status is not part of discovery scoring and must be classified before a lead can become send-ready:

| LinkedIn Status | Meaning | Action |
|---|---|---|
| `weak` | Company page is verified weak, inactive, generic, underbuilt, or absent after checking | Send Pool candidate if the rest of the score supports it |
| `unknown` | Company LinkedIn has not been checked directly, or the available source only lists/omits a page | Signal Lab only |
| `strong` | Active company brand/content presence already exists | Delete for this offer |

Use `linkedin_quality=unknown` for motion-qualified discovery rows where the company looks interesting but the LinkedIn gap is not verified. Use `weak` or `missing` only after direct verification.

| Score | Meaning | Action |
|---:|---|---|
| 9-10 | Perfect ICP plus clear growth pressure and credibility gap | Priority send |
| 7-8 | Strong enough fit with observed trigger | Send |
| 5-6 | Interesting but unclear or incomplete signal | Signal Lab only |
| 0-4 | Weak or guessy | Delete |

## Signal Lab

Use [credibility-launch-signal-lab.csv](credibility-launch-signal-lab.csv) for leads scoring 5-6.

Signal Lab leads are not send-ready. Treat this as the Candidate Pool: a triage queue of motion-qualified companies, not a credibility-gap database.

Use Signal Lab when a company has:

- Strong company but weak or unclear timing signal
- Unknown LinkedIn status that still needs direct verification
- Borderline LinkedIn weakness after a direct check
- Good website but unclear founder presence
- Generic small agency with no visible motion
- Plausible service fit but incomplete evidence

Do not send Signal Lab leads until they are revalidated and rescored to 7+.

Use `04-coding/scripts/credibility_candidate_generator.py` to populate Signal Lab from structured source exports such as YC, Wellfound, job boards, or funding/news sheets. Start from [credibility-candidate-source-template.csv](credibility-candidate-source-template.csv).

## Allowed Triggers

Use one observed trigger:

- `recently_launched`
- `rebranded`
- `hiring`
- `founder_posting`
- `recent_growth`
- `clear_service_offer`
- `website_stronger_than_linkedin`
- `weak_linkedin`

Bad trigger: `probably weak`.

Bad scoring: treating `not checked yet` as `weak`.

Good trigger notes:

- `no company page found`
- `last visible post appears old`
- `bio generic; website positioning stronger`
- `founder active but company page underbuilt`
- `hiring/growth signal but weak credibility layer`
- `linkedin_status=unknown; direct company page review required`

## True Gap Signals

Strong signals, usually score drivers for 7-10:

- Hiring sales, growth, marketing, or revenue roles
- Founder posting recently, within roughly 30-60 days
- New launch or rebrand
- Clear offer but weak LinkedIn/company page
- Visible inbound demand but weak distribution
- Team growing but no content footprint

Weak signals, usually score drivers for 4-6:

- Generic small agency
- Decent website but no activity signal
- Unclear founder presence
- Static company with no visible motion

## Segments

Tier 1: recently active founders building publicly. Best for first sends.

Tier 2: established but invisible online. Good, but slower.

Tier 3: idea-stage or no visible traction. Avoid.