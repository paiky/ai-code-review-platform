from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.code_quality.models import CodeQualityReviewResult
from app.core.errors import AppError
from app.core.json_utils import read_json
from app.evaluation.models import EvaluationCase
from app.evaluation.repository import (
    create_evaluation_case,
    evaluation_case_to_response,
    get_evaluation_case,
    list_evaluation_cases,
    update_evaluation_case,
)
from app.project_integration.models import Project
from app.review_feedback.service import ai_finding_fingerprint
from app.review_record.models import ReviewTask


VERDICTS = {
    "TRUE_POSITIVE",
    "FALSE_POSITIVE",
    "LEVEL_TOO_HIGH",
    "LEVEL_TOO_LOW",
    "CONTEXT_MISSING",
    "DUPLICATE",
    "MISSING_FINDING",
    "UNKNOWN",
}
SOURCES = {"AI_FINDING", "MANUAL"}


def create_evaluation_case_response(db: Session, request: dict[str, Any]) -> dict[str, Any]:
    source = _normalize_enum(request.get("source") or "MANUAL", SOURCES, "source")
    verdict = _normalize_enum(request.get("verdict") or "UNKNOWN", VERDICTS, "verdict")
    if source == "AI_FINDING":
        values = _values_from_ai_finding(db, request, verdict=verdict, source=source)
    else:
        values = _values_from_manual_case(db, request, verdict=verdict, source=source)
    record = create_evaluation_case(db, values)
    db.commit()
    return _case_response(db, record)


def list_evaluation_case_response(
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
    return list_evaluation_cases(
        db,
        project_id=project_id,
        provider=_clean_text(provider, 64),
        profile=_clean_text(profile, 64),
        risk_type=_clean_text(risk_type, 64),
        verdict=_normalize_optional_enum(verdict, VERDICTS, "verdict"),
        page_no=page_no,
        page_size=page_size,
    )


def get_evaluation_case_response(db: Session, case_id: int) -> dict[str, Any]:
    record = get_evaluation_case(db, case_id)
    if record is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Evaluation case not found: {case_id}", 404)
    return _case_response(db, record)


def update_evaluation_case_response(db: Session, case_id: int, request: dict[str, Any]) -> dict[str, Any]:
    record = get_evaluation_case(db, case_id)
    if record is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Evaluation case not found: {case_id}", 404)
    values: dict[str, Any] = {}
    field_map = {
        "reviewKey": "review_key",
        "findingId": "finding_id",
        "fingerprint": "fingerprint",
        "provider": "provider",
        "profile": "profile",
        "riskType": "risk_type",
        "severity": "severity",
        "contextStatus": "context_status",
        "humanComment": "human_comment",
    }
    for api_field, model_field in field_map.items():
        if api_field in request:
            max_length = 4000 if api_field == "humanComment" else 128
            if api_field in {"provider", "profile", "riskType"}:
                max_length = 64
            if api_field in {"severity", "contextStatus"}:
                max_length = 32
            values[model_field] = _clean_text(request.get(api_field), max_length)
    if "verdict" in request:
        values["verdict"] = _normalize_enum(request.get("verdict"), VERDICTS, "verdict")
    if "source" in request:
        values["source"] = _normalize_enum(request.get("source"), SOURCES, "source")
    if not values:
        return _case_response(db, record)
    updated = update_evaluation_case(db, record, values)
    db.commit()
    return _case_response(db, updated)


def _values_from_ai_finding(
    db: Session,
    request: dict[str, Any],
    *,
    verdict: str,
    source: str,
) -> dict[str, Any]:
    task_id = _to_int(request.get("taskId"))
    if task_id is None:
        raise AppError("VALIDATION_ERROR", "taskId is required for AI_FINDING evaluation case", 400)
    task = db.get(ReviewTask, task_id)
    if task is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)

    target = _resolve_ai_finding_target(db, task_id, request)
    result: CodeQualityReviewResult = target["result"]
    finding: dict[str, Any] = target["finding"]
    fingerprint: str = target["fingerprint"]
    finding_id = _clean_text(request.get("findingId"), 128) or _finding_id(finding)
    project_id = _to_int(request.get("projectId")) or result.project_id or task.project_id
    _ensure_project_exists(db, project_id)
    return {
        "task_id": task.id,
        "review_key": result.review_key,
        "finding_id": finding_id,
        "fingerprint": _clean_text(request.get("fingerprint"), 128) or fingerprint,
        "project_id": project_id,
        "provider": _clean_text(request.get("provider"), 64) or result.provider,
        "profile": _clean_text(request.get("profile"), 64) or result.profile_code,
        "risk_type": _clean_text(request.get("riskType"), 64) or _clean_text(finding.get("category"), 64),
        "severity": _clean_text(request.get("severity"), 32) or _clean_text(finding.get("severity"), 32),
        "context_status": _clean_text(request.get("contextStatus"), 32)
        or _clean_text(finding.get("contextStatus"), 32),
        "verdict": verdict,
        "human_comment": _clean_text(request.get("humanComment"), 4000),
        "source": source,
        "item_snapshot_json": json.dumps(finding, ensure_ascii=False),
    }


