"""
Venture OS — MCP Server
Exposes 5 AI-powered tools Copilot Chat can call directly:
  1. score_idea           — 8-criteria niche scorecard via OpenAI
  2. research_competitors — web search via Brave API
  3. generate_outreach    — personalised message for a prospect
  4. weekly_kpi_review    — reads CSV → AI analysis + top 3 priorities
  5. pivot_or_persist     — decides pivot / persist / kill from metrics

Setup:
  1. Copy .env.example → .env and fill in your keys
  2. pip install -r requirements.txt
  3. The MCP server is registered in .vscode/mcp.json — VS Code starts it automatically
"""

import os
import csv
import json
import pathlib
from typing import Optional

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# ── Load environment ──────────────────────────────────────────────────────────
# MCP clients often pass `${env:VAR}` entries even when empty; those become set in
# os.environ and would block load_dotenv() defaults. override=True makes repo .env authoritative.
load_dotenv(pathlib.Path(__file__).parent.parent / ".env", override=True)

OPENAI_API_KEY  = os.environ.get("OPENAI_API_KEY", "")
BRAVE_API_KEY   = os.environ.get("BRAVE_SEARCH_API_KEY", "")
NOTION_API_KEY  = os.environ.get("NOTION_API_KEY", "")
NOTION_IDEAS_DB      = os.environ.get("NOTION_IDEAS_DB", "")
NOTION_PROSPECTS_DB  = os.environ.get("NOTION_PROSPECTS_DB", "")
NOTION_KPIS_DB       = os.environ.get("NOTION_KPIS_DB", "")
NOTION_DECISIONS_DB  = os.environ.get("NOTION_DECISIONS_DB", "")
KPI_CSV  = pathlib.Path(__file__).parent.parent / "07-kpis" / "weekly-kpi-data.csv"
IDEA_CSV = pathlib.Path(__file__).parent.parent / "01-ideas" / "idea-log.csv"

import sys as _sys
_sys.path.insert(0, str(pathlib.Path(__file__).parent))
from notion_helper import (
    sync_idea as _notion_sync_idea,
    sync_prospect as _notion_sync_prospect,
    sync_kpi as _notion_sync_kpi,
    sync_decision as _notion_sync_decision,
    query_database as _notion_query,
    extract_text as _notion_text,
)

mcp = FastMCP("venture-os")


# ── Helper: call OpenAI chat ──────────────────────────────────────────────────
def _openai_chat(prompt: str, max_tokens: int = 800) -> str:
    if not OPENAI_API_KEY:
        return (
            "⚠️  OPENAI_API_KEY not set in .env\n\n"
            "Paste this prompt into ChatGPT or Copilot Chat manually:\n\n" + prompt
        )
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.6,
    }
    try:
        r = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=body,
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except httpx.HTTPStatusError as e:
        return f"OpenAI API error {e.response.status_code}: {e.response.text}"
    except Exception as e:
        return f"Error calling OpenAI: {e}"


# ── TOOL 1: Score Idea ────────────────────────────────────────────────────────
@mcp.tool()
def score_idea(idea: str) -> str:
    """
    Score a venture idea against the 8-criteria niche scorecard.
    Returns a score table, GO/NO-GO verdict, top risk, and next action.

    Args:
        idea: A one-to-three sentence description of the venture idea.
    """
    prompt = f"""Score this venture idea using the 8-criteria niche scorecard.
Score each criterion 1–10 (10 = best).

IDEA: {idea}

Criteria:
1. Pain Intensity — How urgent and expensive is the problem?
2. Niche Specificity — How laser-focused is the target customer?
3. Willingness to Pay — Would they pay $1,000+/month?
4. Reachability — Can I find and contact 500+ prospects this week?
5. Speed to First $ — How fast can I close a paid client?
6. Competitive Gap — Is there room for a better/different player?
7. AI Leverage — Can AI make delivery 10x faster or cheaper?
8. Personal Fit — Skills, network, or credibility in this space?

Format your response EXACTLY like this:
| Criterion | Score | Reasoning |
|---|---|---|
| Pain Intensity | X | ... |
| Niche Specificity | X | ... |
| Willingness to Pay | X | ... |
| Reachability | X | ... |
| Speed to First $ | X | ... |
| Competitive Gap | X | ... |
| AI Leverage | X | ... |
| Personal Fit | X | ... |
| **TOTAL** | X/80 | |

VERDICT: GO / CONDITIONAL GO / NO-GO
TOP RISK (one sentence):
NEXT ACTION (one specific task to do today):
"""
    return _openai_chat(prompt, max_tokens=700)


