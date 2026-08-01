from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, and_, case, func, literal, or_, select, union_all
from sqlalchemy.orm import Session

from app.agent_review.models import AgentReviewRun, AgentReviewSettings, AgentReviewWorker
from app.code_quality.models import (
    CodeQualityModelProvider,
    CodeQualityReviewProgressEvent,
    CodeQualityReviewResult as AiReviewResult,
    CodeQualityReviewSettings,
    CodeQualitySchedulerJob,
)
from app.deterministic_checks.models import DeterministicCheckRun
from app.evaluation.models import EvaluationCase, EvaluationRun
from app.project_integration.models import Project
from app.project_review_policy.models import ProjectReviewPolicy
from app.review_feedback.models import ReviewItemFeedback
from app.review_quality_acceptance.models import ReviewQualityAcceptanceGate
from app.review_record.models import (
    NotificationRecord,
    ReviewResult as RuleReviewResult,
    ReviewTask,
)


REVIEW_JOB_TYPES = ("AI_REVIEW", "AGENT_REVIEW")
ACTIVE_JOB_STATUSES = ("QUEUED", "RUNNING")
ACTIVE_TASK_STATUSES = ("RUNNING",)
ACTIVE_REVIEW_STATUSES = ("REVIEWING",)
FAILED_AGENT_STATUSES = ("FAILED", "TIMED_OUT")
TERMINAL_FAILURE_STATUSES = ("FAILED",)
FINDING_SCAN_LIMIT = 2000
WORKER_LIMIT = 100
MYSQL_ALERT_UNION_COLLATION = "utf8mb4_unicode_ci"


@dataclass(frozen=True)
class RuntimeBaseCounts:
    intake_task_count: int
    active_task_count: int
    queued_job_count: int
    running_job_count: int
    agent_queued_job_count: int = 0
    agent_running_job_count: int = 0
    expired_lease_count: int = 0
    oldest_queued_at: datetime | None = None


@dataclass(frozen=True)
class RuntimeProjectionData:
    counts: RuntimeBaseCounts
    active_jobs: list[dict[str, Any]]
    tasks: list[dict[str, Any]]
    rule_results: list[dict[str, Any]]
    ai_results: list[dict[str, Any]]
    progress_events: list[dict[str, Any]]
    agent_runs: list[dict[str, Any]]
    deterministic_runs: list[dict[str, Any]]
    notifications: list[dict[str, Any]]
    workers: list[dict[str, Any]]
    agent_settings: dict[str, Any] | None
    providers: list[dict[str, Any]]
    alerts: list[dict[str, Any]]
    candidate_task_count: int
    selected_task_count: int


@dataclass(frozen=True)
class GovernanceBaseCounts:
    pending_feedback_count: int
    evaluation_case_count: int


@dataclass(frozen=True)
class GovernanceProjectionData:
    rule_rows: list[dict[str, Any]]
    preflight_rows: list[dict[str, Any]]
    finding_rows: list[dict[str, Any]]
    notification_rows: list[dict[str, Any]]
    feedback_rows: list[dict[str, Any]]
    evaluation_case_rows: list[dict[str, Any]]
    evaluation_run_rows: list[dict[str, Any]]
    policy_rows: list[dict[str, Any]]
    acceptance_rows: list[dict[str, Any]]
    preflight_truncated: bool
    finding_truncated: bool


