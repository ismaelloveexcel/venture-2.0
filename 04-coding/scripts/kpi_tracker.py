"""
KPI Tracker — Weekly Venture Metrics Dashboard
Run: python kpi_tracker.py
"""

import csv
import os
from datetime import datetime, date, timedelta

KPI_FILE = os.path.join(os.path.dirname(__file__), "../../07-kpis/weekly-kpi-data.csv")
FIELDNAMES = [
    "week_ending", "outreach_sent", "positive_replies", "calls_booked",
    "calls_held", "proposals_sent", "clients_closed", "monthly_revenue",
    "churn", "notes"
]


def load_data():
    if not os.path.exists(KPI_FILE):
        return []
    with open(KPI_FILE, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_data(rows):
    os.makedirs(os.path.dirname(KPI_FILE), exist_ok=True)
    with open(KPI_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def log_week():
    print("\n=== Log This Week's KPIs ===")
    week_ending = input(f"Week ending date (YYYY-MM-DD) [{date.today()}]: ").strip()
    if not week_ending:
        week_ending = str(date.today())

    row = {"week_ending": week_ending}
    prompts = {
        "outreach_sent": "Outreach messages sent",
        "positive_replies": "Positive replies received",
        "calls_booked": "Sales calls booked",
        "calls_held": "Sales calls held",
        "proposals_sent": "Proposals sent",
        "clients_closed": "New clients closed",
        "monthly_revenue": "Current monthly revenue ($)",
        "churn": "Clients churned this week",
        "notes": "Notes (wins, blockers, decisions)",
    }
    for field, label in prompts.items():
        row[field] = input(f"  {label}: ").strip()

    rows = load_data()
    rows.append(row)
    save_data(rows)
    print(f"\nSaved! Total weeks tracked: {len(rows)}")


def show_summary():
    rows = load_data()
    if not rows:
        print("No data yet. Run option 1 to log your first week.")
        return

    print("\n=== KPI Summary (Last 8 Weeks) ===")
    header = f"{'Week':12} {'Outreach':>9} {'Replies':>8} {'Calls':>6} {'Closed':>7} {'Revenue':>10}"
    print(header)
    print("-" * len(header))
    for row in rows[-8:]:
        revenue = row.get("monthly_revenue", "0")
        print(
            f"{row['week_ending']:12} "
            f"{row.get('outreach_sent','0'):>9} "
            f"{row.get('positive_replies','0'):>8} "
            f"{row.get('calls_held','0'):>6} "
            f"{row.get('clients_closed','0'):>7} "
            f"${revenue:>9}"
        )

    # Reply rate
    try:
        total_out = sum(int(r.get("outreach_sent", 0) or 0) for r in rows[-4:])
        total_rep = sum(int(r.get("positive_replies", 0) or 0) for r in rows[-4:])
        reply_rate = (total_rep / total_out * 100) if total_out else 0
        latest_rev = float(rows[-1].get("monthly_revenue", 0) or 0)
        gap = 10000 - latest_rev
        print(f"\n4-week reply rate: {reply_rate:.1f}%  (target: 5%)")
        print(f"Revenue gap to $10k: ${gap:,.0f}/month")
        if gap <= 0:
            print("TARGET HIT!")
    except (ValueError, ZeroDivisionError):
        pass


def main():
    print("=== Venture OS KPI Tracker ===")
    print("1. Log this week's KPIs")
    print("2. Show summary dashboard")
    print("3. Exit")
    choice = input("\nChoice: ").strip()
    if choice == "1":
        log_week()
    elif choice == "2":
        show_summary()
    else:
        print("Goodbye.")


if __name__ == "__main__":
    main()
