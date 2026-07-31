from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


CoverageStatus = Literal["BASIC", "DEFERRED"]


class CommandCenterSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class SnapshotWindow(CommandCenterSchema):
    from_at: datetime = Field(alias="from")
    to: datetime
    hours: int


class SnapshotCoverage(CommandCenterSchema):
    phase: Literal["PHASE_0"] = "PHASE_0"
    truncated: bool = False
    sections: dict[str, CoverageStatus]
    limits: dict[str, int] = Field(default_factory=dict)
    filters: dict[str, int | None] = Field(default_factory=dict)


class IntakeSnapshot(CommandCenterSchema):
    status: Literal["BASIC"] = "BASIC"
    scope: Literal["WINDOW_AND_CURRENT_STATE"] = "WINDOW_AND_CURRENT_STATE"
    task_count: int = Field(alias="taskCount")
    active_task_count: int = Field(alias="activeTaskCount")


class SchedulerSnapshot(CommandCenterSchema):
    status: Literal["BASIC"] = "BASIC"
    scope: Literal["CURRENT_STATE"] = "CURRENT_STATE"
    active_job_count: int = Field(alias="activeJobCount")
    queued_job_count: int = Field(alias="queuedJobCount")
    running_job_count: int = Field(alias="runningJobCount")


class DeferredRuntimeSection(CommandCenterSchema):
    status: Literal["DEFERRED"] = "DEFERRED"
    active_flow_count: None = Field(default=None, alias="activeFlowCount")


class DeferredAgentSection(DeferredRuntimeSection):
    worker_pool: dict[str, str] = Field(
        default_factory=lambda: {"status": "DEFERRED"},
        alias="workerPool",
    )
    queue_metrics: dict[str, str] = Field(
        default_factory=lambda: {"status": "DEFERRED"},
        alias="queueMetrics",
    )


class RuntimeSnapshot(CommandCenterSchema):
    schema_version: Literal["command-center-runtime-v1"] = Field(
        default="command-center-runtime-v1",
        alias="schemaVersion",
    )
    generated_at: datetime = Field(alias="generatedAt")
    window: SnapshotWindow
    intake: IntakeSnapshot
    active_tasks: list[dict] = Field(default_factory=list, alias="activeTasks")
    active_flows: list[dict] = Field(default_factory=list, alias="activeFlows")
    scheduler: SchedulerSnapshot
    standard: DeferredRuntimeSection = Field(default_factory=DeferredRuntimeSection)
    agent: DeferredAgentSection = Field(default_factory=DeferredAgentSection)
    providers_observed: list[dict] = Field(default_factory=list, alias="providersObserved")
    alerts: list[dict] = Field(default_factory=list)
    coverage: SnapshotCoverage


class DeferredGovernanceSection(CommandCenterSchema):
    status: Literal["DEFERRED"] = "DEFERRED"


class FeedbackSnapshot(CommandCenterSchema):
    status: Literal["BASIC"] = "BASIC"
    scope: Literal["CURRENT_STATE"] = "CURRENT_STATE"
    pending_count: int = Field(alias="pendingCount")


class EvaluationSnapshot(CommandCenterSchema):
    status: Literal["BASIC"] = "BASIC"
    scope: Literal["ALL_TIME"] = "ALL_TIME"
    case_count: int = Field(alias="caseCount")


class GovernanceSnapshot(CommandCenterSchema):
    schema_version: Literal["command-center-governance-v1"] = Field(
        default="command-center-governance-v1",
        alias="schemaVersion",
    )
    generated_at: datetime = Field(alias="generatedAt")
    window: SnapshotWindow
    rule_analysis: DeferredGovernanceSection = Field(
        default_factory=DeferredGovernanceSection,
        alias="ruleAnalysis",
    )
    preflight: DeferredGovernanceSection = Field(default_factory=DeferredGovernanceSection)
    context_quality: DeferredGovernanceSection = Field(
        default_factory=DeferredGovernanceSection,
        alias="contextQuality",
    )
    finding_risk: DeferredGovernanceSection = Field(
        default_factory=DeferredGovernanceSection,
        alias="findingRisk",
    )
    notifications: DeferredGovernanceSection = Field(
        default_factory=DeferredGovernanceSection
    )
    feedback: FeedbackSnapshot
    evaluation: EvaluationSnapshot
    policies: DeferredGovernanceSection = Field(default_factory=DeferredGovernanceSection)
    coverage: SnapshotCoverage
