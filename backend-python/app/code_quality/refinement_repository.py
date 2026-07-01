from __future__ import annotations

from datetime import datetime
import json
import re
from typing import Any

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.code_quality.models import CodeQualityFindingRefinement, CodeQualityReviewResult
from app.core.json_utils import format_datetime, read_json
from app.review_feedback.service import ai_finding_fingerprint


_LOCAL_PATH_PATTERNS = [
    re.compile(r"[A-Za-z]:\\[^\s,;'\"}]+"),
    re.compile(r"/[^\s,;'\"}]+(?:/\.local|/review-workspaces|/worktrees|/mirrors|/tmp)[^\s,;'\"}]*"),
]


def ensure_finding_refinement_schema(db: Session) -> None:
    connection = db.connection()
    inspector = inspect(connection)
    if not inspector.has_table(CodeQualityFindingRefinement.__tablename__):
        CodeQualityFindingRefinement.__table__.create(connection, checkfirst=True)
        db.flush()
        return
    columns = {column["name"] for column in inspector.get_columns(CodeQualityFindingRefinement.__tablename__)}
    _add_column_if_missing(db, columns, "task_id", "BIGINT NOT NULL")
    _add_column_if_missing(db, columns, "review_key", "VARCHAR(64) NOT NULL DEFAULT 'default'")
    _add_column_if_missing(db, columns, "finding_index", "INT NOT NULL")
    _add_column_if_missing(db, columns, "fingerprint", "VARCHAR(128) NULL")
    _add_column_if_missing(db, columns, "finding_id", "VARCHAR(128) NULL")
    _add_column_if_missing(db, columns, "project_id", "BIGINT NOT NULL")
    _add_column_if_missing(db, columns, "status", "VARCHAR(32) NOT NULL DEFAULT 'PENDING'")
    _add_column_if_missing(db, columns, "trigger_reason", "VARCHAR(255) NULL")
    _add_column_if_missing(db, columns, "trigger_conditions_json", "TEXT NULL")
    _add_column_if_missing(db, columns, "retrieval_plan_json", "TEXT NULL")
    _add_column_if_missing(db, columns, "evidence_summary_json", "TEXT NULL")
    _add_column_if_missing(db, columns, "missing_context_json", "TEXT NULL")
    _add_column_if_missing(db, columns, "failure_reason", "VARCHAR(1024) NULL")
    _add_column_if_missing(db, columns, "started_at", "DATETIME NULL")
    _add_column_if_missing(db, columns, "finished_at", "DATETIME NULL")
    _add_column_if_missing(db, columns, "created_at", "DATETIME NULL")
    _add_column_if_missing(db, columns, "updated_at", "DATETIME NULL")
    db.flush()


def find_refinement(
    db: Session,
    *,
    task_id: int,
    review_key: str,
    finding_index: int,
) -> CodeQualityFindingRefinement | None:
    ensure_finding_refinement_schema(db)
    return db.scalars(
        select(CodeQualityFindingRefinement)
        .where(CodeQualityFindingRefinement.task_id == task_id)
        .where(CodeQualityFindingRefinement.review_key == review_key)
        .where(CodeQualityFindingRefinement.finding_index == finding_index)
    ).first()


