#!/usr/bin/env python
"""
Comprehensive Integration Test — Verify all three resilience modules work correctly
"""
import sys
import pathlib
import sqlite3

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "venture-mcp-server"))

from resilience import RateLimiter, with_retry
from job_queue import get_queue, JobAction, JobStatus
from lifecycle_engine import LifecycleEventType, replay_outreach_state, replay_outreach_state_from_rows
from lifecycle_validation import LifecycleEventValidationError
from logging_config import setup_logging
import time

# Setup
logger = setup_logging(log_dir="logs", name="integration-test")
test_db = pathlib.Path("venture_jobs.integration.db")
if test_db.exists():
    test_db.unlink()
queue = get_queue(db_path=str(test_db))

logger.info("="*80)
logger.info("INTEGRATION TEST: Resilience + Job Queue + Logging")
logger.info("="*80)
failed_assertions = 0

# Test 1: Rate Limiter
logger.info("\n[TEST 1] Rate Limiter")
limiter = RateLimiter(max_per_second=2.0, burst=1)
logger.info(f"  Created limiter: max 2 requests/sec, burst 1")

start = time.time()
for i in range(3):
    limiter.acquire()
    elapsed = time.time() - start
    logger.info(f"  Request {i+1} at {elapsed:.2f}s")
if time.time() - start >= 0.9:  # Should take ~1 second for 3 requests at 2 req/sec
    logger.info("  [PASS] Rate limiting works correctly")
else:
    logger.error("  [FAIL] Rate limiting failed")
    failed_assertions += 1

# Test 2: Retry Decorator
logger.info("\n[TEST 2] Retry Decorator")
attempt_count = [0]

@with_retry(max_attempts=3, initial_wait=0.1, retryable_exceptions=(TimeoutError,))
def flaky_function():
    attempt_count[0] += 1
    if attempt_count[0] < 3:
        raise TimeoutError(f"Attempt {attempt_count[0]} failed")
    return "Success on attempt 3"

try:
    result = flaky_function()
    logger.info(f"  Function succeeded after {attempt_count[0]} attempts")
    if attempt_count[0] == 3:
        logger.info("  [PASS] Retry logic works correctly")
    else:
        logger.error(f"  [FAIL] Expected 3 attempts, got {attempt_count[0]}")
        failed_assertions += 1
except Exception as e:
    logger.error(f"  [FAIL] Retry failed: {e}")
    failed_assertions += 1

# Test 3: Job Queue
logger.info("\n[TEST 3] Job Queue Operations")
queue.cleanup_old_jobs(days=0)  # Clear all old jobs first (including from demo/earlier tests)

job1 = queue.add_job(
    job_id=f"integration_test_email_1_{time.time()}",
    action=JobAction.EMAIL_LOOKUP,
    prospect_id="prospect_1",
    context={"domain": "test.com", "first_name": "John"},
    max_retries=2,
)
logger.info(f"  Queued job: {job1.id}")

job2 = queue.add_job(
    job_id=f"integration_test_email_2_{time.time()}",
    action=JobAction.EMAIL_LOOKUP,
    prospect_id="prospect_2",
    context={"domain": "example.com", "first_name": "Jane"},
)
logger.info(f"  Queued job: {job2.id}")

# Get pending (should be only the 2 we just added)
pending = queue.get_pending_jobs()
logger.info(f"  Pending jobs: {len(pending)}")
if len(pending) == 2:
    logger.info("  [PASS] Job queueing works")
else:
    logger.error(f"  [FAIL] Expected 2 pending, got {len(pending)}")
    failed_assertions += 1

# Mark first as in-progress
queue.start_job(job1.id)
queue.complete_job(job1.id, result="john@test.com")
logger.info(f"  Completed: {job1.id}")

# Fail the second (should be retryable)
queue.fail_job(job2.id, error="HTTP 429 Rate Limited", retry=True)
logger.info(f"  Failed (retryable): {job2.id}")

# Check failed jobs
failed = queue.get_failed_jobs()
logger.info(f"  Failed jobs eligible for retry: {len(failed)}")
if len(failed) == 1 and failed[0].id == job2.id:
    logger.info("  [PASS] Failed job retry tracking works")
else:
    logger.error(f"  [FAIL] Failed job tracking failed")
    failed_assertions += 1

# Get summary
summary = queue.get_summary()
logger.info(f"  Queue summary: {summary}")
if summary['completed'] == 1 and summary['failed'] == 1 and summary['pending'] <= 1:
    logger.info("  [PASS] Job queue statistics correct")
