# 🧭 Signal Interpretation Map — Days 8–14

**Purpose:** When you see early results, immediately know which layer to fix (not "rebuild everything")

**Rule:** Do NOT change anything until ≥50 sends are complete OR failure pattern is consistent across ≥2 independent cycles

---

## The Four Failure Modes

### 🔴 MODE A: Low Reply Rate (<2% on 50 sends)

**What you'll see:**
- Sent 50 messages
- Got 0–1 replies
- (Pipeline is working, no errors)

**What this means:**
- ICP is wrong (targeting wrong people)
- OR list quality is weak (inaccurate Hunter results)
- OR offer is invisible in first line (subject line? headline?)

**What to fix (ONE ONLY):**
1. **Tighten ICP** — Go back to 02-evaluation/, make ICP rules stricter. Re-run prospect_builder.py with --input-csv of hand-picked prospects.
2. OR **Change subject line/hook** — Rewrite first 2 sentences of message prompt to be more attention-grabbing. Re-run message_generator_solo.py on same prospects.
3. OR **Check list quality** — Do 5 manual Hunter lookups for the people you sent to. Are they actually the right role/company?

**Do NOT do:**
- Rewrite entire message (too many variables)
- Change offer ($300 is fine)
- Rebuild system

**Timeline:**
- Try ONE fix
- Send another 20 messages
- If reply rate improves 2x → you isolated the problem
- If no change → try the next fix

---

### 🟡 MODE B: Replies But No Calls Scheduled (3–8 replies, 0–1 calls)

**What you'll see:**
- Sent 50 messages
- Got 5–8 replies (good!)
- Replied back, but prospects don't book calls

**What this means:**
- People are curious (ICP is right, message is working)
- But your reply email is weak (no Calendly link? wrong CTA? too long?)
- OR your positioning was vague in original message

**What to fix (ONE ONLY):**
1. **Reply email template** — When you get a "tell me more" reply, what do you send back?
   - Current: Assume you're sending short email + Calendly link
   - Fix: Make the Calendly link the ONLY CTA. Remove "let me know if you have questions" (extra friction)
2. OR **Call context in original message** — Did your original message make it clear this is a 15-min fit check, not a sales call?
   - Fix: Add "20-minute no-pressure audit" language to message prompt
   - Re-run message_generator_solo.py, send to remaining 20

**Do NOT do:**
- Change the offer
- Rewrite the entire message
- Assume prospects are "not interested" (they replied!)

**Timeline:**
- Check your 3–5 reply-back emails
- Are they clear + have Calendly link only?
- If yes → keep the pattern, wait for booking
- If no → simplify, send next batch with better reply email

---

### 🟠 MODE C: Calls Booked But No Pilots Closed (1–3 calls held, 0 pilots)

**What you'll see:**
- Sent 50 messages
- Got 5–10 replies
- Scheduled 2–3 calls
- Held calls, but no pilots offered/accepted

**What this means:**
- ICP is right (people reply and take calls)
- Message is right (people show up)
- BUT: your call script isn't qualifying correctly
  - You're either too salesy (they don't trust you)
  - OR you're qualifying wrong buyers (talking to wrong person)
  - OR offer isn't clear on the call

**What to fix (ONE ONLY):**
1. **Call script qualification** — Are you asking "is this the right fit for you?" on every call?
   - Current script asks this at the end
   - Fix: Ask earlier (5 min in), so you know if they're even qualified before going deep
2. OR **Offer clarity** — Are you explaining the $300 pilot clearly? What does 14 days mean? What does "5+ replies" mean to them?
   - Fix: Add a 30-second verbal offer description at call start
   - Script this out, use it on next 2 calls
3. OR **Buyer verification** — Are you talking to the actual decision maker, or a gatekeeper?
   - Fix: Start every call with "who else would be involved in this decision?" and escalate if needed

**Do NOT do:**
- Rewrite entire call script (too many variables)
- Change the message (people are already calling)
- Lower the price (signal problem is positioning, not pricing)

