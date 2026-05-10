#!/usr/bin/env python3
"""
Review Queue — Solo Operator Decision Interface

Ultra-simple: APPROVE / REJECT binary decisions only.
Then sends approved messages and logs outcomes.

Usage:
    python review_queue.py
"""

import csv
import sys
import pathlib
from datetime import datetime

BASE = pathlib.Path(__file__).resolve().parents[2]
GENERATED_FILE = BASE / "06-sales" / "generated-outreach.csv"
CALL_LOG_FILE = BASE / "07-kpis" / "call-log.csv"


def run_review() -> int:
    """
    Interactive review loop: APPROVE / REJECT decisions
    """

    print(f"\n=== Review Queue ===\n")

    # Load generated messages
    if not GENERATED_FILE.exists():
        print(
            f"[fail] {GENERATED_FILE} not found. Run message_generator_solo.py first."
        )
        return 1

    messages = []
    with open(GENERATED_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        messages = [row for row in reader if row.get("status") == "PASS"]

    if not messages:
        print(f"[fail] No PASS messages to review in {GENERATED_FILE}")
        return 1

    print(f"[ok] Loaded {len(messages)} messages for review\n")
    print(
        "Instructions: Review each message. Type 'a' to APPROVE, 'r' to REJECT, 'q' to quit\n"
    )

    approved = []
    idx = 0

    while idx < len(messages):
        msg = messages[idx]
        company = msg.get("company_name", "Unknown")
        role = msg.get("role", "Unknown")
        message_text = msg.get("message", "")

        # Display message
        print(f"\n{'='*60}")
        print(f"[{idx + 1}/{len(messages)}] {company} | {role}")
        print(f"{'='*60}")
        print(f"\n{message_text}\n")

        # Get decision
        while True:
            decision = input("Decision (a/r/q): ").lower().strip()

            if decision == "a":
                approved.append(msg)
                idx += 1
                break
            elif decision == "r":
                idx += 1
                break
            elif decision == "q":
                return 0
            else:
                print("Invalid input. Type 'a' (approve), 'r' (reject), or 'q' (quit)")

    # Update generated-outreach.csv with "approved" column
    if approved:
        # Read all messages and mark approved ones
        all_messages = []
        with open(GENERATED_FILE, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            all_messages = list(reader)

        # Mark approved messages
        approved_ids = {msg.get("company_name") + msg.get("role") for msg in approved}
        for msg in all_messages:
            msg_id = msg.get("company_name") + msg.get("role")
            msg["approved"] = "yes" if msg_id in approved_ids else "no"

        # Rewrite file with approved column
        fieldnames = all_messages[0].keys() if all_messages else []
        with open(GENERATED_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_messages)

        print(f"\n[ok] {len(approved)} messages marked as approved")
        print(f"[ok] Updated {GENERATED_FILE} with approval status\n")
        print("Next: Send approved messages via:\n")
        print("  python venture_pipeline.py --dry-run  (preview)")
        print("  python venture_pipeline.py             (execute)\n")
    else:
        print("\n[info] No messages approved")

    return 0


def run_approve_all() -> int:
    """Mark every PASS message as approved without interactive prompts."""
    print("[blocked] --approve-all is disabled for Batch 1.")
    print("[gate] Review each message manually with: python review_queue.py")
    return 2

    if not GENERATED_FILE.exists():
        print(f"[fail] No generated messages. Run generator first.")
        return 1

    with open(GENERATED_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])

    if not rows:
        print(f"[fail] No generated messages in {GENERATED_FILE}")
        return 1

    if "approved" not in fieldnames:
        fieldnames.append("approved")

    approved_count = 0
    for row in rows:
        if row.get("status") == "PASS" and (row.get("message") or "").strip():
            row["approved"] = "yes"
            approved_count += 1
        else:
            row["approved"] = "no"

    with open(GENERATED_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"[ok] Approved {approved_count} PASS messages in {GENERATED_FILE}")
    return 0


def run_send_batch() -> int:
    """
    Show send-ready status
    """

    if not GENERATED_FILE.exists():
        print(f"[fail] No generated messages. Run generator first.")
        return 1

    messages = []
    with open(GENERATED_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        messages = [m for m in reader if m.get("approved") == "yes"]

    if not messages:
        print(f"[info] No approved messages yet. Run review first.")
        return 0

    print(f"\n[ok] {len(messages)} messages ready to send")
    print("[info] Execute send via:\n")
    print("  python venture_pipeline.py --dry-run  (preview)")
    print("  python venture_pipeline.py             (execute)\n")

    return 0


def run_call_logger() -> int:
    """
    Simple call logging interface (4 states only)
    """

    print(f"\n=== Call Logger ===\n")
    print("Log call outcomes: BOOKED | INTERESTED | NOT_NOW | NO_FIT\n")

    # Ensure log file exists
    if not CALL_LOG_FILE.exists():
        CALL_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CALL_LOG_FILE, "w", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["date", "prospect", "company", "outcome", "notes"]
            )
            writer.writeheader()

    # Log entry loop
    while True:
        prospect = input("Prospect name (or 'q' to quit): ").strip()
        if prospect.lower() == "q":
            break

        company = input("Company: ").strip()

        print("Outcome options: BOOKED | INTERESTED | NOT_NOW | NO_FIT")
        outcome = input("Outcome: ").strip().upper()

        if outcome not in ["BOOKED", "INTERESTED", "NOT_NOW", "NO_FIT"]:
            print("[fail] Invalid outcome. Try again.")
            continue

        notes = input("Notes (optional): ").strip()

        # Append to log
        with open(CALL_LOG_FILE, "a", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["date", "prospect", "company", "outcome", "notes"]
            )
            writer.writerow(
                {
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "prospect": prospect,
                    "company": company,
                    "outcome": outcome,
                    "notes": notes,
                }
            )

        print("[ok] Logged\n")

    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "--approve-all":
            sys.exit(run_approve_all())
        if cmd == "--send":
            sys.exit(run_send_batch())
        elif cmd == "--log-calls":
            sys.exit(run_call_logger())

    # Default: run review
    sys.exit(run_review())
