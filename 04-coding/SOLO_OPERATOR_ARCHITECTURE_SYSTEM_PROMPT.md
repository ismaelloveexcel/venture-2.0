# 🧭 Solo Operator Architecture System Prompt
## For Building a Self-Explaining System (Non-Technical Language)

---

## 🎯 What You're Building

A **living business system map** that:
- Shows what happens step-by-step when you run a campaign
- Explains what gets produced and why
- **Tracks every revision you make** and shows what breaks/changes downstream
- Helps prospects understand what they're buying without needing to read code

**This is NOT documentation.** This is your **operating dashboard** that generates itself.

---

## 🚫 Critical: Non-Technical Language ONLY

### ❌ DON'T USE:
- "modules"
- "dependencies"
- "artifacts"
- "API endpoints"
- "database"
- "functions"
- "schema"
- "pipeline"
- "async"

### ✅ USE INSTEAD:
- "steps" or "tasks"
- "what each step depends on"
- "outputs" or "things we create"
- "ways to trigger the system"
- "data we store"
- "things that happen"
- "workflow"
- "things happening at the same time"

---

## 🗺️ Required Outputs (Generated into `/docs/solo-operator/`)

Important:
- You should be able to open ONE file and see everything.
- The system must generate a single combined view: `overview.html`.
- Markdown and JSON files remain the source files, but `overview.html` is the main operator view.

### 1. `what_happens.md`

**The question it answers: "When I run a campaign, what actually happens?"**

Must include:
- **Your starting point**: You decide to run a campaign (when you press the button)
- **Step-by-step workflow**: Each thing that happens, in order
- **What you get back**: What appears when it's done
- **Plain-English explanation**: A story, not a flowchart
- **Mermaid diagram**: Same story, but visual

**Example structure:**
```
## What Happens When You Run a Campaign

### Step 1: You Give Instructions
You tell the system:
- Who to reach out to
- What message to send
- When to send it

### Step 2: System Prepares
The system:
- Checks everything is correct
- Organizes the message
- Gets ready to send

### Step 3: Sending Happens
The system:
- Sends the message to each person
- Tracks what happens
- Records if they reply

### Step 4: You Get Results
You see:
- How many people received it
- How many replied
- What they said
```

---

### 2. `your_responsibilities.md`

**The question it answers: "What do I actually do? What does the system do?"**

Must include:
- **You control**: List of things YOU decide
- **System handles**: List of things it does automatically
- **Decision points**: Moments where YOU need to make a choice
- **When you need to step in**: What triggers your action

**Example structure:**
```
## What You Control

### You Decide:
- Which people to message
- What the message says
- When it should go out
- Who is most important to reach

### You Review:
- How many people replied
- If the message worked
- If you should send again
- If you should change the message

## What the System Handles

### Automatically:
- Sends exactly what you write
- Records every response
- Tracks timing
- Produces a report with numbers
```

---

### 3. `what_gets_created.md`

**The question it answers: "What outputs does the system make, and why?"**

Must include:
- **Every output created**: List each thing
- **Why it exists**: What does it help with?
- **When it gets created**: Before, during, or after the campaign?
- **Who uses it**: You? Your client? The system?
- **Table format + simple explanation**

**Example structure:**
```
| What Gets Created        | Why It Exists                                    | When        | Who Uses It        |
|--------------------------|--------------------------------------------------|-------------|--------------------|
| Campaign Settings File   | Stores your decisions about who and what to send | Before      | You & System       |
| Send Report              | Shows what was sent to whom                      | During      | You                |
| Response Tracking        | Records who replied and what they said           | During      | You & Analysis     |
| Dashboard Report         | Shows your client the campaign results           | After       | Your Client        |
| Insights & Next Steps    | Suggests what to do differently next time        | After       | You & Your Client  |
```

---

### 4. `when_you_make_changes.md`

**The question it answers: "When I change something, what breaks? What needs to happen?"**

This is CRITICAL for solo operators.

Must include:
- **Types of changes** you might make:
  - Changing the message
  - Changing who you reach
  - Changing the timing
  - Changing how you measure success
- **For EACH change type**:
  - What downstream things need to update?
  - What should you check before running again?
  - What will look different in the results?

**Example structure:**
```
## When You Change the Message

### What Happens:
1. You update the message
2. System uses the new version
3. Reports will show the new message was sent
4. Response patterns might change (different message, different replies)

### What to Check:
- [ ] Does the new message make sense?
- [ ] Is it shorter/longer? (might affect response rate)
- [ ] Does it still match your offer?

### What Will Be Different in Results:
- Send report shows NEW message
- Reply rates might go up or down
- Client sees different message in their dashboard

---

## When You Change Who You Reach

### What Happens:
1. You change the target list
2. System sends to NEW people instead
3. Old results stay the same (they're history)
4. New reports start fresh

### What to Check:
- [ ] Are these people a good fit?
- [ ] Do you have enough of them?
- [ ] Are their contact details correct?

### What Will Be Different in Results:
- Different number of sends
- Might need different messaging for different group
- Response rates will be fresh data
```