def load_runtime_projection(
    db: Session,
    *,
    window_from: datetime,
    now: datetime,
    active_limit: int,
    alert_limit: int,
    project_id: int | None,
    group_id: int | None,
) -> RuntimeProjectionData:
    counts = load_runtime_base_counts(
        db,
        window_from=window_from,
        now=now,
        project_id=project_id,
        group_id=group_id,
    )
    candidate_limit = max(active_limit * 4, active_limit)

    active_job_statement = (
        select(
            CodeQualitySchedulerJob.id.label("id"),
            CodeQualitySchedulerJob.job_type.label("job_type"),
            CodeQualitySchedulerJob.task_id.label("task_id"),
            CodeQualitySchedulerJob.review_key.label("review_key"),
            CodeQualitySchedulerJob.project_id.label("project_id"),
            CodeQualitySchedulerJob.status.label("status"),
            CodeQualitySchedulerJob.lease_expires_at.label("lease_expires_at"),
            CodeQualitySchedulerJob.queued_at.label("queued_at"),
            CodeQualitySchedulerJob.started_at.label("started_at"),
            CodeQualitySchedulerJob.created_at.label("created_at"),
            CodeQualitySchedulerJob.updated_at.label("updated_at"),
        )
        .where(
            CodeQualitySchedulerJob.job_type.in_(REVIEW_JOB_TYPES),
            CodeQualitySchedulerJob.status.in_(ACTIVE_JOB_STATUSES),
        )
        .order_by(
            CodeQualitySchedulerJob.updated_at.desc(),
            CodeQualitySchedulerJob.id.desc(),
        )
        .limit(candidate_limit)
    )
    active_job_statement = _apply_project_filters(
        active_job_statement,
        CodeQualitySchedulerJob.project_id,
        project_id=project_id,
        group_id=group_id,
    )
    active_jobs = _rows(db, active_job_statement)

    task_candidate_statement = (
        select(
            ReviewTask.id.label("task_id"),
            ReviewTask.updated_at.label("updated_at"),
            ReviewTask.created_at.label("created_at"),
        )
        .where(
            or_(
                ReviewTask.status.in_(ACTIVE_TASK_STATUSES),
                ReviewTask.review_status.in_(ACTIVE_REVIEW_STATUSES),
            )
        )
        .order_by(ReviewTask.updated_at.desc(), ReviewTask.id.desc())
        .limit(candidate_limit)
    )
    task_candidate_statement = _apply_project_filters(
        task_candidate_statement,
        ReviewTask.project_id,
        project_id=project_id,
        group_id=group_id,
    )
    task_candidates = _rows(db, task_candidate_statement)

    result_candidate_statement = (
        select(
            AiReviewResult.task_id.label("task_id"),
            AiReviewResult.updated_at.label("updated_at"),
            AiReviewResult.created_at.label("created_at"),
        )
        .where(AiReviewResult.status == "RUNNING")
        .order_by(AiReviewResult.updated_at.desc(), AiReviewResult.id.desc())
        .limit(candidate_limit)
    )
    result_candidate_statement = _apply_project_filters(
        result_candidate_statement,
        AiReviewResult.project_id,
        project_id=project_id,
        group_id=group_id,
    )
    result_candidates = _rows(db, result_candidate_statement)

    selected_task_ids, candidate_task_count = _select_active_task_ids(
        active_jobs,
        task_candidates,
        result_candidates,
        active_limit=active_limit,
    )

    tasks = _load_tasks(db, selected_task_ids)
    rule_results = _load_rule_results(db, selected_task_ids)
    ai_results = _load_ai_results(db, selected_task_ids)
    progress_events = _load_progress_events(db, selected_task_ids, active_limit)
    agent_runs = _load_agent_runs(db, selected_task_ids)
    deterministic_runs = _load_deterministic_runs(db, selected_task_ids)
    notifications = _load_notifications(db, selected_task_ids)
    workers = _rows(
        db,
        select(
            AgentReviewWorker.worker_id.label("worker_id"),
            AgentReviewWorker.state.label("state"),
            AgentReviewWorker.capacity.label("capacity"),
            AgentReviewWorker.active_job_id.label("active_job_id"),
            AgentReviewWorker.active_run_id.label("active_run_id"),
            AgentReviewWorker.last_heartbeat_at.label("last_heartbeat_at"),
        )
        .order_by(AgentReviewWorker.last_heartbeat_at.desc())
        .limit(WORKER_LIMIT),
    )
    agent_settings = _row(
        db,
        select(
            AgentReviewSettings.enabled.label("enabled"),
            AgentReviewSettings.worker_id.label("worker_id"),
            AgentReviewSettings.last_worker_heartbeat_at.label(
                "last_worker_heartbeat_at"
            ),
        )
        .order_by(AgentReviewSettings.id.asc())
        .limit(1),
    )
    providers = _load_provider_observations(db, window_from)
    alerts = _load_recent_alerts(
        db,
        window_from=window_from,
        alert_limit=alert_limit,
        project_id=project_id,
        group_id=group_id,
    )

    return RuntimeProjectionData(
        counts=counts,
        active_jobs=active_jobs,
        tasks=tasks,
        rule_results=rule_results,
        ai_results=ai_results,
        progress_events=progress_events,
        agent_runs=agent_runs,
        deterministic_runs=deterministic_runs,
        notifications=notifications,
        workers=workers,
        agent_settings=agent_settings,
        providers=providers,
        alerts=alerts,
        candidate_task_count=candidate_task_count,
        selected_task_count=len(selected_task_ids),
    )