def _values_from_manual_case(
    db: Session,
    request: dict[str, Any],
    *,
    verdict: str,
    source: str,
) -> dict[str, Any]:
    task_id = _to_int(request.get("taskId"))
    task = db.get(ReviewTask, task_id) if task_id is not None else None
    if task_id is not None and task is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)
    project_id = _to_int(request.get("projectId")) or (task.project_id if task is not None else None)
    if project_id is None:
        raise AppError("VALIDATION_ERROR", "projectId is required", 400)
    _ensure_project_exists(db, project_id)
    snapshot = request.get("itemSnapshot") if isinstance(request.get("itemSnapshot"), dict) else None
    return {
        "task_id": task_id,
        "review_key": _clean_text(request.get("reviewKey"), 64),
        "finding_id": _clean_text(request.get("findingId"), 128),
        "fingerprint": _clean_text(request.get("fingerprint"), 128),
        "project_id": project_id,
        "provider": _clean_text(request.get("provider"), 64),
        "profile": _clean_text(request.get("profile"), 64),
        "risk_type": _clean_text(request.get("riskType"), 64),
        "severity": _clean_text(request.get("severity"), 32),
        "context_status": _clean_text(request.get("contextStatus"), 32),
        "verdict": verdict,
        "human_comment": _clean_text(request.get("humanComment"), 4000),
        "source": source,
        "item_snapshot_json": json.dumps(snapshot, ensure_ascii=False) if snapshot else None,
    }


def _resolve_ai_finding_target(db: Session, task_id: int, request: dict[str, Any]) -> dict[str, Any]:
    review_key = _clean_text(request.get("reviewKey"), 64)
    requested_fingerprint = _clean_text(request.get("fingerprint"), 128)
    finding_id = _clean_text(request.get("findingId"), 128)
    if not requested_fingerprint and not finding_id:
        raise AppError("VALIDATION_ERROR", "fingerprint or findingId is required", 400)

    stmt = select(CodeQualityReviewResult).where(CodeQualityReviewResult.task_id == task_id)
    if review_key:
        stmt = stmt.where(CodeQualityReviewResult.review_key == review_key)
    records = db.scalars(stmt.order_by(CodeQualityReviewResult.sort_order.asc(), CodeQualityReviewResult.id.asc())).all()
    for result in records:
        findings = read_json(result.findings_json, [])
        if not isinstance(findings, list):
            continue
        for index, finding in enumerate(findings):
            if not isinstance(finding, dict):
                continue
            fingerprint = ai_finding_fingerprint(result, finding, index)
            if requested_fingerprint and requested_fingerprint == fingerprint:
                return {"result": result, "finding": finding, "fingerprint": fingerprint}
            if finding_id and finding_id == _finding_id(finding):
                return {"result": result, "finding": finding, "fingerprint": fingerprint}
    raise AppError("RESOURCE_NOT_FOUND", "Evaluation case source finding not found", 404)


def _case_response(db: Session, record: EvaluationCase) -> dict[str, Any]:
    project = db.get(Project, record.project_id)
    task = db.get(ReviewTask, record.task_id) if record.task_id is not None else None
    return evaluation_case_to_response(record, project=project, task=task)


def _ensure_project_exists(db: Session, project_id: int) -> None:
    if db.get(Project, project_id) is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {project_id}", 404)


def _finding_id(finding: dict[str, Any]) -> str | None:
    return _clean_text(finding.get("findingId") or finding.get("id"), 128)


def _normalize_enum(value: Any, allowed: set[str], field: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in allowed:
        raise AppError("VALIDATION_ERROR", f"{field} is invalid", 400)
    return normalized


def _normalize_optional_enum(value: Any, allowed: set[str], field: str) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    return _normalize_enum(value, allowed, field)


def _clean_text(value: Any, max_length: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_length]


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
