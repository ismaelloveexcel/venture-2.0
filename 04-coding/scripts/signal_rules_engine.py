"""
Signal Rules Engine — Deterministic failure detection
Used by: venture_pipeline.py (before sending), dashboard_streamlit.py (for diagnostics)
Reads: execution_state.json
"""

import json
from pathlib import Path
from dataclasses import dataclass
from enum import Enum


class RuleSeverity(Enum):
    HARD_STOP = "HARD_STOP"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class RuleResult:
    triggered: bool
    severity: RuleSeverity
    rule_id: str
    diagnosis: str
    operator_action: str


class SignalRulesEngine:
    def __init__(self, state_file: str | Path = None):
        if state_file is None:
            state_file = Path(__file__).parent.parent / "execution_state.json"
        self.state_file = Path(state_file)

    def load_state(self) -> dict:
        """Load current execution state"""
        if not self.state_file.exists():
            return {}
        try:
            with open(self.state_file, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    def evaluate_all(self) -> tuple[RuleSeverity, list[RuleResult]]:
        """
        Evaluate all rules, return highest severity + all triggered rules

        Returns:
            (highest_severity, list of all triggered rules)
        """
        state = self.load_state()
        results = []

        # Evaluate HARD STOP rules first
        for rule in self._hard_stop_rules():
            result = rule(state)
            if result.triggered:
                results.append(result)

        # Then WARNING rules
        for rule in self._warning_rules():
            result = rule(state)
            if result.triggered:
                results.append(result)

        # Then INFO rules
        for rule in self._info_rules():
            result = rule(state)
            if result.triggered:
                results.append(result)

        # Determine highest severity
        highest = RuleSeverity.INFO
        for result in results:
            if result.severity == RuleSeverity.HARD_STOP:
                highest = RuleSeverity.HARD_STOP
                break
            elif (
                result.severity == RuleSeverity.WARNING
                and highest != RuleSeverity.HARD_STOP
            ):
                highest = RuleSeverity.WARNING

        return highest, results

    def should_pause_execution(self) -> bool:
        """Return True if any HARD_STOP rule is triggered"""
        severity, _ = self.evaluate_all()
        return severity == RuleSeverity.HARD_STOP

    def get_primary_diagnosis(self) -> str:
        """Return the most critical diagnosis for dashboard display"""
        severity, results = self.evaluate_all()

        if not results:
            return "✅ All systems normal"

        # Return the first HARD_STOP or WARNING rule
        for result in results:
            if result.severity in (RuleSeverity.HARD_STOP, RuleSeverity.WARNING):
                return f"{result.rule_id}: {result.diagnosis}"

        # Fall back to first INFO
        if results:
            return f"{results[0].rule_id}: {results[0].diagnosis}"

        return "No diagnoses available"

    # ========== HARD STOP RULES ==========

    def _hard_stop_rules(self) -> list:
        return [
            self._hs1_zero_replies_after_25_sends,
            self._hs3_approval_rate_catastrophically_low,
            self._hs4_send_success_rate_below_threshold,
        ]

    def _hs1_zero_replies_after_25_sends(self, state: dict) -> RuleResult:
        """HS-1: Zero replies after 25+ sends"""
        send_status = state.get("send_status", {})
        reply_status = state.get("reply_status", {})

        sent_count = send_status.get("sent_count", 0)
        reply_count = reply_status.get("reply_count", 0)

        triggered = sent_count >= 25 and reply_count == 0

        return RuleResult(
            triggered=triggered,
            severity=RuleSeverity.HARD_STOP,
            rule_id="HS-1",
            diagnosis=f"Zero replies after {sent_count} sends (ICP completely wrong or message invisible)",
            operator_action="Review first 5 messages manually. Check targeting. Consider ICP pivot.",
        )

    def _hs3_approval_rate_catastrophically_low(self, state: dict) -> RuleResult:
        """HS-3: Approval rate < 20% with 10+ reviewed"""
        approval = state.get("approval_status", {})

        approved_count = approval.get("approved_count", 0)
        approval_rate = (
            approval.get("approval_rate_pct", 0) / 100.0
            if approval.get("approval_rate_pct")
            else 0
        )

        triggered = approved_count >= 10 and approval_rate < 0.20

        return RuleResult(
            triggered=triggered,
            severity=RuleSeverity.HARD_STOP,
            rule_id="HS-3",
            diagnosis=f"Approval rate {approval_rate:.0%} (reviewing {approved_count} messages, but rejecting {100-approval_rate:.0%})",
            operator_action="Review message prompt. Ask: 'Would I reply to these?' If no, fix messaging before sending.",
        )

    def _hs4_send_success_rate_below_threshold(self, state: dict) -> RuleResult:
        """HS-4: Send success rate < 90%"""
        send_status = state.get("send_status", {})

        sent_count = send_status.get("sent_count", 0)
        success_rate = (
            send_status.get("send_success_rate_pct", 100) / 100.0
            if send_status.get("send_success_rate_pct")
            else 1.0
        )

        triggered = sent_count >= 10 and success_rate < 0.90

        return RuleResult(
            triggered=triggered,
            severity=RuleSeverity.HARD_STOP,
            rule_id="HS-4",
            diagnosis=f"Send success rate {success_rate:.0%} (infrastructure failure: API, auth, or email provider issue)",
            operator_action="Check .env keys. Check OpenAI/email provider status. Review venture_pipeline.py logs.",
        )

    # ========== WARNING RULES ==========

    def _warning_rules(self) -> list:
        return [
            self._w1_low_reply_rate,
            self._w2_low_qualified_rate,
            self._w3_low_booking_rate,
            self._w4_low_closure_rate,
            self._w5_approval_drift,
        ]

    def _w1_low_reply_rate(self, state: dict) -> RuleResult:
        """W-1: Reply rate < 3% after 20+ sends"""
        send_status = state.get("send_status", {})
        reply_status = state.get("reply_status", {})

        sent_count = send_status.get("sent_count", 0)
        reply_rate = (
            reply_status.get("reply_rate_pct", 0) / 100.0
            if reply_status.get("reply_rate_pct")
            else 0
        )

        triggered = sent_count >= 20 and reply_rate < 0.03

        return RuleResult(
            triggered=triggered,
            severity=RuleSeverity.WARNING,
            rule_id="W-1",
            diagnosis=f"Low reply rate {reply_rate:.1%} after {sent_count} sends (ICP likely misaligned)",
            operator_action="Review any existing replies. Tighten prospect filtering. Check if targeting wrong buyer persona.",
        )

    def _w2_low_qualified_rate(self, state: dict) -> RuleResult:
        """W-2: Qualified rate < 25%"""
        reply_status = state.get("reply_status", {})

        reply_count = reply_status.get("reply_count", 0)
        qualified_rate = (
            reply_status.get("qualified_rate_pct", 0) / 100.0
            if reply_status.get("qualified_rate_pct")
            else 0
        )

        triggered = reply_count >= 5 and qualified_rate < 0.25

        return RuleResult(
            triggered=triggered,
            severity=RuleSeverity.WARNING,
            rule_id="W-2",
            diagnosis=f"Low qualified rate {qualified_rate:.0%} (message not clarifying fit for {reply_count} replies)",
            operator_action="Review 'thanks but not relevant' replies. Improve message clarity. Check if ICP is attracting wrong people.",
        )

    def _w3_low_booking_rate(self, state: dict) -> RuleResult:
        """W-3: Booking rate < 40% from qualified replies"""
        reply_status = state.get("reply_status", {})
        call_status = state.get("call_status", {})

        qualified_replies = reply_status.get("qualified_replies", 0)
        calls_booked = call_status.get("calls_booked", 0)

        booking_rate = calls_booked / qualified_replies if qualified_replies > 0 else 0

        triggered = qualified_replies >= 3 and booking_rate < 0.40

        return RuleResult(
            triggered=triggered,
            severity=RuleSeverity.WARNING,
            rule_id="W-3",
            diagnosis=f"Low booking rate {booking_rate:.0%} from {qualified_replies} qualified replies (reply-back email or calendar unclear)",
            operator_action="Check your follow-up email. Is Calendly link clear? Test the flow on yourself. Verify email delivery.",
        )

    def _w4_low_closure_rate(self, state: dict) -> RuleResult:
        """W-4: Closure rate < 25% from held calls"""
        call_status = state.get("call_status", {})

        calls_held = call_status.get("calls_held", 0)
        pilots_closed = call_status.get("pilots_closed", 0)

        closure_rate = pilots_closed / calls_held if calls_held > 0 else 0

        triggered = calls_held >= 2 and closure_rate < 0.25

        return RuleResult(
            triggered=triggered,
            severity=RuleSeverity.WARNING,
            rule_id="W-4",
            diagnosis=f"Low closure rate {closure_rate:.0%} from {calls_held} calls (offer unclear or sales qualification weak)",
            operator_action="Listen to call recordings. Did you explain pilot scope? Did you ask for commitment? Review call script.",
        )

    def _w5_approval_drift(self, state: dict) -> RuleResult:
        """W-5: Approval rate < 50% with 20+ reviewed"""
        approval = state.get("approval_status", {})

        approved_count = approval.get("approved_count", 0)
        approval_rate = (
            approval.get("approval_rate_pct", 0) / 100.0
            if approval.get("approval_rate_pct")
            else 0
        )

        triggered = approved_count >= 20 and approval_rate < 0.50

        return RuleResult(
            triggered=triggered,
            severity=RuleSeverity.WARNING,
            rule_id="W-5",
            diagnosis=f"Approval rate drift {approval_rate:.0%} (many rejects = message variance or quality control working too hard)",
            operator_action="Review why you're rejecting so many. Are standards too high? Is message prompt inconsistent? Adjust expectations.",
        )

    # ========== INFO RULES ==========

    def _info_rules(self) -> list:
        return [
            self._i1_campaign_running,
            self._i3_healthy_reply_rate,
        ]

    def _i1_campaign_running(self, state: dict) -> RuleResult:
        """I-1: Campaign actively running"""
        send_status = state.get("send_status", {})
        last_send = send_status.get("last_send_timestamp")

        # For now, always consider campaign running if we have approval
        approval = state.get("approval_status", {})
        approved_count = approval.get("approved_count", 0)

        triggered = approved_count > 0

        return RuleResult(
            triggered=triggered,
            severity=RuleSeverity.INFO,
            rule_id="I-1",
            diagnosis=f"Campaign active ({approved_count} messages approved, ready to send)",
            operator_action="Monitor replies daily. Log calls. Check dashboard progress.",
        )

    def _i3_healthy_reply_rate(self, state: dict) -> RuleResult:
        """I-3: Reply rate >= 5%"""
        send_status = state.get("send_status", {})
        reply_status = state.get("reply_status", {})

        sent_count = send_status.get("sent_count", 0)
        reply_rate = (
            reply_status.get("reply_rate_pct", 0) / 100.0
            if reply_status.get("reply_rate_pct")
            else 0
        )

        triggered = sent_count >= 20 and reply_rate >= 0.05

        return RuleResult(
            triggered=triggered,
            severity=RuleSeverity.INFO,
            rule_id="I-3",
            diagnosis=f"Healthy reply rate {reply_rate:.1%} (ICP targeting is solid)",
            operator_action="Continue sending. Monitor qualified rate. Track calls booked.",
        )


# Convenience function for dashboard + pipeline
def check_system_health(
    state_file: str | Path = None,
) -> tuple[RuleSeverity, str, list[dict]]:
    """
    Quick health check for dashboard

    Returns:
        (severity, primary_diagnosis, [all_triggered_rules])
    """
    engine = SignalRulesEngine(state_file)
    severity, results = engine.evaluate_all()
    diagnosis = engine.get_primary_diagnosis()

    rules_dict = [
        {
            "rule_id": r.rule_id,
            "severity": r.severity.value,
            "diagnosis": r.diagnosis,
            "action": r.operator_action,
        }
        for r in results
    ]

    return severity, diagnosis, rules_dict
