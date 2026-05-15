#!/usr/bin/env python3
"""
Bootstrap local .env secrets from Notion.

This script needs one bootstrap credential in .env:
  NOTION_API_KEY=secret_...  or  NOTION_TOKEN=ntn_...

It searches pages/databases shared with that integration for KEY=VALUE style
entries, then writes recognized missing keys back to .env. It never prints
secret values.
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import Iterable

import httpx
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parents[2]
ENV_FILE = BASE / ".env"

TARGET_KEYS = [
    "OPENAI_API_KEY",
    "APOLLO_API_KEY",
    "HUNTER_API_KEY",
    "RESEND_API_KEY",
    "RESEND_FROM_EMAIL",
    "RESEND_FROM_NAME",
    "AIRTABLE_API_KEY",
    "AIRTABLE_BASE_ID",
    "AIRTABLE_PROSPECTS_TABLE",
    "AIRTABLE_KPIS_TABLE",
    "CALENDLY_API_KEY",
    "NOTION_API_KEY",
    "NOTION_TOKEN",
    "NOTION_IDEAS_DB",
    "NOTION_PROSPECTS_DB",
    "NOTION_KPIS_DB",
    "NOTION_DECISIONS_DB",
    "YOUR_NAME",
    "YOUR_EMAIL",
    "YOUR_SERVICE",
    "YOUR_UNIQUE_VALUE",
    "YOUR_SOCIAL_PROOF",
    "DIGEST_TO_EMAIL",
]

KEY_PATTERN = re.compile(r"(?m)^\s*([A-Z][A-Z0-9_]{2,})\s*(?:=|:)\s*([^\r\n]+?)\s*$")

PLACEHOLDER_HINTS = ("...", "your", "example", "sk-...", "secret_...", "re_...")


def is_placeholder(value: str) -> bool:
    text = (value or "").strip().strip('"').strip("'")
    if not text:
        return True
    lowered = text.lower()
    return any(hint in lowered for hint in PLACEHOLDER_HINTS)


def clean_value(value: str) -> str:
    return (value or "").strip().strip('"').strip("'")


def read_env_lines() -> list[str]:
    if not ENV_FILE.exists():
        return []
    return ENV_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()


def read_env_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in read_env_lines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = clean_value(value)
    return values


def notion_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }


def rich_text_plain(items: Iterable[dict]) -> str:
    return "".join(str(item.get("plain_text", "")) for item in items or [])


def extract_property_text(prop: dict) -> str:
    ptype = prop.get("type", "")
    if ptype in {"title", "rich_text"}:
        return rich_text_plain(prop.get(ptype, []))
    if ptype == "email":
        return str(prop.get("email") or "")
    if ptype == "url":
        return str(prop.get("url") or "")
    if ptype == "phone_number":
        return str(prop.get("phone_number") or "")
    if ptype == "select":
        return str((prop.get("select") or {}).get("name") or "")
    if ptype == "multi_select":
        return " ".join(
            str(item.get("name", "")) for item in prop.get("multi_select", [])
        )
    if ptype == "number":
        return str(prop.get("number") or "")
    if ptype == "formula":
        formula = prop.get("formula") or {}
        return str(formula.get(formula.get("type", ""), ""))
    return ""


def block_text(block: dict) -> str:
    btype = block.get("type", "")
    payload = block.get(btype) or {}
    pieces: list[str] = []
    if "rich_text" in payload:
        pieces.append(rich_text_plain(payload.get("rich_text", [])))
    if btype == "table_row":
        cells = [rich_text_plain(cell) for cell in payload.get("cells", [])]
        pieces.append(" = ".join(cell for cell in cells if cell))
    return "\n".join(piece for piece in pieces if piece)


def list_block_children(client: httpx.Client, block_id: str) -> list[dict]:
    blocks: list[dict] = []
    cursor = None
    while True:
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        response = client.get(f"/v1/blocks/{block_id}/children", params=params)
        response.raise_for_status()
        payload = response.json()
        blocks.extend(payload.get("results", []))
        if not payload.get("has_more"):
            break
        cursor = payload.get("next_cursor")
    return blocks


def collect_page_text(client: httpx.Client, page_id: str, depth: int = 0) -> str:
    if depth > 2:
        return ""
    pieces: list[str] = []
    for block in list_block_children(client, page_id):
        text = block_text(block)
        if text:
            pieces.append(text)
        if block.get("has_children"):
            nested = collect_page_text(client, block["id"], depth + 1)
            if nested:
                pieces.append(nested)
    return "\n".join(pieces)


def query_database_pages(client: httpx.Client, database_id: str) -> list[dict]:
    pages: list[dict] = []
    cursor = None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        response = client.post(f"/v1/databases/{database_id}/query", json=body)
        response.raise_for_status()
        payload = response.json()
        pages.extend(payload.get("results", []))
        if not payload.get("has_more"):
            break
        cursor = payload.get("next_cursor")
    return pages


def search_notion(client: httpx.Client, query: str = "") -> list[dict]:
    results: list[dict] = []
    cursor = None
    while True:
        body: dict[str, object] = {"page_size": 100}
        if query:
            body["query"] = query
        if cursor:
            body["start_cursor"] = cursor
        response = client.post("/v1/search", json=body)
        response.raise_for_status()
        payload = response.json()
        results.extend(payload.get("results", []))
        if not payload.get("has_more"):
            break
        cursor = payload.get("next_cursor")
    return results


def extract_key_values(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for key, raw_value in KEY_PATTERN.findall(text or ""):
        if key not in TARGET_KEYS:
            continue
        value = clean_value(raw_value)
        if value and not is_placeholder(value):
            found[key] = value
    return found


def update_env(found: dict[str, str], overwrite: bool) -> list[str]:
    lines = read_env_lines()
    existing = read_env_values()
    changed: list[str] = []
    line_by_key: dict[str, int] = {}
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            line_by_key[key] = idx

    for key, value in found.items():
        current = existing.get(key, "")
        if current and not is_placeholder(current) and not overwrite:
            continue
        if key in line_by_key:
            lines[line_by_key[key]] = f"{key}={value}"
        else:
            lines.append(f"{key}={value}")
        changed.append(key)

    if changed:
        ENV_FILE.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import missing .env secrets from Notion"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Find values but do not write .env"
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing non-placeholder .env values",
    )
    args = parser.parse_args()

    load_dotenv(ENV_FILE)
    token = (
        os.environ.get("NOTION_API_KEY", "").strip()
        or os.environ.get("NOTION_TOKEN", "").strip()
    )
    if not token or is_placeholder(token):
        print(
            "[fail] Add NOTION_API_KEY or NOTION_TOKEN to .env first, then rerun this script."
        )
        return 2

    found: dict[str, str] = {}
    with httpx.Client(
        base_url="https://api.notion.com",
        headers=notion_headers(token),
        timeout=20,
    ) as client:
        probe = client.post("/v1/search", json={"page_size": 1})
        if probe.status_code == 401:
            print(
                "[fail] Notion token was rejected (401). Check the integration secret in .env."
            )
            return 3
        probe.raise_for_status()

        candidates = search_notion(client)
        print(f"[ok] Notion auth works; scanning {len(candidates)} shared objects")

        for obj in candidates:
            obj_type = obj.get("object")
            if obj_type == "page":
                properties = obj.get("properties") or {}
                prop_text = "\n".join(
                    extract_property_text(p) for p in properties.values()
                )
                found.update(extract_key_values(prop_text))
                found.update(extract_key_values(collect_page_text(client, obj["id"])))
            elif obj_type == "database":
                for page in query_database_pages(client, obj["id"]):
                    properties = page.get("properties") or {}
                    prop_text = "\n".join(
                        extract_property_text(p) for p in properties.values()
                    )
                    found.update(extract_key_values(prop_text))
                    found.update(
                        extract_key_values(collect_page_text(client, page["id"]))
                    )

    if "NOTION_API_KEY" in found and "NOTION_TOKEN" not in found:
        found["NOTION_TOKEN"] = found["NOTION_API_KEY"]
    elif "NOTION_TOKEN" in found and "NOTION_API_KEY" not in found:
        found["NOTION_API_KEY"] = found["NOTION_TOKEN"]

    found_keys = sorted(found)
    print("[ok] Found keys: " + (", ".join(found_keys) if found_keys else "none"))
    if args.dry_run:
        print("[info] Dry run only; .env not changed")
        return 0

    changed = update_env(found, overwrite=args.overwrite)
    print(
        "[ok] Updated .env keys: " + (", ".join(sorted(changed)) if changed else "none")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