---

### 5. `revision_map.md`

**The question it answers: "Where am I in my revisions, and what changes should I NOT make right now?"**

Must include:
- **Current revision status**: What phase are you in?
- **What's locked**: What you should NOT change (locked by system rules)
- **What's open**: What you can change freely
- **Revision history**: Previous versions and why you changed them
- **Impact timeline**: What happens if you change it now vs later

**Example structure:**
```
## Your Current Revision Status

### Current Phase: **Messaging Refinement**

### What's Locked (Don't Change):
- Target audience list (60 people selected)
- Send timing (Tuesday mornings)
- Campaign name

**Why:** If you change these now, you'll lose comparison data from the last run.

### What's Open (Safe to Change):
- Message copy (you can rewrite it)
- Subject line (experimental)
- Call-to-action wording

**Why:** These changes won't affect your comparison metrics.

### Revision History:
| Date       | What Changed       | Why                          | Results              |
|------------|--------------------|------------------------------|----------------------|
| May 10     | First draft        | Initial launch                | 8% reply rate        |
| May 12     | Shortened message  | Test shorter = faster reads  | 12% reply rate ⬆️    |
| May 14     | Added social proof | Test more credibility        | 15% reply rate ⬆️    |

### If You Change Message Today:
- New version starts tracking TODAY
- Previous results (15% rate) stay for comparison
- Can compare old vs new side-by-side
- BUT: You lose the comparison with May 12 version

### Recommendation:
Run one more day with current message, lock it, then revise.
```

---

### 6. `business_flow.md`

**The question it answers: "If I show this to a prospect, can they understand what they're buying?"**

Must include:
- **Their perspective**: What do THEY experience?
- **What they see**: At each step, what's in front of them?
- **Value they get**: Why should they care?
- **Mermaid diagram**: Simple, clean, no jargon
- **Story format**: Like a walkthrough

**Example structure:**
```
## What Your Client Experiences

### Day 1: Onboarding
You: "Tell me about your campaign goals"
Client provides:
- Who they want to reach
- What problem they solve
- Budget or timeline

### Day 2-3: Campaign Runs
Client: Doesn't need to do anything
Behind the scenes:
- You refine the message
- System sends to targets
- Tracking starts

### Day 4: First Results
Client sees:
- Number of people contacted
- Number who replied
- Quality of replies

They also see:
- Your recommendation: "Here's what I suggest changing"

### Day 7: Optimization
You: "Let's try a new approach"
Client: Approves new version

### Day 14: Full Report
Client sees:
- Full journey of what worked
- How many high-quality leads generated
- Next steps and pricing

### Value Delivered:
✅ 20+ qualified conversations
✅ 3 active opportunities
✅ Clear playbook for next month
```

---

### 7. `control_center.json`

**The question it answers: "Where do I look to understand the whole system right now?"**

Machine-readable map of everything:

```json
{
  "operator": "isuda",
  "system_status": {
    "last_run": "2026-05-15T14:30:00Z",
    "current_revision": "messaging_refinement_v3",
    "is_locked_for_revision": false
  },
  
  "phases": {
    "understanding": {
      "file": "what_happens.md",
      "description": "Learn the workflow"
    },
    "your_role": {
      "file": "your_responsibilities.md",
      "description": "Know what you control"
    },
    "outputs": {
      "file": "what_gets_created.md",
      "description": "See what gets made"
    },
    "revisions": {
      "file": "when_you_make_changes.md",
      "description": "Understand change impact"
    },
    "current_status": {
      "file": "revision_map.md",
      "description": "Know where you are now"
    },
    "sales_story": {
      "file": "business_flow.md",
      "description": "Show prospects what they get"
    }
  },

  "latest_outputs": {
    "config_file": "campaigns/campaign_2026_05_15.json",
    "send_report": "reports/send_log_2026_05_15.txt",
    "response_tracking": "reports/responses_2026_05_15.json",
    "client_dashboard": "dashboards/client_view_2026_05_15.html",
    "insights": "reports/insights_2026_05_15.md"
  },

  "revision_timeline": [
    {
      "date": "2026-05-10",
      "phase": "initial_draft",
      "changed": ["message", "target_list"],
      "locked_until": "2026-05-13"
    },
    {
      "date": "2026-05-12",
      "phase": "messaging_refinement_v1",
      "changed": ["message_length"],
      "impact": "reply_rate: 8% → 12%"
    },
    {
      "date": "2026-05-14",
      "phase": "messaging_refinement_v2",
      "changed": ["social_proof"],
      "impact": "reply_rate: 12% → 15%"
    }
  ],

  "change_impact_rules": {
    "message_change": {
      "what_breaks": "direct comparison with previous runs",
      "what_stays": "target list, timing, client visibility",
      "recommendation": "document the change reason"
    },
    "target_list_change": {
      "what_breaks": "response rate comparisons",
      "what_stays": "message quality, send process",
      "recommendation": "start new segment tracking"
    },
    "timing_change": {
      "what_breaks": "all response data (people might reply at different times)",
      "what_stays": "message quality, target list",
      "recommendation": "lock timing for at least one full run"
    }
  }
}
```

