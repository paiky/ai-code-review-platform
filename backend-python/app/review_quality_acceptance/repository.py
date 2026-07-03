from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, inspect, select, text
from sqlalchemy.orm import Session

from app.core.json_utils import format_datetime, page_response, read_json
from app.project_integration.models import Project
from app.review_quality_acceptance.models import ReviewQualityAcceptanceGate


def ensure_acceptance_gate_schema(db: Session) -> None:
    connection = db.connection()
    inspector = inspect(connection)
    if not inspector.has_table(ReviewQualityAcceptanceGate.__tablename__):
        ReviewQualityAcceptanceGate.__table__.create(bind=connection)
        db.flush()
        return
    columns = {column["name"] for column in inspector.get_columns(ReviewQualityAcceptanceGate.__tablename__)}
    _add_column_if_missing(db, columns, "project_id", "BIGINT NOT NULL")
    _add_column_if_missing(db, columns, "title", "VARCHAR(255) NOT NULL DEFAULT 'Acceptance Gate'")
    _add_column_if_missing(db, columns, "change_type", "VARCHAR(64) NOT NULL DEFAULT 'OTHER'")
    _add_column_if_missing(db, columns, "status", "VARCHAR(64) NOT NULL DEFAULT 'DRAFT'")
    _add_column_if_missing(db, columns, "provider", "VARCHAR(64) NULL")
    _add_column_if_missing(db, columns, "profile", "VARCHAR(64) NULL")
    _add_column_if_missing(db, columns, "risk_type", "VARCHAR(64) NULL")
    _add_column_if_missing(db, columns, "evaluation_case_ids_json", "TEXT NULL")
    _add_column_if_missing(db, columns, "evaluation_run_ids_json", "TEXT NULL")
    _add_column_if_missing(db, columns, "rule_gap_summary_json", "TEXT NULL")
    _add_column_if_missing(db, columns, "admission_json", "TEXT NULL")
    _add_column_if_missing(db, columns, "exit_json", "TEXT NULL")
    _add_column_if_missing(db, columns, "created_at", "DATETIME NULL")
    _add_column_if_missing(db, columns, "updated_at", "DATETIME NULL")
    db.flush()


def create_acceptance_gate(db: Session, values: dict[str, Any]) -> ReviewQualityAcceptanceGate:
    ensure_acceptance_gate_schema(db)
    now = datetime.now()
    record = ReviewQualityAcceptanceGate(created_at=now, updated_at=now, **values)
    db.add(record)
    db.flush()
    return record


def get_acceptance_gate(db: Session, gate_id: int) -> ReviewQualityAcceptanceGate | None:
    ensure_acceptance_gate_schema(db)
    return db.get(ReviewQualityAcceptanceGate, gate_id)


def update_acceptance_gate(
    db: Session,
    record: ReviewQualityAcceptanceGate,
    values: dict[str, Any],
) -> ReviewQualityAcceptanceGate:
    for key, value in values.items():
        setattr(record, key, value)
    record.updated_at = datetime.now()
    db.flush()
    return record


def list_acceptance_gates(
    db: Session,
    *,
    project_id: int | None,
    change_type: str | None,
    status: str | None,
    provider: str | None,
    profile: str | None,
    risk_type: str | None,
    page_no: int,
    page_size: int,
) -> dict[str, Any]:
    ensure_acceptance_gate_schema(db)
    page_no = max(page_no, 1)
    page_size = max(page_size, 1)
    filters = _filters(
        project_id=project_id,
        change_type=change_type,
        status=status,
        provider=provider,
        profile=profile,
        risk_type=risk_type,
    )
    total_stmt = select(func.count()).select_from(ReviewQualityAcceptanceGate)
    rows_stmt = select(ReviewQualityAcceptanceGate, Project).join(Project, Project.id == ReviewQualityAcceptanceGate.project_id)
    if filters:
        total_stmt = total_stmt.where(and_(*filters))
        rows_stmt = rows_stmt.where(and_(*filters))
    total = db.scalar(total_stmt) or 0
    rows = db.execute(
        rows_stmt.order_by(ReviewQualityAcceptanceGate.updated_at.desc(), ReviewQualityAcceptanceGate.id.desc())
        .limit(page_size)
        .offset((page_no - 1) * page_size)
    ).all()
    page = page_response(
        [acceptance_gate_to_response(record, project=project, include_detail=False) for record, project in rows],
        page_no,
        page_size,
        total,
    )
    if total == 0:
        page["explanation"] = "No review quality acceptance gate record matches the current filters."
    return page


