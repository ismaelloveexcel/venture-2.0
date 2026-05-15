#!/usr/bin/env python3
"""
Venture OS — Local run console (operator-facing)

Run:  python 04-coding/scripts/dashboard.py
Open: http://localhost:5000   (opens automatically)
Stop: Ctrl+C
"""

import csv
import json
import os
import pathlib
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import httpx
from dotenv import load_dotenv
from runtime_config import RuntimeConfig, build_config_status, resolve_data_base
from operator_ux import operator_status_payload

# Job queue support
sys.path.insert(
    0, str(pathlib.Path(__file__).parent.parent.parent / "venture-mcp-server")
)
from job_queue import JobQueue, get_queue
from resend_webhook_handler import process_resend_event, verify_resend_webhook
from lifecycle_validation import LifecycleEventValidationError

BASE = pathlib.Path(__file__).parent.parent.parent
load_dotenv(BASE / ".env")


def _insecure_webhooks_allowed() -> bool:
    return os.environ.get("VENTURE_ALLOW_INSECURE_WEBHOOKS", "").lower() in (
        "1",
        "true",
        "yes",
    )


def _dashboard_bind_host_and_port() -> tuple[str, int]:
    """
    Bind address for the HTTP server. When VENTURE_ALLOW_INSECURE_WEBHOOKS is set (unsigned
    webhook acceptance), refuse any non-loopback DASHBOARD_BIND so dev mode cannot accidentally
    expose that path on the LAN.
    """
    host = (os.environ.get("DASHBOARD_BIND", "127.0.0.1") or "127.0.0.1").strip()
    port = int(os.environ.get("DASHBOARD_PORT", "5000"))
    loopback_only = {"127.0.0.1", "localhost", "::1"}
    if _insecure_webhooks_allowed():
        if host.lower() not in loopback_only:
            print(
                "\n[fail] VENTURE_ALLOW_INSECURE_WEBHOOKS is enabled but DASHBOARD_BIND is not loopback-only "
                f"(current DASHBOARD_BIND={host!r}).\n"
                "Refusing to start: unsigned webhooks must not be reachable off this machine.\n"
                "Fix: unset VENTURE_ALLOW_INSECURE_WEBHOOKS for real deployments, or set DASHBOARD_BIND=127.0.0.1\n"
            )
            raise SystemExit(2)
        if host.lower() == "localhost":
            host = "127.0.0.1"
    return host, port


DASHBOARD_BIND, PORT = _dashboard_bind_host_and_port()
PYTHON = sys.executable
RUN_DAILY = str(BASE / "04-coding" / "scripts" / "run_daily.py")
PROSPECTS_FILE = BASE / "06-sales" / "prospects.csv"
KPI_FILE = BASE / "07-kpis" / "weekly-kpi-data.csv"
JOB_QUEUE_DB = BASE / "venture_jobs.db"
HTML_FILE = pathlib.Path(__file__).parent / "dashboard.html"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
REVENUE_TARGET = int(os.environ.get("REVENUE_TARGET", 10000))
PROSPECT_FIELDS = [
    "name",
    "company",
    "role",
    "industry",
    "pain_point",
    "linkedin_url",
    "email",
    "status",
]


# ── Data helpers ──────────────────────────────────────────────────────────────


