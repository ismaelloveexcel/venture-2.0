"""
Single source of truth for run_report.json (vFINAL.1).

Used by writer, validator, and tests — do not duplicate field definitions elsewhere.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

OutboundStatus = Literal["SUCCESS", "BLOCKED", "FAILED", "SKIPPED", "NOT_EXECUTED"]

MoneyPathSource = Literal["pipeline_telemetry", "orchestrator", "none"]


class PipelineTelemetry(BaseModel):
    """Subset of child pipeline JSON; unknown keys ignored (shape drift contained)."""

    model_config = {"extra": "ignore"}

    schema_version: int | None = None
    dry_run: bool | None = None
    auto_send_emails: bool | None = None
    run_health: dict[str, Any] | None = None
    job_queue_summary: dict[str, Any] | None = None
    funnel_counts_7d: dict[str, Any] | None = None
    phase1_structured: Phase1StructuredTelemetryModel | None = None


class Phase1SeverityDeltaModel(BaseModel):
    model_config = {"extra": "forbid"}

    hard: int = 0
    soft: int = 0
    info: int = 0


class Phase1WindowModel(BaseModel):
    model_config = {"extra": "forbid"}

    pipeline_started_at_utc: str | None = None
    pipeline_finished_at_utc: str | None = None


class Phase1QueueOperationsEventModel(BaseModel):
    model_config = {"extra": "forbid"}

    event: Literal["queue_operations"]
    job_summary_before: dict[str, Any] | None = None
    job_summary_after: dict[str, Any] | None = None
    jobs_total_delta: int | None = None


class Phase1StateTransitionsEventModel(BaseModel):
    model_config = {"extra": "forbid"}

    event: Literal["state_transitions"]
    lifecycle_events_delta: int | None = None


class Phase1GovernanceBlocksEventModel(BaseModel):
    model_config = {"extra": "forbid"}

    event: Literal["governance_blocks"]
    block_logs_delta: int | None = None
    severity_delta: Phase1SeverityDeltaModel | None = None


class Phase1RetriesFailuresEventModel(BaseModel):
    model_config = {"extra": "forbid"}

    event: Literal["retries_failures"]
    jobs_retry_sum_delta: int | None = None
    failed_status_delta: int | None = None
    abandoned_status_delta: int | None = None


class Phase1OperatorInterventionsEventModel(BaseModel):
    model_config = {"extra": "forbid"}

    event: Literal["operator_interventions"]
    operator_pause_blocks_delta: int | None = None
    operator_lifecycle_events_delta: int | None = None


Phase1EventModel = (
    Phase1QueueOperationsEventModel
    | Phase1StateTransitionsEventModel
    | Phase1GovernanceBlocksEventModel
    | Phase1RetriesFailuresEventModel
    | Phase1OperatorInterventionsEventModel
)


class Phase1StructuredTelemetryModel(BaseModel):
    model_config = {"extra": "forbid"}

    version: Literal[1] = 1
    window: Phase1WindowModel | None = None
    events: list[Phase1EventModel] = Field(default_factory=list)


class OrchestratorTelemetryModel(BaseModel):
    model_config = {"extra": "forbid"}

    started_at_utc: str | None = None
    finished_at_utc: str | None = None
    execute_outbound: bool = False
    dry_run: bool = False
    venture_pipeline_subprocess_ran: bool = False
    subprocess_return_code: int | None = None


class MoneyPathModel(BaseModel):
    model_config = {"extra": "forbid"}

    attempted: int = 0
    sent: int = 0
    blocked: int = 0
    reasons: list[str] = Field(default_factory=list)


class ProspectBatchModel(BaseModel):
    """Prospect + message prep before venture_pipeline (governed counts for run_report)."""

    model_config = {"extra": "forbid"}

    builder_ran: bool = False
    builder_exit_code: int | None = None
    ready: int = 0
    review: int = 0
    reject: int = 0
    rows_validated: int = 0
    message_gen_ran: bool = False
    message_gen_exit_code: int | None = None
    message_gen_pass: int = 0
    message_gen_fail: int = 0
    approved_pass_rows: int = 0
    outbound_skipped: bool = False
    reasons: list[str] = Field(default_factory=list)
    # Populated when prospect_builder writes 07-kpis/prospect_generation_digest/<run_id>.json
    prospect_generation_digest: dict[str, Any] = Field(default_factory=dict)


class CohortMetadataModel(BaseModel):
    """Frozen cohort / version tuple for audit (v1.4).

    ``freeze_timestamp_utc`` + ``subject_cta_fingerprint`` support deterministic
    run snapshots (launch doctrine): reconstruct which subject/CTA policy and
    when the cohort lock was materialized for this run.
    """

    model_config = {"extra": "forbid"}

    cohort_id: str = ""
    run_id: str = ""
    message_version: str = ""
    guard_version: str = ""
    generator_version: str = ""
    git_sha: str = "unknown"
    freeze_timestamp_utc: str = ""
    subject_cta_fingerprint: str = ""


class FunnelHealthSnapshotModel(BaseModel):
    """Append-only per-batch funnel snapshot row (immutable in the report JSON)."""

    model_config = {"extra": "forbid", "frozen": True}

    snapshot_schema_version: Literal["1"] = "1"
    prospect_id: str = ""
    campaign_id: str = ""
    send_timestamp: str = ""
    reply_intent_model_version: str = ""
    approval_user: str = ""
    approval_timestamp: str = ""
    sent: int = 0
    blocked: int = 0
    qualified: int = 0


class RuntimeGovernanceSystemTrustCenter(BaseModel):
    model_config = {"extra": "ignore"}

    system_trust_score: int = 0
    confidence_score: int = 0
    instability_level: int = 0
    system_trend: str = "unknown"
    active_regressions: int = 0
    misleading_modules: list[str] = Field(default_factory=list)
    blast_radius: int = 0
    critical_blockers: list[str] = Field(default_factory=list)


class RuntimeGovernanceTelemetryIntegrity(BaseModel):
    model_config = {"extra": "ignore"}

    coverage_score: int = 0
    freshness_score: int = 0
    integrity_score: int = 0
    age_minutes: int | None = None
    invariants: list[dict[str, Any]] = Field(default_factory=list)


class RuntimeGovernanceModuleRow(BaseModel):
    model_config = {"extra": "ignore"}

    id: str = ""
    name: str = ""
    runtime_state: str = "UNKNOWN"
    resolved_state: str = "UNKNOWN"
    execution_state: str = "UNKNOWN"
    usefulness_score: int | None = None
    confidence_score: int = 0
    stability_score: int = 0
    downstream_impact_score: int = 0
    trust_score: int = 0
    evidence_quality: str = "unknown"
    regression_detected: bool = False
    degraded_by: list[str] = Field(default_factory=list)
    affects: list[str] = Field(default_factory=list)
    root_cause: str = ""
    operator_action_required: bool = False
    last_known_good_run: str = ""
    historical_baseline_delta: int = 0
    depends_on: list[str] = Field(default_factory=list)
    soft_dependencies: list[str] = Field(default_factory=list)
    causal_chain_depth: int = 0
    upstream_degradation_sources: list[str] = Field(default_factory=list)
    downstream_modules_affected: list[str] = Field(default_factory=list)
    scoring_category: str = ""
    trend_direction: str = "stable"
    blast_radius: int = 0
    runtime_status: str = "UNKNOWN"
    confidence: int = 0
    dependencies: dict[str, Any] = Field(default_factory=dict)
    regression_events: list[dict[str, Any]] = Field(default_factory=list)
    trust_decay_multiplier: float = 1.0
    confidence_penalty: int = 0
    derived_trustworthiness: int = 0


class RuntimeGovernanceCausalImpactMap(BaseModel):
    model_config = {"extra": "ignore"}

    edges: list[dict[str, Any]] = Field(default_factory=list)
    degradation_paths: list[dict[str, Any]] = Field(default_factory=list)


class RuntimeGovernanceRegressionCenter(BaseModel):
    model_config = {"extra": "ignore"}

    top_regressions: list[dict[str, Any]] = Field(default_factory=list)
    system_delta_vs_baseline: int = 0


class RuntimeGovernanceRegressionTimeline(BaseModel):
    model_config = {"extra": "ignore"}

    events: list[dict[str, Any]] = Field(default_factory=list)
    first_regression_timestamp: str = ""


class RuntimeGovernanceChangeImpactTimeline(BaseModel):
    model_config = {"extra": "ignore"}

    points: list[dict[str, Any]] = Field(default_factory=list)


class RuntimeGovernanceRootCauseIntelligence(BaseModel):
    model_config = {"extra": "ignore"}

    root_cause: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)


class RuntimeGovernanceDecisionSafety(BaseModel):
    model_config = {"extra": "ignore"}

    safe_to_scale: bool = False
    safe_to_change_messaging: bool = False
    safe_to_change_audience: bool = False
    safe_to_run_ab_test: bool = False
    confidence_in_recommendation: int = 0
    unsafe_reasons: list[str] = Field(default_factory=list)
    recommended_next_move: str = ""


class RuntimeGovernanceHistoricalIntelligence(BaseModel):
    model_config = {"extra": "ignore"}

    records: list[dict[str, Any]] = Field(default_factory=list)
    degradation_acceleration: int = 0
    last_stable_configuration: dict[str, Any] = Field(default_factory=dict)
    latest_operator_changes: list[dict[str, Any]] = Field(default_factory=list)


class RuntimeGovernanceModel(BaseModel):
    """Backend-authoritative runtime governance payload consumed by dashboards."""

    model_config = {"extra": "ignore"}

    model_version: str = ""
    generated_at_utc: str = ""
    system_trust_center: RuntimeGovernanceSystemTrustCenter = Field(
        default_factory=RuntimeGovernanceSystemTrustCenter
    )
    executive_health: dict[str, Any] = Field(default_factory=dict)
    telemetry_integrity: RuntimeGovernanceTelemetryIntegrity = Field(
        default_factory=RuntimeGovernanceTelemetryIntegrity
    )
    module_governance_grid: list[RuntimeGovernanceModuleRow] = Field(
        default_factory=list
    )
    causal_impact_map: RuntimeGovernanceCausalImpactMap = Field(
        default_factory=RuntimeGovernanceCausalImpactMap
    )
    regression_center: RuntimeGovernanceRegressionCenter = Field(
        default_factory=RuntimeGovernanceRegressionCenter
    )
    regression_timeline: RuntimeGovernanceRegressionTimeline = Field(
        default_factory=RuntimeGovernanceRegressionTimeline
    )
    change_impact_timeline: RuntimeGovernanceChangeImpactTimeline = Field(
        default_factory=RuntimeGovernanceChangeImpactTimeline
    )
    root_cause_intelligence: RuntimeGovernanceRootCauseIntelligence = Field(
        default_factory=RuntimeGovernanceRootCauseIntelligence
    )
    decision_safety: RuntimeGovernanceDecisionSafety = Field(
        default_factory=RuntimeGovernanceDecisionSafety
    )
    historical_intelligence: RuntimeGovernanceHistoricalIntelligence = Field(
        default_factory=RuntimeGovernanceHistoricalIntelligence
    )


class OutboundSection(BaseModel):
    model_config = {"extra": "forbid"}

    status: OutboundStatus = "NOT_EXECUTED"
    phases: list[str] = Field(default_factory=list)
    money_path: MoneyPathModel = Field(default_factory=MoneyPathModel)
    policy_snapshot: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    subprocess_return_code: int | None = None
    # Set when --execute-outbound runs (audit: dry-run vs live child)
    dry_run: bool | None = None
    # Which layer last defined money_path counts (audit precedence; not execution truth alone)
    money_path_source: MoneyPathSource = "none"
    # Populated by run_daily when child sets VENTURE_PIPELINE_TELEMETRY_JSON (P3)
    pipeline_telemetry: PipelineTelemetry = Field(default_factory=PipelineTelemetry)
    orchestrator_telemetry: OrchestratorTelemetryModel = Field(
        default_factory=OrchestratorTelemetryModel
    )
    prospect_batch: ProspectBatchModel = Field(default_factory=ProspectBatchModel)
    cohort_metadata: CohortMetadataModel | None = None
    funnel_health_snapshots: list[FunnelHealthSnapshotModel] = Field(
        default_factory=list
    )
    # Backend-authored deterministic governance state consumed by dashboards.
    runtime_governance: RuntimeGovernanceModel = Field(
        default_factory=RuntimeGovernanceModel
    )


class CisEvalSection(BaseModel):
    model_config = {"extra": "forbid"}

    enabled: bool = False
    metrics: dict[str, Any] = Field(default_factory=dict)
    bootstrap: dict[str, Any] = Field(default_factory=dict)
    risk: float | None = None
    decision: str = "N/A"
    dashboard_path: str | None = None


class SystemSection(BaseModel):
    model_config = {"extra": "forbid"}

    record_count: int = 0
    random_seed: int = 42
    cost_estimates: dict[str, Any] = Field(default_factory=dict)
    logs_ref: str = ""


class RunReport(BaseModel):
    """Atomic per-run report; full overwrite each run."""

    model_config = {"extra": "forbid"}

    schema_version: Literal["1.0"] = "1.0"
    run_id: str
    timestamp_utc: str
    outbound: OutboundSection = Field(default_factory=OutboundSection)
    cis_eval: CisEvalSection = Field(default_factory=CisEvalSection)
    system: SystemSection = Field(default_factory=SystemSection)
