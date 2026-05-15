"""
Outreach Message Generator — Personalised cold email/LinkedIn DMs using AI
Run: python outreach_automator.py
Requires: pip install openai python-dotenv
"""

import os
import csv
import json
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # .env optional

PROSPECTS_FILE = os.path.join(os.path.dirname(__file__), "../../06-sales/prospects.csv")
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "../../06-sales/generated-outreach.csv")

PROSPECT_FIELDS = ["name", "company", "role", "industry", "pain_point", "linkedin_url", "email", "status"]

OUTREACH_TEMPLATE = """
You are an expert B2B copywriter. Write a short, personalised cold outreach message.

Sender info:
- Service: {service}
- Unique value: {unique_value}
- Social proof: {social_proof}

Prospect:
- Name: {name}
- Company: {company}
- Role: {role}
- Industry: {industry}
- Known pain point: {pain_point}

Requirements:
- Format: {format}
- Max length: {max_length}
- Tone: conversational, no jargon, not salesy
- No fake familiarity ("Hope you're well!")
- End with a soft CTA (e.g. "Worth a 15-min call?")
- Do NOT mention AI unless they asked for AI help

Write the message only. No subject line unless email format is requested.
"""


def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "outreach_config.json")
    if os.path.exists(config_path):
        with open(config_path, encoding="utf-8") as f:
            return json.load(f)
    # Defaults
    return {
        "service": "AI-powered lead follow-up automation",
        "unique_value": "Automates follow-up sequences so no lead falls through the cracks",
        "social_proof": "Helped 3 clients reduce no-show rates by 40%",
        "format": "LinkedIn DM",
        "max_length": "80 words"
    }


def load_prospects():
    if not os.path.exists(PROSPECTS_FILE):
        print(f"No prospects file found at: {PROSPECTS_FILE}")
        print(
            "This script does not create or overwrite prospects.csv (governed path: "
            "python 04-coding/scripts/run_daily.py --generate-prospects --prospects-demo)."
        )
        return []
    with open(PROSPECTS_FILE, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r.get("status", "").lower() == "pending"]


def generate_with_openai(prompt: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return "[OPENAI_API_KEY not set — paste this prompt into ChatGPT or Copilot Chat manually]\n\n" + prompt

    try:
        import openai
        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[Error calling OpenAI: {e}]\n\nPrompt:\n{prompt}"


def main():
    config = load_config()
    prospects = load_prospects()

    if not prospects:
        return

    print(f"\nFound {len(prospects)} pending prospects. Generating messages...\n")

    output_rows = []
    for p in prospects:
        prompt = OUTREACH_TEMPLATE.format(
            service=config["service"],
            unique_value=config["unique_value"],
            social_proof=config["social_proof"],
            format=config["format"],
            max_length=config["max_length"],
            name=p.get("name", ""),
            company=p.get("company", ""),
            role=p.get("role", ""),
            industry=p.get("industry", ""),
            pain_point=p.get("pain_point", ""),
        )
        message = generate_with_openai(prompt)
        print(f"--- {p['name']} @ {p['company']} ---")
        print(message)
        print()
        output_rows.append({**p, "generated_message": message, "generated_at": datetime.now().isoformat()})

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        all_fields = PROSPECT_FIELDS + ["generated_message", "generated_at"]
        writer = csv.DictWriter(f, fieldnames=all_fields)
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"Saved {len(output_rows)} messages to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
