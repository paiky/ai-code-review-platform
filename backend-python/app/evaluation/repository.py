from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, inspect, select, text
from sqlalchemy.orm import Session

from app.core.json_utils import format_datetime, page_response, read_json
from app.evaluation.models import EvaluationCase
from app.project_integration.models import Project
from app.review_record.models import ReviewTask


def ensure_evaluation_case_schema(db: Session) -> None:
    connection = db.connection()
    inspector = inspect(connection)
    if not inspector.has_table(EvaluationCase.__tablename__):
        EvaluationCase.__table__.create(bind=connection)
        db.flush()
        return
    columns = {column["name"] for column in inspector.get_columns(EvaluationCase.__tablename__)}
    _add_column_if_missing(db, columns, "task_id", "BIGINT NULL")
    _add_column_if_missing(db, columns, "review_key", "VARCHAR(64) NULL")
    _add_column_if_missing(db, columns, "finding_id", "VARCHAR(128) NULL")
    _add_column_if_missing(db, columns, "fingerprint", "VARCHAR(128) NULL")
    _add_column_if_missing(db, columns, "project_id", "BIGINT NOT NULL")
    _add_column_if_missing(db, columns, "provider", "VARCHAR(64) NULL")
    _add_column_if_missing(db, columns, "profile", "VARCHAR(64) NULL")
    _add_column_if_missing(db, columns, "risk_type", "VARCHAR(64) NULL")
    _add_column_if_missing(db, columns, "severity", "VARCHAR(32) NULL")
    _add_column_if_missing(db, columns, "context_status", "VARCHAR(32) NULL")
    _add_column_if_missing(db, columns, "verdict", "VARCHAR(64) NOT NULL DEFAULT 'UNKNOWN'")
    _add_column_if_missing(db, columns, "human_comment", "TEXT NULL")
    _add_column_if_missing(db, columns, "source", "VARCHAR(32) NOT NULL DEFAULT 'MANUAL'")
    _add_column_if_missing(db, columns, "item_snapshot_json", "TEXT NULL")
    _add_column_if_missing(db, columns, "created_at", "DATETIME NULL")
    _add_column_if_missing(db, columns, "updated_at", "DATETIME NULL")
    db.flush()


def evaluation_case_to_response(
    record: EvaluationCase,
    *,
    project: Project | None = None,
    task: ReviewTask | None = None,
) -> dict[str, Any]:
    return {
        "id": record.id,
        "taskId": record.task_id,
        "reviewKey": record.review_key,
        "findingId": record.finding_id,
        "fingerprint": record.fingerprint,
        "projectId": record.project_id,
        "projectName": project.name if project is not None else None,
        "triggerType": task.trigger_type if task is not None else None,
        "externalSourceId": task.external_source_id if task is not None else None,
        "externalUrl": task.external_url if task is not None else None,
        "provider": record.provider,
        "profile": record.profile,
        "riskType": record.risk_type,
        "severity": record.severity,
        "contextStatus": record.context_status,
        "verdict": record.verdict,
        "humanComment": record.human_comment,
        "source": record.source,
        "itemSnapshot": read_json(record.item_snapshot_json, None),
        "createdAt": format_datetime(record.created_at),
        "updatedAt": format_datetime(record.updated_at),
    }


def create_evaluation_case(db: Session, values: dict[str, Any]) -> EvaluationCase:
    ensure_evaluation_case_schema(db)
    now = datetime.now()
    record = EvaluationCase(created_at=now, updated_at=now, **values)
    db.add(record)
    db.flush()
    return record


def get_evaluation_case(db: Session, case_id: int) -> EvaluationCase | None:
    ensure_evaluation_case_schema(db)
    return db.get(EvaluationCase, case_id)


def update_evaluation_case(db: Session, record: EvaluationCase, values: dict[str, Any]) -> EvaluationCase:
    for key, value in values.items():
        setattr(record, key, value)
    record.updated_at = datetime.now()
    db.flush()
    return record


def list_evaluation_cases(
    db: Session,
    *,
    project_id: int | None,
    provider: str | None,
    profile: str | None,
    risk_type: str | None,
    verdict: str | None,
    page_no: int,
    page_size: int,
) -> dict[str, Any]:
    ensure_evaluation_case_schema(db)
    page_no = max(page_no, 1)
    page_size = max(page_size, 1)
    filters = []
    if project_id is not None:
        filters.append(EvaluationCase.project_id == project_id)
    if provider:
        filters.append(EvaluationCase.provider == provider)
    if profile:
        filters.append(EvaluationCase.profile == profile)
    if risk_type:
        filters.append(EvaluationCase.risk_type == risk_type)
    if verdict:
        filters.append(EvaluationCase.verdict == verdict)

    total_stmt = select(func.count()).select_from(EvaluationCase)
    rows_stmt = (
        select(EvaluationCase, Project, ReviewTask)
        .join(Project, Project.id == EvaluationCase.project_id)
        .outerjoin(ReviewTask, ReviewTask.id == EvaluationCase.task_id)
    )
    if filters:
        total_stmt = total_stmt.where(and_(*filters))
        rows_stmt = rows_stmt.where(and_(*filters))
    total = db.scalar(total_stmt) or 0
    rows = db.execute(
        rows_stmt.order_by(EvaluationCase.created_at.desc(), EvaluationCase.id.desc())
        .limit(page_size)
        .offset((page_no - 1) * page_size)
    ).all()
    return page_response(
        [evaluation_case_to_response(record, project=project, task=task) for record, project, task in rows],
        page_no,
        page_size,
        total,
    )


def _add_column_if_missing(db: Session, columns: set[str], column_name: str, definition: str) -> None:
    if column_name in columns:
        return
    db.execute(text(f"ALTER TABLE evaluation_cases ADD COLUMN {column_name} {definition}"))
    columns.add(column_name)
