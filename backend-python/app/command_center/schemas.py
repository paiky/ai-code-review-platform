from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


CoverageStatus = Literal["FULL", "BOUNDED"]
Scope = Literal["WINDOW", "ALL_TIME", "CURRENT_STATE", "WINDOW_AND_CURRENT_STATE"]
StageSource = Literal[
    "INFERRED",
    "RULE_RESULT",
    "PROGRESS",
    "SCHEDULER_JOB",
    "AGENT_RUN",
    "AI_RESULT",
    "TASK",
]


class CommandCenterSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class SnapshotWindow(CommandCenterSchema):
    from_at: datetime = Field(alias="from")
    to: datetime
    hours: int


class SnapshotCoverage(CommandCenterSchema):
    phase: Literal["PHASE_1"] = "PHASE_1"
    truncated: bool = False
    sections: dict[str, CoverageStatus]
    limits: dict[str, int] = Field(default_factory=dict)
    filters: dict[str, int | None] = Field(default_factory=dict)
    scanned: dict[str, int] = Field(default_factory=dict)


class IntakeSnapshot(CommandCenterSchema):
    status: Literal["LIVE"] = "LIVE"
    scope: Literal["WINDOW_AND_CURRENT_STATE"] = "WINDOW_AND_CURRENT_STATE"
    task_count: int = Field(alias="taskCount")
    active_task_count: int = Field(alias="activeTaskCount")


class SchedulerSnapshot(CommandCenterSchema):
    status: Literal["LIVE"] = "LIVE"
    scope: Literal["CURRENT_STATE"] = "CURRENT_STATE"
    active_job_count: int = Field(alias="activeJobCount")
    queued_job_count: int = Field(alias="queuedJobCount")
    running_job_count: int = Field(alias="runningJobCount")


class ActiveTaskSnapshot(CommandCenterSchema):
    task_id: int = Field(alias="taskId")
    project_id: int = Field(alias="projectId")
    project_name: str = Field(alias="projectName")
    group_id: int | None = Field(default=None, alias="groupId")
    trigger_type: str = Field(alias="triggerType")
    technical_status: str = Field(alias="technicalStatus")
    review_status: str = Field(alias="reviewStatus")
    risk_level: str | None = Field(default=None, alias="riskLevel")
    rule_risk_item_count: int = Field(alias="ruleRiskItemCount")
    flow_count: int = Field(alias="flowCount")
    stage: str
    stage_source: StageSource = Field(alias="stageSource")
    created_at: datetime | None = Field(default=None, alias="createdAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")


class ActiveFlowSnapshot(CommandCenterSchema):
    id: str
    task_id: int = Field(alias="taskId")
    review_key: str = Field(alias="reviewKey")
    display_name: str = Field(alias="displayName")
    job_type: str | None = Field(default=None, alias="jobType")
    requested_engine: str = Field(alias="requestedEngine")
    effective_engine: str = Field(alias="effectiveEngine")
    fallback: bool
    status: str
    stage: str
    stage_source: StageSource = Field(alias="stageSource")
    provider_code: str | None = Field(default=None, alias="providerCode")
    model: str | None = None
    finding_count: int = Field(alias="findingCount")
    highest_risk: str | None = Field(default=None, alias="highestRisk")
    context_status_counts: dict[str, int] = Field(alias="contextStatusCounts")
    queued_at: datetime | None = Field(default=None, alias="queuedAt")
    started_at: datetime | None = Field(default=None, alias="startedAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")
    duration_seconds: int | None = Field(default=None, alias="durationSeconds")


class FlowEngineSnapshot(CommandCenterSchema):
    status: Literal["LIVE"] = "LIVE"
    active_flow_count: int = Field(alias="activeFlowCount")
    finding_count: int = Field(alias="findingCount")
    status_counts: dict[str, int] = Field(alias="statusCounts")