# ── TOOL 2: Research Competitors ─────────────────────────────────────────────
@mcp.tool()
def research_competitors(niche: str, idea: str) -> str:
    """
    Search the web for competitors in a niche, then summarise gaps and differentiation.
    Uses Brave Search API for live results, then OpenAI to analyse them.

    Args:
        niche: The specific niche (e.g. "solo immigration lawyers US")
        idea: Brief description of your venture idea
    """
    search_results = ""

    if BRAVE_API_KEY:
        query = f"{niche} {idea} software service tool competitors pricing"
        try:
            r = httpx.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": 8, "text_decorations": False},
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": BRAVE_API_KEY,
                },
                timeout=15,
            )
            r.raise_for_status()
            results = r.json().get("web", {}).get("results", [])
            lines = []
            for res in results[:6]:
                lines.append(f"- {res.get('title', '')} | {res.get('url', '')} | {res.get('description', '')}")
            search_results = "\n".join(lines)
        except Exception as e:
            search_results = f"[Brave search error: {e}]"
    else:
        search_results = "[BRAVE_SEARCH_API_KEY not set — analysis will be based on training data only]"

    prompt = f"""Analyse competitors for this venture idea.

NICHE: {niche}
IDEA: {idea}

Web search results:
{search_results}

Provide:
1. Top 5 competitors with: name, what they offer, price (if known), weakness
2. The ONE positioning gap I can exploit
3. My differentiation statement (fill-in template: "For [customer] who [problem], [my service] is [category] that [benefit], unlike [competitor] which [limitation]")
4. GO / RISKY / TOO CROWDED verdict with one-line reason
"""
    return _openai_chat(prompt, max_tokens=800)


# ── TOOL 3: Generate Outreach ─────────────────────────────────────────────────
@mcp.tool()
def generate_outreach(
    name: str,
    company: str,
    role: str,
    industry: str,
    pain_point: str,
    format: str = "LinkedIn DM",
    max_words: int = 80,
) -> str:
    """
    Generate a personalised cold outreach message for one prospect.
    Reads your service/offer settings from the .env file.

    Args:
        name: Prospect's first name
        company: Prospect's company name
        role: Prospect's job title
        industry: Prospect's industry/niche
        pain_point: The specific problem they likely have
        format: "LinkedIn DM", "Cold Email", or "Cold Email with Subject"
        max_words: Maximum word count for the message
    """
    service = os.environ.get("YOUR_SERVICE", "AI-powered automation service")
    unique_value = os.environ.get("YOUR_UNIQUE_VALUE", "saves time and increases revenue")
    social_proof = os.environ.get("YOUR_SOCIAL_PROOF", "helped similar businesses get results")
    your_name = os.environ.get("YOUR_NAME", "[Your Name]")

    prompt = f"""Write a short, personalised {format} for this prospect.

SENDER:
- Service: {service}
- Unique value: {unique_value}
- Social proof: {social_proof}
- Name: {your_name}

PROSPECT:
- Name: {name}
- Company: {company}
- Role: {role}
- Industry: {industry}
- Pain point: {pain_point}

RULES:
- Max {max_words} words
- Conversational, no jargon, not salesy
- No fake openers ("Hope you're well!")
- Reference their specific situation — not generic
- Soft CTA at the end (e.g. "Worth a quick call?")
- Do NOT mention AI unless they asked about AI
{"- Include a compelling subject line first" if "Subject" in format else ""}

Write the message only.
"""
    return _openai_chat(prompt, max_tokens=300)