---

### 8. `overview.html` (Single-File View)

**The question it answers: "Can I see the full system in one place right now?"**

Must include in one page:
- Current revision status card (locked/open/current phase)
- Visual workflow section (from `what_happens.md`)
- Your role section (from `your_responsibilities.md`)
- Outputs table (from `what_gets_created.md`)
- Change impact section (from `when_you_make_changes.md`)
- Revision map section (from `revision_map.md`)
- Client story section (from `business_flow.md`)
- Last updated timestamp + run id

Rules:
- No frontend frameworks
- Plain HTML + CSS + optional minimal JS only
- Deterministic generation (same input state = same output)
- Must be regenerated by script, never hand-edited

---

## 🔄 How Auto-Update Works

Create: `scripts/update_solo_operator_docs.py`

This script:
1. **Reads what actually exists** in your system (real files, real workflow)
2. **Detects any changes** you made:
   - Changed a message? Marks it in revision map.
   - Changed targets? Tracks it.
   - Changed timing? Records it.
3. **Regenerates all docs** to reflect current state
  - Includes regenerating `overview.html` as the single-file operator view
4. **Runs automatically**:
   - When you execute a campaign
   - After each revision
   - Daily check (optional)

---

## ⚠️ Revision Tracking Rules

### When you make a change:

1. **Document why**: "Testing shorter message for faster reads"
2. **Mark what's locked**: "Target list stays same for comparison"
3. **Show the impact**: "Previous rate was 12%, new version measures against that"
4. **Decide next action**: "Run for 3 days, then evaluate"

### System auto-tracks:
- What changed
- When it changed
- Previous version
- Impact on downstream outputs
- What can't be compared anymore

### You make the decision:
- Is the change worth losing comparison data?
- Should I run longer before next revision?
- Is this revision locked or open?

---

## 📊 Validation Requirements

After each update, system checks:
- [ ] Every output file listed in `what_gets_created.md` actually exists
- [ ] Every revision in `revision_map.md` is traceable to actual files
- [ ] No locked revision was accidentally changed
- [ ] All diagrams show current state (not old state)
- [ ] `overview.html` contains all required sections and renders without errors

---

## 🎯 What This Gives YOU (Solo Operator)

### 1. Clarity While Revising
You never lose track of:
- What you changed
- Why you changed it
- What can't be compared anymore
- What should stay locked

### 2. Safe Experiments
You can freely revise because you always know:
- What's safe to change
- What will break comparisons
- When to lock vs. when to stay open

### 3. Prospect-Ready Explanation
When you show `business_flow.md`:
- Prospects see value, not complexity
- They understand what they're buying
- No jargon, just outcomes

### 4. Your Operating Dashboard
`control_center.json` is YOUR checklist:
- Current status at a glance
- Where to look for what
- Revision history
- Change impact rules

---

## 🚀 Implementation Order

1. **Start with** `what_happens.md` (understand your own workflow)
2. **Then add** `your_responsibilities.md` (clarify your role)
3. **Then create** `what_gets_created.md` (inventory all outputs)
4. **Critical next** `when_you_make_changes.md` (safety rules)
5. **Then build** `revision_map.md` (real-time status)
6. **Then craft** `business_flow.md` (prospect story)
7. **Finally** `control_center.json` (master index)

---

## 🔥 Most Important

At any point, ask these questions:

**"Where am I revising right now?"**
→ Answer in `revision_map.md`

**"What will break if I change X?"**
→ Answer in `when_you_make_changes.md`

**"What should I NOT change?"**
→ Answer in `revision_map.md` (locked section)

**"How do I explain this to a prospect?"**
→ Show them `business_flow.md`

---

This system is YOUR tool. It evolves with your decisions, not separate from them.
