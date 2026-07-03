from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, inspect, select, text
from sqlalchemy.orm import Session

from app.core.json_utils import format_datetime, page_response, read_json
from app.evaluation.models import EvaluationCase, EvaluationRun, EvaluationRunItem
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
    _add_column_if_missing(db, columns, "rule_gap_attribution_type", "VARCHAR(64) NULL")
    _add_column_if_missing(db, columns, "rule_gap_summary_json", "TEXT NULL")
    _add_column_if_missing(db, columns, "rule_gap_attribution_comment", "TEXT NULL")
    _add_column_if_missing(db, columns, "rule_gap_attributed_by", "VARCHAR(128) NULL")
    _add_column_if_missing(db, columns, "rule_gap_attributed_at", "DATETIME NULL")
    _add_column_if_missing(db, columns, "created_at", "DATETIME NULL")
    _add_column_if_missing(db, columns, "updated_at", "DATETIME NULL")
    db.flush()


def ensure_evaluation_run_schema(db: Session) -> None:
    connection = db.connection()
    inspector = inspect(connection)
    if not inspector.has_table(EvaluationRun.__tablename__):
        EvaluationRun.__table__.create(bind=connection)
    else:
        columns = {column["name"] for column in inspector.get_columns(EvaluationRun.__tablename__)}
        _add_table_column_if_missing(db, columns, "evaluation_runs", "name", "VARCHAR(255) NOT NULL DEFAULT 'Evaluation Run'")
        _add_table_column_if_missing(db, columns, "evaluation_runs", "run_type", "VARCHAR(32) NOT NULL DEFAULT 'EVALUATION'")
        _add_table_column_if_missing(db, columns, "evaluation_runs", "sample_set_name", "VARCHAR(255) NULL")
        _add_table_column_if_missing(db, columns, "evaluation_runs", "sample_set_json", "TEXT NULL")
        _add_table_column_if_missing(db, columns, "evaluation_runs", "project_id", "BIGINT NULL")
        _add_table_column_if_missing(db, columns, "evaluation_runs", "provider", "VARCHAR(64) NULL")
        _add_table_column_if_missing(db, columns, "evaluation_runs", "profile", "VARCHAR(64) NULL")
        _add_table_column_if_missing(db, columns, "evaluation_runs", "model", "VARCHAR(128) NULL")
        _add_table_column_if_missing(db, columns, "evaluation_runs", "prompt_hash", "VARCHAR(128) NULL")
        _add_table_column_if_missing(db, columns, "evaluation_runs", "context_pack_version", "VARCHAR(64) NULL")
        _add_table_column_if_missing(db, columns, "evaluation_runs", "retriever_version", "VARCHAR(64) NULL")
        _add_table_column_if_missing(db, columns, "evaluation_runs", "rule_gap_version", "VARCHAR(64) NULL")
        _add_table_column_if_missing(db, columns, "evaluation_runs", "baseline_json", "TEXT NULL")
        _add_table_column_if_missing(db, columns, "evaluation_runs", "candidate_json", "TEXT NULL")
        _add_table_column_if_missing(db, columns, "evaluation_runs", "status", "VARCHAR(32) NOT NULL DEFAULT 'PENDING'")
        _add_table_column_if_missing(db, columns, "evaluation_runs", "total_count", "INT NOT NULL DEFAULT 0")
        _add_table_column_if_missing(db, columns, "evaluation_runs", "completed_count", "INT NOT NULL DEFAULT 0")
        _add_table_column_if_missing(db, columns, "evaluation_runs", "failed_count", "INT NOT NULL DEFAULT 0")
        _add_table_column_if_missing(db, columns, "evaluation_runs", "result_summary_json", "TEXT NULL")
        _add_table_column_if_missing(db, columns, "evaluation_runs", "duration_ms", "BIGINT NULL")
        _add_table_column_if_missing(db, columns, "evaluation_runs", "notes", "TEXT NULL")
        _add_table_column_if_missing(db, columns, "evaluation_runs", "started_at", "DATETIME NULL")
        _add_table_column_if_missing(db, columns, "evaluation_runs", "finished_at", "DATETIME NULL")
        _add_table_column_if_missing(db, columns, "evaluation_runs", "created_at", "DATETIME NULL")
        _add_table_column_if_missing(db, columns, "evaluation_runs", "updated_at", "DATETIME NULL")

    inspector = inspect(connection)
    if not inspector.has_table(EvaluationRunItem.__tablename__):
        EvaluationRunItem.__table__.create(bind=connection)
    else:
        columns = {column["name"] for column in inspector.get_columns(EvaluationRunItem.__tablename__)}
        _add_table_column_if_missing(db, columns, "evaluation_run_items", "run_id", "BIGINT NOT NULL")
        _add_table_column_if_missing(db, columns, "evaluation_run_items", "case_id", "BIGINT NOT NULL")
        _add_table_column_if_missing(db, columns, "evaluation_run_items", "item_index", "INT NOT NULL DEFAULT 0")
        _add_table_column_if_missing(db, columns, "evaluation_run_items", "task_id", "BIGINT NULL")
        _add_table_column_if_missing(db, columns, "evaluation_run_items", "review_key", "VARCHAR(64) NULL")
        _add_table_column_if_missing(db, columns, "evaluation_run_items", "fingerprint", "VARCHAR(128) NULL")
        _add_table_column_if_missing(db, columns, "evaluation_run_items", "project_id", "BIGINT NOT NULL")
        _add_table_column_if_missing(db, columns, "evaluation_run_items", "provider", "VARCHAR(64) NULL")
        _add_table_column_if_missing(db, columns, "evaluation_run_items", "profile", "VARCHAR(64) NULL")
        _add_table_column_if_missing(db, columns, "evaluation_run_items", "risk_type", "VARCHAR(64) NULL")
        _add_table_column_if_missing(db, columns, "evaluation_run_items", "severity", "VARCHAR(32) NULL")
        _add_table_column_if_missing(db, columns, "evaluation_run_items", "context_status", "VARCHAR(32) NULL")
        _add_table_column_if_missing(db, columns, "evaluation_run_items", "verdict", "VARCHAR(64) NOT NULL DEFAULT 'UNKNOWN'")
        _add_table_column_if_missing(db, columns, "evaluation_run_items", "status", "VARCHAR(32) NOT NULL DEFAULT 'PENDING'")
        _add_table_column_if_missing(db, columns, "evaluation_run_items", "duration_ms", "BIGINT NULL")
        _add_table_column_if_missing(db, columns, "evaluation_run_items", "baseline_summary_json", "TEXT NULL")
        _add_table_column_if_missing(db, columns, "evaluation_run_items", "candidate_summary_json", "TEXT NULL")
        _add_table_column_if_missing(db, columns, "evaluation_run_items", "result_summary_json", "TEXT NULL")
        _add_table_column_if_missing(db, columns, "evaluation_run_items", "error_message", "VARCHAR(1024) NULL")
        _add_table_column_if_missing(db, columns, "evaluation_run_items", "created_at", "DATETIME NULL")
        _add_table_column_if_missing(db, columns, "evaluation_run_items", "updated_at", "DATETIME NULL")
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
        "ruleGapAttribution": rule_gap_attribution_to_response(record),
        "createdAt": format_datetime(record.created_at),
        "updatedAt": format_datetime(record.updated_at),
    }