def get_kpi_data() -> dict:
    revenue = reply_rate = 0
    if KPI_FILE.exists():
        with open(KPI_FILE, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if rows:
            last = rows[-1]
            try:
                revenue = float(last.get("monthly_revenue", 0) or 0)
            except ValueError:
                pass
            recent4 = rows[-4:]
            try:
                out = sum(int(r.get("outreach_sent", 0) or 0) for r in recent4)
                rep = sum(int(r.get("positive_replies", 0) or 0) for r in recent4)
                reply_rate = rep / out * 100 if out else 0
            except ValueError:
                pass

    pending = 0
    if PROSPECTS_FILE.exists():
        with open(PROSPECTS_FILE, newline="", encoding="utf-8") as f:
            pending = sum(
                1 for r in csv.DictReader(f) if r.get("status", "").lower() == "pending"
            )

    return {
        "revenue": revenue,
        "gap": max(REVENUE_TARGET - revenue, 0),
        "pct": round(revenue / REVENUE_TARGET * 100, 1) if REVENUE_TARGET else 0,
        "reply_rate": round(reply_rate, 1),
        "pending_prospects": pending,
        "target": REVENUE_TARGET,
    }


def get_prospects() -> list:
    if not PROSPECTS_FILE.exists():
        return []
    with open(PROSPECTS_FILE, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def get_env_status() -> dict:
    cfg = RuntimeConfig.from_env()
    status = build_config_status(cfg)
    return {
        "OpenAI": status["OPENAI_API_KEY"],
        "Hunter": status["HUNTER_API_KEY"],
        "Resend": status["RESEND_API_KEY"],
        "Notion": status["NOTION_API_KEY"],
        "Airtable": status["AIRTABLE_API_KEY"],
    }


def get_job_queue_status() -> dict:
    """Get job queue statistics from SQLite database."""
    if not JOB_QUEUE_DB.exists():
        return {
            "pending": 0,
            "in_progress": 0,
            "completed": 0,
            "failed": 0,
            "abandoned": 0,
            "total": 0,
        }

    try:
        queue = get_queue(db_path=str(JOB_QUEUE_DB))
        summary = queue.get_summary()
        total = sum(summary.values())
        return {
            "pending": summary.get("pending", 0),
            "in_progress": summary.get("in_progress", 0),
            "completed": summary.get("completed", 0),
            "failed": summary.get("failed", 0),
            "abandoned": summary.get("abandoned", 0),
            "total": total,
        }
    except Exception as e:
        return {
            "pending": 0,
            "in_progress": 0,
            "completed": 0,
            "failed": 0,
            "abandoned": 0,
            "total": 0,
            "error": str(e),
        }


def get_funnel_status() -> dict:
    try:
        queue = get_queue(db_path=str(JOB_QUEUE_DB))
        return queue.get_funnel_counts(days=7)
    except Exception as e:
        return {"error": str(e)}


def get_blocked_status() -> list:
    try:
        queue = get_queue(db_path=str(JOB_QUEUE_DB))
        return queue.get_blocked_prospects(limit=25)
    except Exception:
        return []


def score_idea_openai(idea: str) -> str:
    if not OPENAI_API_KEY:
        return "⚠  OPENAI_API_KEY not set. Add it to your .env file and restart the dashboard."
    prompt = (
        f"Score this venture idea against 8 criteria.\n\nIDEA: {idea}\n\n"
        "Criteria (score each):\n"
        "1. Pain Level (1–10)\n"
        "2. Willingness to Pay (1–10)\n"
        "3. Market Size (Small / Medium / Large)\n"
        "4. Speed to First Revenue (Fast <30d / Medium / Slow)\n"
        "5. Competition Level (Low / Medium / High)\n"
        "6. Founder Fit (1–10)\n"
        "7. Proof of Demand (Yes / Maybe / No)\n"
        "8. Scalability (1–10)\n\n"
        "Format: one scored line per criterion, then a blank line, "
        "then VERDICT: GO / RESEARCH / SKIP with a 1-sentence reason."
    )
    try:
        r = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 400,
                "temperature": 0.4,
            },
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"Error calling OpenAI: {e}"


def add_prospect_to_csv(data: dict) -> None:
    """
    Side-channel writes to prospects.csv are disabled: the governed path is
    prospect_builder + prospect_gate (audit + ELIGIBLE projection). Use run_daily
    --generate-prospects or prospect_builder.py from the repo root.
    """
    raise RuntimeError(
        "add_prospect_to_csv is disabled: use prospect_builder / run_daily "
        "to write DATA_BASE/06-sales/prospects.csv under gate + audit."
    )


# ── HTTP Request Handler ──────────────────────────────────────────────────────


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress default access log

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            html = HTML_FILE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
        elif path == "/api/kpis":
            self._send_json(get_kpi_data())
        elif path == "/api/prospects":
            self._send_json(get_prospects())
        elif path == "/api/env-status":
            self._send_json(get_env_status())
        elif path == "/api/job-queue":
            self._send_json(get_job_queue_status())
        elif path == "/api/funnel":
            self._send_json(get_funnel_status())
        elif path == "/api/blocked":
            self._send_json(get_blocked_status())
        elif path == "/api/operator-status":
            self._send_json(
                operator_status_payload(
                    repo_root=BASE,
                    data_base=resolve_data_base(BASE),
                )
            )
        elif path.startswith("/api/opportunity"):
            q = parse_qs(urlparse(self.path).query)
            bid = (q.get("business_id") or q.get("id") or [""])[0]
            try:
                qn = get_queue(db_path=str(JOB_QUEUE_DB))
                self._send_json(qn.get_opportunity(bid) or {"error": "not_found"})
            except Exception as e:
                self._send_json({"error": str(e)})
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/run-pipeline":
            try:
                env = os.environ.copy()
                env["VENTURE_CANONICAL_ENTRY"] = "1"
                result = subprocess.run(
                    [PYTHON, RUN_DAILY, "--execute"],
                    capture_output=True,
                    text=True,
                    timeout=300,
                    cwd=str(BASE),
                    env=env,
                )
                out = result.stdout
                if result.returncode != 0 and result.stderr:
                    out += "\n[stderr]\n" + result.stderr
                self._send_json({"output": out or "Pipeline completed with no output."})
            except subprocess.TimeoutExpired:
                self._send_json({"output": "Pipeline timed out after 5 minutes."})
            except Exception as e:
                self._send_json({"output": f"Error running pipeline: {e}"})
        elif path == "/score-idea":
            data = self._read_json()
            self._send_json({"result": score_idea_openai(data.get("idea", ""))})
        elif path == "/add-prospect":
            data = self._read_json()
            try:
                add_prospect_to_csv(data)
                self._send_json({"success": True})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=500)
        elif path == "/webhooks/resend":
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b""
            try:
                qn = get_queue(db_path=str(JOB_QUEUE_DB))
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, status=500)
                return
            try:
                ok, data, err = verify_resend_webhook(self.headers, raw)
                if not ok:
                    qn.record_webhook_dlq(
                        "resend_webhook_verify",
                        raw.decode("utf-8", errors="replace")[:50000],
                        (err or "verify_failed")[:2000],
                    )
                    self._send_json(
                        {"ok": False, "error": err, "dlq": True}, status=202
                    )
                    return
                try:
                    result = process_resend_event(data, db_path=str(JOB_QUEUE_DB))
                    if isinstance(result, dict) and result.get("ok") is False:
                        qn.record_webhook_dlq(
                            "resend_webhook_process",
                            json.dumps(data)[:50000],
                            str(result.get("error", "process_failed"))[:2000],
                        )
                        self._send_json({**result, "dlq": True}, status=202)
                        return
                    self._send_json(result)
                except LifecycleEventValidationError as err:
                    qn.record_webhook_dlq(
                        "resend_webhook_process",
                        json.dumps(data)[:50000],
                        str(err)[:2000],
                    )
                    self._send_json(
                        {
                            "ok": False,
                            "error": "lifecycle_validation_failed",
                            "dlq": True,
                        },
                        status=202,
                    )
                except Exception as e:
                    qn.record_webhook_dlq(
                        "resend_webhook_process",
                        json.dumps(data)[:50000],
                        str(e)[:2000],
                    )
                    self._send_json(
                        {"ok": False, "error": str(e), "dlq": True}, status=202
                    )
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, status=500)
        else:
            self.send_response(404)
            self.end_headers()


# ── Entry point ───────────────────────────────────────────────────────────────


def main():
    server = HTTPServer((DASHBOARD_BIND, PORT), Handler)
    display_host = "localhost" if DASHBOARD_BIND == "127.0.0.1" else DASHBOARD_BIND
    url = f"http://{display_host}:{PORT}"
    print(f"\n  Venture OS Dashboard")
    print(f"  {'─' * 34}")
    print(f"  URL  : {url}")
    print(f"  Stop : Ctrl+C\n")
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Dashboard stopped.")


if __name__ == "__main__":
    if os.getenv("VENTURE_CANONICAL_ENTRY", "0") != "1":
        raise RuntimeError("Execution must originate from canonical orchestrator")
    main()
