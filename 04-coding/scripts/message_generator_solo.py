#!/usr/bin/env python3
"""
Message Generator + Validator — Solo Operator Version

Generates messages using ICP prompt, validates with 3-tier output (PASS/RETRY/FAIL).
Regenerates RETRY messages once.
Output: CSV with message, status, auto_score

Usage:
    python message_generator_solo.py
"""

import csv
import sys
import pathlib
import json
import os
from typing import Optional

from dotenv import load_dotenv

# Add venture-mcp-server to path (for resilience module)
BASE = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "venture-mcp-server"))

from openai import OpenAI

load_dotenv(BASE / ".env")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
PROSPECTS_FILE = BASE / "06-sales" / "prospects.csv"
OUTPUT_FILE = BASE / "06-sales" / "generated-outreach.csv"
LOCAL_GENERATION = "--local" in sys.argv or os.environ.get(
    "VENTURE_LOCAL_GENERATION", ""
).strip().lower() in {"1", "true", "yes", "on"}
DEFAULT_OUTREACH_SIGNATURE = (
    "Best,\n"
    "Ismael Sudally\n"
    "ReplyPilot AI\n"
    "Outbound systems for B2B service firms"
)
OUTREACH_SIGNATURE = (
    os.environ.get("OUTREACH_SIGNATURE", DEFAULT_OUTREACH_SIGNATURE)
    .replace("\\n", "\n")
    .strip()
)
TRUST_REJECT_PATTERNS = (
    r"\bventure os\b",
    r"\bguaranteed pipeline\b",
    r"\bcut costs by\b",
    r"\breduce no-show rates? by\b",
    r"\bhelp(?:ed)? \d+ clients\b",
    r"\bwe help businesses grow\b",
    r"\bai-driven\b",
    r"\bleverag(?:e|ing) ai\b",
    r"\bai-powered\b",
    r"\bguarantee(?:d|s)?\b",
    r"\bperformance promises?\b",
    r"\bscale your business\b",
    r"\blead gen agency\b",
    r"\btransform\b",
    r"\bunlock\b",
    r"\bdominate\b",
    r"\bgame[- ]changing\b",
    r"\brevolutionary\b",
    r"\bfree audit\b",
    r"\b\$300\b",
    r"\b14-day pilot\b",
    r"https?://",
    r"\bwww\.",
    r"\bcalendly\b",
    r"\bloom\b",
)

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)


class FatalGenerationError(RuntimeError):
    """Raised when generation cannot proceed (e.g., invalid API auth)."""


# Batch 1 prompt: single-variable outbound signal experiment.
ICP_PROMPT = """You are writing the single locked Batch 1 outbound email for B2B service firms.

Objective: preserve one fixed email architecture. The only allowed content variable is the specific observation.

STRICT BODY STRUCTURE:
Hi {first_name},

Noticed {specific_observation}.

A lot of B2B service firms have a strong service, but outbound tends to break once it moves beyond referrals: unclear target accounts, inconsistent first-touch messaging, and no clear way to see what is actually working.

I build client-owned outbound systems focused on one market with structured targeting, message review, sending controls, and reply tracking.

Worth a quick look, or not relevant right now?

RULES:
- Do not change the structure, CTA, positioning, or audience anchor.
- type_of_firm is always B2B service firms.
- No call requests.
- No links, Calendly, Loom, attachments, fake proof, guarantees, or hype language.
- No bullet points
- Operator-to-operator tone

Generate ONLY the message body before the signature, nothing else."""