def rule_gap_attribution_to_response(record: EvaluationCase) -> dict[str, Any]:
    summary = read_json(record.rule_gap_summary_json, [])
    if not isinstance(summary, list):
        summary = []
    return {
        "caseId": record.id,
        "attributionType": record.rule_gap_attribution_type,
        "ruleGapSummary": summary,
        "comment": record.rule_gap_attribution_comment,
        "attributedBy": record.rule_gap_attributed_by,
        "attributedAt": format_datetime(record.rule_gap_attributed_at),
        "explanation": None
        if record.rule_gap_attribution_type
        else "Rule gap attribution has not been recorded for this evaluation case.",
    }


def evaluation_run_to_response(
    record: EvaluationRun,
    *,
    project: Project | None = None,
    items: list[EvaluationRunItem] | None = None,
) -> dict[str, Any]:
    data = {
        "id": record.id,
        "name": record.name,
        "runType": record.run_type,
        "sampleSetName": record.sample_set_name,
        "sampleSet": read_json(record.sample_set_json, None),
        "projectId": record.project_id,
        "projectName": project.name if project is not None else None,
        "provider": record.provider,
        "profile": record.profile,
        "model": record.model,
        "promptHash": record.prompt_hash,
        "contextPackVersion": record.context_pack_version,
        "retrieverVersion": record.retriever_version,
        "ruleGapVersion": record.rule_gap_version,
        "baseline": read_json(record.baseline_json, None),
        "candidate": read_json(record.candidate_json, None),
        "status": record.status,
        "totalCount": record.total_count,
        "completedCount": record.completed_count,
        "failedCount": record.failed_count,
        "resultSummary": read_json(record.result_summary_json, None),
        "durationMs": record.duration_ms,
        "notes": record.notes,
        "startedAt": format_datetime(record.started_at),
        "finishedAt": format_datetime(record.finished_at),
        "createdAt": format_datetime(record.created_at),
        "updatedAt": format_datetime(record.updated_at),
    }
    if items is not None:
        data["items"] = [evaluation_run_item_to_response(item) for item in items]
    return data