class WorkerSnapshot(CommandCenterSchema):
    worker_id: str = Field(alias="workerId")
    state: Literal["IDLE", "BUSY", "DRAINING"]
    online: bool
    capacity: int
    active_job_id: int | None = Field(default=None, alias="activeJobId")
    active_run_id: int | None = Field(default=None, alias="activeRunId")
    last_heartbeat_at: datetime | None = Field(default=None, alias="lastHeartbeatAt")
    source: Literal["REGISTERED", "LEGACY"]


class WorkerPoolSnapshot(CommandCenterSchema):
    status: Literal["LIVE"] = "LIVE"
    enabled: bool
    online_count: int = Field(alias="onlineCount")
    offline_count: int = Field(alias="offlineCount")
    idle_count: int = Field(alias="idleCount")
    busy_count: int = Field(alias="busyCount")
    draining_count: int = Field(alias="drainingCount")
    workers: list[WorkerSnapshot] = Field(default_factory=list)


class AgentQueueSnapshot(CommandCenterSchema):
    queued: int
    running: int
    expired_lease: int = Field(alias="expiredLease")
    oldest_queued_seconds: int | None = Field(default=None, alias="oldestQueuedSeconds")
    online_capacity: int = Field(alias="onlineCapacity")
    busy_capacity: int = Field(alias="busyCapacity")
    utilization_percent: int = Field(alias="utilizationPercent")
    draining_workers: int = Field(alias="drainingWorkers")


class AgentSnapshot(FlowEngineSnapshot):
    worker_pool: WorkerPoolSnapshot = Field(alias="workerPool")
    queue_metrics: AgentQueueSnapshot = Field(alias="queueMetrics")


class ProviderSnapshot(CommandCenterSchema):
    provider_code: str = Field(alias="providerCode")
    provider_name: str = Field(alias="providerName")
    provider_type: str = Field(alias="providerType")
    model_name: str | None = Field(default=None, alias="modelName")
    enabled: bool
    default_provider: bool = Field(alias="defaultProvider")
    status: Literal[
        "DISABLED",
        "ACTIVE",
        "RECENT_SUCCESS",
        "RECENT_FAILURE",
        "NO_RECENT_DATA",
    ]
    active_flow_count: int = Field(alias="activeFlowCount")
    recent_success_count: int = Field(alias="recentSuccessCount")
    recent_failure_count: int = Field(alias="recentFailureCount")
    last_observed_at: datetime | None = Field(default=None, alias="lastObservedAt")


class AlertSnapshot(CommandCenterSchema):
    id: str
    type: str
    status: str
    task_id: int | None = Field(default=None, alias="taskId")
    review_key: str | None = Field(default=None, alias="reviewKey")
    project_id: int | None = Field(default=None, alias="projectId")
    project_name: str | None = Field(default=None, alias="projectName")
    occurred_at: datetime | None = Field(default=None, alias="occurredAt")
    navigation_target: str | None = Field(default=None, alias="navigationTarget")


class RuntimeSnapshot(CommandCenterSchema):
    schema_version: Literal["command-center-runtime-v1"] = Field(
        default="command-center-runtime-v1",
        alias="schemaVersion",
    )
    generated_at: datetime = Field(alias="generatedAt")
    window: SnapshotWindow
    intake: IntakeSnapshot
    active_tasks: list[ActiveTaskSnapshot] = Field(alias="activeTasks")
    active_flows: list[ActiveFlowSnapshot] = Field(alias="activeFlows")
    scheduler: SchedulerSnapshot
    standard: FlowEngineSnapshot
    agent: AgentSnapshot
    providers_observed: list[ProviderSnapshot] = Field(alias="providersObserved")
    alerts: list[AlertSnapshot]
    coverage: SnapshotCoverage


class RuleAnalysisSnapshot(CommandCenterSchema):
    status: Literal["LIVE"] = "LIVE"
    scope: Literal["WINDOW"] = "WINDOW"
    result_count: int = Field(alias="resultCount")
    risk_item_count: int = Field(alias="riskItemCount")
    risk_distribution: dict[str, int] = Field(alias="riskDistribution")