else:
    logger.error(f"  [FAIL] Queue summary incorrect")
    failed_assertions += 1

# Test 4: Lifecycle replay + opportunity record
logger.info("\n[TEST 4] Lifecycle event engine (replayable state)")
queue.record_lifecycle_event(
    "lc_test_prospect",
    LifecycleEventType.PROSPECT_LOADED,
    payload={"company": "TestCo"},
    name="Test",
    company="TestCo",
    email="t@test.co",
    pipeline_stage="loaded",
)
queue.record_lifecycle_event(
    "lc_test_prospect",
    LifecycleEventType.OUTREACH_SENT,
    payload={"email": "t@test.co"},
    pipeline_stage="sent",
    sync_funnel=False,
)
queue.record_lifecycle_event(
    "lc_test_prospect",
    LifecycleEventType.REPLIED,
    payload={},
    pipeline_stage="",
    sync_funnel=False,
)
snap = queue.get_opportunity("lc_test_prospect")
if snap and snap.get("state") == "WARM":
    logger.info("  [PASS] Reply event transitions COLD -> WARM via replay")
else:
    logger.error(f"  [FAIL] Expected outreach state WARM, got {snap}")
    failed_assertions += 1

pure = replay_outreach_state(
    [
        ("prospect_loaded", "{}"),
        ("replied", "{}"),
    ]
)
if pure == "WARM":
    logger.info("  [PASS] Pure replay_outreach_state matches")
else:
    logger.error(f"  [FAIL] Pure replay expected WARM, got {pure}")
    failed_assertions += 1

try:
    queue.record_lifecycle_event(
        "lc_test_prospect",
        LifecycleEventType.REPLIED,
        payload={},
        sync_funnel=False,
    )
    logger.error("  [FAIL] Duplicate replied should be rejected")
    failed_assertions += 1
except LifecycleEventValidationError:
    logger.info("  [PASS] Duplicate singleton lifecycle event rejected")

# Snapshot vs full replay parity (20 events)
snap_bid = "snap_replay_test"
queue.record_lifecycle_event(snap_bid, LifecycleEventType.PROSPECT_LOADED, {"c": "x"}, pipeline_stage="loaded")
for _ in range(17):
    queue.record_lifecycle_event(
        snap_bid,
        LifecycleEventType.MESSAGE_DRAFTED,
        {"evidence_confidence": 0.65},
        pipeline_stage="drafted",
        sync_funnel=False,
    )
queue.record_lifecycle_event(
    snap_bid,
    LifecycleEventType.OUTREACH_SENT,
    {"email": "s@test.co"},
    pipeline_stage="sent",
    sync_funnel=False,
)
queue.record_lifecycle_event(snap_bid, LifecycleEventType.REPLIED, {}, sync_funnel=False)
with sqlite3.connect(str(test_db)) as _conn:
    opp_id = queue.opportunity_id_for(snap_bid)
    ev_rows = queue._fetch_lifecycle_rows(_conn, opp_id)
    snap = queue._get_lifecycle_snapshot(_conn, opp_id)
full_s, _ = replay_outreach_state_from_rows(ev_rows, None)
snap_s, _ = replay_outreach_state_from_rows(ev_rows, snap)
if full_s == snap_s:
    logger.info("  [PASS] Snapshot tail replay matches full replay")
else:
    logger.error(f"  [FAIL] Snapshot mismatch full={full_s} snap_replay={snap_s}")
    failed_assertions += 1

# Test 6: Logging
logger.info("\n[TEST 6] Logging to File")
logger.debug("This is a DEBUG message")
logger.info("This is an INFO message")
logger.warning("This is a WARNING message")
logger.error("This is an ERROR message")
logger.info("  [PASS] All log levels working")

logger.info("\n" + "="*80)
if failed_assertions == 0:
    logger.info("INTEGRATION TEST COMPLETE - ALL TESTS PASSED")
else:
    logger.error(f"INTEGRATION TEST COMPLETE - {failed_assertions} ASSERTION(S) FAILED")
logger.info("="*80)

if failed_assertions == 0:
    print("\n[PASS] All integration tests passed!")
else:
    print(f"\n[FAIL] {failed_assertions} integration assertion(s) failed.")
print("\nKey artifacts created:")
print("  - logs/integration-test-*.log (structured logging)")
print("  - venture_jobs.db (SQLite job queue)")
print("  - See logs for full details")
if failed_assertions > 0:
    sys.exit(1)