PAIN_SIGNAL_COPY = {
    "hiring_for_sales": "new sales capacity only pays off if the outbound motion is focused enough to create real conversations",
    "scaling_outbound": "scaling outbound gets noisy fast when messaging is not tied to a specific buyer pain",
    "leads_declining": "declining lead flow usually points to a message-market fit issue before it becomes a pipeline issue",
    "competitor_pressure": "competitive pressure makes it harder to rely on broad positioning or generic follow-up",
    "churn_rate_high": "churn pressure often exposes weak acquisition fit, because the wrong prospects enter the funnel",
    "course_completion_low": "completion issues usually make enrollment messaging harder because proof has to feel more concrete",
    "pipeline_visibility": "pipeline visibility gets harder when outbound replies are inconsistent and hard to interpret",
    "candidate_shortage": "candidate shortage creates pressure to make every outreach touch more relevant and timely",
    "low_roi": "low ROI from marketing often means the first conversation is not being framed around a sharp enough pain",
    "client_retention": "retention pressure often starts with expectations set before the first sales conversation",
    "project_delivery": "delivery pressure makes poor-fit leads expensive because they consume capacity before proving value",
    "scaling_team": "team scaling usually exposes which outreach messages create qualified demand versus noise",
    "market_awareness": "market awareness is hard to build when outreach sounds like everyone else's pitch",
    "media_placement_low": "low placement volume often comes back to whether the outreach angle is specific enough to earn attention",
    "program_enrollment": "enrollment pressure usually needs clearer pain-led messaging, not more generic promotion",
    "market_differentiation": "differentiation gets difficult when prospects cannot quickly see why the conversation matters now",
    "employee_retention": "retention-focused offers need outreach that quickly connects the business pain to measurable outcomes",
    "tax_deadline_stress": "deadline-driven stress makes timing and relevance matter more than broad service descriptions",
    "project_scope_creep": "scope creep usually starts before kickoff when expectations and fit are not qualified clearly",
    "rep_performance_tracking": "rep performance issues are easier to fix when the outreach process reveals which messages create real buying intent",
    "content_performance": "content performance problems often show up as weak conversion from attention into qualified conversations",
    "linkedin_profile_optimization": "profile optimization is easier to sell when outreach ties visibility to one concrete business outcome",
    "talent_recruitment": "talent recruitment pressure makes generic outreach expensive because the best-fit prospects ignore it",
    "student_results_proof": "proof of results matters most when prospects are deciding whether a program is credible enough to explore",
    "stakeholder_alignment": "stakeholder alignment gets harder when outreach does not identify one clear business problem first",
    "client_turnaround": "turnaround pressure makes it risky to spend time on poorly qualified conversations",
    "certification_value": "certification value has to be framed around concrete career or business outcomes to create serious replies",
    "technology_adoption": "technology adoption stalls when prospects do not see the immediate operational reason to change",
    "employee_engagement_metrics": "engagement metrics are only useful when the message connects them to a decision-maker's current priority",
    "insights_actionability": "research loses value when insights do not turn into specific decisions or qualified demand",
}


def build_specific_observation(prospect: dict) -> str:
    company = (prospect.get("company_name") or "your company").strip()
    role = (prospect.get("role") or "operator").strip()
    pain_signal = (prospect.get("pain_signal") or "low_reply_rate").strip()
    explicit = (prospect.get("specific_observation") or "").strip()
    if explicit:
        return explicit.rstrip(".")
    signal_label = pain_signal.replace("_", " ")
    return f"{company} is led by a {role}, with {signal_label} showing up as a visible growth signal"


def generate_local_message(prospect: dict) -> str:
    """Provider-free Batch 1 message with one variable: specific observation."""
    first_name = (prospect.get("name") or "there").strip().split()[0]
    observation = build_specific_observation(prospect)

    return f"""Hi {first_name},

Noticed {observation}.

A lot of B2B service firms have a strong service, but outbound tends to break once it moves beyond referrals: unclear target accounts, inconsistent first-touch messaging, and no clear way to see what is actually working.

I build client-owned outbound systems focused on one market with structured targeting, message review, sending controls, and reply tracking.

Worth a quick look, or not relevant right now?"""


def strip_outreach_signature(message: str) -> str:
    text = (message or "").strip()
    if OUTREACH_SIGNATURE and OUTREACH_SIGNATURE.lower() in text.lower():
        start = text.lower().find(OUTREACH_SIGNATURE.lower())
        return text[:start].strip()
    return text


def ensure_outreach_signature(message: str) -> str:
    body = strip_outreach_signature(message)
    if not body:
        return ""
    return f"{body}\n\n{OUTREACH_SIGNATURE}"


def founder_trust_issues(message: str) -> list[str]:
    import re

    text = (message or "").strip().lower()
    issues: list[str] = []
    if not text:
        return ["empty message"]
    for pattern in TRUST_REJECT_PATTERNS:
        if re.search(pattern, text):
            issues.append(pattern)
    if OUTREACH_SIGNATURE.lower() not in text:
        issues.append("missing fixed premium signature")
    return issues


def validate_message(message: str, prospect: dict) -> tuple[str, int]:
    """
    Validate message with hard rules.

    Returns: (status, score)
    - PASS: ready to send (score 4-5)
    - RETRY: fixable issue (score 2-3)
    - FAIL: structurally bad (score 0-1)
    """

    if not message or len(message.strip()) < 50:
        return "FAIL", 0

    body = strip_outreach_signature(message)
    trust_issues = founder_trust_issues(message)
    if trust_issues:
        return "FAIL", 0

    word_count = len(body.split())

    # Hard length rule
    if word_count < 45:
        return "RETRY", 2
    if word_count > 105:
        return "FAIL", 1

    # CTA check: fixed Batch 1 CTA only.
    required_cta = "worth a quick look, or not relevant right now?"
    if required_cta not in body.lower():
        return "FAIL", 1

    forbidden_cta_terms = ["call", "book", "calendly", "meeting", "demo"]
    if any(term in body.lower() for term in forbidden_cta_terms):
        return "FAIL", 1

    # Soft CTA rejection
    if "let me know" in body.lower() or "what do you think" in body.lower():
        return "FAIL", 1

    # Personalization check (must reference company or role)
    company = prospect.get("company_name", "").lower()
    role = prospect.get("role", "").lower()
    msg_lower = body.lower()

    personalized = (company and company in msg_lower) or (role and role in msg_lower)
    if not personalized:
        return "RETRY", 2

    # Filler/artifact check
    filler_phrases = ["hope you're well", "quick question", "lorem", "{", "{{"]
    has_filler = any(phrase in body.lower() for phrase in filler_phrases)
    if has_filler:
        return "FAIL", 0

    # If we got here, it's likely PASS
    return "PASS", 4


