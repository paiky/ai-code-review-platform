from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.code_quality.models import CodeQualitySchedulerJob
from app.evaluation.models import EvaluationCase
from app.project_integration.models import Project
from app.review_feedback.models import ReviewItemFeedback
from app.review_record.models import ReviewTask


REVIEW_JOB_TYPES = ("AI_REVIEW", "AGENT_REVIEW")
ACTIVE_TASK_STATUSES = ("RUNNING",)
ACTIVE_REVIEW_STATUSES = ("REVIEWING",)


@dataclass(frozen=True)
class RuntimeBaseCounts:
    intake_task_count: int
    active_task_count: int
    queued_job_count: int
    running_job_count: int


@dataclass(frozen=True)
class GovernanceBaseCounts:
    pending_feedback_count: int
    evaluation_case_count: int


def load_runtime_base_counts(
    db: Session,
    *,
    window_from: datetime,
    project_id: int | None,
    group_id: int | None,
) -> RuntimeBaseCounts:
    intake_statement = select(func.count()).select_from(ReviewTask).where(
        ReviewTask.created_at >= window_from
    )
    intake_statement = _apply_project_filters(
        intake_statement,
        ReviewTask.project_id,
        project_id=project_id,
        group_id=group_id,
    )

    active_task_statement = select(func.count()).select_from(ReviewTask).where(
        (ReviewTask.status.in_(ACTIVE_TASK_STATUSES))
        | (ReviewTask.review_status.in_(ACTIVE_REVIEW_STATUSES))
    )
    active_task_statement = _apply_project_filters(
        active_task_statement,
        ReviewTask.project_id,
        project_id=project_id,
        group_id=group_id,
    )

    active_job_base = (
        select(func.count())
        .select_from(CodeQualitySchedulerJob)
        .where(CodeQualitySchedulerJob.job_type.in_(REVIEW_JOB_TYPES))
    )
    active_job_base = _apply_project_filters(
        active_job_base,
        CodeQualitySchedulerJob.project_id,
        project_id=project_id,
        group_id=group_id,
    )

    return RuntimeBaseCounts(
        intake_task_count=_count(db, intake_statement),
        active_task_count=_count(db, active_task_statement),
        queued_job_count=_count(
            db,
            active_job_base.where(CodeQualitySchedulerJob.status == "QUEUED"),
        ),
        running_job_count=_count(
            db,
            active_job_base.where(CodeQualitySchedulerJob.status == "RUNNING"),
        ),
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


def _count(db: Session, statement: Select) -> int:
    return int(db.scalar(statement) or 0)