def acceptance_gate_to_response(
    record: ReviewQualityAcceptanceGate,
    *,
    project: Project | None = None,
    include_detail: bool = True,
) -> dict[str, Any]:
    evaluation_case_ids = _int_list(read_json(record.evaluation_case_ids_json, []))
    evaluation_run_ids = _int_list(read_json(record.evaluation_run_ids_json, []))
    admission = read_json(record.admission_json, {})
    exit_result = read_json(record.exit_json, {})
    rule_gap_summary = read_json(record.rule_gap_summary_json, [])
    data = {
        "id": record.id,
        "projectId": record.project_id,
        "projectName": project.name if project is not None else None,
        "title": record.title,
        "changeType": record.change_type,
        "status": record.status,
        "provider": record.provider,
        "profile": record.profile,
        "riskType": record.risk_type,
        "evaluationCaseIds": evaluation_case_ids,
        "evaluationRunIds": evaluation_run_ids,
        "evaluationCaseCount": len(evaluation_case_ids),
        "evaluationRunCount": len(evaluation_run_ids),
        "coreDelta": _core_delta(exit_result),
        "updatedAt": format_datetime(record.updated_at),
        "createdAt": format_datetime(record.created_at),
    }
    if include_detail:
        data.update(
            {
                "ruleGapSummary": rule_gap_summary if isinstance(rule_gap_summary, list) else [],
                "admission": admission if isinstance(admission, dict) else {},
                "exit": exit_result if isinstance(exit_result, dict) else {},
            }
        )
    return data


def acceptance_gate_summary(
    db: Session,
    *,
    project_id: int | None,
    provider: str | None,
    profile: str | None,
    risk_type: str | None,
) -> dict[str, Any]:
    ensure_acceptance_gate_schema(db)
    filters = _filters(
        project_id=project_id,
        change_type=None,
        status=None,
        provider=provider,
        profile=profile,
        risk_type=risk_type,
    )
    stmt = select(ReviewQualityAcceptanceGate)
    if filters:
        stmt = stmt.where(and_(*filters))
    records = list(db.scalars(stmt.order_by(ReviewQualityAcceptanceGate.updated_at.desc(), ReviewQualityAcceptanceGate.id.desc())).all())
    status_counts: dict[str, int] = {}
    change_type_counts: dict[str, int] = {}
    for record in records:
        status_counts[record.status or "UNKNOWN"] = status_counts.get(record.status or "UNKNOWN", 0) + 1
        change_type_counts[record.change_type or "OTHER"] = change_type_counts.get(record.change_type or "OTHER", 0) + 1
    latest = records[0] if records else None
    return {
        "recordCount": len(records),
        "statusCounts": status_counts,
        "changeTypeCounts": change_type_counts,
        "latestStatus": latest.status if latest is not None else None,
        "latestGateId": latest.id if latest is not None else None,
        "latestTitle": latest.title if latest is not None else None,
        "latestUpdatedAt": format_datetime(latest.updated_at) if latest is not None else None,
        "scopeNote": "Acceptance gates are manual governance records and do not block runtime review or code merges.",
    }


def _filters(
    *,
    project_id: int | None,
    change_type: str | None,
    status: str | None,
    provider: str | None,
    profile: str | None,
    risk_type: str | None,
) -> list[Any]:
    filters = []
    if project_id is not None:
        filters.append(ReviewQualityAcceptanceGate.project_id == project_id)
    if change_type:
        filters.append(ReviewQualityAcceptanceGate.change_type == change_type)
    if status:
        filters.append(ReviewQualityAcceptanceGate.status == status)
    if provider:
        filters.append(ReviewQualityAcceptanceGate.provider == provider)
    if profile:
        filters.append(ReviewQualityAcceptanceGate.profile == profile)
    if risk_type:
        filters.append(ReviewQualityAcceptanceGate.risk_type == risk_type)
    return filters


def _core_delta(exit_result: Any) -> dict[str, Any]:
    if not isinstance(exit_result, dict):
        exit_result = {}
    return {
        "resultStatus": exit_result.get("resultStatus"),
        "falsePositiveDelta": exit_result.get("falsePositiveDelta"),
        "contextMissingDelta": exit_result.get("contextMissingDelta"),
        "missingFindingDelta": exit_result.get("missingFindingDelta"),
        "findingCountDelta": exit_result.get("findingCountDelta"),
        "durationDeltaMs": exit_result.get("durationDeltaMs"),
        "tokenCostDelta": exit_result.get("tokenCostDelta"),
    }


def _int_list(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return result


def _add_column_if_missing(db: Session, columns: set[str], column_name: str, definition: str) -> None:
    if column_name in columns:
        return
    db.execute(text(f"ALTER TABLE review_quality_acceptance_gates ADD COLUMN {column_name} {definition}"))
    columns.add(column_name)
