"""Deterministic client dashboard renderer (render-only)."""

from __future__ import annotations

from typing import Any


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _extract_metrics(run_report: dict[str, Any]) -> dict[str, Any]:
    outbound = run_report.get("outbound") if isinstance(run_report, dict) else {}
    outbound = outbound if isinstance(outbound, dict) else {}
    telemetry = outbound.get("pipeline_telemetry")
    telemetry = telemetry if isinstance(telemetry, dict) else {}
    run_health = telemetry.get("run_health")
    run_health = run_health if isinstance(run_health, dict) else {}

    sent = _safe_int(run_health.get("sent"))
    replies = _safe_int(run_health.get("replies"))
    qualified = _safe_int(run_health.get("qualified"))
    reply_rate = _safe_float(
        run_health.get("reply_rate_estimate") or run_health.get("reply_rate")
    )
    if sent > 0 and reply_rate <= 0.0:
        reply_rate = replies / sent
    qualification_rate = (qualified / sent) if sent > 0 else 0.0

    return {
        "sent": sent,
        "replies": replies,
        "qualified": qualified,
        "reply_rate": reply_rate,
        "qualification_rate": qualification_rate,
    }


def _extract_ranked_signals(projection: dict[str, Any]) -> list[dict[str, Any]]:
    ranked = projection.get("ranked_signals") if isinstance(projection, dict) else None
    if isinstance(ranked, list):
        return [x for x in ranked if isinstance(x, dict)]
    meta = projection.get("insight_metadata") if isinstance(projection, dict) else None
    if isinstance(meta, dict) and isinstance(meta.get("ranked_signals"), list):
        return [x for x in meta["ranked_signals"] if isinstance(x, dict)]
    return []


def _render_signal_rows(signals: list[dict[str, Any]]) -> str:
    if not signals:
        return "<li>No ranked signals available.</li>"
    rows: list[str] = []
    for signal in signals:
        title = str(
            signal.get("title") or signal.get("name") or signal.get("id") or "signal"
        )
        sev = (
            signal.get("severity_label")
            or signal.get("severity")
            or signal.get("score")
            or "n/a"
        )
        rows.append(f"<li><strong>{title}</strong> <span>severity={sev}</span></li>")
    return "".join(rows)


def render_client_dashboard(
    run_report: dict[str, Any],
    projection: dict[str, Any],
    output_path: Any,
    client_id: str,
    comparison: dict[str, Any] | None = None,
    health: dict[str, Any] | None = None,
) -> str:
    """Render dashboard HTML. This function does not write files."""
    metrics = _extract_metrics(run_report)
    signals = _extract_ranked_signals(projection)
    run_id = str(run_report.get("run_id") or "unknown")
    timestamp_utc = str(run_report.get("timestamp_utc") or "unknown")

    cmp = comparison or {
        "trend": "BASELINE",
        "metrics_delta": {},
        "signal_delta": {},
        "notable_changes": ["No comparison data"],
        "breakpoints": [],
    }
    hlth = health or {
        "health_score": 70,
        "label": "BASELINE",
        "drivers": ["No health data"],
        "risk_flags": ["no_history"],
    }

    notable = (
        "".join(f"<li>{str(x)}</li>" for x in list(cmp.get("notable_changes") or []))
        or "<li>None</li>"
    )
    breakpoints = (
        "".join(f"<li>{str(x)}</li>" for x in list(cmp.get("breakpoints") or []))
        or "<li>None</li>"
    )
    drivers = (
        "".join(f"<li>{str(x)}</li>" for x in list(hlth.get("drivers") or []))
        or "<li>None</li>"
    )
    risks = (
        "".join(f"<li>{str(x)}</li>" for x in list(hlth.get("risk_flags") or []))
        or "<li>None</li>"
    )

    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Client Dashboard</title>
  <style>
    body {{ font-family: Segoe UI, sans-serif; margin: 24px; color: #222; }}
    h1, h2 {{ margin: 0 0 12px 0; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(200px, 1fr)); gap: 12px; }}
    .card {{ border: 1px solid #ddd; border-radius: 8px; padding: 12px; background: #fff; }}
    ul {{ margin: 8px 0 0 18px; }}
    code {{ background: #f5f5f5; padding: 2px 6px; border-radius: 4px; }}
  </style>
</head>
<body>
  <h1>Client Campaign Dashboard</h1>
  <p>client_id=<code>{client_id}</code> run_id=<code>{run_id}</code> generated=<code>{timestamp_utc}</code></p>

  <h2>Core Metrics</h2>
  <div class=\"grid\">
    <div class=\"card\">sent: <strong>{metrics['sent']}</strong></div>
    <div class=\"card\">replies: <strong>{metrics['replies']}</strong></div>
    <div class=\"card\">qualified: <strong>{metrics['qualified']}</strong></div>
    <div class=\"card\">reply_rate: <strong>{metrics['reply_rate']:.4f}</strong></div>
    <div class=\"card\">qualification_rate: <strong>{metrics['qualification_rate']:.4f}</strong></div>
  </div>

  <h2>Ranked Signals</h2>
  <div class=\"card\">
    <ul>{_render_signal_rows(signals)}</ul>
  </div>

  <h2>Comparison</h2>
  <div class=\"grid\">
    <div class=\"card\">trend: <strong>{cmp.get('trend', 'BASELINE')}</strong></div>
    <div class=\"card\">metrics_delta: <code>{cmp.get('metrics_delta', {})}</code></div>
    <div class=\"card\">signal_delta: <code>{cmp.get('signal_delta', {})}</code></div>
    <div class=\"card\"><strong>notable_changes</strong><ul>{notable}</ul></div>
    <div class=\"card\"><strong>breakpoints</strong><ul>{breakpoints}</ul></div>
  </div>

  <h2>Health</h2>
  <div class=\"grid\">
    <div class=\"card\">score: <strong>{_safe_int(hlth.get('health_score'))}</strong></div>
    <div class=\"card\">label: <strong>{hlth.get('label', 'BASELINE')}</strong></div>
    <div class=\"card\"><strong>drivers</strong><ul>{drivers}</ul></div>
    <div class=\"card\"><strong>risk_flags</strong><ul>{risks}</ul></div>
  </div>
</body>
</html>
"""