def load_runtime_base_counts(
    db: Session,
    *,
    window_from: datetime,
    now: datetime,
    project_id: int | None,
    group_id: int | None,
) -> RuntimeBaseCounts:
    intake_task_statement = (
        select(func.count())
        .select_from(ReviewTask)
        .where(ReviewTask.created_at >= window_from)
    )
    intake_task_statement = _apply_project_filters(
        intake_task_statement,
        ReviewTask.project_id,
        project_id=project_id,
        group_id=group_id,
    )
    intake_task_count = _count(db, intake_task_statement)

    active_task_statement = (
        select(func.count())
        .select_from(ReviewTask)
        .where(
            or_(
                ReviewTask.status.in_(ACTIVE_TASK_STATUSES),
                ReviewTask.review_status.in_(ACTIVE_REVIEW_STATUSES),
            )
        )
    )
    active_task_statement = _apply_project_filters(
        active_task_statement,
        ReviewTask.project_id,
        project_id=project_id,
        group_id=group_id,
    )
    active_task_count = _count(db, active_task_statement)

    job_statement = (
        select(
            func.coalesce(
                func.sum(
                    case((CodeQualitySchedulerJob.status == "QUEUED", 1), else_=0)
                ),
                0,
            ).label("queued_job_count"),
            func.coalesce(
                func.sum(
                    case((CodeQualitySchedulerJob.status == "RUNNING", 1), else_=0)
                ),
                0,
            ).label("running_job_count"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                CodeQualitySchedulerJob.job_type == "AGENT_REVIEW",
                                CodeQualitySchedulerJob.status == "QUEUED",
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("agent_queued_job_count"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                CodeQualitySchedulerJob.job_type == "AGENT_REVIEW",
                                CodeQualitySchedulerJob.status == "RUNNING",
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("agent_running_job_count"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                CodeQualitySchedulerJob.job_type == "AGENT_REVIEW",
                                CodeQualitySchedulerJob.status == "RUNNING",
                                CodeQualitySchedulerJob.lease_expires_at.is_not(None),
                                CodeQualitySchedulerJob.lease_expires_at < now,
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("expired_lease_count"),
            func.min(
                case(
                    (
                        and_(
                            CodeQualitySchedulerJob.job_type == "AGENT_REVIEW",
                            CodeQualitySchedulerJob.status == "QUEUED",
                        ),
                        CodeQualitySchedulerJob.queued_at,
                    ),
                    else_=None,
                )
            ).label("oldest_queued_at"),
        )
        .select_from(CodeQualitySchedulerJob)
        .where(
            CodeQualitySchedulerJob.job_type.in_(REVIEW_JOB_TYPES),
            CodeQualitySchedulerJob.status.in_(ACTIVE_JOB_STATUSES),
        )
    )
    job_statement = _apply_project_filters(
        job_statement,
        CodeQualitySchedulerJob.project_id,
        project_id=project_id,
        group_id=group_id,
    )
    job_counts = _row(db, job_statement) or {}

    return RuntimeBaseCounts(
        intake_task_count=intake_task_count,
        active_task_count=active_task_count,
        queued_job_count=int(job_counts.get("queued_job_count") or 0),
        running_job_count=int(job_counts.get("running_job_count") or 0),
        agent_queued_job_count=int(
            job_counts.get("agent_queued_job_count") or 0
        ),
        agent_running_job_count=int(
            job_counts.get("agent_running_job_count") or 0
        ),
        expired_lease_count=int(job_counts.get("expired_lease_count") or 0),
        oldest_queued_at=job_counts.get("oldest_queued_at"),
    )


def load_governance_projection(
    db: Session,
    *,
    window_from: datetime,
    project_id: int | None,
    group_id: int | None,
) -> GovernanceProjectionData:
    rule_statement = (
        select(
            RuleReviewResult.risk_level.label("risk_level"),
            func.count().label("result_count"),
            func.coalesce(func.sum(RuleReviewResult.risk_item_count), 0).label(
                "risk_item_count"
            ),
        )
        .where(RuleReviewResult.created_at >= window_from)
        .group_by(RuleReviewResult.risk_level)
    )
    rule_statement = _apply_project_filters(
        rule_statement,
        RuleReviewResult.project_id,
        project_id=project_id,
        group_id=group_id,
    )

    preflight_statement = (
        select(
            DeterministicCheckRun.status.label("status"),
            DeterministicCheckRun.findings_json.label("findings_json"),
        )
        .where(DeterministicCheckRun.created_at >= window_from)
        .order_by(
            DeterministicCheckRun.created_at.desc(),
            DeterministicCheckRun.id.desc(),
        )
        .limit(FINDING_SCAN_LIMIT + 1)
    )
    preflight_statement = _apply_project_filters(
        preflight_statement,
        DeterministicCheckRun.project_id,
        project_id=project_id,
        group_id=group_id,
    )

    finding_statement = (
        select(
            AiReviewResult.task_id.label("task_id"),
            AiReviewResult.findings_json.label("findings_json"),
        )
        .where(AiReviewResult.updated_at >= window_from)
        .order_by(AiReviewResult.updated_at.desc(), AiReviewResult.id.desc())
        .limit(FINDING_SCAN_LIMIT + 1)
    )
    finding_statement = _apply_project_filters(
        finding_statement,
        AiReviewResult.project_id,
        project_id=project_id,
        group_id=group_id,
    )

    notification_statement = (
        select(
            NotificationRecord.status.label("status"),
            func.count().label("count"),
        )
        .join(ReviewTask, ReviewTask.id == NotificationRecord.task_id)
        .where(NotificationRecord.created_at >= window_from)
        .group_by(NotificationRecord.status)
    )
    notification_statement = _apply_project_filters(
        notification_statement,
        ReviewTask.project_id,
        project_id=project_id,
        group_id=group_id,
    )

    feedback_statement = select(
        ReviewItemFeedback.status.label("status"),
        ReviewItemFeedback.feedback_type.label("feedback_type"),
        ReviewItemFeedback.reason_type.label("reason_type"),
        ReviewItemFeedback.suggest_as_project_rule.label(
            "suggest_as_project_rule"
        ),
        func.count().label("count"),
    ).group_by(
        ReviewItemFeedback.status,
        ReviewItemFeedback.feedback_type,
        ReviewItemFeedback.reason_type,
        ReviewItemFeedback.suggest_as_project_rule,
    )
    feedback_statement = _apply_project_filters(
        feedback_statement,
        ReviewItemFeedback.project_id,
        project_id=project_id,
        group_id=group_id,
    )

    evaluation_case_statement = select(
        EvaluationCase.verdict.label("verdict"),
        EvaluationCase.rule_gap_attribution_type.label("rule_gap_type"),
        func.count().label("count"),
    ).group_by(
        EvaluationCase.verdict,
        EvaluationCase.rule_gap_attribution_type,
    )
    evaluation_case_statement = _apply_project_filters(
        evaluation_case_statement,
        EvaluationCase.project_id,
        project_id=project_id,
        group_id=group_id,
    )

    evaluation_run_statement = select(
        EvaluationRun.status.label("status"),
        func.count().label("count"),
    ).group_by(EvaluationRun.status)
    evaluation_run_statement = _apply_project_filters(
        evaluation_run_statement,
        EvaluationRun.project_id,
        project_id=project_id,
        group_id=group_id,
    )

    policy_statement = select(
        ProjectReviewPolicy.enabled.label("enabled"),
        func.count().label("count"),
    ).group_by(ProjectReviewPolicy.enabled)
    policy_statement = _apply_project_filters(
        policy_statement,
        ProjectReviewPolicy.project_id,
        project_id=project_id,
        group_id=group_id,
    )

    acceptance_statement = select(
        ReviewQualityAcceptanceGate.status.label("status"),
        func.count().label("count"),
        func.max(ReviewQualityAcceptanceGate.updated_at).label("latest_at"),
    ).group_by(ReviewQualityAcceptanceGate.status)
    acceptance_statement = _apply_project_filters(
        acceptance_statement,
        ReviewQualityAcceptanceGate.project_id,
        project_id=project_id,
        group_id=group_id,
    )

    preflight_rows = _rows(db, preflight_statement)
    finding_rows = _rows(db, finding_statement)
    return GovernanceProjectionData(
        rule_rows=_rows(db, rule_statement),
        preflight_rows=preflight_rows[:FINDING_SCAN_LIMIT],
        finding_rows=finding_rows[:FINDING_SCAN_LIMIT],
        notification_rows=_rows(db, notification_statement),
        feedback_rows=_rows(db, feedback_statement),
        evaluation_case_rows=_rows(db, evaluation_case_statement),
        evaluation_run_rows=_rows(db, evaluation_run_statement),
        policy_rows=_rows(db, policy_statement),
        acceptance_rows=_rows(db, acceptance_statement),
        preflight_truncated=len(preflight_rows) > FINDING_SCAN_LIMIT,
        finding_truncated=len(finding_rows) > FINDING_SCAN_LIMIT,
    )


def load_governance_base_counts(
    db: Session,
    *,
    project_id: int | None,
    group_id: int | None,
) -> GovernanceBaseCounts:
    pending_feedback_statement = (
        select(func.count())
        .select_from(ReviewItemFeedback)
        .where(ReviewItemFeedback.status == "PENDING")
    )
    pending_feedback_statement = _apply_project_filters(
        pending_feedback_statement,
        ReviewItemFeedback.project_id,
        project_id=project_id,
        group_id=group_id,
    )
    evaluation_case_statement = select(func.count()).select_from(EvaluationCase)
    evaluation_case_statement = _apply_project_filters(
        evaluation_case_statement,
        EvaluationCase.project_id,
        project_id=project_id,
        group_id=group_id,
    )
    return GovernanceBaseCounts(
        pending_feedback_count=_count(db, pending_feedback_statement),
        evaluation_case_count=_count(db, evaluation_case_statement),
    )


def _load_tasks(db: Session, task_ids: list[int]) -> list[dict[str, Any]]:
    if not task_ids:
        return []
    return _rows(
        db,
        select(
            ReviewTask.id.label("task_id"),
            ReviewTask.project_id.label("project_id"),
            Project.name.label("project_name"),
            Project.group_id.label("group_id"),
            ReviewTask.trigger_type.label("trigger_type"),
            ReviewTask.status.label("technical_status"),
            ReviewTask.review_status.label("review_status"),
            ReviewTask.risk_level.label("risk_level"),
            ReviewTask.created_at.label("created_at"),
            ReviewTask.updated_at.label("updated_at"),
        )
        .join(Project, Project.id == ReviewTask.project_id)
        .where(ReviewTask.id.in_(task_ids)),
    )


def _load_rule_results(db: Session, task_ids: list[int]) -> list[dict[str, Any]]:
    if not task_ids:
        return []
    return _rows(
        db,
        select(
            RuleReviewResult.task_id.label("task_id"),
            RuleReviewResult.risk_level.label("risk_level"),
            RuleReviewResult.risk_item_count.label("risk_item_count"),
            RuleReviewResult.created_at.label("created_at"),
            RuleReviewResult.updated_at.label("updated_at"),
        ).where(RuleReviewResult.task_id.in_(task_ids)),
    )


def _load_ai_results(db: Session, task_ids: list[int]) -> list[dict[str, Any]]:
    if not task_ids:
        return []
    return _rows(
        db,
        select(
            AiReviewResult.id.label("id"),
            AiReviewResult.task_id.label("task_id"),
            AiReviewResult.review_key.label("review_key"),
            AiReviewResult.provider.label("provider"),
            AiReviewResult.model.label("model"),
            AiReviewResult.display_name.label("display_name"),
            AiReviewResult.status.label("status"),
            AiReviewResult.overall_level.label("overall_level"),
            AiReviewResult.finding_count.label("finding_count"),
            AiReviewResult.findings_json.label("findings_json"),
            AiReviewResult.requested_engine.label("requested_engine"),
            AiReviewResult.effective_engine.label("effective_engine"),
            AiReviewResult.started_at.label("started_at"),
            AiReviewResult.finished_at.label("finished_at"),
            AiReviewResult.created_at.label("created_at"),
            AiReviewResult.updated_at.label("updated_at"),
        )
        .where(AiReviewResult.task_id.in_(task_ids))
        .order_by(AiReviewResult.updated_at.desc(), AiReviewResult.id.desc()),
    )


def _load_progress_events(
    db: Session,
    task_ids: list[int],
    active_limit: int,
) -> list[dict[str, Any]]:
    if not task_ids:
        return []
    return _rows(
        db,
        select(
            CodeQualityReviewProgressEvent.id.label("id"),
            CodeQualityReviewProgressEvent.task_id.label("task_id"),
            CodeQualityReviewProgressEvent.review_key.label("review_key"),
            CodeQualityReviewProgressEvent.phase.label("phase"),
            CodeQualityReviewProgressEvent.level.label("level"),
            CodeQualityReviewProgressEvent.created_at.label("created_at"),
        )
        .where(CodeQualityReviewProgressEvent.task_id.in_(task_ids))
        .order_by(
            CodeQualityReviewProgressEvent.created_at.desc(),
            CodeQualityReviewProgressEvent.id.desc(),
        )
        .limit(max(active_limit * 50, 200)),
    )


def _load_agent_runs(db: Session, task_ids: list[int]) -> list[dict[str, Any]]:
    if not task_ids:
        return []
    return _rows(
        db,
        select(
            AgentReviewRun.id.label("id"),
            AgentReviewRun.task_id.label("task_id"),
            AgentReviewRun.review_key.label("review_key"),
            AgentReviewRun.requested_engine.label("requested_engine"),
            AgentReviewRun.effective_engine.label("effective_engine"),
            AgentReviewRun.model.label("model"),
            AgentReviewRun.status.label("status"),
            AgentReviewRun.duration_ms.label("duration_ms"),
            AgentReviewRun.heartbeat_at.label("heartbeat_at"),
            AgentReviewRun.started_at.label("started_at"),
            AgentReviewRun.finished_at.label("finished_at"),
            AgentReviewRun.created_at.label("created_at"),
            AgentReviewRun.updated_at.label("updated_at"),
        )
        .where(AgentReviewRun.task_id.in_(task_ids))
        .order_by(AgentReviewRun.updated_at.desc(), AgentReviewRun.id.desc()),
    )


def _load_deterministic_runs(
    db: Session,
    task_ids: list[int],
) -> list[dict[str, Any]]:
    if not task_ids:
        return []
    return _rows(
        db,
        select(
            DeterministicCheckRun.id.label("id"),
            DeterministicCheckRun.task_id.label("task_id"),
            DeterministicCheckRun.status.label("status"),
            DeterministicCheckRun.started_at.label("started_at"),
            DeterministicCheckRun.finished_at.label("finished_at"),
            DeterministicCheckRun.created_at.label("created_at"),
            DeterministicCheckRun.updated_at.label("updated_at"),
        ).where(DeterministicCheckRun.task_id.in_(task_ids)),
    )


def _load_notifications(
    db: Session,
    task_ids: list[int],
) -> list[dict[str, Any]]:
    if not task_ids:
        return []
    return _rows(
        db,
        select(
            NotificationRecord.id.label("id"),
            NotificationRecord.task_id.label("task_id"),
            NotificationRecord.result_id.label("result_id"),
            NotificationRecord.status.label("status"),
            NotificationRecord.sent_at.label("sent_at"),
            NotificationRecord.created_at.label("created_at"),
            NotificationRecord.updated_at.label("updated_at"),
        )
        .where(NotificationRecord.task_id.in_(task_ids))
        .order_by(NotificationRecord.updated_at.desc(), NotificationRecord.id.desc()),
    )


def _load_provider_observations(
    db: Session,
    window_from: datetime,
) -> list[dict[str, Any]]:
    provider_match = _case_insensitive_equal(
        db,
        AiReviewResult.provider,
        CodeQualityModelProvider.provider_code,
    )
    default_provider = (
        select(CodeQualityReviewSettings.default_provider_code)
        .order_by(CodeQualityReviewSettings.id.asc())
        .limit(1)
        .scalar_subquery()
    )
    success_count = (
        select(func.count())
        .select_from(AiReviewResult)
        .where(
            provider_match,
            AiReviewResult.updated_at >= window_from,
            AiReviewResult.status == "SUCCESS",
        )
        .correlate(CodeQualityModelProvider)
        .scalar_subquery()
    )
    failure_count = (
        select(func.count())
        .select_from(AiReviewResult)
        .where(
            provider_match,
            AiReviewResult.updated_at >= window_from,
            AiReviewResult.status == "FAILED",
        )
        .correlate(CodeQualityModelProvider)
        .scalar_subquery()
    )
    last_observed = (
        select(func.max(AiReviewResult.updated_at))
        .where(
            provider_match,
            AiReviewResult.updated_at >= window_from,
        )
        .correlate(CodeQualityModelProvider)
        .scalar_subquery()
    )
    return _rows(
        db,
        select(
            CodeQualityModelProvider.provider_code.label("provider_code"),
            CodeQualityModelProvider.provider_name.label("provider_name"),
            CodeQualityModelProvider.provider_type.label("provider_type"),
            CodeQualityModelProvider.model_name.label("model_name"),
            CodeQualityModelProvider.enabled.label("enabled"),
            case(
                (
                    _case_insensitive_equal(
                        db,
                        CodeQualityModelProvider.provider_code,
                        default_provider,
                    ),
                    True,
                ),
                else_=False,
            ).label("default_provider"),
            success_count.label("recent_success_count"),
            failure_count.label("recent_failure_count"),
            last_observed.label("last_observed_at"),
        ).order_by(
            CodeQualityModelProvider.sort_order.asc(),
            CodeQualityModelProvider.provider_code.asc(),
        ),
    )


def _load_recent_alerts(
    db: Session,
    *,
    window_from: datetime,
    alert_limit: int,
    project_id: int | None,
    group_id: int | None,
) -> list[dict[str, Any]]:
    failed_jobs = (
        select(
            literal("JOB_FAILED").label("alert_type"),
            CodeQualitySchedulerJob.id.label("source_id"),
            _alert_union_text(db, CodeQualitySchedulerJob.status).label("status"),
            CodeQualitySchedulerJob.task_id.label("task_id"),
            _alert_union_text(db, CodeQualitySchedulerJob.review_key).label(
                "review_key"
            ),
            CodeQualitySchedulerJob.project_id.label("project_id"),
            Project.name.label("project_name"),
            CodeQualitySchedulerJob.updated_at.label("occurred_at"),
        )
        .join(Project, Project.id == CodeQualitySchedulerJob.project_id)
        .where(
            CodeQualitySchedulerJob.job_type.in_(REVIEW_JOB_TYPES),
            CodeQualitySchedulerJob.status == "FAILED",
            CodeQualitySchedulerJob.updated_at >= window_from,
        )
    )
    failed_jobs = _apply_project_filters(
        failed_jobs,
        CodeQualitySchedulerJob.project_id,
        project_id=project_id,
        group_id=group_id,
    )

    failed_runs = (
        select(
            literal("AGENT_RUN_FAILED").label("alert_type"),
            AgentReviewRun.id.label("source_id"),
            _alert_union_text(db, AgentReviewRun.status).label("status"),
            AgentReviewRun.task_id.label("task_id"),
            _alert_union_text(db, AgentReviewRun.review_key).label("review_key"),
            ReviewTask.project_id.label("project_id"),
            Project.name.label("project_name"),
            AgentReviewRun.updated_at.label("occurred_at"),
        )
        .join(ReviewTask, ReviewTask.id == AgentReviewRun.task_id)
        .join(Project, Project.id == ReviewTask.project_id)
        .where(
            AgentReviewRun.status.in_(FAILED_AGENT_STATUSES),
            AgentReviewRun.updated_at >= window_from,
        )
    )
    failed_runs = _apply_project_filters(
        failed_runs,
        ReviewTask.project_id,
        project_id=project_id,
        group_id=group_id,
    )

    failed_notifications = (
        select(
            literal("NOTIFICATION_FAILED").label("alert_type"),
            NotificationRecord.id.label("source_id"),
            _alert_union_text(db, NotificationRecord.status).label("status"),
            NotificationRecord.task_id.label("task_id"),
            literal(None).label("review_key"),
            ReviewTask.project_id.label("project_id"),
            Project.name.label("project_name"),
            NotificationRecord.updated_at.label("occurred_at"),
        )
        .join(ReviewTask, ReviewTask.id == NotificationRecord.task_id)
        .join(Project, Project.id == ReviewTask.project_id)
        .where(
            NotificationRecord.status == "FAILED",
            NotificationRecord.updated_at >= window_from,
        )
    )
    failed_notifications = _apply_project_filters(
        failed_notifications,
        ReviewTask.project_id,
        project_id=project_id,
        group_id=group_id,
    )

    fallback_alerts = (
        select(
            literal("FALLBACK").label("alert_type"),
            AiReviewResult.id.label("source_id"),
            _alert_union_text(db, AiReviewResult.status).label("status"),
            AiReviewResult.task_id.label("task_id"),
            _alert_union_text(db, AiReviewResult.review_key).label("review_key"),
            AiReviewResult.project_id.label("project_id"),
            Project.name.label("project_name"),
            AiReviewResult.updated_at.label("occurred_at"),
        )
        .join(Project, Project.id == AiReviewResult.project_id)
        .where(
            AiReviewResult.updated_at >= window_from,
            AiReviewResult.requested_engine == "AGENT",
            AiReviewResult.effective_engine == "STANDARD_FALLBACK",
        )
    )
    fallback_alerts = _apply_project_filters(
        fallback_alerts,
        AiReviewResult.project_id,
        project_id=project_id,
        group_id=group_id,
    )

    critical_alerts = (
        select(
            literal("CRITICAL_FINDING").label("alert_type"),
            AiReviewResult.id.label("source_id"),
            _alert_union_text(db, AiReviewResult.status).label("status"),
            AiReviewResult.task_id.label("task_id"),
            _alert_union_text(db, AiReviewResult.review_key).label("review_key"),
            AiReviewResult.project_id.label("project_id"),
            Project.name.label("project_name"),
            AiReviewResult.updated_at.label("occurred_at"),
        )
        .join(Project, Project.id == AiReviewResult.project_id)
        .where(
            AiReviewResult.updated_at >= window_from,
            AiReviewResult.overall_level.in_(("CRITICAL", "BLOCKER")),
        )
    )
    critical_alerts = _apply_project_filters(
        critical_alerts,
        AiReviewResult.project_id,
        project_id=project_id,
        group_id=group_id,
    )

    combined = union_all(
        failed_jobs,
        failed_runs,
        failed_notifications,
        fallback_alerts,
        critical_alerts,
    ).subquery()
    return _rows(
        db,
        select(
            combined.c.alert_type,
            combined.c.source_id,
            combined.c.status,
            combined.c.task_id,
            combined.c.review_key,
            combined.c.project_id,
            combined.c.project_name,
            combined.c.occurred_at,
        )
        .order_by(combined.c.occurred_at.desc())
        .limit(alert_limit),
    )


def _alert_union_text(db: Session, expression):
    bind = db.get_bind()
    if bind.dialect.name == "mysql":
        return expression.collate(MYSQL_ALERT_UNION_COLLATION)
    return expression


def _case_insensitive_equal(db: Session, left, right):
    bind = db.get_bind()
    if bind.dialect.name == "mysql":
        return left == right
    return func.upper(left) == func.upper(right)


def _select_active_task_ids(
    active_jobs: list[dict[str, Any]],
    task_candidates: list[dict[str, Any]],
    result_candidates: list[dict[str, Any]],
    *,
    active_limit: int,
) -> tuple[list[int], int]:
    activity: dict[int, datetime | None] = {}
    for row in [*active_jobs, *task_candidates, *result_candidates]:
        task_id = int(row["task_id"])
        occurred_at = row.get("updated_at") or row.get("created_at")
        current = activity.get(task_id)
        if current is None or (occurred_at is not None and occurred_at > current):
            activity[task_id] = occurred_at
    ordered = sorted(
        activity,
        key=lambda task_id: (activity[task_id] or datetime.min, task_id),
        reverse=True,
    )
    return ordered[:active_limit], len(ordered)


def _apply_project_filters(
    statement: Select,
    project_column: object,
    *,
    project_id: int | None,
    group_id: int | None,
) -> Select:
    if project_id is not None:
        statement = statement.where(project_column == project_id)
    if group_id is not None:
        group_project_ids = select(Project.id).where(Project.group_id == group_id)
        statement = statement.where(project_column.in_(group_project_ids))
    return statement


def _rows(db: Session, statement: Select) -> list[dict[str, Any]]:
    return [dict(row) for row in db.execute(statement).mappings().all()]


def _row(db: Session, statement: Select) -> dict[str, Any] | None:
    row = db.execute(statement).mappings().first()
    return dict(row) if row is not None else None


def _count(db: Session, statement: Select) -> int:
    return int(db.scalar(statement) or 0)