class PreflightSnapshot(CommandCenterSchema):
    status: Literal["LIVE"] = "LIVE"
    scope: Literal["WINDOW"] = "WINDOW"
    run_count: int = Field(alias="runCount")
    finding_count: int = Field(alias="findingCount")
    status_counts: dict[str, int] = Field(alias="statusCounts")


class ContextQualitySnapshot(CommandCenterSchema):
    status: Literal["LIVE"] = "LIVE"
    scope: Literal["WINDOW"] = "WINDOW"
    finding_count: int = Field(alias="findingCount")
    status_counts: dict[str, int] = Field(alias="statusCounts")


class FindingRiskSnapshot(CommandCenterSchema):
    status: Literal["LIVE"] = "LIVE"
    scope: Literal["WINDOW"] = "WINDOW"
    finding_count: int = Field(alias="findingCount")
    highest_risk: str | None = Field(default=None, alias="highestRisk")
    affected_task_count: int = Field(alias="affectedTaskCount")
    severity_counts: dict[str, int] = Field(alias="severityCounts")


class NotificationGovernanceSnapshot(CommandCenterSchema):
    status: Literal["LIVE"] = "LIVE"
    scope: Literal["WINDOW"] = "WINDOW"
    record_count: int = Field(alias="recordCount")
    status_counts: dict[str, int] = Field(alias="statusCounts")


class FeedbackSnapshot(CommandCenterSchema):
    status: Literal["LIVE"] = "LIVE"
    scope: Literal["ALL_TIME"] = "ALL_TIME"
    total_count: int = Field(alias="totalCount")
    pending_count: int = Field(alias="pendingCount")
    status_counts: dict[str, int] = Field(alias="statusCounts")
    type_counts: dict[str, int] = Field(alias="typeCounts")
    context_missing_count: int = Field(alias="contextMissingCount")
    policy_candidate_count: int = Field(alias="policyCandidateCount")


class AcceptanceSnapshot(CommandCenterSchema):
    total_count: int = Field(alias="totalCount")
    status_counts: dict[str, int] = Field(alias="statusCounts")
    latest_status: str | None = Field(default=None, alias="latestStatus")


class SampleGateSnapshot(CommandCenterSchema):
    annotated_sample_count: int = Field(alias="annotatedSampleCount")
    required_sample_count: int = Field(default=30, alias="requiredSampleCount")
    ready: bool


class EvaluationSnapshot(CommandCenterSchema):
    status: Literal["LIVE"] = "LIVE"
    scope: Literal["ALL_TIME"] = "ALL_TIME"
    case_count: int = Field(alias="caseCount")
    verdict_counts: dict[str, int] = Field(alias="verdictCounts")
    rule_gap_counts: dict[str, int] = Field(alias="ruleGapCounts")
    run_count: int = Field(alias="runCount")
    run_status_counts: dict[str, int] = Field(alias="runStatusCounts")
    acceptance: AcceptanceSnapshot
    agent_sample_gate: SampleGateSnapshot = Field(alias="agentSampleGate")


class PolicySnapshot(CommandCenterSchema):
    status: Literal["LIVE"] = "LIVE"
    scope: Literal["ALL_TIME"] = "ALL_TIME"
    total_count: int = Field(alias="totalCount")
    enabled_count: int = Field(alias="enabledCount")
    candidate_count: int = Field(alias="candidateCount")


class GovernanceSnapshot(CommandCenterSchema):
    schema_version: Literal["command-center-governance-v1"] = Field(
        default="command-center-governance-v1",
        alias="schemaVersion",
    )
    generated_at: datetime = Field(alias="generatedAt")
    window: SnapshotWindow
    rule_analysis: RuleAnalysisSnapshot = Field(alias="ruleAnalysis")
    preflight: PreflightSnapshot
    context_quality: ContextQualitySnapshot = Field(alias="contextQuality")
    finding_risk: FindingRiskSnapshot = Field(alias="findingRisk")
    notifications: NotificationGovernanceSnapshot
    feedback: FeedbackSnapshot
    evaluation: EvaluationSnapshot
    policies: PolicySnapshot
    coverage: SnapshotCoverage
