from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.code_quality.repository import scrub_sensitive
from app.core.errors import AppError
from app.evaluation.repository import get_evaluation_cases_by_ids, get_evaluation_run
from app.project_integration.models import Project
from app.review_quality_acceptance.repository import (
    acceptance_gate_to_response,
    create_acceptance_gate,
    get_acceptance_gate,
    list_acceptance_gates,
    update_acceptance_gate,
)


CHANGE_TYPES = {"RULE", "RETRIEVER", "PROMPT", "CONTEXT_PACK", "DETERMINISTIC_CHECK", "PROVIDER", "OTHER"}
STATUSES = {"DRAFT", "ADMITTED", "RUNNING_VALIDATION", "PASSED", "FAILED", "CANCELED"}
RESULT_STATUSES = {"IMPROVED", "NEUTRAL", "REGRESSED", "INCONCLUSIVE"}
_LOCAL_PATH_PATTERNS = [
    re.compile(r"[A-Za-z]:\\[^\s,;'\"}]+"),
    re.compile(r"/[^\s,;'\"}]+(?:/\.local|/review-workspaces|/worktrees|/mirrors|/tmp)[^\s,;'\"}]*"),
]


def create_acceptance_gate_response(db: Session, request: dict[str, Any]) -> dict[str, Any]:
    project_id = _required_int(request.get("projectId"), "projectId")
    _ensure_project_exists(db, project_id)
    case_ids = _linked_ids(request.get("evaluationCaseIds"), "evaluationCaseIds")
    run_ids = _linked_ids(request.get("evaluationRunIds"), "evaluationRunIds")
    _ensure_cases_exist(db, case_ids)
    _ensure_runs_exist(db, run_ids)
    values = {
        "project_id": project_id,
        "title": _required_text(request.get("title"), 255, "title"),
        "change_type": _normalize_enum(request.get("changeType") or "OTHER", CHANGE_TYPES, "changeType"),
        "status": _normalize_enum(request.get("status") or "DRAFT", STATUSES, "status"),
        "provider": _clean_text(request.get("provider"), 64),
        "profile": _clean_text(request.get("profile"), 64),
        "risk_type": _clean_text(request.get("riskType"), 64),
        "evaluation_case_ids_json": json.dumps(case_ids, ensure_ascii=False),
        "evaluation_run_ids_json": json.dumps(run_ids, ensure_ascii=False),
        "rule_gap_summary_json": json.dumps(_rule_gap_summary_from_request(request.get("ruleGapSummary")), ensure_ascii=False),
        "admission_json": json.dumps(_admission_from_request(request.get("admission")), ensure_ascii=False),
        "exit_json": json.dumps(_exit_from_request(request.get("exit")), ensure_ascii=False),
    }
    record = create_acceptance_gate(db, values)
    db.commit()
    project = db.get(Project, record.project_id)
    return acceptance_gate_to_response(record, project=project)


