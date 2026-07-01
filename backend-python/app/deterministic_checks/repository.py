from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session

from app.core.json_utils import format_datetime, read_json
from app.deterministic_checks.models import DeterministicCheckRun


def ensure_deterministic_check_schema(db: Session) -> None:
    connection = db.connection()
    inspector = inspect(connection)
    if not inspector.has_table(DeterministicCheckRun.__tablename__):
        DeterministicCheckRun.__table__.create(bind=connection)
        _create_index_if_missing(db, "deterministic_check_runs", "idx_deterministic_check_runs_task_type_created", "task_id, check_type, created_at")
        db.flush()
        return
    columns = {column["name"] for column in inspector.get_columns(DeterministicCheckRun.__tablename__)}
    _add_column_if_missing(db, columns, "task_id", "BIGINT NOT NULL")
    _add_column_if_missing(db, columns, "project_id", "BIGINT NOT NULL")
    _add_column_if_missing(db, columns, "check_type", "VARCHAR(64) NOT NULL DEFAULT 'SECRET_SCAN'")
    _add_column_if_missing(db, columns, "status", "VARCHAR(32) NOT NULL DEFAULT 'NOT_RUN'")
    _add_column_if_missing(db, columns, "config_snapshot_json", "TEXT NULL")
    _add_column_if_missing(db, columns, "result_summary_json", "TEXT NULL")
    _add_column_if_missing(db, columns, "findings_json", "TEXT NULL")
    _add_column_if_missing(db, columns, "duration_ms", "BIGINT NULL")
    _add_column_if_missing(db, columns, "failure_reason", "VARCHAR(1024) NULL")
    _add_column_if_missing(db, columns, "started_at", "DATETIME NULL")
    _add_column_if_missing(db, columns, "finished_at", "DATETIME NULL")
    _add_column_if_missing(db, columns, "created_at", "DATETIME NULL")
    _add_column_if_missing(db, columns, "updated_at", "DATETIME NULL")
    _create_index_if_missing(db, "deterministic_check_runs", "idx_deterministic_check_runs_task_type_created", "task_id, check_type, created_at")
    db.flush()


def create_check_run(db: Session, values: dict[str, Any]) -> DeterministicCheckRun:
    ensure_deterministic_check_schema(db)
    now = datetime.now()
    record = DeterministicCheckRun(created_at=now, updated_at=now, **values)
    db.add(record)
    db.flush()
    return record


def list_check_runs(db: Session, task_id: int, check_type: str | None = None) -> list[DeterministicCheckRun]:
    ensure_deterministic_check_schema(db)
    stmt = select(DeterministicCheckRun).where(DeterministicCheckRun.task_id == task_id)
    if check_type:
        stmt = stmt.where(DeterministicCheckRun.check_type == check_type)
    return list(db.scalars(stmt.order_by(DeterministicCheckRun.created_at.desc(), DeterministicCheckRun.id.desc())).all())


def latest_check_run(db: Session, task_id: int, check_type: str = "SECRET_SCAN") -> DeterministicCheckRun | None:
    records = list_check_runs(db, task_id, check_type)
    return records[0] if records else None


def deterministic_check_run_to_response(record: DeterministicCheckRun) -> dict[str, Any]:
    return {
        "id": record.id,
        "taskId": record.task_id,
        "projectId": record.project_id,
        "checkType": record.check_type,
        "status": record.status,
        "configSnapshot": read_json(record.config_snapshot_json, {}),
        "resultSummary": read_json(record.result_summary_json, {}),
        "findings": read_json(record.findings_json, []),
        "durationMs": record.duration_ms,
        "failureReason": record.failure_reason,
        "startedAt": format_datetime(record.started_at),
        "finishedAt": format_datetime(record.finished_at),
        "createdAt": format_datetime(record.created_at),
        "updatedAt": format_datetime(record.updated_at),
    }


def deterministic_check_security_summary(record: DeterministicCheckRun | None) -> dict[str, Any]:
    if record is None:
        return {
            "status": "NOT_RUN",
            "checkType": "SECRET_SCAN",
            "explanation": "No deterministic check run has been recorded for this task.",
        }
    data = deterministic_check_run_to_response(record)
    summary = data.get("resultSummary") or {}
    config = data.get("configSnapshot") or {}
    findings = data.get("findings") or []
    return {
        "status": data["status"],
        "checkType": data["checkType"],
        "rulesetVersion": config.get("rulesetVersion"),
        "scope": config.get("scope"),
        "durationMs": data.get("durationMs"),
        "findingCount": summary.get("findingCount", 0),
        "ruleTypeCounts": summary.get("ruleTypeCounts") or {},
        "truncated": bool(summary.get("truncated", False)),
        "failureReason": data.get("failureReason"),
        "findings": findings[:5],
    }


def _add_column_if_missing(db: Session, columns: set[str], column_name: str, definition: str) -> None:
    if column_name in columns:
        return
    db.execute(text(f"ALTER TABLE deterministic_check_runs ADD COLUMN {column_name} {definition}"))
    columns.add(column_name)


def _create_index_if_missing(db: Session, table_name: str, index_name: str, columns: str) -> None:
    bind_name = db.bind.dialect.name if db.bind is not None else ""
    if bind_name == "sqlite":
        db.execute(text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({columns})"))
        return
    existing = db.execute(
        text(
            "SELECT COUNT(1) FROM information_schema.statistics "
            "WHERE table_schema = DATABASE() AND table_name = :table_name AND index_name = :index_name"
        ),
        {"table_name": table_name, "index_name": index_name},
    ).scalar()
    if not existing:
        db.execute(text(f"CREATE INDEX {index_name} ON {table_name} ({columns})"))


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
