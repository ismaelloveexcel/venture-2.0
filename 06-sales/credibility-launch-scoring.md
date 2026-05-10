# Credibility Launch Lead Scoring

Use this to decide send vs no-send. Do not score company age directly. Score buying pressure and visibility gap.

## Purpose

This is a pressure-first candidate filter plus a final LinkedIn verification gate for B2B trust-based selling.

Do not optimize for perfect precision yet. For the first 50-100 evaluated leads, use high recall with controlled quality:

- Candidate Pool / Signal Lab: high-motion companies that may deserve LinkedIn inspection
- Send Pool: verified credibility-gap leads only

Pipeline order:

```text
spend trigger filter -> motion signal detection -> revenue model classification -> distribution gap scoring -> urgency proxy scoring -> binary LinkedIn check
```

Do not use LinkedIn as a discovery source. Use LinkedIn only as the final binary verification gate.

## Decision Semantics v1

Operational routing uses motion class, not fit score:

- `SPEND_ELIGIBLE + HOT` -> send candidate lane (subject to LinkedIn weak/missing + safety gate)
- `SPEND_ELIGIBLE + POSSIBLE` -> test lane
- all others -> discard/log only

`fit_score` remains in schema as a diagnostic field for backward compatibility and analytics.

Spend eligibility is a hard gate that must pass before HOT can route to send.

## Spend Trigger Layer (Hard Signals)

At least one hard spend trigger must be observed:

- tool transition
- failed internal build
- budget release
- execution bottleneck
- partner/agency switching

These are detection signals, not schema fields. They are written into `notes` and shadow logs.

## Message Angle Mapping

Message angle should be selected by spend trigger type:

| Spend Trigger | Message Angle |
|---|---|
| tool transition | replacement positioning |
| failed internal build | execution relief |
| budget release | scaling acceleration |
| execution bottleneck | operational unblock |
| partner switch | efficiency / cost reduction |

## Buying Intensity Score (0-11)

Compute internally before LinkedIn verification:

$$
Buying\_Intensity\_Score =
Hiring\_Intent\;(0\!\!\text{-}\!3) +
Founder\_Growth\_Signal\;(0\!\!\text{-}\!3) +
Revenue\_Model\_Pressure\;(0\!\!\text{-}\!2) +
Distribution\_Gap\;(0\!\!\text{-}\!3)
$$

Map to handling:

| Buying Intensity | Action |
|---:|---|
| 0-4 | Discard |
| 5-6 | Signal Lab |
| 7-9 | Send Pool candidate |
| 10-11 | Priority send candidate |

Convert to an integer motion score for routing:

$$
motion\_score \in [0,10]
$$

The generator derives `motion_class` from configured thresholds and stores both in `notes`.

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

## Score Components

### 1) Hiring Intent (0-3)

Count only hiring tied to revenue generation:

- sales
- growth
- marketing
- SDR/BDR
- RevOps

Do not reward engineering/product-only hiring.

### 2) Founder Growth Signal (0-3)

Reward explicit growth push language, for example:

- scaling
- need more leads
- expanding pipeline
- looking for clients

### 3) Revenue Model Pressure (0-2)

Prioritize business models where pipeline inconsistency hurts quickly:

- agency
- MSP
- consultancy
- B2B service firm
- founder-led sales org

### 4) Distribution Gap (0-3)

Highest score when:

- website is professional and offer is clear
- outbound/inbound distribution footprint is weak or absent
- LinkedIn quality has not been scored yet (still unknown until binary check)

Top-ranked rows go to Signal Lab with `linkedin_quality=unknown`. Inspect only top 20% manually.

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
| 7-8 | Strong enough fit with observed pressure type | Send |
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

## Allowed Triggers (Pressure Types)

Use one pressure type:

- `revenue_pressure`
- `scaling_pressure`
- `acquisition_pressure`
- `visibility_pressure`
- `talent_pressure`

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