**Timeline:**
- Review recordings/notes from your 2–3 calls
- Which one made it furthest in conversation?
- Why? (Answer = your next fix)
- Test that fix on calls 4–5

---

### 🔴 MODE D: Everything Low (Low replies + Low calls + No pilots)

**What you'll see:**
- Sent 50 messages
- 0–2 replies (or low reply rate)
- 0 calls scheduled
- System working, no errors, but signal is just absent

**What this means:**
- Multiple layers are misaligned (ICP + message + list quality all off)
- This is rare if you ran preflight + sample quality gate correctly
- If you see this, you need to:

**What to do:**
1. **STOP.** Do not send 30 more messages hoping for better luck
2. **Diagnose using day14-failure-analysis-template.md** — Fill it out with what you have so far
3. **Pivot to warm channel** — Consider:
   - Referral asks from existing network
   - Warm intro LinkedIn outreach (mutual connections)
   - Different ICP entirely (law firms → marketing agencies, etc.)
4. **OR loop: Pick ONE variable to test**
   - Change ICP, keep message/list same
   - OR change message, keep ICP/list same
   - Rerun with 30 new prospects
   - If no improvement → pivot

**Do NOT do:**
- Rebuild system
- Change 5 things at once
- Keep sending to same cold list hoping it improves

**Timeline:**
- This is your "kill decision" point
- If Mode D at Day 10, you're likely pivoting by Day 15
- Use that time to set up warm channel or test new ICP

---

## Expected Outcome Distributions (for reference)

If your system is working and ICP is decent:

| Stage | Typical Range | What it signals |
|-------|---------------|-----------------|
| Reply rate | 2–15% | ICP quality + list quality |
| Replies that are qualified | 30–70% of replies | Message alignment (are you talking to right person?) |
| Replies that become calls | 40–80% of qualified replies | Your reply email + call confidence |
| Calls that result in pilot offer | 40–80% of calls | Your call script + offer clarity |
| Pilots offered that are accepted | 20–50% of offers | Price positioning + risk reversal credibility |

**If you're outside these ranges:**
- Below low end = something in that layer is wrong
- Above high end = congratulations, you're winning

---

## The Decision Rule (Critical)

For Days 8–14, follow this:

### ✅ DO THIS
- [ ] Run preflight check Day 8
- [ ] Sample quality gate (first 5 messages)
- [ ] Send first 50 messages Days 9–13
- [ ] Log everything daily (replies, calls, outcomes)
- [ ] Observe which mode you're in by Day 12

### ❌ DON'T DO THIS
- [ ] Change ICP after 5 sends (too small sample)
- [ ] Rewrite message after 2 replies (wait for ≥5 replies)
- [ ] Rebuild pipeline because "vibes feel off" (vibes aren't data)
- [ ] Change multiple variables simultaneously
- [ ] Send to new list without understanding first list

---

## One-Minute Reality Check (When you panic on Day 10)

Ask yourself:

1. **Did preflight check pass?** → Yes → system is not broken
2. **Which mode am I in?** (A/B/C/D) → See the mode above
3. **Do I have ≥50 sends data yet?** → No → wait until Day 13, you're observing noise
4. **Which ONE variable does this mode point to?** → Fix that ONE
5. **Does the fix require changing the code, or just my behavior?** → If behavior → implement it on next call/reply/send

---

## Print This

This is your desk reference for Days 8–14.

When panic strikes (it will, around Day 10):
- Find your mode
- Read what it means
- Fix ONE thing
- Don't rebuild

---

**Remember:**

> You are not testing if the system works.
>
> You are testing which layer of reality the system is misaligned with.
>
> The answer will be worth $10k/month once you isolate it.

---

**Last thing:**

If on Day 14 you're in Mode A (low replies), that's not a failure.

That's **market data worth $300 to you** because you know cold outreach doesn't work for that ICP.

Now you can pivot to warm channels, referrals, or a different market entirely.

*That's* how you win.