def upsert_refinement(
    db: Session,
    *,
    task_id: int,
    review_key: str,
    finding_index: int,
    fingerprint: str | None,
    finding_id: str | None,
    project_id: int,
    status: str,
    trigger_reason: str | None,
    trigger_conditions: dict[str, Any],
    retrieval_plan: dict[str, Any] | None = None,
    evidence_summary: dict[str, Any] | None = None,
    missing_context: list[dict[str, Any]] | None = None,
    failure_reason: str | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> CodeQualityFindingRefinement:
    ensure_finding_refinement_schema(db)
    now = datetime.now()
    record = find_refinement(
        db,
        task_id=task_id,
        review_key=review_key,
        finding_index=finding_index,
    )
    if record is None:
        record = CodeQualityFindingRefinement(
            task_id=task_id,
            review_key=review_key,
            finding_index=finding_index,
            created_at=now,
        )
        db.add(record)
    record.fingerprint = _clean_text(fingerprint, 128)
    record.finding_id = _clean_text(finding_id, 128)
    record.project_id = project_id
    record.status = _clean_text(status, 32) or status
    record.trigger_reason = _clean_text(trigger_reason, 255)
    record.trigger_conditions_json = _safe_json(trigger_conditions)
    record.retrieval_plan_json = _safe_json(retrieval_plan) if retrieval_plan is not None else None
    record.evidence_summary_json = _safe_json(evidence_summary) if evidence_summary is not None else None
    record.missing_context_json = _safe_json(missing_context or [])
    record.failure_reason = _clean_text(failure_reason, 1024)
    record.started_at = started_at
    record.finished_at = finished_at
    record.updated_at = now
    db.flush()
    return record


def list_refinement_records(
    db: Session,
    *,
    task_id: int,
    review_key: str | None = None,
) -> list[CodeQualityFindingRefinement]:
    ensure_finding_refinement_schema(db)
    stmt = select(CodeQualityFindingRefinement).where(CodeQualityFindingRefinement.task_id == task_id)
    if review_key:
        stmt = stmt.where(CodeQualityFindingRefinement.review_key == review_key)
    return db.scalars(
        stmt.order_by(
            CodeQualityFindingRefinement.review_key.asc(),
            CodeQualityFindingRefinement.finding_index.asc(),
            CodeQualityFindingRefinement.id.asc(),
        )
    ).all()


def list_refinement_responses(
    db: Session,
    *,
    task_id: int,
    review_key: str | None = None,
) -> list[dict[str, Any]]:
    return [refinement_to_response(record) for record in list_refinement_records(db, task_id=task_id, review_key=review_key)]


def attach_refinement_overlays(
    db: Session,
    result: CodeQualityReviewResult,
    findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(findings, list) or not findings:
        return findings
    records = list_refinement_records(db, task_id=result.task_id, review_key=result.review_key)
    if not records:
        return findings
    by_index = {int(record.finding_index): record for record in records}
    enriched: list[dict[str, Any]] = []
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            enriched.append(finding)
            continue
        record = by_index.get(index)
        if record is None:
            enriched.append(finding)
            continue
        fingerprint = ai_finding_fingerprint(result, finding, index)
        if record.fingerprint and record.fingerprint != fingerprint:
            enriched.append(finding)
            continue
        next_finding = dict(finding)
        next_finding["refinementOverlay"] = refinement_overlay(record)
        enriched.append(next_finding)
    return enriched


def refinement_to_response(record: CodeQualityFindingRefinement) -> dict[str, Any]:
    return {
        "id": record.id,
        "taskId": record.task_id,
        "reviewKey": record.review_key,
        "findingIndex": record.finding_index,
        "fingerprint": record.fingerprint,
        "findingId": record.finding_id,
        "projectId": record.project_id,
        "status": record.status,
        "triggerReason": record.trigger_reason,
        "triggerConditions": _safe_response(read_json(record.trigger_conditions_json, {})),
        "retrievalPlan": _safe_response(read_json(record.retrieval_plan_json, None)),
        "evidenceSummary": _safe_response(read_json(record.evidence_summary_json, None)),
        "missingContext": _safe_response(read_json(record.missing_context_json, [])),
        "failureReason": _clean_text(record.failure_reason, 1024),
        "startedAt": format_datetime(record.started_at),
        "finishedAt": format_datetime(record.finished_at),
        "createdAt": format_datetime(record.created_at),
        "updatedAt": format_datetime(record.updated_at),
    }


def refinement_overlay(record: CodeQualityFindingRefinement) -> dict[str, Any]:
    return {
        "id": record.id,
        "status": record.status,
        "triggerReason": record.trigger_reason,
        "retrievalPlan": _safe_response(read_json(record.retrieval_plan_json, None)),
        "evidenceSummary": _safe_response(read_json(record.evidence_summary_json, None)),
        "missingContext": _safe_response(read_json(record.missing_context_json, [])),
        "failureReason": _clean_text(record.failure_reason, 1024),
        "finishedAt": format_datetime(record.finished_at),
    }


def _add_column_if_missing(db: Session, columns: set[str], column_name: str, definition: str) -> None:
    if column_name in columns:
        return
    db.execute(text(f"ALTER TABLE code_quality_finding_refinements ADD COLUMN {column_name} {definition}"))
    columns.add(column_name)


def _safe_json(value: Any) -> str:
    return json.dumps(_safe_response(value), ensure_ascii=False)


def _safe_response(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key)
            if normalized_key in {"snippets", "lines", "promptText", "rawOutput", "providerRawOutput", "sourceSnippet"}:
                continue
            result[normalized_key] = _safe_response(item)
        return result
    if isinstance(value, list):
        return [_safe_response(item) for item in value[:50]]
    if isinstance(value, str):
        return _clean_text(_mask_local_paths(value), 1024)
    return value


def _mask_local_paths(value: str) -> str:
    text_value = value
    for pattern in _LOCAL_PATH_PATTERNS:
        text_value = pattern.sub("[local-path]", text_value)
    return text_value


def _clean_text(value: Any, max_length: int) -> str | None:
    if value is None:
        return None
    text_value = _scrub_sensitive(_mask_local_paths(str(value))).strip()
    if not text_value:
        return None
    return text_value[:max_length]


def _scrub_sensitive(value: str) -> str:
    text_value = value
    for marker in ("Authorization", "apiKey", "api_key", "token", "secret", "password", "x-api-key"):
        text_value = _mask_after_marker(text_value, marker)
    return text_value


def _mask_after_marker(text_value: str, marker: str) -> str:
    lower = text_value.lower()
    marker_lower = marker.lower()
    start = 0
    while True:
        index = lower.find(marker_lower, start)
        if index < 0:
            return text_value
        colon = text_value.find(":", index)
        equals = text_value.find("=", index)
        separator = min([pos for pos in (colon, equals) if pos >= 0], default=-1)
        if separator < 0:
            start = index + len(marker)
            continue
        end = separator + 1
        while end < len(text_value) and text_value[end] in " \t'\"":
            end += 1
        value_end = end
        while value_end < len(text_value) and text_value[value_end] not in ", \n\r\t'\"}":
            value_end += 1
        text_value = text_value[:end] + "****" + text_value[value_end:]
        lower = text_value.lower()
        start = end + 4
