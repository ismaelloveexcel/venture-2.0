"""
Execution Dashboard — Streamlit version
Real-time control panel for Day 8–14 operator
Reads from: prospects.csv, generated-outreach.csv, call-log.csv, execution_state.json
Shows: status, next action, pipeline flow, issues, progress, signal diagnostics
"""

import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime
import json
import sys

# Add scripts to path for signal rules engine
sys.path.insert(0, str(Path(__file__).parent))

# Page config
st.set_page_config(
    page_title="Venture OS Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Paths
BASE_PATH = Path(__file__).parent.parent.parent
PROSPECTS_FILE = BASE_PATH / "06-sales" / "prospects.csv"
OUTREACH_FILE = BASE_PATH / "06-sales" / "generated-outreach.csv"
CALL_LOG_FILE = BASE_PATH / "07-kpis" / "call-log.csv"
EXECUTION_STATE_FILE = BASE_PATH / "execution_state.json"

# Import signal rules engine
try:
    from signal_rules_engine import RuleSeverity, check_system_health

    SIGNAL_ENGINE_AVAILABLE = True
except ImportError:
    SIGNAL_ENGINE_AVAILABLE = False


# Helper functions
@st.cache_data(ttl=30)
def load_prospects():
    """Load prospects CSV"""
    if PROSPECTS_FILE.exists():
        try:
            return pd.read_csv(PROSPECTS_FILE)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


@st.cache_data(ttl=30)
def load_outreach():
    """Load generated outreach CSV"""
    if OUTREACH_FILE.exists():
        try:
            return pd.read_csv(OUTREACH_FILE)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


@st.cache_data(ttl=30)
def load_call_log():
    """Load call log CSV"""
    if CALL_LOG_FILE.exists():
        try:
            return pd.read_csv(CALL_LOG_FILE)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def get_system_status():
    """Determine overall system status"""
    try:
        prospects = load_prospects()
        outreach = load_outreach()

        if prospects.empty:
            return "🔴", "NOT STARTED", "Run preflight check first"

        if outreach.empty:
            return "🟡", "PROSPECTS READY", "Generate messages next"

        # Check if approval is happening
        if "approved" in outreach.columns:
            approved_count = (
                (outreach["approved"] == "yes").sum()
                if "approved" in outreach.columns
                else 0
            )
            pass_count = (
                (outreach["status"] == "PASS").sum()
                if "status" in outreach.columns
                else 0
            )

            if approved_count == 0 and pass_count > 0:
                return "🟡", "REVIEWING", f"{pass_count} messages to approve"
            elif approved_count > 0 and approved_count < 20:
                return "🟡", "REVIEWING", f"{approved_count} approved, continue..."
            elif approved_count >= 20:
                return "🟢", "READY TO SEND", f"{approved_count} approved ✓"

        return "🟡", "GENERATING", "Messages in progress"

    except Exception as e:
        return "🔴", "ERROR", str(e)[:50]


def get_pipeline_status():
    """Get counts across pipeline stages"""
    prospects = load_prospects()
    outreach = load_outreach()
    call_log = load_call_log()

    prospect_count = len(prospects) if not prospects.empty else 0

    if outreach.empty:
        message_count = 0
        pass_count = 0
        approved_count = 0
    else:
        message_count = len(outreach)
        pass_count = (outreach.get("status", "") == "PASS").sum()
        approved_count = (outreach.get("approved", "") == "yes").sum()

    if call_log.empty:
        call_count = 0
        pilot_count = 0
    else:
        call_count = len(call_log)
        # Count calls that led to pilots (outcome = BOOKED or pilot offered)
        pilot_count = (call_log.get("outcome", "").isin(["BOOKED", "INTERESTED"])).sum()

    return {
        "prospects": prospect_count,
        "messages": message_count,
        "pass": pass_count,
        "approved": approved_count,
        "calls": call_count,
        "pilots": pilot_count,
    }


def get_next_action():
    """Determine next immediate action"""
    prospects = load_prospects()
    outreach = load_outreach()

    if prospects.empty:
        return (
            "1️⃣",
            "Run Preflight Check",
            [
                "Open terminal: python 04-coding/scripts/preflight_check_day8.py",
                "Fix any missing keys or dependencies",
            ],
        )

    if outreach.empty:
        return (
            "2️⃣",
            "Generate Prospects & Messages",
            [
                "Run: python 04-coding/scripts/prospect_builder.py",
                "Then: python 04-coding/scripts/message_generator_solo.py",
            ],
        )

    approved_count = (
        (outreach.get("approved", "") == "yes").sum()
        if "approved" in outreach.columns
        else 0
    )
    pass_count = (
        (outreach.get("status", "") == "PASS").sum()
        if "status" in outreach.columns
        else 0
    )

    if approved_count == 0 and pass_count > 0:
        return (
            "3️⃣",
            "Review & Approve Messages",
            [
                f"Run: python 04-coding/scripts/review_queue.py",
                f"{pass_count} PASS messages waiting",
                "Approve the best 20-30 (binary: yes/no only)",
            ],
        )

    if approved_count < 20:
        return (
            "3️⃣",
            "Continue Reviewing Messages",
            [
                f"Current: {approved_count} approved",
                "Target: 20-30 approved messages",
                "Run: python 04-coding/scripts/review_queue.py again",
            ],
        )

    return (
        "4️⃣",
        "Ready to Send (Day 9)",
        [
            f"✅ You have {approved_count} approved messages",
            "Tomorrow morning run: python venture_pipeline.py --dry-run",
            "Then: python venture_pipeline.py (to actually send)",
        ],
    )


def get_active_issues():
    """Identify active issues using signal rules engine"""
    issues = []

    try:
        # First, check signal rules if engine is available
        if SIGNAL_ENGINE_AVAILABLE:
            severity, diagnosis, rules = check_system_health(EXECUTION_STATE_FILE)

            if severity == RuleSeverity.HARD_STOP:
                issues.append(("🔴", "EXECUTION PAUSED", diagnosis))
                for rule in rules:
                    if rule["severity"] == "HARD_STOP":
                        issues.append(("🔴", f"{rule['rule_id']}", rule["action"]))
            elif severity == RuleSeverity.WARNING:
                issues.append(("🟡", "System Warning", diagnosis))
                for rule in rules:
                    if rule["severity"] == "WARNING":
                        issues.append(("🟡", f"{rule['rule_id']}", rule["action"]))

        # Also check basic file existence
        if not PROSPECTS_FILE.exists():
            issues.append(("❌", "No prospects file", "Run prospect_builder.py first"))

        if not OUTREACH_FILE.exists():
            issues.append(("❌", "No outreach file", "Run message_generator_solo.py"))

        # Check data quality
        prospects = load_prospects()
        if not prospects.empty and len(prospects) < 50:
            if not any("Low prospect volume" in issue[1] for issue in issues):
                issues.append(
                    (
                        "🟡",
                        f"Low prospect volume ({len(prospects)}/50)",
                        "Generate more or use existing ones",
                    )
                )

        if not issues:
            issues.append(("✅", "All systems go", "No active issues"))

    except Exception as e:
        issues.append(("🔴", "Error reading files", str(e)[:60]))

    return issues


def get_recent_activity():
    """Get recent activity from file timestamps"""
    activity = []

    try:
        if PROSPECTS_FILE.exists():
            mtime = PROSPECTS_FILE.stat().st_mtime
            dt = datetime.fromtimestamp(mtime)
            prospects = load_prospects()
            activity.append((dt, "📍 Prospects generated", f"({len(prospects)} total)"))

        if OUTREACH_FILE.exists():
            mtime = OUTREACH_FILE.stat().st_mtime
            dt = datetime.fromtimestamp(mtime)
            outreach = load_outreach()
            approved = (
                (outreach.get("approved", "") == "yes").sum()
                if not outreach.empty
                else 0
            )
            activity.append((dt, "✉️ Messages ready", f"({approved} approved)"))

        if CALL_LOG_FILE.exists():
            mtime = CALL_LOG_FILE.stat().st_mtime
            dt = datetime.fromtimestamp(mtime)
            call_log = load_call_log()
            activity.append((dt, "📞 Call logged", f"({len(call_log)} total)"))

    except Exception:
        pass

    # Sort by recency
    activity.sort(key=lambda x: x[0], reverse=True)
    return activity[:5]


# ============================================
# PAGE RENDERING
# ============================================

st.title("📊 Venture OS — Execution Dashboard")
st.markdown("**Day 8–14 Control Panel** — See status, next action, pipeline progress")

# 1. SYSTEM STATUS BAR
st.divider()
col1, col2, col3, col4 = st.columns(4)

status_icon, status_name, status_detail = get_system_status()

with col1:
    st.metric("System Status", status_name, status_detail)

pipeline = get_pipeline_status()
with col2:
    st.metric("Prospects", pipeline["prospects"], "target: 50")

with col3:
    st.metric("Pass Quality", pipeline["pass"], "to approve")

with col4:
    st.metric("Approved", pipeline["approved"], "ready to send")

st.divider()

# 2. NEXT ACTION BOX (PROMINENT)
emoji, action_title, action_steps = get_next_action()

with st.container(border=True):
    st.subheader(f"{emoji} NEXT ACTION")
    st.write(f"### {action_title}")
    for i, step in enumerate(action_steps, 1):
        st.write(f"**{i}.** {step}")

st.divider()

# 3. PIPELINE VISUAL FLOW
st.subheader("📈 Pipeline Flow")

col1, col2, col3, col4, col5, col6 = st.columns(6)

stages = [
    ("PROSPECTS", pipeline["prospects"]),
    ("MESSAGES", pipeline["messages"]),
    ("PASS", pipeline["pass"]),
    ("APPROVED", pipeline["approved"]),
    ("CALLS", pipeline["calls"]),
    ("PILOTS", pipeline["pilots"]),
]

with col1:
    st.metric("Prospects", stages[0][1])
with col2:
    st.metric("Messages", stages[1][1])
with col3:
    st.metric("Pass", stages[2][1])
with col4:
    st.metric("Approved", stages[3][1])
with col5:
    st.metric("Calls", stages[4][1])
with col6:
    st.metric("Pilots", stages[5][1])

st.divider()

# 4. ISSUES PANEL (ERROR-FIRST)
st.subheader("⚠️ Status & Issues")

issues = get_active_issues()

for icon, issue_title, issue_detail in issues:
    if "✅" in icon:
        st.success(f"{icon} {issue_title}")
    elif "🟡" in icon:
        st.warning(f"{icon} {issue_title} — {issue_detail}")
    else:
        st.error(f"{icon} {issue_title} — {issue_detail}")

st.divider()

# 5. PROGRESS TOWARDS GOAL
st.subheader("🎯 Progress Towards Goal (Day 14)")

st.write("**Target:** 3–5 pilots in 14 days")

current_pilots = pipeline["pilots"]
target_pilots = 5
progress_pct = (
    min(100, (current_pilots / target_pilots) * 100) if target_pilots > 0 else 0
)

st.progress(progress_pct / 100)
st.write(
    f"**Current:** {current_pilots} pilots (target: {target_pilots}) — {progress_pct:.0f}% progress"
)

st.divider()

# 6. RECENT ACTIVITY LOG
st.subheader("🕒 Recent Activity")

activity = get_recent_activity()

if activity:
    for timestamp, event, detail in activity:
        time_str = timestamp.strftime("%H:%M")
        st.write(f"**{time_str}** → {event} {detail}")
else:
    st.info("No activity yet. Start with Step 1 above.")

st.divider()

# 7. QUICK REFERENCE (FAILURE MAPPING)
st.subheader("🧭 Quick Diagnostic")

with st.expander("📚 If results are low, read this first"):
    st.markdown("""
    #### Signal Interpretation (what it means)
    
    | **If you see...** | **Then...** | **Action** |
    |---|---|---|
    | **Low reply rate** (<2%) | ICP is wrong or list quality is bad | Tighten prospect targeting |
    | **Replies but no calls** | Message is weak or reply email unclear | Improve call-to-action |
    | **Calls but no pilots** | Offer unclear or call script weak | Fix offer positioning or sales pitch |
    | **Everything low** | Multiple variables broken | Pivot to warm channel (referrals) |
    
    #### Golden Rules
    - Change **ONE variable at a time**
    - Wait until ≥50 sends before iterating
    - Don't optimize based on <10 data points
    - By Day 14, you'll have clear signal
    """)

st.divider()

# Footer with refresh
col1, col2, col3 = st.columns(3)
with col2:
    if st.button("🔄 Refresh Dashboard", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.caption(
    f"Last updated: {datetime.now().strftime('%H:%M:%S')} | Refresh every 30 seconds in Streamlit"
)

# Add instruction
st.divider()
st.markdown("""
**To run this dashboard:**
```
streamlit run 04-coding/scripts/dashboard_streamlit.py
```

**Then** open: http://localhost:8501 in your browser
""")
