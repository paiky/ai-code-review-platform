from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.command_center.repository import (
    GovernanceBaseCounts,
    RuntimeBaseCounts,
    load_governance_base_counts,
    load_runtime_base_counts,
)
from app.command_center.schemas import (
    EvaluationSnapshot,
    FeedbackSnapshot,
    GovernanceSnapshot,
    IntakeSnapshot,
    RuntimeSnapshot,
    SchedulerSnapshot,
    SnapshotCoverage,
    SnapshotWindow,
)


RUNTIME_COVERAGE = {
    "intake": "BASIC",
    "activeTasks": "DEFERRED",
    "activeFlows": "DEFERRED",
    "scheduler": "BASIC",
    "standard": "DEFERRED",
    "agent": "DEFERRED",
    "providersObserved": "DEFERRED",
    "alerts": "DEFERRED",
}

GOVERNANCE_COVERAGE = {
    "ruleAnalysis": "DEFERRED",
    "preflight": "DEFERRED",
    "contextQuality": "DEFERRED",
    "findingRisk": "DEFERRED",
    "notifications": "DEFERRED",
    "feedback": "BASIC",
    "evaluation": "BASIC",
    "policies": "DEFERRED",
}


def get_runtime_snapshot(
    db: Session,
    *,
    window_hours: int,
    active_limit: int,
    alert_limit: int,
    project_id: int | None,
    group_id: int | None,
    now: datetime | None = None,
) -> RuntimeSnapshot:
    generated_at = _normalize_utc(now)
    window_from = generated_at - timedelta(hours=window_hours)
    counts = load_runtime_base_counts(
        db,
        window_from=_database_datetime(window_from),
        project_id=project_id,
        group_id=group_id,
    )
    return build_runtime_snapshot(
        counts,
        now=generated_at,
        window_hours=window_hours,
        active_limit=active_limit,
        alert_limit=alert_limit,
        project_id=project_id,
        group_id=group_id,
    )


def get_governance_snapshot(
    db: Session,
    *,
    window_hours: int,
    project_id: int | None,
    group_id: int | None,
    now: datetime | None = None,
) -> GovernanceSnapshot:
    generated_at = _normalize_utc(now)
    counts = load_governance_base_counts(
        db,
        project_id=project_id,
        group_id=group_id,
    )
    return build_governance_snapshot(
        counts,
        now=generated_at,
        window_hours=window_hours,
        project_id=project_id,
        group_id=group_id,
    )


def build_runtime_snapshot(
    counts: RuntimeBaseCounts,
    *,
    now: datetime,
    window_hours: int,
    active_limit: int,
    alert_limit: int,
    project_id: int | None,
    group_id: int | None,
) -> RuntimeSnapshot:
    generated_at = _normalize_utc(now)
    return RuntimeSnapshot(
        generatedAt=generated_at,
        window=_window(generated_at, window_hours),
        intake=IntakeSnapshot(
            taskCount=counts.intake_task_count,
            activeTaskCount=counts.active_task_count,
        ),
        scheduler=SchedulerSnapshot(
            activeJobCount=counts.queued_job_count + counts.running_job_count,
            queuedJobCount=counts.queued_job_count,
            runningJobCount=counts.running_job_count,
        ),
        coverage=SnapshotCoverage(
            sections=RUNTIME_COVERAGE,
            limits={
                "activeLimit": active_limit,
                "alertLimit": alert_limit,
            },
            filters={
                "projectId": project_id,
                "groupId": group_id,
            },
        ),
    )


def build_governance_snapshot(
    counts: GovernanceBaseCounts,
    *,
    now: datetime,
    window_hours: int,
    project_id: int | None,
    group_id: int | None,
) -> GovernanceSnapshot:
    generated_at = _normalize_utc(now)
    return GovernanceSnapshot(
        generatedAt=generated_at,
        window=_window(generated_at, window_hours),
        feedback=FeedbackSnapshot(pendingCount=counts.pending_feedback_count),
        evaluation=EvaluationSnapshot(caseCount=counts.evaluation_case_count),
        coverage=SnapshotCoverage(
            sections=GOVERNANCE_COVERAGE,
            filters={
                "projectId": project_id,
                "groupId": group_id,
            },
        ),
    )


def _window(now: datetime, hours: int) -> SnapshotWindow:
    return SnapshotWindow(
        **{
            "from": now - timedelta(hours=hours),
            "to": now,
            "hours": hours,
        }
    )


def _normalize_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _database_datetime(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None)
