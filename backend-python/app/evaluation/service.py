from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.code_quality.models import CodeQualityReviewProgressEvent
from app.code_quality.models import CodeQualityReviewResult
from app.code_quality.repository import scrub_sensitive
from app.core.errors import AppError
from app.core.json_utils import read_json
from app.evaluation.models import EvaluationCase
from app.evaluation.repository import (
    create_evaluation_case,
    create_evaluation_run,
    evaluation_case_to_response,
    evaluation_run_to_response,
    get_evaluation_cases_by_ids,
    get_evaluation_case,
    get_evaluation_run,
    get_evaluation_run_item,
    list_evaluation_run_items,
    list_evaluation_runs,
    list_evaluation_cases,
    refresh_evaluation_run_aggregate,
    rule_gap_attribution_to_response,
    update_evaluation_case,
    update_evaluation_run_item,
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
RUN_TYPES = {"EVALUATION", "REVIEW_REPLAY"}
RUN_STATUSES = {"PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELED"}
RULE_GAP_ATTRIBUTION_TYPES = {
    "RULE_GAP_CAUSED",
    "RULE_GAP_RELATED",
    "NOT_RULE_GAP",
    "PROMPT_ISSUE",
    "MODEL_REASONING_ISSUE",
    "PROJECT_POLICY_MISSING",
    "INSUFFICIENT_LABEL",
}
RULE_GAP_PROVEN_ATTRIBUTIONS = {"RULE_GAP_CAUSED", "RULE_GAP_RELATED"}
RULE_GAP_PROVEN_VERDICTS = {"FALSE_POSITIVE", "CONTEXT_MISSING", "MISSING_FINDING"}
_LOCAL_PATH_PATTERNS = [
    re.compile(r"[A-Za-z]:\\[^\s,;'\"}]+"),
    re.compile(r"/[^\s,;'\"}]+(?:/\.local|/review-workspaces|/worktrees|/mirrors|/tmp)[^\s,;'\"}]*"),
]


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


def get_rule_gap_attribution_response(db: Session, case_id: int) -> dict[str, Any]:
    record = get_evaluation_case(db, case_id)
    if record is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Evaluation case not found: {case_id}", 404)
    return rule_gap_attribution_to_response(record)


def update_rule_gap_attribution_response(db: Session, case_id: int, request: dict[str, Any]) -> dict[str, Any]:
    record = get_evaluation_case(db, case_id)
    if record is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Evaluation case not found: {case_id}", 404)
    values = {
        "rule_gap_attribution_type": _normalize_optional_enum(
            request.get("attributionType"), RULE_GAP_ATTRIBUTION_TYPES, "attributionType"
        ),
        "rule_gap_summary_json": json.dumps(_rule_gap_summary_from_request(request.get("ruleGapSummary")), ensure_ascii=False),
        "rule_gap_attribution_comment": _safe_summary_text(request.get("comment"), 4000) or None,
        "rule_gap_attributed_by": _clean_text(request.get("attributedBy"), 128),
        "rule_gap_attributed_at": datetime.now(),
    }
    updated = update_evaluation_case(db, record, values)
    db.commit()
    return rule_gap_attribution_to_response(updated)


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


def create_evaluation_run_response(db: Session, request: dict[str, Any]) -> dict[str, Any]:
    case_ids = _case_ids(request.get("caseIds"))
    case_records = get_evaluation_cases_by_ids(db, case_ids)
    by_id = {case.id: case for case in case_records}
    missing = [case_id for case_id in case_ids if case_id not in by_id]
    if missing:
        raise AppError("RESOURCE_NOT_FOUND", f"Evaluation case not found: {missing[0]}", 404)
    ordered_cases = [by_id[case_id] for case_id in case_ids]
    project_id = _to_int(request.get("projectId"))
    if project_id is not None:
        _ensure_project_exists(db, project_id)
    else:
        distinct_project_ids = {case.project_id for case in ordered_cases}
        project_id = next(iter(distinct_project_ids)) if len(distinct_project_ids) == 1 else None
    run_type = _normalize_enum(request.get("runType") or "EVALUATION", RUN_TYPES, "runType")
    sample_set = {
        "caseIds": case_ids,
        "count": len(case_ids),
    }
    if request.get("sampleSetFilters") and isinstance(request.get("sampleSetFilters"), dict):
        sample_set["filters"] = _safe_json_value(request.get("sampleSetFilters"))
    values = {
        "name": _clean_text(request.get("name"), 255) or "Evaluation Run",
        "run_type": run_type,
        "sample_set_name": _clean_text(request.get("sampleSetName"), 255),
        "sample_set_json": json.dumps(sample_set, ensure_ascii=False),
        "project_id": project_id,
        "provider": _clean_text(request.get("provider"), 64),
        "profile": _clean_text(request.get("profile"), 64),
        "model": _clean_text(request.get("model"), 128),
        "prompt_hash": _clean_text(request.get("promptHash"), 128),
        "context_pack_version": _clean_text(request.get("contextPackVersion"), 64),
        "retriever_version": _clean_text(request.get("retrieverVersion"), 64),
        "rule_gap_version": _clean_text(request.get("ruleGapVersion"), 64),
        "baseline_json": json.dumps(_safe_json_value(request.get("baseline")), ensure_ascii=False)
        if isinstance(request.get("baseline"), dict)
        else None,
        "candidate_json": json.dumps(_safe_json_value(request.get("candidate")), ensure_ascii=False)
        if isinstance(request.get("candidate"), dict)
        else None,
        "status": "PENDING",
        "total_count": len(case_ids),
        "completed_count": 0,
        "failed_count": 0,
        "result_summary_json": json.dumps(
            {
                "totalCount": len(case_ids),
                "completedCount": 0,
                "failedCount": 0,
                "statusCounts": {"PENDING": len(case_ids)},
                "verdictCounts": _count_values([case.verdict for case in ordered_cases]),
            },
            ensure_ascii=False,
        ),
        "duration_ms": None,
        "notes": _clean_text(request.get("notes"), 4000),
    }
    record = create_evaluation_run(db, values, ordered_cases)
    db.commit()
    return get_evaluation_run_response(db, record.id)


def list_evaluation_run_response(
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
    return list_evaluation_runs(
        db,
        project_id=project_id,
        provider=_clean_text(provider, 64),
        profile=_clean_text(profile, 64),
        run_type=_normalize_optional_enum(run_type, RUN_TYPES, "runType"),
        status=_normalize_optional_enum(status, RUN_STATUSES, "status"),
        page_no=page_no,
        page_size=page_size,
    )


def get_evaluation_run_response(db: Session, run_id: int) -> dict[str, Any]:
    record = get_evaluation_run(db, run_id)
    if record is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Evaluation run not found: {run_id}", 404)
    project = db.get(Project, record.project_id) if record.project_id is not None else None
    items = list_evaluation_run_items(db, run_id)
    return evaluation_run_to_response(record, project=project, items=items)


def update_evaluation_run_item_response(
    db: Session,
    run_id: int,
    item_id: int,
    request: dict[str, Any],
) -> dict[str, Any]:
    run = get_evaluation_run(db, run_id)
    if run is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Evaluation run not found: {run_id}", 404)
    item = get_evaluation_run_item(db, item_id)
    if item is None or item.run_id != run_id:
        raise AppError("RESOURCE_NOT_FOUND", f"Evaluation run item not found: {item_id}", 404)
    values: dict[str, Any] = {}
    if "status" in request:
        values["status"] = _normalize_enum(request.get("status"), RUN_STATUSES, "status")
    if "durationMs" in request:
        values["duration_ms"] = _non_negative_int(request.get("durationMs"), "durationMs")
    for api_field, model_field in (
        ("baselineSummary", "baseline_summary_json"),
        ("candidateSummary", "candidate_summary_json"),
        ("resultSummary", "result_summary_json"),
    ):
        if api_field in request:
            values[model_field] = json.dumps(_safe_json_value(request.get(api_field)), ensure_ascii=False)
    if "errorMessage" in request:
        values["error_message"] = _clean_text(request.get("errorMessage"), 1024)
    if not values:
        return get_evaluation_run_response(db, run_id)
    update_evaluation_run_item(db, item, values)
    refresh_evaluation_run_aggregate(db, run)
    db.commit()
    return get_evaluation_run_response(db, run_id)


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
        "rule_gap_summary_json": json.dumps(
            _latest_rule_gap_summary_for_case(db, task.id, result.review_key), ensure_ascii=False
        ),
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
        "rule_gap_summary_json": json.dumps(_rule_gap_summary_from_request(request.get("ruleGapSummary")), ensure_ascii=False),
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


def _latest_rule_gap_summary_for_case(db: Session, task_id: int, review_key: str | None) -> list[dict[str, Any]]:
    stmt = (
        select(CodeQualityReviewProgressEvent)
        .where(CodeQualityReviewProgressEvent.task_id == task_id)
        .where(CodeQualityReviewProgressEvent.phase == "CONTEXT_PACK_BUILT")
    )
    if review_key:
        stmt = stmt.where(CodeQualityReviewProgressEvent.review_key == review_key)
    event = db.scalars(stmt.order_by(CodeQualityReviewProgressEvent.created_at.desc(), CodeQualityReviewProgressEvent.id.desc())).first()
    if event is None:
        return []
    detail = read_json(event.detail, {})
    summary = detail.get("summary") if isinstance(detail, dict) and isinstance(detail.get("summary"), dict) else detail
    items = summary.get("ruleGapItems") if isinstance(summary, dict) else []
    enriched = []
    for index, item in enumerate(items if isinstance(items, list) else []):
        normalized = _normalize_rule_gap_summary_item(item, task_id=task_id, review_key=review_key, progress_event_id=event.id)
        if normalized:
            normalized["summaryKey"] = normalized.get("summaryKey") or _rule_gap_summary_key(normalized, index)
            enriched.append(normalized)
        if len(enriched) >= 5:
            break
    return enriched


def _rule_gap_summary_from_request(value: Any) -> list[dict[str, Any]]:
    items = value if isinstance(value, list) else []
    result = []
    for index, item in enumerate(items):
        normalized = _normalize_rule_gap_summary_item(item)
        if normalized:
            normalized["summaryKey"] = normalized.get("summaryKey") or _rule_gap_summary_key(normalized, index)
            result.append(normalized)
        if len(result) >= 20:
            break
    return result


def _normalize_rule_gap_summary_item(
    item: Any,
    *,
    task_id: int | None = None,
    review_key: str | None = None,
    progress_event_id: int | None = None,
) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    gap_type = _safe_summary_text(item.get("gapType"), 64).upper()
    signal = _safe_summary_text(item.get("signal"), 120).upper()
    if not gap_type or not signal:
        return None
    requested_context = _safe_summary_text(item.get("requestedContext"), 160).upper()
    suggested_capability = _safe_summary_text(item.get("suggestedCapability"), 240)
    result: dict[str, Any] = {
        "gapType": gap_type,
        "signal": signal,
        "requestedContext": requested_context or "-",
        "suggestedCapability": suggested_capability or "-",
    }
    item_task_id = _to_int(item.get("taskId")) or task_id
    if item_task_id is not None:
        result["taskId"] = item_task_id
    item_review_key = _clean_text(item.get("reviewKey"), 64) or review_key
    if item_review_key:
        result["reviewKey"] = item_review_key
    item_progress_id = _to_int(item.get("progressEventId")) or progress_event_id
    if item_progress_id is not None:
        result["progressEventId"] = item_progress_id
    summary_key = _clean_text(item.get("summaryKey"), 180)
    if summary_key:
        result["summaryKey"] = _safe_summary_text(summary_key, 180)
    return result


def _rule_gap_summary_key(item: dict[str, Any], index: int) -> str:
    raw = "|".join(
        str(item.get(key) or "")
        for key in ("gapType", "signal", "requestedContext", "suggestedCapability", "taskId", "reviewKey")
    )
    return _safe_summary_text(raw, 180) or f"rule-gap-{index}"


def _safe_summary_text(value: Any, max_length: int) -> str:
    text = scrub_sensitive(str(value or "").strip())
    for pattern in _LOCAL_PATH_PATTERNS:
        text = pattern.sub("[local-path]", text)
    text = re.sub(r"(?i)authorization\s*[:=]\s*(?:bearer\s+)?[^,\s;}]+", "Authorization: ****", text)
    text = re.sub(r"(?i)authorization\s*[:=]\s*\*+\s+[^,\s;}]+", "Authorization: ****", text)
    text = re.sub(r"(?i)(token|secret|password|api[_-]?key)\s*[:=]\s*[^,\s;}]+", r"\1: ****", text)
    return text[:max_length]


def _ensure_project_exists(db: Session, project_id: int) -> None:
    if db.get(Project, project_id) is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {project_id}", 404)


def _case_ids(value: Any) -> list[int]:
    if not isinstance(value, list) or not value:
        raise AppError("VALIDATION_ERROR", "caseIds is required", 400)
    result: list[int] = []
    seen: set[int] = set()
    for item in value:
        case_id = _to_int(item)
        if case_id is None or case_id <= 0:
            raise AppError("VALIDATION_ERROR", "caseIds is invalid", 400)
        if case_id in seen:
            continue
        seen.add(case_id)
        result.append(case_id)
    return result


def _non_negative_int(value: Any, field: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise AppError("VALIDATION_ERROR", f"{field} is invalid", 400) from None
    if number < 0:
        raise AppError("VALIDATION_ERROR", f"{field} is invalid", 400)
    return number


def _safe_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key)
            if normalized_key in {"rawOutput", "providerRawOutput", "promptText", "sourceSnippet", "diffText"}:
                continue
            result[normalized_key] = _safe_json_value(item)
        return result
    if isinstance(value, list):
        return [_safe_json_value(item) for item in value[:100]]
    if isinstance(value, str):
        return _clean_text(value, 1024)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _clean_text(value, 1024)


def _count_values(values: list[str | None]) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        key = value or "UNKNOWN"
        result[key] = result.get(key, 0) + 1
    return result


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