def evaluation_run_item_to_response(record: EvaluationRunItem) -> dict[str, Any]:
    return {
        "id": record.id,
        "runId": record.run_id,
        "caseId": record.case_id,
        "itemIndex": record.item_index,
        "taskId": record.task_id,
        "reviewKey": record.review_key,
        "fingerprint": record.fingerprint,
        "projectId": record.project_id,
        "provider": record.provider,
        "profile": record.profile,
        "riskType": record.risk_type,
        "severity": record.severity,
        "contextStatus": record.context_status,
        "verdict": record.verdict,
        "status": record.status,
        "durationMs": record.duration_ms,
        "baselineSummary": read_json(record.baseline_summary_json, None),
        "candidateSummary": read_json(record.candidate_summary_json, None),
        "resultSummary": read_json(record.result_summary_json, None),
        "errorMessage": record.error_message,
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


def create_evaluation_run(
    db: Session,
    run_values: dict[str, Any],
    case_records: list[EvaluationCase],
) -> EvaluationRun:
    ensure_evaluation_run_schema(db)
    now = datetime.now()
    record = EvaluationRun(created_at=now, updated_at=now, **run_values)
    db.add(record)
    db.flush()
    for index, case in enumerate(case_records):
        db.add(
            EvaluationRunItem(
                run_id=record.id,
                case_id=case.id,
                item_index=index,
                task_id=case.task_id,
                review_key=case.review_key,
                fingerprint=case.fingerprint,
                project_id=case.project_id,
                provider=case.provider,
                profile=case.profile,
                risk_type=case.risk_type,
                severity=case.severity,
                context_status=case.context_status,
                verdict=case.verdict,
                status="PENDING",
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()
    return record


def get_evaluation_case(db: Session, case_id: int) -> EvaluationCase | None:
    ensure_evaluation_case_schema(db)
    return db.get(EvaluationCase, case_id)


def get_evaluation_cases_by_ids(db: Session, case_ids: list[int]) -> list[EvaluationCase]:
    ensure_evaluation_case_schema(db)
    if not case_ids:
        return []
    return db.scalars(select(EvaluationCase).where(EvaluationCase.id.in_(case_ids))).all()


def get_evaluation_run(db: Session, run_id: int) -> EvaluationRun | None:
    ensure_evaluation_run_schema(db)
    return db.get(EvaluationRun, run_id)


def get_evaluation_run_item(db: Session, item_id: int) -> EvaluationRunItem | None:
    ensure_evaluation_run_schema(db)
    return db.get(EvaluationRunItem, item_id)


def update_evaluation_case(db: Session, record: EvaluationCase, values: dict[str, Any]) -> EvaluationCase:
    for key, value in values.items():
        setattr(record, key, value)
    record.updated_at = datetime.now()
    db.flush()
    return record


def update_evaluation_run_item(db: Session, record: EvaluationRunItem, values: dict[str, Any]) -> EvaluationRunItem:
    for key, value in values.items():
        setattr(record, key, value)
    record.updated_at = datetime.now()
    db.flush()
    return record


def list_evaluation_run_items(db: Session, run_id: int) -> list[EvaluationRunItem]:
    ensure_evaluation_run_schema(db)
    return db.scalars(
        select(EvaluationRunItem)
        .where(EvaluationRunItem.run_id == run_id)
        .order_by(EvaluationRunItem.item_index.asc(), EvaluationRunItem.id.asc())
    ).all()


def refresh_evaluation_run_aggregate(db: Session, run: EvaluationRun) -> EvaluationRun:
    items = list_evaluation_run_items(db, run.id)
    status_counts: dict[str, int] = {}
    verdict_counts: dict[str, int] = {}
    duration_ms = 0
    duration_present = False
    for item in items:
        status_counts[item.status] = status_counts.get(item.status, 0) + 1
        verdict_counts[item.verdict] = verdict_counts.get(item.verdict, 0) + 1
        if item.duration_ms is not None:
            duration_ms += int(item.duration_ms)
            duration_present = True
    total = len(items)
    completed = status_counts.get("COMPLETED", 0)
    failed = status_counts.get("FAILED", 0)
    canceled = status_counts.get("CANCELED", 0)
    running = status_counts.get("RUNNING", 0)
    terminal = completed + failed + canceled
    if running > 0:
        status = "RUNNING"
    elif total > 0 and terminal == total:
        if failed > 0:
            status = "FAILED"
        elif canceled == total:
            status = "CANCELED"
        else:
            status = "COMPLETED"
    elif terminal > 0:
        status = "RUNNING"
    else:
        status = "PENDING"

    run.status = status
    run.total_count = total
    run.completed_count = completed
    run.failed_count = failed
    run.duration_ms = duration_ms if duration_present else None
    run.result_summary_json = _safe_json(
        {
            "totalCount": total,
            "completedCount": completed,
            "failedCount": failed,
            "canceledCount": canceled,
            "statusCounts": status_counts,
            "verdictCounts": verdict_counts,
        }
    )
    now = datetime.now()
    if status == "RUNNING" and run.started_at is None:
        run.started_at = now
    if status in {"COMPLETED", "FAILED", "CANCELED"}:
        run.finished_at = now
        if run.started_at is None:
            run.started_at = run.created_at
    else:
        run.finished_at = None
    run.updated_at = now
    db.flush()
    return run


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


def list_evaluation_runs(
    db: Session,
    *,
    project_id: int | None,
    provider: str | None,
    profile: str | None,
    run_type: str | None,
    status: str | None,
    page_no: int,
    page_size: int,
) -> dict[str, Any]:
    ensure_evaluation_run_schema(db)
    page_no = max(page_no, 1)
    page_size = max(page_size, 1)
    filters = []
    if project_id is not None:
        filters.append(EvaluationRun.project_id == project_id)
    if provider:
        filters.append(EvaluationRun.provider == provider)
    if profile:
        filters.append(EvaluationRun.profile == profile)
    if run_type:
        filters.append(EvaluationRun.run_type == run_type)
    if status:
        filters.append(EvaluationRun.status == status)

    total_stmt = select(func.count()).select_from(EvaluationRun)
    rows_stmt = select(EvaluationRun, Project).outerjoin(Project, Project.id == EvaluationRun.project_id)
    if filters:
        total_stmt = total_stmt.where(and_(*filters))
        rows_stmt = rows_stmt.where(and_(*filters))
    total = db.scalar(total_stmt) or 0
    rows = db.execute(
        rows_stmt.order_by(EvaluationRun.created_at.desc(), EvaluationRun.id.desc())
        .limit(page_size)
        .offset((page_no - 1) * page_size)
    ).all()
    return page_response(
        [evaluation_run_to_response(record, project=project) for record, project in rows],
        page_no,
        page_size,
        total,
    )


def _safe_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _add_column_if_missing(db: Session, columns: set[str], column_name: str, definition: str) -> None:
    _add_table_column_if_missing(db, columns, "evaluation_cases", column_name, definition)


def _add_table_column_if_missing(
    db: Session,
    columns: set[str],
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    if column_name in columns:
        return
    db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"))
    columns.add(column_name)
