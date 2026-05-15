"""
Resend webhook processing — single module for verify + apply (Phase B).

Dashboard and DLQ replay call into here; do not duplicate Resend response logic elsewhere.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any

from lifecycle_engine import LifecycleEventType
from lifecycle_validation import LifecycleEventValidationError

from job_queue import JobQueue

logger = logging.getLogger(__name__)


def verify_resend_webhook(headers: Any, body: bytes) -> tuple[bool, dict, str]:
    """
    Resend delivers Svix-signed webhooks. Require RESEND_WEBHOOK_SIGNING_SECRET unless
    VENTURE_ALLOW_INSECURE_WEBHOOKS=true (local dev only).
    """
    if not body:
        return False, {}, "empty body"
    insecure = os.environ.get("VENTURE_ALLOW_INSECURE_WEBHOOKS", "").lower() in (
        "1",
        "true",
        "yes",
    )
    if insecure:
        try:
            return True, json.loads(body.decode("utf-8")), ""
        except json.JSONDecodeError as exc:
            return False, {}, f"invalid json: {exc}"
    secret = (
        os.environ.get("RESEND_WEBHOOK_SIGNING_SECRET", "").strip()
        or os.environ.get("RESEND_WEBHOOK_SECRET", "").strip()
    )
    if not secret:
        return False, {}, (
            "Missing RESEND_WEBHOOK_SIGNING_SECRET (from Resend → Webhooks). "
            "For local testing only, set VENTURE_ALLOW_INSECURE_WEBHOOKS=true in .env."
        )
    try:
        from svix.webhooks import Webhook

        hdrs = {k: v for k, v in headers.items()}
        payload = Webhook(secret).verify(body.decode("utf-8"), hdrs)
        if isinstance(payload, str):
            payload = json.loads(payload)
        if not isinstance(payload, dict):
            return False, {}, "unexpected webhook payload shape"
        return True, payload, ""
    except Exception as exc:  # noqa: BLE001
        return False, {}, str(exc)


def _extract_email_from_event(payload: dict) -> str:
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    to_field = data.get("to") or payload.get("to")
    if isinstance(to_field, list) and to_field:
        return str(to_field[0]).strip().lower()
    if isinstance(to_field, str):
        return to_field.strip().lower()
    return ""


def _extract_event_id(payload: dict) -> str:
    eid = str(payload.get("id") or "").strip()
    if eid:
        return eid
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("email_id", "id", "message_id"):
            v = str(data.get(key) or "").strip()
            if v:
                return v
    base = json.dumps(
        {
            "t": payload.get("type"),
            "to": _extract_email_from_event(payload),
            "created_at": str((payload.get("data") or {}).get("created_at", "")),
        },
        sort_keys=True,
    )
    return "synthetic:" + hashlib.sha256(base.encode("utf-8")).hexdigest()[:40]


def _evaluate_delivery_health_queue(queue: JobQueue) -> None:
    """Log SOFT/HARD delivery health from rolling ratios; HARD may freeze outreach."""
    if os.environ.get("VENTURE_DELIVERY_HEALTH_GATES", "true").lower() not in (
        "1",
        "true",
        "yes",
    ):
        return
    min_sends = int(os.environ.get("VENTURE_DELIVERY_HEALTH_MIN_SENDS", "20") or 20)
    days = int(os.environ.get("VENTURE_DELIVERY_METRICS_DAYS", "7") or 7)
    m = queue.get_delivery_ratio_metrics(days)
    if int(m.get("sent") or 0) < min_sends:
        return
    bh = float(os.environ.get("VENTURE_BOUNCE_HARD_RATIO", "0.12") or 0.12)
    ch = float(os.environ.get("VENTURE_COMPLAINT_HARD_RATIO", "0.003") or 0.003)
    bw = float(os.environ.get("VENTURE_BOUNCE_WARN_RATIO", "0.06") or 0.06)
    cw = float(os.environ.get("VENTURE_COMPLAINT_WARN_RATIO", "0.001") or 0.001)
    br = float(m.get("bounce_ratio") or 0.0)
    cr = float(m.get("complaint_ratio") or 0.0)
    detail = json.dumps(m)[:2000]
    if br >= bh:
        queue.log_block(
            "system",
            "delivery_health",
            "bounce_ratio_hard_stop",
            detail,
            block_type="DELIVERY_BLOCK",
            severity="HARD",
        )
        queue.log_decision(
            "delivery_health",
            "system",
            "bounce_ratio_hard_stop",
            [detail[:500]],
        )
    elif cr >= ch:
        queue.log_block(
            "system",
            "delivery_health",
            "complaint_ratio_hard_stop",
            detail,
            block_type="DELIVERY_BLOCK",
            severity="HARD",
        )
        queue.log_decision(
            "delivery_health",
            "system",
            "complaint_ratio_hard_stop",
            [detail[:500]],
        )
    elif br >= bw:
        queue.log_block(
            "system",
            "delivery_health",
            "bounce_ratio_soft_warn",
            detail,
            block_type="DELIVERY_WARN",
            severity="SOFT",
        )
        logger.warning("delivery_health soft warn: bounce_ratio br=%.4f", br)
    elif cr >= cw:
        queue.log_block(
            "system",
            "delivery_health",
            "complaint_ratio_soft_warn",
            detail,
            block_type="DELIVERY_WARN",
            severity="SOFT",
        )
        logger.warning("delivery_health soft warn: complaint_ratio cr=%.4f", cr)


def process_resend_event(payload: dict, *, db_path: str | None = None) -> dict:
    """
    Apply a Resend-style webhook payload to trust + lifecycle + funnel.
    Idempotent on Svix/Resend ``event_id`` (duplicate deliveries are no-ops).
    """
    event_type = str(payload.get("type", "")).lower()
    email = _extract_email_from_event(payload)
    if not event_type:
        return {"ok": False, "error": "missing event type"}
    if not email:
        return {"ok": False, "error": "missing recipient email"}

    event_id = _extract_event_id(payload)
    raw_payload = json.dumps(payload, separators=(",", ":"), sort_keys=True)[:50000]

    repo_root = Path(__file__).resolve().parents[1]
    default_db = repo_root / "venture_jobs.db"
    queue = JobQueue(str(db_path or default_db))
    if not queue.try_register_resend_webhook_event(event_id, event_type, email, raw_payload):
        return {
            "ok": True,
            "duplicate": True,
            "event_id": event_id,
            "event_type": event_type,
            "email": email,
        }

    suppressed_types = {
        "email.bounced": "hard_bounce",
        "email.hard_bounced": "hard_bounce",
        "email.bounce": "hard_bounce",
        "email.complained": "complaint",
        "email.complaint": "complaint",
        "audience.unsubscribed": "unsubscribe",
    }
    if event_type in suppressed_types:
        reason = suppressed_types[event_type]
        queue.suppress_email(
            email=email,
            reason=reason,
            source="resend_webhook",
            notes=f"event_id:{event_id}",
        )

    if event_type == "email.delivery_delayed":
        bid = queue.resolve_lifecycle_business_id(email)
        queue.record_funnel_event(
            prospect_id=bid,
            stage="delivery_delayed",
            metadata={"type": event_type, "email": email, "event_id": event_id},
        )
        queue.log_decision(
            "outreach_event",
            bid,
            "delivery_delayed",
            [f"event_type:{event_type}", f"email:{email}"],
        )
        return {
            "ok": True,
            "event_type": event_type,
            "email": email,
            "stage": "delivery_delayed",
            "business_id": bid,
            "event_id": event_id,
        }

    stage_map = {
        "email.delivered": "delivered",
        "email.opened": "opened",
        "email.clicked": "clicked",
        "email.replied": "replied",
        "email.bounced": "bounced",
        "email.hard_bounced": "bounced",
        "email.bounce": "bounced",
        "email.complained": "complained",
        "email.complaint": "complained",
        "audience.unsubscribed": "unsubscribed",
    }
    stage = stage_map.get(event_type, "event_received")
    trust_delta_map = {
        "delivered": 0.05,
        "opened": 0.1,
        "clicked": 0.15,
        "replied": 0.4,
        "bounced": -0.5,
        "complained": -0.7,
        "unsubscribed": -0.6,
    }
    bid = queue.resolve_lifecycle_business_id(email)
    trust_score = queue.record_trust_event(
        business_id=bid,
        event_type=stage,
        trust_delta=trust_delta_map.get(stage, 0.0),
        metadata={"type": event_type, "email": email, "event_id": event_id},
    )
    queue.log_decision(
        "outreach_event",
        bid,
        "event_processed",
        [f"event_type:{event_type}", f"stage:{stage}", f"trust_score:{trust_score:.2f}"],
    )

    lifecycle_map = {
        "delivered": LifecycleEventType.DELIVERED,
        "opened": LifecycleEventType.OPENED,
        "clicked": LifecycleEventType.CLICKED,
        "replied": LifecycleEventType.REPLIED,
        "bounced": LifecycleEventType.BOUNCED,
        "complained": LifecycleEventType.COMPLAINED,
        "unsubscribed": LifecycleEventType.UNSUBSCRIBED,
    }
    if stage in lifecycle_map:
        suppressed = stage in {"bounced", "complained", "unsubscribed"}
        try:
            queue.record_lifecycle_event(
                bid,
                lifecycle_map[stage],
                {"resend_type": event_type, "email": email, "event_id": event_id},
                source="resend_webhook",
                email=email,
                pipeline_stage="blocked_suppressed" if suppressed else "",
                status_reason=f"suppressed:{stage}" if suppressed else "",
                sync_funnel=True,
                validation_mode="webhook",
            )
        except LifecycleEventValidationError as err:
            return {
                "ok": False,
                "error": "lifecycle_validation_failed",
                "reasons": err.reasons,
                "event_type": event_type,
                "email": email,
            }
    else:
        queue.record_funnel_event(
            prospect_id=bid, stage=stage, metadata={"type": event_type, "email": email}
        )

    if event_type in suppressed_types and suppressed_types[event_type] in (
        "hard_bounce",
        "complaint",
    ):
        _evaluate_delivery_health_queue(queue)

    return {
        "ok": True,
        "event_type": event_type,
        "email": email,
        "stage": stage,
        "business_id": bid,
        "event_id": event_id,
    }
