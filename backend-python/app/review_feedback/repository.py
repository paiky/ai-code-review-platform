from __future__ import annotations

from collections import Counter
from datetime import datetime
import json
from typing import Any

from sqlalchemy import and_, func, inspect, or_, select, text
from sqlalchemy.orm import Session

from app.core.json_utils import format_datetime, page_response, read_json, read_json_array
from app.project_integration.models import Project
from app.review_feedback.models import ReviewItemFeedback
from app.review_record.models import ReviewTask


def ensure_feedback_schema(db: Session) -> None:
    connection = db.connection()
    inspector = inspect(connection)
    if not inspector.has_table(ReviewItemFeedback.__tablename__):
        ReviewItemFeedback.__table__.create(bind=connection)
        db.flush()
        return
    columns = {column["name"] for column in inspector.get_columns(ReviewItemFeedback.__tablename__)}
    _add_column_if_missing(db, columns, "missing_context_types_json", "TEXT NULL")
    db.flush()


def feedback_to_response(
    record: ReviewItemFeedback,
    *,
    task: ReviewTask | None = None,
    project: Project | None = None,
) -> dict[str, Any]:
    return {
        "id": record.id,
        "projectId": record.project_id,
        "projectName": project.name if project is not None else None,
        "taskId": record.task_id,
        "triggerType": task.trigger_type if task is not None else None,
        "externalSourceId": task.external_source_id if task is not None else None,
        "externalUrl": task.external_url if task is not None else None,
        "sourceType": record.source_type,
        "itemFingerprint": record.item_fingerprint,
        "feedbackKey": record.item_fingerprint,
        "cardId": record.card_id,
        "riskId": record.risk_id,
        "reviewKey": record.review_key,
        "findingIndex": record.finding_index,
        "riskType": record.risk_type,
        "riskTitle": record.risk_title,
        "originalRiskLevel": record.original_risk_level,
        "feedbackType": record.feedback_type,
        "reasonType": record.reason_type,
        "reasonText": record.reason_text,
        "missingContextTypes": read_json_array(record.missing_context_types_json),
        "suggestAsProjectRule": bool(record.suggest_as_project_rule),
        "status": record.status,
        "adminComment": record.admin_comment,
        "itemSnapshot": read_json(record.item_snapshot_json, None),
        "operatorName": record.operator_name,
        "operatorUsername": record.operator_username,
        "createdAt": format_datetime(record.created_at),
        "updatedAt": format_datetime(record.updated_at),
    }


def get_feedback_map_for_task(db: Session, task_id: int) -> dict[tuple[str, str], dict[str, Any]]:
    ensure_feedback_schema(db)
    records = db.scalars(
        select(ReviewItemFeedback)
        .where(ReviewItemFeedback.task_id == task_id)
        .order_by(ReviewItemFeedback.id.asc())
    ).all()
    return {
        (record.source_type, record.item_fingerprint): feedback_to_response(record)
        for record in records
    }


def list_task_feedbacks(db: Session, task_id: int) -> list[dict[str, Any]]:
    ensure_feedback_schema(db)
    rows = db.execute(
        select(ReviewItemFeedback, ReviewTask, Project)
        .join(ReviewTask, ReviewTask.id == ReviewItemFeedback.task_id)
        .join(Project, Project.id == ReviewItemFeedback.project_id)
        .where(ReviewItemFeedback.task_id == task_id)
        .order_by(ReviewItemFeedback.created_at.desc(), ReviewItemFeedback.id.desc())
    ).all()
    return [feedback_to_response(record, task=task, project=project) for record, task, project in rows]


def upsert_feedback(
    db: Session,
    *,
    task: ReviewTask,
    source_type: str,
    item_fingerprint: str,
    target: dict[str, Any],
    feedback_type: str,
    reason_type: str | None,
    reason_text: str | None,
    missing_context_types: list[str],
    suggest_as_project_rule: bool,
    operator_name: str | None,
    operator_username: str | None,
    item_snapshot_json: str | None,
) -> ReviewItemFeedback:
    ensure_feedback_schema(db)
    now = datetime.now()
    record = db.scalars(
        select(ReviewItemFeedback)
        .where(ReviewItemFeedback.task_id == task.id)
        .where(ReviewItemFeedback.source_type == source_type)
        .where(ReviewItemFeedback.item_fingerprint == item_fingerprint)
    ).first()
    if record is None:
        record = ReviewItemFeedback(
            project_id=task.project_id,
            task_id=task.id,
            source_type=source_type,
            item_fingerprint=item_fingerprint,
            status="PENDING",
            created_at=now,
        )
        db.add(record)
    record.project_id = task.project_id
    record.card_id = target.get("cardId")
    record.risk_id = target.get("riskId")
    record.review_key = target.get("reviewKey")
    record.finding_index = target.get("findingIndex")
    record.risk_type = target.get("riskType")
    record.risk_title = target.get("riskTitle")
    record.original_risk_level = target.get("originalRiskLevel")
    record.feedback_type = feedback_type
    record.reason_type = reason_type
    record.reason_text = reason_text
    record.missing_context_types_json = (
        json.dumps(missing_context_types, ensure_ascii=False) if missing_context_types else None
    )
    record.suggest_as_project_rule = suggest_as_project_rule
    record.item_snapshot_json = item_snapshot_json
    record.operator_name = operator_name
    record.operator_username = operator_username
    record.updated_at = now
    db.flush()
    return record


