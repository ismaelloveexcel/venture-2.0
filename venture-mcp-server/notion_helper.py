"""
Notion API helper — used by venture_pipeline.py and the MCP server.
Handles creating and querying records in the 4 Venture OS databases.

Requires: httpx (already in requirements.txt)
Notion API docs: https://developers.notion.com/reference
"""

import os
import httpx
from datetime import date as _date

NOTION_VERSION = "2022-06-28"
BASE_URL = "https://api.notion.com/v1"


def _headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _rich_text(value: str) -> list:
    return [{"type": "text", "text": {"content": str(value)[:2000]}}]


def _title(value: str) -> list:
    return [{"type": "text", "text": {"content": str(value)[:2000]}}]


# ── Create a page in a Notion database ───────────────────────────────────────
def create_page(api_key: str, database_id: str, properties: dict) -> dict:
    """
    Create a new page (row) in a Notion database.
    `properties` must be a valid Notion properties dict.
    Returns the created page object or raises on error.
    """
    url = f"{BASE_URL}/pages"
    body = {
        "parent": {"database_id": database_id},
        "properties": properties,
    }
    r = httpx.post(url, headers=_headers(api_key), json=body, timeout=15)
    r.raise_for_status()
    return r.json()


# ── Update an existing page ───────────────────────────────────────────────────
def update_page(api_key: str, page_id: str, properties: dict) -> dict:
    """Patch an existing Notion page's properties."""
    url = f"{BASE_URL}/pages/{page_id}"
    r = httpx.patch(url, headers=_headers(api_key), json={"properties": properties}, timeout=15)
    r.raise_for_status()
    return r.json()


# ── Find an existing page by its title/name field ─────────────────────────────
def find_page_by_name(api_key: str, database_id: str, name: str) -> str | None:
    """Return the page_id of the first row whose title matches `name`, or None."""
    url = f"{BASE_URL}/databases/{database_id}/query"
    body = {
        "filter": {
            "property": "Name",
            "title": {"equals": name},
        },
        "page_size": 1,
    }
    try:
        r = httpx.post(url, headers=_headers(api_key), json=body, timeout=15)
        r.raise_for_status()
        results = r.json().get("results", [])
        return results[0]["id"] if results else None
    except Exception:
        return None


# ── Upsert helper (create or update) ─────────────────────────────────────────
def _upsert(api_key: str, db_id: str, name: str, props: dict) -> tuple[dict, bool]:
    """Create the page if it doesn't exist; update it if it does. Returns (page, created)."""
    existing_id = find_page_by_name(api_key, db_id, name)
    if existing_id:
        return update_page(api_key, existing_id, props), False
    return create_page(api_key, db_id, props), True


# ── Query a Notion database ───────────────────────────────────────────────────
def query_database(api_key: str, database_id: str, page_size: int = 20) -> list[dict]:
    """
    Return the most recent `page_size` rows from a database.
    """
    url = f"{BASE_URL}/databases/{database_id}/query"
    body = {"page_size": page_size, "sorts": [{"timestamp": "created_time", "direction": "descending"}]}
    r = httpx.post(url, headers=_headers(api_key), json=body, timeout=15)
    r.raise_for_status()
    return r.json().get("results", [])


# ── Extract plain text from a page property ──────────────────────────────────
def extract_text(prop: dict) -> str:
    ptype = prop.get("type", "")
    if ptype == "title":
        items = prop.get("title", [])
    elif ptype == "rich_text":
        items = prop.get("rich_text", [])
    elif ptype == "number":
        return str(prop.get("number", ""))
    elif ptype == "select":
        sel = prop.get("select")
        return sel["name"] if sel else ""
    elif ptype == "date":
        d = prop.get("date")
        return d["start"] if d else ""
    else:
        return ""
    return "".join(t.get("plain_text", "") for t in items)