# ── TOOL 4: Weekly KPI Review ─────────────────────────────────────────────────
@mcp.tool()
def weekly_kpi_review() -> str:
    """
    Reads 07-kpis/weekly-kpi-data.csv and returns an AI analysis with:
    - Revenue progress toward $10k/month goal
    - Reply rate, call conversion, close rate trends
    - Top 3 priorities for this week
    - One metric that is the biggest bottleneck right now
    """
    if not KPI_CSV.exists():
        return "No KPI data found. Run `python 04-coding/scripts/kpi_tracker.py` to log your first week."

    with open(KPI_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        return "KPI file exists but has no data yet."

    revenue_target = int(os.environ.get("REVENUE_TARGET", 10000))
    recent = rows[-8:]  # last 8 weeks max
    summary_lines = []
    for r in recent:
        summary_lines.append(
            f"Week {r.get('week_ending','?')}: "
            f"outreach={r.get('outreach_sent','?')}, "
            f"replies={r.get('positive_replies','?')}, "
            f"calls={r.get('calls_held','?')}, "
            f"closed={r.get('clients_closed','?')}, "
            f"revenue=${r.get('monthly_revenue','?')}, "
            f"churn={r.get('churn','?')}, "
            f"notes={r.get('notes','')}"
        )
    data_block = "\n".join(summary_lines)

    prompt = f"""You are a venture growth advisor. Analyse this weekly KPI data and give actionable feedback.

REVENUE TARGET: ${revenue_target:,}/month
KPI DATA (last {len(recent)} weeks):
{data_block}

Provide:
1. Revenue gap — how far from target and at current trajectory, when will it be hit?
2. Key metrics analysis — reply rate, call-to-close rate, weekly trend (improving/declining?)
3. BIGGEST BOTTLENECK — the single metric that, if improved, would have the most impact
4. TOP 3 PRIORITIES for this week (specific, actionable — e.g. "Send 250 outreach messages to [niche]")
5. One-line morale check — are they on track, behind, or ahead?
"""
    return _openai_chat(prompt, max_tokens=600)


# ── TOOL 5: Pivot or Persist ──────────────────────────────────────────────────
@mcp.tool()
def pivot_or_persist(
    outreach_sent: int,
    positive_replies: int,
    calls_held: int,
    clients_closed: int,
    weeks_active: int,
    main_objection: str = "",
    idea_description: str = "",
) -> str:
    """
    Decide whether to pivot, persist, or kill a venture based on current metrics.
    Returns a clear verdict with specific recommended next action.

    Args:
        outreach_sent: Total outreach messages sent so far
        positive_replies: Total positive replies received
        calls_held: Total discovery/sales calls completed
        clients_closed: Total paying clients acquired
        weeks_active: How many weeks you've been working this idea
        main_objection: Most common objection heard on calls (optional)
        idea_description: Brief description of current idea (optional)
    """
    reply_rate = (positive_replies / outreach_sent * 100) if outreach_sent else 0
    call_to_close = (clients_closed / calls_held * 100) if calls_held else 0

    prompt = f"""You are a no-nonsense venture advisor. Based on these metrics, decide: PERSIST, PIVOT, or KILL.

IDEA: {idea_description or "not specified"}
WEEKS ACTIVE: {weeks_active}
OUTREACH SENT: {outreach_sent}
POSITIVE REPLIES: {positive_replies} ({reply_rate:.1f}% reply rate)
CALLS HELD: {calls_held}
CLIENTS CLOSED: {clients_closed} ({call_to_close:.1f}% close rate)
MAIN OBJECTION: {main_objection or "not specified"}

BENCHMARKS:
- Healthy reply rate: ≥5%
- Minimum outreach before judging: 250 messages
- Minimum calls before judging: 5
- Minimum weeks before judging: 4

Respond with:
VERDICT: PERSIST / PIVOT / KILL
REASONING: (2-3 sentences, brutally honest)
IF PIVOT — specify the exact type: Niche pivot / Problem pivot / Channel pivot / Price pivot / Delivery pivot
EXACT CHANGE: (one sentence — what specifically changes)
THIS WEEK'S EXPERIMENT: (one action to test within 7 days)
"""
    return _openai_chat(prompt, max_tokens=400)


# ── TOOL 6: Add Idea to Log ───────────────────────────────────────────────────
@mcp.tool()
def log_idea(name: str, description: str, niche: str, notes: str = "") -> str:
    """
    Add a new idea to the idea-log.csv file automatically.
    Call this after scoring — it saves the idea for future reference.

    Args:
        name: Short name for the idea
        description: One-sentence description
        niche: Target niche/market
        notes: Any extra notes (optional)
    """
    IDEA_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["id", "date", "name", "description", "niche", "pain_score", "wtp_score",
                  "speed_score", "ai_leverage_score", "total_score", "status", "notes"]

    existing = []
    if IDEA_CSV.exists():
        with open(IDEA_CSV, newline="", encoding="utf-8") as f:
            existing = list(csv.DictReader(f))

    new_id = len(existing) + 1
    from datetime import date
    new_row = {
        "id": new_id, "date": str(date.today()), "name": name,
        "description": description, "niche": niche,
        "pain_score": "", "wtp_score": "", "speed_score": "", "ai_leverage_score": "",
        "total_score": "", "status": "Raw", "notes": notes
    }
    existing.append(new_row)

    with open(IDEA_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(existing)

    return f"✅ Idea #{new_id} '{name}' added to idea-log.csv. Run score_idea() next to score it."


# ── TOOL 7: Sync to Notion ────────────────────────────────────────────────────
@mcp.tool()
def notion_sync(
    record_type: str,
    name: str,
    # shared / idea fields
    niche: str = "",
    description: str = "",
    score: str = "",
    status: str = "",
    notes: str = "",
    # prospect fields
    company: str = "",
    role: str = "",
    industry: str = "",
    pain_point: str = "",
    email: str = "",
    message: str = "",
    # kpi fields (name = week_ending)
    outreach: str = "",
    replies: str = "",
    calls: str = "",
    closed: str = "",
    revenue: str = "",
    churn: str = "",
    # decision fields (name = topic)
    decision: str = "",
    reason: str = "",
    next_action: str = "",
) -> str:
    """
    Push a record directly into Notion from Copilot Chat.
    Reads NOTION_API_KEY and database IDs from .env automatically.
    Performs an upsert — updates existing records instead of creating duplicates.

    record_type options:
      "idea"      — name, niche, description, score, status, notes
      "prospect"  — name, company, role, industry, pain_point, email, message
      "kpi"       — name=week_ending, outreach, replies, calls, closed, revenue, churn, notes
      "decision"  — name=topic, decision (Pursue/Pivot/Kill), reason, next_action

    Args:
        record_type: One of "idea", "prospect", "kpi", "decision"
        name: Primary identifier (idea name, prospect name, week date, or decision topic)
    """
    rt = record_type.lower().strip()
    if not NOTION_API_KEY:
        return "⚠️  NOTION_API_KEY not set in .env — open .env and add your Notion integration secret."

    if rt == "idea":
        return _notion_sync_idea(
            NOTION_API_KEY, NOTION_IDEAS_DB,
            name=name, niche=niche, description=description,
            score=score, status=status or "Raw", notes=notes,
        )
    elif rt == "prospect":
        return _notion_sync_prospect(
            NOTION_API_KEY, NOTION_PROSPECTS_DB,
            name=name, company=company, role=role, industry=industry,
            pain_point=pain_point, email=email, message=message,
        )
    elif rt == "kpi":
        return _notion_sync_kpi(
            NOTION_API_KEY, NOTION_KPIS_DB,
            week_ending=name, outreach=outreach, replies=replies,
            calls=calls, closed=closed, revenue=revenue, churn=churn, notes=notes,
        )
    elif rt == "decision":
        return _notion_sync_decision(
            NOTION_API_KEY, NOTION_DECISIONS_DB,
            topic=name, decision=decision, reason=reason, next_action=next_action,
        )
    else:
        return f"Unknown record_type '{record_type}'. Use: idea, prospect, kpi, or decision."


# ── TOOL 8: Read from Notion ──────────────────────────────────────────────────
@mcp.tool()
def notion_read(database: str, limit: int = 10) -> str:
    """
    Read recent records from one of the 4 Venture OS Notion databases.
    Returns a plain-text table of the latest rows.

    Args:
        database: One of "ideas", "prospects", "kpis", "decisions"
        limit: Number of recent rows to return (default 10, max 50)
    """
    if not NOTION_API_KEY:
        return "⚠️  NOTION_API_KEY not set in .env."

    db_map = {
        "ideas":      NOTION_IDEAS_DB,
        "prospects":  NOTION_PROSPECTS_DB,
        "kpis":       NOTION_KPIS_DB,
        "decisions":  NOTION_DECISIONS_DB,
    }
    db_id = db_map.get(database.lower().strip(), "")
    if not db_id:
        return f"Database '{database}' not configured. Set NOTION_{database.upper()}_DB in .env."

    try:
        pages = _notion_query(NOTION_API_KEY, db_id, page_size=min(limit, 50))
    except Exception as e:
        return f"Error reading Notion: {e}"

    if not pages:
        return f"No records found in '{database}' database."

    lines = [f"=== Notion: {database.upper()} (last {len(pages)}) ==="]
    for p in pages:
        props = p.get("properties", {})
        row_parts = []
        for key, val in props.items():
            text = _notion_text(val)
            if text:
                row_parts.append(f"{key}: {text}")
        lines.append(" | ".join(row_parts))

    return "\n".join(lines)


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mcp.run(transport="stdio")
