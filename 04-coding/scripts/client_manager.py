#!/usr/bin/env python3
"""
Per-client workspace manager for Venture OS.

This keeps Venture OS as the internal engine while giving each client an isolated
runtime folder: config, secrets, SQLite state, CSV inputs/outputs, logs, reports.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import pathlib
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CLIENTS_ROOT = REPO_ROOT / "clients"
PIPELINE = REPO_ROOT / "04-coding" / "scripts" / "venture_pipeline.py"
REPLY_TYPES = {"interested", "not_now", "not_interested", "wrong_person", "spam_block"}

REPLY_TEMPLATES = {
    "interested": [
        "Thanks for the reply. The useful next step is a short fit check so we can map the target segment and what would count as a qualified conversation.",
        "Makes sense. I can show you how the outbound system would work for your offer and where the first campaign would start.",
        "Great. The quickest way to see if this is worth doing is to look at your target market, current pipeline, and what a qualified conversation is worth.",
    ],
    "not_now": [
        "Totally understood. I will leave this for now. If pipeline becomes a priority later, the cleanest starting point is a small diagnostic sprint to validate targeting before building anything.",
        "No problem. Timing matters with outbound, so I would rather revisit when there is a real growth push behind it.",
        "That makes sense. I will close the loop for now and can send the short diagnostic checklist later if outbound becomes a priority.",
    ],
    "not_interested": [
        "Understood, thanks for letting me know. I will close the loop here and make sure you are not contacted again about this campaign.",
        "Thanks for the reply. I will mark this as not relevant and stop follow-up.",
        "Appreciate the direct answer. I will take you off this sequence.",
    ],
    "wrong_person": [
        "Thanks for pointing me in the right direction. Who owns outbound, growth, or new client acquisition on your side?",
        "Got it. Who would be the right person to ask about pipeline or new client acquisition?",
        "Thanks for clarifying. Is there someone else who handles growth systems or outbound internally?",
    ],
    "spam_block": [
        "No problem. I will suppress this contact and stop further outreach.",
        "Understood. I will remove this contact from future outreach.",
        "Confirmed. I will mark this as suppressed and prevent additional follow-up.",
    ],
}


def _slug(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    return "-".join(part for part in cleaned.split("-") if part)


def client_path(name: str) -> pathlib.Path:
    slug = _slug(name)
    if not slug:
        raise ValueError("Client name must contain at least one letter or number")
    return CLIENTS_ROOT / slug


def load_client(name: str) -> dict[str, Any]:
    path = client_path(name)
    config_path = path / "config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"No client config found at {config_path}")
    with config_path.open(encoding="utf-8") as handle:
        config = json.load(handle)
    config["workspace"] = str(path)
    return config


def create_client(name: str, *, force: bool = False) -> pathlib.Path:
    path = client_path(name)
    if path.exists() and not force:
        raise FileExistsError(f"Client workspace already exists: {path}")

    (path / "reports").mkdir(parents=True, exist_ok=True)
    (path / "logs").mkdir(parents=True, exist_ok=True)

    config = {
        "client_name": name.strip(),
        "offer": "Core System",
        "status": "draft",
        "icp": {
            "vertical": "B2B services",
            "employee_range": "2-30",
            "average_deal_size_min_usd": 2000,
            "geographies": ["UK", "US", "Canada", "Australia"],
        },
        "commercials": {
            "setup_fee_usd": 5500,
            "monthly_retainer_usd": 1350,
            "minimum_months": 3,
        },
        "support": {
            "included_days": 90,
            "request_cap": 6,
            "scope": "Bug fixes only; new campaigns, integrations, and strategy changes are paid.",
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    (path / "config.json").write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )
    (path / ".env.example").write_text(
        "OPENAI_API_KEY=\n"
        "APOLLO_API_KEY=\n"
        "HUNTER_API_KEY=\n"
        "RESEND_API_KEY=\n"
        "RESEND_FROM_EMAIL=\n"
        "RESEND_FROM_NAME=Ismael Sudally\n"
        "OUTREACH_SIGNATURE=Best,\\nIsmael Sudally\\nReplyPilot AI\\nOutbound systems for B2B service firms\n"
        "NOTION_API_KEY=\n"
        "NOTION_PROSPECTS_DB=\n"
        "NOTION_KPIS_DB=\n"
        "AIRTABLE_API_KEY=\n"
        "AIRTABLE_BASE_ID=\n"
        "AUTO_SEND_EMAILS=false\n"
        "OUTREACH_TEST_TO=\n"
        "INTERNAL_TEST_RECIPIENTS=\n"
        "BATCH_LOCK_SECRET=\n"
        "ALLOWED_SENDER_DOMAINS=replypilot.ai\n"
        "RESEND_DOMAIN_VERIFIED=false\n"
        "ENABLE_FOLLOWUPS=false\n"
        "ENABLE_SEND_EMAIL_RETRIES=false\n"
        "SEND_DAILY_CAP=40\n"
        "SEND_HOURLY_CAP=12\n",
        encoding="utf-8",
    )
    (path / "prospects.csv").write_text(
        "company_name,domain,name,email,role,industry,pain_signal,linkedin_url,readiness_status,reason\n",
        encoding="utf-8",
    )
    (path / "weekly-kpi-data.csv").write_text(
        "week_ending,outreach_sent,positive_replies,calls_booked,calls_held,clients_closed,revenue,notes\n",
        encoding="utf-8",
    )
    (path / "replies.csv").write_text(
        "received_at,from_email,company,contact_name,reply_type,body,suggested_response,status\n",
        encoding="utf-8",
    )
    (path / "reports" / ".gitkeep").write_text("", encoding="utf-8")
    return path


def create_demo_client(*, force: bool = True) -> pathlib.Path:
    path = create_client("Demo Client", force=force)
    config = load_client("Demo Client")
    config.update(
        {
            "client_name": "Demo Client",
            "offer": "Core System Demo",
            "status": "demo",
            "icp": {
                "vertical": "UK B2B agencies",
                "employee_range": "2-30",
                "average_deal_size_min_usd": 3000,
                "geographies": ["UK"],
            },
        }
    )
    (path / "config.json").write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )
    (path / "prospects.csv").write_text(
        "company_name,domain,name,email,role,industry,pain_signal,linkedin_url,readiness_status,reason\n"
        "Northstar Digital,northstardigital.example,Amelia Grant,amelia@northstardigital.example,Founder,Marketing Agency,referral_dependency,https://linkedin.com/in/demo-amelia,READY,clear_b2b_service_fit\n"
        "BrightOps Studio,brightops.example,Daniel Reed,daniel@brightops.example,Managing Director,Web Design Agency,inconsistent_pipeline,https://linkedin.com/in/demo-daniel,READY,clear_b2b_service_fit\n"
        "ScaleWorks MSP,scaleworks.example,Priya Shah,priya@scaleworks.example,Owner,Managed IT Services,referral_dependency,https://linkedin.com/in/demo-priya,READY,clear_b2b_service_fit\n"
        "TalentBridge Search,talentbridge.example,Marcus Hill,marcus@talentbridge.example,Director,Recruitment Agency,client_acquisition,https://linkedin.com/in/demo-marcus,READY,clear_b2b_service_fit\n"
        "Conversion Foundry,conversionfoundry.example,Sophie Lane,sophie@conversionfoundry.example,Head of Growth,Performance Agency,low_reply_rate,https://linkedin.com/in/demo-sophie,READY,clear_b2b_service_fit\n",
        encoding="utf-8",
    )
    (path / "generated-outreach.csv").write_text(
        "company_name,role,message,status,auto_score,approved\n"
        "Northstar Digital,Founder,Noticed Northstar Digital works with service businesses where referrals can hide pipeline gaps. Most agency founders I speak with want more qualified conversations without turning outbound into a high-volume mess. We install a narrow outbound system around one ICP, reviewed messages, and weekly reporting so the first campaign proves whether the market is responding. Worth exploring briefly on a call?,PASS,5,yes\n"
        "BrightOps Studio,Managing Director,BrightOps Studio looks positioned for clients who need clearer web conversion, but agencies often rely on referrals for their own growth. The risk is that good delivery capacity sits idle when no repeatable outbound motion exists. We build the first monitored campaign, track replies, and show which segment is worth scaling. Should I show you how this would work in your setup?,PASS,5,yes\n"
        "ScaleWorks MSP,Owner,ScaleWorks MSP has the kind of recurring service where outbound can work if it is targeted and low-volume. Most MSPs I see still depend heavily on referrals, which makes growth uneven. We install a client-owned outreach workflow with prospect filters, message review, sending controls, and weekly reporting. Open to a quick 15-minute fit check this week?,PASS,5,yes\n",
        encoding="utf-8",
    )
    (path / "weekly-kpi-data.csv").write_text(
        "week_ending,outreach_sent,positive_replies,calls_booked,calls_held,clients_closed,revenue,notes\n"
        "2026-05-03,300,17,2,1,0,0,First controlled demo week. UK agencies showed stronger reply quality than MSPs.\n"
        "2026-05-10,420,28,3,2,1,5500,Variant B CTA outperformed A. UK agencies were the strongest segment.\n",
        encoding="utf-8",
    )
    (path / "replies.csv").write_text(
        "received_at,from_email,company,contact_name,reply_type,body,suggested_response,status\n"
        "2026-05-06T10:15:00Z,amelia@northstardigital.example,Northstar Digital,Amelia Grant,interested,This is relevant. We have relied mostly on referrals and want to test outbound without spamming people,Thanks for the reply. The useful next step is a short fit check so we can map the target segment and what would count as a qualified conversation. Happy to show you quickly - does a 15-min call sometime this week work?,open\n"
        "2026-05-07T14:40:00Z,daniel@brightops.example,BrightOps Studio,Daniel Reed,not_now,Timing is not right this month but the system sounds useful later,Totally understood. I will leave this for now. If pipeline becomes a priority later, the cleanest starting point is a small diagnostic sprint to validate targeting before building anything.,closed\n"
        "2026-05-08T09:05:00Z,marcus@talentbridge.example,TalentBridge Search,Marcus Hill,wrong_person,I do not own growth anymore. You should speak to our managing partner,Thanks for pointing me in the right direction. Who owns outbound, growth, or new client acquisition on your side?,open\n",
        encoding="utf-8",
    )
    report_path = generate_report("Demo Client")
    print(f"[ok] Demo report written: {report_path}")
    return path


def _client_env(path: pathlib.Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "VENTURE_CLIENT_WORKSPACE": str(path),
            "VENTURE_DOTENV_PATH": str(path / ".env"),
            "VENTURE_DB_PATH": str(path / "database.sqlite"),
            "VENTURE_LOG_DIR": str(path / "logs"),
            "VENTURE_PROSPECTS_FILE": str(path / "prospects.csv"),
            "VENTURE_OUTPUT_FILE": str(path / "generated-outreach.csv"),
            "VENTURE_KPI_FILE": str(path / "weekly-kpi-data.csv"),
            "VENTURE_OUTREACH_CONFIG": str(path / "outreach_config.json"),
        }
    )
    return env


def run_pipeline(name: str, *, dry_run: bool = True, status: bool = False) -> int:
    config = load_client(name)
    path = pathlib.Path(config["workspace"])
    if not (path / ".env").exists():
        print(
            f"[warn] {path / '.env'} missing; copy .env.example and add client-owned keys before live runs"
        )

    command = [sys.executable, str(PIPELINE)]
    if status:
        command.append("--status")
    elif dry_run:
        command.append("--dry-run")

    completed = subprocess.run(
        command, cwd=str(REPO_ROOT), env=_client_env(path), check=False
    )
    return completed.returncode


def _count_csv_rows(path: pathlib.Path) -> int:
    if not path.exists():
        return 0
    with path.open(newline="", encoding="utf-8") as handle:
        return max(sum(1 for _ in csv.DictReader(handle)), 0)


def _read_csv_rows(path: pathlib.Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _safe_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _classify_reply(body: str) -> str:
    text = (body or "").lower()
    if any(
        term in text for term in ("unsubscribe", "spam", "stop contacting", "remove me")
    ):
        return "spam_block"
    if any(
        term in text
        for term in ("wrong person", "not the right person", "speak to", "contact my")
    ):
        return "wrong_person"
    if any(
        term in text
        for term in ("not interested", "no thanks", "no thank", "not relevant")
    ):
        return "not_interested"
    if any(
        term in text
        for term in ("later", "not now", "next quarter", "next month", "circle back")
    ):
        return "not_now"
    if any(
        term in text
        for term in (
            "interested",
            "relevant",
            "let's",
            "lets",
            "call",
            "meeting",
            "send more",
            "tell me more",
            "sounds useful",
        )
    ):
        return "interested"
    return "not_now"


def _call_booking_cta(config: dict[str, Any]) -> str:
    calendly_link = str(
        config.get("calendly_link") or os.environ.get("CALENDLY_LINK") or ""
    ).strip()
    if calendly_link:
        return f"You can grab a slot here: {calendly_link}"
    return "Happy to show you quickly - does a 15-min call sometime this week work?"


def _suggested_response(
    reply_type: str, config: dict[str, Any], existing_replies: pathlib.Path
) -> str:
    templates = REPLY_TEMPLATES[reply_type]
    current_count = _reply_summary(existing_replies).get(reply_type, 0)
    response = templates[current_count % len(templates)]
    if reply_type == "interested":
        response = f"{response} {_call_booking_cta(config)}"
    return response


def add_reply(
    name: str,
    *,
    body: str,
    from_email: str = "",
    company: str = "",
    contact_name: str = "",
    reply_type: str = "",
) -> pathlib.Path:
    config = load_client(name)
    path = pathlib.Path(config["workspace"])
    replies_path = path / "replies.csv"
    if not replies_path.exists():
        replies_path.write_text(
            "received_at,from_email,company,contact_name,reply_type,body,suggested_response,status\n",
            encoding="utf-8",
        )

    classified = (reply_type or _classify_reply(body)).strip().lower()
    if classified not in REPLY_TYPES:
        raise ValueError(f"reply_type must be one of: {', '.join(sorted(REPLY_TYPES))}")
    suggested = _suggested_response(classified, config, replies_path)
    status = (
        "open" if classified in {"interested", "wrong_person", "not_now"} else "closed"
    )

    with replies_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "received_at",
                "from_email",
                "company",
                "contact_name",
                "reply_type",
                "body",
                "suggested_response",
                "status",
            ],
        )
        writer.writerow(
            {
                "received_at": datetime.now(timezone.utc).isoformat(),
                "from_email": from_email,
                "company": company,
                "contact_name": contact_name,
                "reply_type": classified,
                "body": body,
                "suggested_response": suggested,
                "status": status,
            }
        )
    print(f"[ok] Reply classified as: {classified}")
    print(f"[suggested] {suggested}")
    return replies_path


def _latest_kpi(path: pathlib.Path) -> dict[str, str]:
    rows = _read_csv_rows(path)
    return rows[-1] if rows else {}


def _reply_summary(path: pathlib.Path) -> dict[str, int]:
    rows = _read_csv_rows(path)
    summary = {reply_type: 0 for reply_type in sorted(REPLY_TYPES)}
    for row in rows:
        reply_type = (row.get("reply_type") or "").strip().lower()
        if reply_type in summary:
            summary[reply_type] += 1
    return summary


def _best_segment(
    prospects: list[dict[str, str]], replies: list[dict[str, str]]
) -> str:
    if not replies:
        return "Not enough reply data yet"
    company_to_industry = {
        (row.get("company_name") or "")
        .strip()
        .lower(): (row.get("industry") or "Unknown")
        .strip()
        for row in prospects
    }
    counts: dict[str, int] = {}
    for reply in replies:
        if (reply.get("reply_type") or "").strip().lower() not in {
            "interested",
            "not_now",
            "wrong_person",
        }:
            continue
        industry = company_to_industry.get(
            (reply.get("company") or "").strip().lower(), "Unknown"
        )
        counts[industry] = counts.get(industry, 0) + 1
    if not counts:
        return "No positive segment signal yet"
    segment, count = max(counts.items(), key=lambda item: item[1])
    noun = "reply" if count == 1 else "replies"
    return f"{segment} ({count} commercially relevant {noun})"


def _next_actions(reply_rate: float, positive_replies: int, meetings: int) -> list[str]:
    actions: list[str] = []
    if reply_rate >= 5.0:
        actions.append(
            "Increase volume by 20% while keeping the same ICP and approval standards."
        )
    else:
        actions.append(
            "Hold volume steady and tighten the first-line hook before increasing sends."
        )
    if positive_replies > 0 and meetings == 0:
        actions.append(
            "Refine the reply-back CTA so positive replies convert into booked calls faster."
        )
    elif meetings > 0:
        actions.append(
            "Prioritize fast follow-up on interested replies and move booked calls into proposal review."
        )
    actions.append(
        "Keep suppressing not-interested and spam-block replies to protect deliverability."
    )
    return actions


def generate_report(name: str) -> pathlib.Path:
    config = load_client(name)
    path = pathlib.Path(config["workspace"])
    output_file = path / "generated-outreach.csv"
    kpi_file = path / "weekly-kpi-data.csv"
    replies_file = path / "replies.csv"
    report_path = (
        path / "reports" / f"report-{datetime.now(timezone.utc).date().isoformat()}.md"
    )

    prospects = _read_csv_rows(path / "prospects.csv")
    reply_rows = _read_csv_rows(replies_file)
    latest = _latest_kpi(kpi_file)
    sent = _safe_int(latest.get("outreach_sent"))
    positive_replies = _safe_int(latest.get("positive_replies"))
    meetings = _safe_int(latest.get("calls_booked") or latest.get("calls_held"))
    total_replies = max(len(reply_rows), positive_replies)
    reply_rate = (total_replies / sent * 100.0) if sent else 0.0
    reply_types = _reply_summary(replies_file)
    best_segment = _best_segment(prospects, reply_rows)
    next_actions = _next_actions(reply_rate, positive_replies, meetings)
    generated_count = _count_csv_rows(output_file)

    report = f"""# {config['client_name']} Weekly Outreach Report

