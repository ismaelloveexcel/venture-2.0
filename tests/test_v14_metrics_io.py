from __future__ import annotations

from pathlib import Path

from job_queue import JobQueue
from metrics import canonical_message_hash


def test_canonical_message_hash_matches_job_queue():
    subj = "outbound fit for your venture"
    html = "<p>Hi</p>"
    assert canonical_message_hash(subj, html) == JobQueue.message_hash(subj, html)


def test_atomic_write_creates_file(tmp_path: Path):
    from atomic_io import atomic_write

    p = tmp_path / "nested" / "a.txt"
    atomic_write(p, "hello")
    assert p.read_text(encoding="utf-8") == "hello"


def test_compute_metrics_join(tmp_path: Path):
    from metrics import compute_metrics

    send = tmp_path / "send.csv"
    reply = tmp_path / "reply.csv"
    send.write_text(
        "timestamp_utc,run_id,send_attempt_id,email,company,cohort_id,message_version,message_hash,send_status\n"
        "2026-01-01T00:00:00Z,r1,a1,a@x.com,Co,c1,mv,h1,sent\n",
        encoding="utf-8",
    )
    reply.write_text(
        "logged_at_utc,cohort_id,segment_name,message_version,cta_version,send_window_label,prospect_email,company_name,delivered_utc,reply_first_seen_utc,reply_classification,reply_excerpt,handled_by,notes\n"
        "2026-01-02T00:00:00Z,c1,s,mv,c,w,a@x.com,Co,,,positive_reply,,,\n",
        encoding="utf-8",
    )
    m = compute_metrics(reply, send)
    assert m.delivered == 1
    assert m.positive_replies == 1
    assert m.walkthrough_yes == 0