# ── Sync an Idea ──────────────────────────────────────────────────────────────
def sync_idea(api_key: str, db_id: str, name: str, niche: str,
              description: str, score: str = "", status: str = "Raw", notes: str = "") -> str:
    if not api_key or not db_id:
        return "skipped (NOTION_API_KEY or NOTION_IDEAS_DB not set)"
    props = {
        "Name":        {"title": _title(name)},
        "Niche":       {"rich_text": _rich_text(niche)},
        "Description": {"rich_text": _rich_text(description)},
        "Score":       {"rich_text": _rich_text(score)},
        "Status":      {"select": {"name": status}},
        "Notes":       {"rich_text": _rich_text(notes)},
        "Date":        {"date": {"start": str(_date.today())}},
    }
    try:
        page, created = _upsert(api_key, db_id, name, props)
        action = "created" if created else "updated"
        return f"[ok] Idea {action} in Notion (id: {page['id'][:8]}...)"
    except Exception as e:
        return f"[error] Notion sync error: {e}"


# ── Sync a Prospect + outreach message ───────────────────────────────────────
def sync_prospect(api_key: str, db_id: str, name: str, company: str,
                  role: str, industry: str, pain_point: str,
                  email: str = "", linkedin: str = "",
                  message: str = "", status: str = "Outreach Ready") -> str:
    if not api_key or not db_id:
        return "skipped (NOTION_API_KEY or NOTION_PROSPECTS_DB not set)"
    # Use "Name — Company" as dedup key so two people at different firms don't collide
    dedup_name = f"{name} — {company}" if company else name
    props = {
        "Name":        {"title": _title(dedup_name)},
        "Company":     {"rich_text": _rich_text(company)},
        "Role":        {"rich_text": _rich_text(role)},
        "Industry":    {"rich_text": _rich_text(industry)},
        "Pain Point":  {"rich_text": _rich_text(pain_point)},
        "Email":       {"email": email} if email else {"rich_text": _rich_text("")},
        "LinkedIn":    {"url": linkedin} if linkedin else {"rich_text": _rich_text("")},
        "Message":     {"rich_text": _rich_text(message)},
        "Status":      {"select": {"name": status}},
        "Date":        {"date": {"start": str(_date.today())}},
    }
    try:
        page, created = _upsert(api_key, db_id, dedup_name, props)
        action = "created" if created else "updated"
        return f"[ok] Prospect {action} in Notion (id: {page['id'][:8]}...)"
    except Exception as e:
        return f"[error] Notion sync error: {e}"


# ── Sync a KPI week ───────────────────────────────────────────────────────────
def sync_kpi(api_key: str, db_id: str, week_ending: str, outreach: str,
             replies: str, calls: str, closed: str, revenue: str,
             churn: str, notes: str = "") -> str:
    if not api_key or not db_id:
        return "skipped (NOTION_API_KEY or NOTION_KPIS_DB not set)"

    def _num(v):
        try:
            return {"number": float(v)}
        except (ValueError, TypeError):
            return {"rich_text": _rich_text(str(v))}

    props = {
        "Week Ending":    {"title": _title(week_ending)},
        "Outreach Sent":  _num(outreach),
        "Replies":        _num(replies),
        "Calls Held":     _num(calls),
        "Clients Closed": _num(closed),
        "Revenue ($)":    _num(revenue),
        "Churn":          _num(churn),
        "Notes":          {"rich_text": _rich_text(notes)},
    }
    try:
        page, created = _upsert(api_key, db_id, week_ending, props)
        action = "created" if created else "updated"
        return f"[ok] KPI week {action} in Notion (id: {page['id'][:8]}...)"
    except Exception as e:
        return f"[error] Notion sync error: {e}"


# ── Sync a Decision ───────────────────────────────────────────────────────────
def sync_decision(api_key: str, db_id: str, topic: str, decision: str,
                  reason: str, next_action: str = "") -> str:
    if not api_key or not db_id:
        return "skipped (NOTION_API_KEY or NOTION_DECISIONS_DB not set)"
    props = {
        "Topic":       {"title": _title(topic)},
        "Decision":    {"select": {"name": decision}},
        "Reason":      {"rich_text": _rich_text(reason)},
        "Next Action": {"rich_text": _rich_text(next_action)},
        "Date":        {"date": {"start": str(_date.today())}},
    }
    try:
        page, created = _upsert(api_key, db_id, topic, props)
        action = "created" if created else "updated"
        return f"[ok] Decision {action} in Notion (id: {page['id'][:8]}...)"
    except Exception as e:
        return f"[error] Notion sync error: {e}"