Generated: {datetime.now(timezone.utc).isoformat()}

## Snapshot

| Metric | Value |
|---|---:|
| Prospects in workspace | {len(prospects)} |
| Messages generated | {generated_count} |
| Messages sent | {sent} |
| Replies received | {total_replies} ({reply_rate:.1f}%) |
| Positive replies | {positive_replies} |
| Meetings / calls | {meetings} |

## Reply Breakdown

| Reply Type | Count |
|---|---:|
| Interested | {reply_types.get('interested', 0)} |
| Not now | {reply_types.get('not_now', 0)} |
| Wrong person | {reply_types.get('wrong_person', 0)} |
| Not interested | {reply_types.get('not_interested', 0)} |
| Spam block / suppress | {reply_types.get('spam_block', 0)} |

## Insights

- Best performing segment: {best_segment}
- Reply quality: {positive_replies} positive replies from {total_replies} total replies.
- Campaign health: {'Strong early signal' if reply_rate >= 5 else 'Needs sharper targeting or message hook before scaling'}.

## Next Actions

"""
    for action in next_actions:
        report += f"- {action}\n"

    report += """
## Scope Control

- Review `generated-outreach.csv` for copy quality and approval status.
- Update `weekly-kpi-data.csv` before sending this report to the client.
- Keep scope inside the signed offer: new ICPs, integrations, and campaign strategy changes are paid changes.
"""
    report_path.write_text(report, encoding="utf-8")
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Manage isolated Venture OS client workspaces"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("name")
    create_parser.add_argument("--force", action="store_true")

    subparsers.add_parser("demo")

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("name")

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("name")
    run_parser.add_argument("--live", action="store_true")

    report_parser = subparsers.add_parser("report")
    report_parser.add_argument("name")

    reply_parser = subparsers.add_parser("reply")
    reply_parser.add_argument("name")
    reply_parser.add_argument("--body", required=True)
    reply_parser.add_argument("--from-email", default="")
    reply_parser.add_argument("--company", default="")
    reply_parser.add_argument("--contact-name", default="")
    reply_parser.add_argument("--type", choices=sorted(REPLY_TYPES), default="")

    args = parser.parse_args()

    if args.command == "create":
        path = create_client(args.name, force=args.force)
        print(f"[ok] Client workspace ready: {path}")
        return 0
    if args.command == "demo":
        path = create_demo_client(force=True)
        print(f"[ok] Demo client ready: {path}")
        return 0
    if args.command == "status":
        return run_pipeline(args.name, status=True)
    if args.command == "run":
        return run_pipeline(args.name, dry_run=not args.live)
    if args.command == "report":
        report_path = generate_report(args.name)
        print(f"[ok] Report written: {report_path}")
        return 0
    if args.command == "reply":
        replies_path = add_reply(
            args.name,
            body=args.body,
            from_email=args.from_email,
            company=args.company,
            contact_name=args.contact_name,
            reply_type=args.type,
        )
        print(f"[ok] Reply logged: {replies_path}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