def generate_message(prospect: dict, attempt: int = 1) -> Optional[str]:
    """
    Generate message using OpenAI + ICP prompt.

    Returns: message text or None if generation failed
    """

    if LOCAL_GENERATION:
        return generate_local_message(prospect)

    if not OPENAI_API_KEY:
        raise FatalGenerationError("OPENAI_API_KEY not set")

    company = prospect.get("company_name", "Unknown")
    role = prospect.get("role", "Unknown")
    observation = build_specific_observation(prospect)

    user_prompt = f"""Write an outreach message for:
- Company: {company}
- Role: {role}
- Specific observation: {observation}

Use the strict Batch 1 structure exactly."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": ICP_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=300,
        )
        message_text = response.choices[0].message.content.strip()

        if response:
            return message_text
    except Exception as e:
        err = str(e)
        if (
            "invalid_api_key" in err
            or "Incorrect API key provided" in err
            or "Error code: 401" in err
        ):
            raise FatalGenerationError(
                "OpenAI authentication failed (invalid API key). "
                "Update OPENAI_API_KEY in .env."
            ) from e
        print(f"[warn] Generation failed for {company}: {e}")

    return None


def run() -> int:
    """
    Main execution: generate messages, validate, output CSV
    """

    print(f"\n=== Message Generator (Solo) ===\n")
    if LOCAL_GENERATION:
        print("[info] Using local generation mode (--local): no API calls will be made")

    # Load prospects
    if not PROSPECTS_FILE.exists():
        print(f"[fail] {PROSPECTS_FILE} not found. Run prospect_builder.py first.")
        return 1

    prospects = []
    with open(PROSPECTS_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        prospects = [row for row in reader if row.get("readiness_status") == "READY"]

    if not prospects:
        print(f"[fail] No READY prospects in {PROSPECTS_FILE}")
        return 1

    print(f"[ok] Loaded {len(prospects)} READY prospects")

    # Generate and validate
    generated = []
    pass_count = 0
    retry_count = 0
    fail_count = 0

    for idx, prospect in enumerate(prospects, 1):
        print(f"\r[{idx}/{len(prospects)}] Generating...", end="", flush=True)

        company = prospect.get("company_name", "Unknown")

        # First attempt
        try:
            message = generate_message(prospect, attempt=1)
        except FatalGenerationError as e:
            print(f"\n[fail] {e}")
            print("[fail] Generation aborted. Existing output file was not modified.")
            return 2

        if not message:
            status = "FAIL"
            score = 0
        else:
            message = ensure_outreach_signature(message)
            status, score = validate_message(message, prospect)

        # Retry once if RETRY status
        if status == "RETRY":
            try:
                message = generate_message(prospect, attempt=2)
            except FatalGenerationError as e:
                print(f"\n[fail] {e}")
                print(
                    "[fail] Generation aborted. Existing output file was not modified."
                )
                return 2
            if message:
                message = ensure_outreach_signature(message)
                status, score = validate_message(message, prospect)
            else:
                status = "FAIL"
                score = 0

        generated.append(
            {
                "company_name": company,
                "role": prospect.get("role", ""),
                "message": message or "",
                "status": status,
                "auto_score": score,
            }
        )

        if status == "PASS":
            pass_count += 1
        elif status == "RETRY":
            retry_count += 1
        else:
            fail_count += 1

    print(f"\n[ok] Generation complete:")
    print(f"  PASS: {pass_count}")
    print(f"  RETRY: {retry_count}")
    print(f"  FAIL: {fail_count}")

    if pass_count == 0 and retry_count == 0 and fail_count == len(prospects):
        print(
            "\n[fail] All generations failed; preserving existing generated-outreach.csv"
        )
        return 2

    # Write output
    fieldnames = ["company_name", "role", "message", "status", "auto_score"]

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(generated)

    print(f"\n[ok] Messages written to {OUTPUT_FILE}")
    print(f"\nNext: run review_queue.py (to review and approve)\n")

    return 0


if __name__ == "__main__":
    sys.exit(run())
