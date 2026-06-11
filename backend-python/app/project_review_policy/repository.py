from __future__ import annotations

from datetime import datetime
from threading import Lock
from typing import Any

from sqlalchemy import and_, inspect, select, text
from sqlalchemy.orm import Session

from app.core.json_utils import format_datetime
from app.project_integration.models import Project
from app.project_review_policy.models import ProjectReviewPolicy


_SCHEMA_LOCK = Lock()
_SCHEMA_ENSURED_ENGINE_IDS: set[int] = set()


def ensure_project_review_policy_schema(db: Session) -> None:
    engine_id = id(db.get_bind())
    if engine_id in _SCHEMA_ENSURED_ENGINE_IDS:
        return
    with _SCHEMA_LOCK:
        if engine_id in _SCHEMA_ENSURED_ENGINE_IDS:
            return
        connection = db.connection()
        inspector = inspect(connection)
        if not inspector.has_table(ProjectReviewPolicy.__tablename__):
            ProjectReviewPolicy.__table__.create(connection, checkfirst=True)
            db.flush()
            _SCHEMA_ENSURED_ENGINE_IDS.add(engine_id)
            return
        columns = {column["name"] for column in inspector.get_columns(ProjectReviewPolicy.__tablename__)}
        _add_column_if_missing(db, columns, "project_id", "BIGINT NOT NULL")
        _add_column_if_missing(db, columns, "policy_type", "VARCHAR(64) NOT NULL DEFAULT 'PROJECT_RULE'")
        _add_column_if_missing(db, columns, "risk_type", "VARCHAR(64) NULL")
        _add_column_if_missing(db, columns, "title", "VARCHAR(255) NOT NULL DEFAULT ''")
        _add_column_if_missing(db, columns, "content", "TEXT NULL")
        _add_column_if_missing(db, columns, "source_feedback_id", "BIGINT NULL")
        _add_column_if_missing(db, columns, "enabled", "BOOLEAN NOT NULL DEFAULT TRUE")
        _add_column_if_missing(db, columns, "version", "INT NOT NULL DEFAULT 1")
        _add_column_if_missing(db, columns, "created_by", "VARCHAR(128) NULL")
        _add_column_if_missing(db, columns, "created_at", "DATETIME NULL")
        _add_column_if_missing(db, columns, "updated_at", "DATETIME NULL")
        _add_index_if_missing(
            db,
            "idx_project_review_policies_project_enabled",
            "project_id, enabled",
        )
        _add_index_if_missing(
            db,
            "idx_project_review_policies_project_risk_type",
            "project_id, risk_type",
        )
        _add_index_if_missing(
            db,
            "idx_project_review_policies_source_feedback",
            "source_feedback_id",
        )
        db.flush()
        _SCHEMA_ENSURED_ENGINE_IDS.add(engine_id)


def policy_to_response(
    record: ProjectReviewPolicy,
    *,
    project: Project | None = None,
) -> dict[str, Any]:
    return {
        "id": record.id,
        "projectId": record.project_id,
        "projectName": project.name if project is not None else None,
        "policyType": record.policy_type,
        "riskType": record.risk_type,
        "title": record.title,
        "content": record.content,
        "sourceFeedbackId": record.source_feedback_id,
        "enabled": bool(record.enabled),
        "version": record.version,
        "createdBy": record.created_by,
        "createdAt": format_datetime(record.created_at),
        "updatedAt": format_datetime(record.updated_at),
    }


def create_policy(
    db: Session,
    *,
    project_id: int,
    policy_type: str,
    risk_type: str | None,
    title: str,
    content: str,
    source_feedback_id: int | None,
    enabled: bool,
    created_by: str | None,
) -> ProjectReviewPolicy:
    ensure_project_review_policy_schema(db)
    now = datetime.now()
    record = ProjectReviewPolicy(
        project_id=project_id,
        policy_type=policy_type,
        risk_type=risk_type,
        title=title,
        content=content,
        source_feedback_id=source_feedback_id,
        enabled=enabled,
        version=1,
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )
    db.add(record)
    db.flush()
    return record


def list_project_policies(
    db: Session,
    *,
    project_id: int,
    enabled: bool | None,
    policy_type: str | None,
    risk_type: str | None,
) -> list[dict[str, Any]]:
    ensure_project_review_policy_schema(db)
    filters = [ProjectReviewPolicy.project_id == project_id]
    if enabled is not None:
        filters.append(ProjectReviewPolicy.enabled.is_(enabled))
    if policy_type:
        filters.append(ProjectReviewPolicy.policy_type == policy_type)
    if risk_type:
        filters.append(ProjectReviewPolicy.risk_type == risk_type)
    rows = db.execute(
        select(ProjectReviewPolicy, Project)
        .join(Project, Project.id == ProjectReviewPolicy.project_id)
        .where(and_(*filters))
        .order_by(ProjectReviewPolicy.updated_at.desc(), ProjectReviewPolicy.id.desc())
    ).all()
    return [policy_to_response(record, project=project) for record, project in rows]


def get_policy(db: Session, policy_id: int) -> ProjectReviewPolicy | None:
    ensure_project_review_policy_schema(db)
    return db.get(ProjectReviewPolicy, policy_id)


def update_policy(
    db: Session,
    record: ProjectReviewPolicy,
    *,
    policy_type: str,
    risk_type: str | None,
    title: str,
    content: str,
    enabled: bool,
) -> ProjectReviewPolicy:
    record.policy_type = policy_type
    record.risk_type = risk_type
    record.title = title
    record.content = content
    record.enabled = enabled
    record.version = int(record.version or 1) + 1
    record.updated_at = datetime.now()
    db.flush()
    return record


def set_policy_enabled(
    db: Session,
    record: ProjectReviewPolicy,
    *,
    enabled: bool,
) -> ProjectReviewPolicy:
    record.enabled = enabled
    record.updated_at = datetime.now()
    db.flush()
    return record


def list_enabled_injectable_policies(db: Session, project_id: int) -> list[ProjectReviewPolicy]:
    ensure_project_review_policy_schema(db)
    return db.scalars(
        select(ProjectReviewPolicy)
        .where(ProjectReviewPolicy.project_id == project_id)
        .where(ProjectReviewPolicy.enabled.is_(True))
        .where(ProjectReviewPolicy.policy_type.in_(("PROJECT_RULE", "CONTEXT_FACT")))
        .order_by(ProjectReviewPolicy.updated_at.desc(), ProjectReviewPolicy.id.desc())
    ).all()


def _add_column_if_missing(db: Session, columns: set[str], column_name: str, definition: str) -> None:
    if column_name in columns:
        return
    db.execute(text(f"ALTER TABLE project_review_policies ADD COLUMN {column_name} {definition}"))
    columns.add(column_name)


def _add_index_if_missing(db: Session, index_name: str, columns_sql: str) -> None:
    existing = {index["name"] for index in inspect(db.connection()).get_indexes("project_review_policies")}
    if index_name in existing:
        return
    db.execute(text(f"CREATE INDEX {index_name} ON project_review_policies ({columns_sql})"))
