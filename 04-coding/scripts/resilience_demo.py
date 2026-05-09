#!/usr/bin/env python
"""
Venture OS — Resilience Integration Demo

This shows how the three new modules work together:
1. resilience.py — automatic retry + rate limiting
2. job_queue.py — fault-tolerant operation tracking
3. logging_config.py — structured file-based logging

To use in your pipeline:

1. Queue jobs before running them:
    job = job_queue.add_job(
        job_id=f"{prospect['name']}_{prospect['company']}_email",
        action=JobAction.EMAIL_LOOKUP,
        prospect_id=prospect.get("id"),
        context={"first_name": first_name, "last_name": last_name, "domain": domain},
    )

2. Run with automatic retry + rate limiting (via decorators):
    @hunter_api_call  # Max 0.5 req/sec, auto-retry on 429/timeout
    def _hunter_request(...):
        return httpx.get(...)

3. Log results to file:
    logger.info(f"Email found: {email}")
    logger.warning(f"Hunter.io rate limited")
    logger.error(f"Hunter.io failed after 3 retries")

4. Track job completion:
    if email_found:
        job_queue.complete_job(job.id, result=email)
    else:
        job_queue.fail_job(job.id, error="Email not found", retry=False)

5. Inspect what failed and retry:
    failed = job_queue.get_failed_jobs()
    for job in failed:
        print(f"Retry: {job.id} (attempt {job.retry_count+1})")
        # Re-run the job

6. Get statistics:
    summary = job_queue.get_summary()
    print(f"Pending: {summary['pending']}, Completed: {summary['completed']}, Failed: {summary['failed']}")

---

Example: Processing 50 prospects with resilience
"""

import sys
import pathlib
from datetime import datetime

# Add MCP server to path FIRST
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "venture-mcp-server"))

from resilience import with_retry, RateLimiter
from job_queue import get_queue, JobAction, JobStatus
from logging_config import setup_logging

# Initialize
logger = setup_logging(log_dir="logs", name="demo")
job_queue = get_queue(db_path="venture_jobs.db")

logger.info("="*80)
logger.info("DEMO: Resilience + Job Queue Integration")
logger.info("="*80)

# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO: Process 50 prospects, some fail, we retry them later
# ──────────────────────────────────────────────────────────────────────────────

logger.info("\nStep 1: Queue 5 sample jobs")
prospects = [
    {"id": "1", "name": "Alice", "company": "Acme Inc", "domain": "acme.com"},
    {"id": "2", "name": "Bob", "company": "Beta Corp", "domain": "beta.com"},
    {"id": "3", "name": "Carol", "company": "Gamma Ltd", "domain": "gamma.com"},
    {"id": "4", "name": "David", "company": "Delta Org", "domain": "delta.com"},
    {"id": "5", "name": "Eve", "company": "Epsilon Co", "domain": "epsilon.com"},
]

for p in prospects:
    job = job_queue.add_job(
        job_id=f"{p['id']}_email_lookup_{datetime.now().timestamp()}",
        action=JobAction.EMAIL_LOOKUP,
        prospect_id=p['id'],
        context={"name": p['name'], "company": p['company'], "domain": p['domain']},
        max_retries=3,
    )
    logger.info(f"  Queued: {job.id}")

# ──────────────────────────────────────────────────────────────────────────────
# Step 2: Simulate processing (some succeed, some fail)
# ──────────────────────────────────────────────────────────────────────────────

logger.info("\nStep 2: Process pending jobs (simulate successes + failures)")
pending = job_queue.get_pending_jobs(limit=3)
for job in pending:
    logger.info(f"  Processing: {job.id}")
    job_queue.start_job(job.id)
    
    # Simulate: 2 succeed, 1 fails
    import random
    if random.random() > 0.33:  # 67% success
        job_queue.complete_job(job.id, result="alice@acme.com")
        logger.info(f"    ✓ Completed with result: alice@acme.com")
    else:
        job_queue.fail_job(job.id, error="Rate limited (HTTP 429)", retry=True)
        logger.info(f"    ✗ Failed, marked for retry")

# ──────────────────────────────────────────────────────────────────────────────
# Step 3: Check failed jobs (next run will retry these)
# ──────────────────────────────────────────────────────────────────────────────

logger.info("\nStep 3: Check what failed and needs retry")
failed = job_queue.get_failed_jobs()
for job in failed:
    logger.info(f"  Retry candidate: {job.id}")
    logger.info(f"    Error: {job.error}")
    logger.info(f"    Attempts: {job.retry_count}/{job.max_retries}")

# ──────────────────────────────────────────────────────────────────────────────
# Step 4: Get summary stats
# ──────────────────────────────────────────────────────────────────────────────

logger.info("\nStep 4: Queue Summary")
summary = job_queue.get_summary()
for status, count in summary.items():
    logger.info(f"  {status.upper()}: {count}")

logger.info("\n" + "="*80)
logger.info("Demo complete. Check logs/demo-*.log for full output.")
logger.info("="*80)

print("\n✓ Demo ran successfully. Check the logs/ folder for detailed output.")