def update_feedback_status(
    db: Session,
    record: ReviewItemFeedback,
    *,
    status: str,
    admin_comment: str | None,
) -> ReviewItemFeedback:
    now = datetime.now()
    record.status = status
    record.admin_comment = admin_comment
    record.updated_at = now
    db.flush()
    return record


def get_feedback(db: Session, feedback_id: int) -> ReviewItemFeedback | None:
    ensure_feedback_schema(db)
    return db.get(ReviewItemFeedback, feedback_id)


def list_feedback_pool(
    db: Session,
    *,
    project_id: int | None,
    source_type: str | None,
    risk_type: str | None,
    feedback_type: str | None,
    reason_type: str | None,
    missing_context_type: str | None,
    policy_candidate: bool,
    status: str | None,
    keyword: str | None,
    page_no: int,
    page_size: int,
) -> dict[str, Any]:
    ensure_feedback_schema(db)
    page_no = max(page_no, 1)
    page_size = max(page_size, 1)
    filters = []
    if project_id is not None:
        filters.append(ReviewItemFeedback.project_id == project_id)
    if source_type:
        filters.append(ReviewItemFeedback.source_type == source_type)
    if risk_type:
        filters.append(ReviewItemFeedback.risk_type == risk_type)
    if feedback_type:
        filters.append(ReviewItemFeedback.feedback_type == feedback_type)
    if reason_type:
        filters.append(ReviewItemFeedback.reason_type == reason_type)
    if missing_context_type:
        filters.append(ReviewItemFeedback.missing_context_types_json.like(f'%"{missing_context_type}"%'))
    if policy_candidate:
        filters.append(
            or_(
                ReviewItemFeedback.suggest_as_project_rule.is_(True),
                ReviewItemFeedback.status == "VALID",
            )
        )
        filters.append(ReviewItemFeedback.status.notin_(("INSUFFICIENT", "IGNORED", "CONVERTED")))
        filters.append(
            or_(
                ReviewItemFeedback.reason_type.is_(None),
                ReviewItemFeedback.reason_type != "CONTEXT_MISSING",
            )
        )
    if status:
        filters.append(ReviewItemFeedback.status == status)
    if keyword:
        like = f"%{keyword}%"
        filters.append(
            (ReviewItemFeedback.risk_title.like(like))
            | (Project.name.like(like))
            | (ReviewTask.external_source_id.like(like))
            | (ReviewItemFeedback.reason_text.like(like))
        )

    total_stmt = (
        select(func.count())
        .select_from(ReviewItemFeedback)
        .join(ReviewTask, ReviewTask.id == ReviewItemFeedback.task_id)
        .join(Project, Project.id == ReviewItemFeedback.project_id)
    )
    if filters:
        total_stmt = total_stmt.where(and_(*filters))
    total = db.scalar(total_stmt) or 0

    rows_stmt = (
        select(ReviewItemFeedback, ReviewTask, Project)
        .join(ReviewTask, ReviewTask.id == ReviewItemFeedback.task_id)
        .join(Project, Project.id == ReviewItemFeedback.project_id)
    )
    if filters:
        rows_stmt = rows_stmt.where(and_(*filters))
    rows = db.execute(
        rows_stmt
        .order_by(ReviewItemFeedback.created_at.desc(), ReviewItemFeedback.id.desc())
        .limit(page_size)
        .offset((page_no - 1) * page_size)
    ).all()
    response = page_response(
        [feedback_to_response(record, task=task, project=project) for record, task, project in rows],
        page_no,
        page_size,
        total,
    )
    response["contextMissingStats"] = _context_missing_stats(db, filters)
    return response


def _context_missing_stats(db: Session, filters: list[Any]) -> dict[str, Any]:
    stats_filters = [*filters, ReviewItemFeedback.reason_type == "CONTEXT_MISSING"]
    total_stmt = (
        select(func.count())
        .select_from(ReviewItemFeedback)
        .join(ReviewTask, ReviewTask.id == ReviewItemFeedback.task_id)
        .join(Project, Project.id == ReviewItemFeedback.project_id)
        .where(and_(*stats_filters))
    )
    total = db.scalar(total_stmt) or 0

    risk_rows = db.execute(
        select(ReviewItemFeedback.risk_type, func.count())
        .select_from(ReviewItemFeedback)
        .join(ReviewTask, ReviewTask.id == ReviewItemFeedback.task_id)
        .join(Project, Project.id == ReviewItemFeedback.project_id)
        .where(and_(*stats_filters))
        .group_by(ReviewItemFeedback.risk_type)
        .order_by(func.count().desc())
    ).all()

    context_type_counter: Counter[str] = Counter()
    context_rows = db.execute(
        select(ReviewItemFeedback.missing_context_types_json)
        .select_from(ReviewItemFeedback)
        .join(ReviewTask, ReviewTask.id == ReviewItemFeedback.task_id)
        .join(Project, Project.id == ReviewItemFeedback.project_id)
        .where(and_(*stats_filters))
    ).all()
    for (raw_types,) in context_rows:
        for item in read_json_array(raw_types):
            if item:
                context_type_counter[str(item)] += 1

    return {
        "total": int(total),
        "byRiskType": [
            {"riskType": risk_type or "UNKNOWN", "count": int(count)}
            for risk_type, count in risk_rows
        ],
        "byMissingContextType": [
            {"missingContextType": item, "count": count}
            for item, count in context_type_counter.most_common()
        ],
    }


def _add_column_if_missing(db: Session, columns: set[str], column_name: str, definition: str) -> None:
    if column_name in columns:
        return
    db.execute(text(f"ALTER TABLE review_item_feedbacks ADD COLUMN {column_name} {definition}"))
    columns.add(column_name)