def list_acceptance_gate_response(
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
    return list_acceptance_gates(
        db,
        project_id=project_id,
        change_type=_normalize_optional_enum(change_type, CHANGE_TYPES, "changeType"),
        status=_normalize_optional_enum(status, STATUSES, "status"),
        provider=_clean_text(provider, 64),
        profile=_clean_text(profile, 64),
        risk_type=_clean_text(risk_type, 64),
        page_no=page_no,
        page_size=page_size,
    )


def get_acceptance_gate_response(db: Session, gate_id: int) -> dict[str, Any]:
    record = get_acceptance_gate(db, gate_id)
    if record is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Acceptance gate not found: {gate_id}", 404)
    project = db.get(Project, record.project_id)
    return acceptance_gate_to_response(record, project=project)


def update_acceptance_gate_response(db: Session, gate_id: int, request: dict[str, Any]) -> dict[str, Any]:
    record = get_acceptance_gate(db, gate_id)
    if record is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Acceptance gate not found: {gate_id}", 404)
    values: dict[str, Any] = {}
    if "projectId" in request:
        project_id = _required_int(request.get("projectId"), "projectId")
        _ensure_project_exists(db, project_id)
        values["project_id"] = project_id
    if "title" in request:
        values["title"] = _required_text(request.get("title"), 255, "title")
    if "changeType" in request:
        values["change_type"] = _normalize_enum(request.get("changeType"), CHANGE_TYPES, "changeType")
    if "status" in request:
        values["status"] = _normalize_enum(request.get("status"), STATUSES, "status")
    for api_field, model_field in (("provider", "provider"), ("profile", "profile"), ("riskType", "risk_type")):
        if api_field in request:
            values[model_field] = _clean_text(request.get(api_field), 64)
    if "evaluationCaseIds" in request:
        case_ids = _linked_ids(request.get("evaluationCaseIds"), "evaluationCaseIds")
        _ensure_cases_exist(db, case_ids)
        values["evaluation_case_ids_json"] = json.dumps(case_ids, ensure_ascii=False)
    if "evaluationRunIds" in request:
        run_ids = _linked_ids(request.get("evaluationRunIds"), "evaluationRunIds")
        _ensure_runs_exist(db, run_ids)
        values["evaluation_run_ids_json"] = json.dumps(run_ids, ensure_ascii=False)
    if "ruleGapSummary" in request:
        values["rule_gap_summary_json"] = json.dumps(_rule_gap_summary_from_request(request.get("ruleGapSummary")), ensure_ascii=False)
    if "admission" in request:
        values["admission_json"] = json.dumps(_admission_from_request(request.get("admission")), ensure_ascii=False)
    if "exit" in request:
        values["exit_json"] = json.dumps(_exit_from_request(request.get("exit")), ensure_ascii=False)
    if values:
        record = update_acceptance_gate(db, record, values)
        db.commit()
    project = db.get(Project, record.project_id)
    return acceptance_gate_to_response(record, project=project)


def _admission_from_request(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    return {
        "problemStatement": _safe_summary_text(source.get("problemStatement"), 4000),
        "expectedBenefit": _safe_summary_text(source.get("expectedBenefit"), 4000),
        "riskAssessment": _safe_summary_text(source.get("riskAssessment"), 4000),
        "costEstimate": _safe_summary_text(source.get("costEstimate"), 4000),
        "decisionBy": _safe_summary_text(source.get("decisionBy"), 128),
        "decisionAt": _parse_datetime_text(source.get("decisionAt")),
    }


def _exit_from_request(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    result_status = _normalize_optional_enum(source.get("resultStatus"), RESULT_STATUSES, "resultStatus")
    return {
        "resultStatus": result_status,
        "falsePositiveDelta": _optional_number(source.get("falsePositiveDelta"), "falsePositiveDelta"),
        "contextMissingDelta": _optional_number(source.get("contextMissingDelta"), "contextMissingDelta"),
        "missingFindingDelta": _optional_number(source.get("missingFindingDelta"), "missingFindingDelta"),
        "findingCountDelta": _optional_number(source.get("findingCountDelta"), "findingCountDelta"),
        "durationDeltaMs": _optional_number(source.get("durationDeltaMs"), "durationDeltaMs"),
        "tokenCostDelta": _optional_number(source.get("tokenCostDelta"), "tokenCostDelta"),
        "notes": _safe_summary_text(source.get("notes"), 4000),
        "decidedBy": _safe_summary_text(source.get("decidedBy"), 128),
        "decidedAt": _parse_datetime_text(source.get("decidedAt")),
    }


def _rule_gap_summary_from_request(value: Any) -> list[dict[str, Any]]:
    items = value if isinstance(value, list) else []
    result = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        gap_type = _safe_summary_text(item.get("gapType"), 64).upper()
        signal = _safe_summary_text(item.get("signal"), 120).upper()
        if not gap_type or not signal:
            continue
        requested_context = _safe_summary_text(item.get("requestedContext"), 160).upper()
        suggested_capability = _safe_summary_text(item.get("suggestedCapability"), 240)
        summary_key = _safe_summary_text(item.get("summaryKey"), 180)
        result.append(
            {
                "gapType": gap_type,
                "signal": signal,
                "requestedContext": requested_context or "-",
                "suggestedCapability": suggested_capability or "-",
                "summaryKey": summary_key or f"{gap_type}|{signal}|{requested_context or '-'}|{index}",
            }
        )
        if len(result) >= 20:
            break
    return result


def _ensure_project_exists(db: Session, project_id: int) -> None:
    if db.get(Project, project_id) is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {project_id}", 404)


def _ensure_cases_exist(db: Session, case_ids: list[int]) -> None:
    if not case_ids:
        return
    found = {record.id for record in get_evaluation_cases_by_ids(db, case_ids)}
    missing = [case_id for case_id in case_ids if case_id not in found]
    if missing:
        raise AppError("RESOURCE_NOT_FOUND", f"Evaluation case not found: {missing[0]}", 404)


def _ensure_runs_exist(db: Session, run_ids: list[int]) -> None:
    for run_id in run_ids:
        if get_evaluation_run(db, run_id) is None:
            raise AppError("RESOURCE_NOT_FOUND", f"Evaluation run not found: {run_id}", 404)


def _linked_ids(value: Any, field: str) -> list[int]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise AppError("VALIDATION_ERROR", f"{field} is invalid", 400)
    result: list[int] = []
    seen: set[int] = set()
    for item in value:
        item_id = _to_int(item)
        if item_id is None or item_id <= 0:
            raise AppError("VALIDATION_ERROR", f"{field} is invalid", 400)
        if item_id in seen:
            continue
        seen.add(item_id)
        result.append(item_id)
    return result


def _safe_summary_text(value: Any, max_length: int) -> str:
    text = scrub_sensitive(str(value or "").strip())
    for pattern in _LOCAL_PATH_PATTERNS:
        text = pattern.sub("[local-path]", text)
    text = re.sub(r"(?i)authorization\s*[:=]\s*(?:bearer\s+)?[^,\s;}]+", "Authorization: ****", text)
    text = re.sub(r"(?i)authorization\s*[:=]\s*\*+\s+[^,\s;}]+", "Authorization: ****", text)
    text = re.sub(r"(?i)(token|secret|password|api[_-]?key)\s*[:=]\s*[^,\s;}]+", r"\1: ****", text)
    return text[:max_length]


def _clean_text(value: Any, max_length: int) -> str | None:
    text = _safe_summary_text(value, max_length)
    return text or None


def _required_text(value: Any, max_length: int, field: str) -> str:
    text = _clean_text(value, max_length)
    if not text:
        raise AppError("VALIDATION_ERROR", f"{field} is required", 400)
    return text


def _required_int(value: Any, field: str) -> int:
    number = _to_int(value)
    if number is None:
        raise AppError("VALIDATION_ERROR", f"{field} is required", 400)
    return number


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_number(value: Any, field: str) -> int | float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise AppError("VALIDATION_ERROR", f"{field} is invalid", 400)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise AppError("VALIDATION_ERROR", f"{field} is invalid", 400) from None
    return int(number) if number.is_integer() else number


def _parse_datetime_text(value: Any) -> str | None:
    text = _safe_summary_text(value, 64)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return text


def _normalize_enum(value: Any, allowed: set[str], field: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in allowed:
        raise AppError("VALIDATION_ERROR", f"{field} is invalid", 400)
    return normalized


def _normalize_optional_enum(value: Any, allowed: set[str], field: str) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    return _normalize_enum(value, allowed, field)
