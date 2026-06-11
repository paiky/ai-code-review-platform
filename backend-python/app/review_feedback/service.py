from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.code_quality.models import CodeQualityReviewResult
from app.core.errors import AppError
from app.core.json_utils import read_json
from app.review_feedback.models import ReviewItemFeedback
from app.review_feedback.repository import (
    feedback_to_response,
    get_feedback,
    get_feedback_map_for_task,
    list_feedback_pool,
    list_task_feedbacks,
    update_feedback_status,
    upsert_feedback,
)
from app.review_record.models import ReviewResult, ReviewTask


SOURCE_TYPES = {"RULE_REMINDER", "AI_FINDING"}
FEEDBACK_TYPES = {"USEFUL", "FALSE_POSITIVE", "LEVEL_TOO_HIGH", "DUPLICATE", "FIXED"}
REASON_TYPES = {
    "PROJECT_ALLOWED",
    "HAS_EXTERNAL_GUARD",
    "CONTEXT_MISSING",
    "RULE_NOT_APPLICABLE",
    "LEVEL_TOO_HIGH",
    "DESCRIPTION_INACCURATE",
    "DUPLICATE",
    "OTHER",
}
STATUSES = {"PENDING", "VALID", "INSUFFICIENT", "IGNORED", "CONVERTED"}
MISSING_CONTEXT_TYPES = {
    "SAME_FILE_CONTEXT",
    "SAME_CLASS_METHODS",
    "REFERENCE_SEARCH",
    "CALLER_CONTEXT",
    "CALLEE_CONTEXT",
    "RELATED_FILE",
    "DB_SCHEMA_CONTEXT",
    "CONFIG_CONTEXT",
    "PROJECT_POLICY_CONTEXT",
    "TEST_RESULT_CONTEXT",
    "OTHER",
}


def attach_rule_feedbacks(db: Session, task_id: int, risk_card: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(risk_card, dict):
        return risk_card
    feedback_map = get_feedback_map_for_task(db, task_id)
    clone = dict(risk_card)
    items = []
    for item in risk_card.get("riskItems") or []:
        if not isinstance(item, dict):
            items.append(item)
            continue
        next_item = dict(item)
        feedback_key = rule_item_fingerprint(next_item)
        next_item["feedbackKey"] = feedback_key
        next_item["feedback"] = feedback_map.get(("RULE_REMINDER", feedback_key))
        items.append(next_item)
    clone["riskItems"] = items
    return clone


def attach_ai_finding_feedbacks(
    db: Session,
    result: CodeQualityReviewResult,
    findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    feedback_map = get_feedback_map_for_task(db, result.task_id)
    items = []
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            items.append(finding)
            continue
        next_finding = dict(finding)
        fingerprint = ai_finding_fingerprint(result, next_finding, index)
        next_finding["fingerprint"] = fingerprint
        next_finding["feedbackKey"] = fingerprint
        next_finding["feedback"] = feedback_map.get(("AI_FINDING", fingerprint))
        items.append(next_finding)
    return items


def create_or_update_feedback(db: Session, task_id: int, request: dict[str, Any]) -> dict[str, Any]:
    task = db.get(ReviewTask, task_id)
    if task is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)

    source_type = _normalize_enum(request.get("sourceType"), SOURCE_TYPES, "sourceType")
    item_fingerprint = _clean_text(
        request.get("itemFingerprint") or request.get("feedbackKey") or request.get("fingerprint"),
        128,
    )
    if not item_fingerprint:
        raise AppError("VALIDATION_ERROR", "itemFingerprint is required", 400)
    feedback_type = _normalize_enum(request.get("feedbackType"), FEEDBACK_TYPES, "feedbackType")
    reason_type = _normalize_optional_enum(request.get("reasonType"), REASON_TYPES, "reasonType")
    reason_text = _clean_text(request.get("reasonText"), 4000)
    missing_context_types = (
        _normalize_missing_context_types(request.get("missingContextTypes"))
        if reason_type == "CONTEXT_MISSING"
        else []
    )
    target = _resolve_feedback_target(db, task, source_type, item_fingerprint, request)
    snapshot_json = json.dumps(target.get("snapshot") or {}, ensure_ascii=False)
    record = upsert_feedback(
        db,
        task=task,
        source_type=source_type,
        item_fingerprint=item_fingerprint,
        target=target,
        feedback_type=feedback_type,
        reason_type=reason_type,
        reason_text=reason_text,
        missing_context_types=missing_context_types,
        suggest_as_project_rule=bool(request.get("suggestAsProjectRule")),
        operator_name=_clean_text(request.get("operatorName"), 128),
        operator_username=_clean_text(request.get("operatorUsername"), 128),
        item_snapshot_json=snapshot_json,
    )
    db.commit()
    return feedback_to_response(record)


def get_task_feedback_response(db: Session, task_id: int) -> list[dict[str, Any]]:
    if db.get(ReviewTask, task_id) is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)
    return list_task_feedbacks(db, task_id)


def list_feedback_pool_response(
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
    normalized_source_type = _normalize_optional_enum(source_type, SOURCE_TYPES, "sourceType")
    normalized_feedback_type = _normalize_optional_enum(feedback_type, FEEDBACK_TYPES, "feedbackType")
    normalized_reason_type = _normalize_optional_enum(reason_type, REASON_TYPES, "reasonType")
    normalized_missing_context_type = _normalize_optional_enum(
        missing_context_type,
        MISSING_CONTEXT_TYPES,
        "missingContextType",
    )
    normalized_status = _normalize_optional_enum(status, STATUSES, "status")
    return list_feedback_pool(
        db,
        project_id=project_id,
        source_type=normalized_source_type,
        risk_type=_clean_text(risk_type, 64),
        feedback_type=normalized_feedback_type,
        reason_type=normalized_reason_type,
        missing_context_type=normalized_missing_context_type,
        policy_candidate=policy_candidate,
        status=normalized_status,
        keyword=_clean_text(keyword, 255),
        page_no=page_no,
        page_size=page_size,
    )


def update_feedback_status_response(db: Session, feedback_id: int, request: dict[str, Any]) -> dict[str, Any]:
    record = get_feedback(db, feedback_id)
    if record is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Feedback not found: {feedback_id}", 404)
    status = _normalize_enum(request.get("status"), STATUSES, "status")
    updated = update_feedback_status(
        db,
        record,
        status=status,
        admin_comment=_clean_text(request.get("adminComment"), 2000),
    )
    db.commit()
    return feedback_to_response(updated)


def _resolve_feedback_target(
    db: Session,
    task: ReviewTask,
    source_type: str,
    item_fingerprint: str,
    request: dict[str, Any],
) -> dict[str, Any]:
    targets = _rule_targets(db, task) if source_type == "RULE_REMINDER" else _ai_targets(db, task)
    target = targets.get(item_fingerprint)
    if target is not None:
        return target
    if source_type == "RULE_REMINDER" and request.get("riskTitle"):
        return _fallback_target(source_type, item_fingerprint, request)
    raise AppError("RESOURCE_NOT_FOUND", f"Feedback target not found: {item_fingerprint}", 404)


def _rule_targets(db: Session, task: ReviewTask) -> dict[str, dict[str, Any]]:
    result = db.scalars(select(ReviewResult).where(ReviewResult.task_id == task.id)).first()
    risk_card = read_json(result.risk_card_json, {}) if result is not None else {}
    if not isinstance(risk_card, dict):
        return {}
    targets = {}
    for item in risk_card.get("riskItems") or []:
        if not isinstance(item, dict):
            continue
        key = rule_item_fingerprint(item)
        targets[key] = {
            "cardId": risk_card.get("cardId"),
            "riskId": item.get("riskId"),
            "riskType": item.get("category") or item.get("ruleCode"),
            "riskTitle": _clean_text(item.get("title"), 255),
            "originalRiskLevel": item.get("riskLevel"),
            "snapshot": item,
        }
    return targets


def _ai_targets(db: Session, task: ReviewTask) -> dict[str, dict[str, Any]]:
    records = db.scalars(
        select(CodeQualityReviewResult)
        .where(CodeQualityReviewResult.task_id == task.id)
        .order_by(CodeQualityReviewResult.sort_order.asc(), CodeQualityReviewResult.id.asc())
    ).all()
    targets = {}
    for result in records:
        findings = read_json(result.findings_json, [])
        if not isinstance(findings, list):
            continue
        for index, finding in enumerate(findings):
            if not isinstance(finding, dict):
                continue
            key = ai_finding_fingerprint(result, finding, index)
            targets[key] = {
                "reviewKey": result.review_key,
                "findingIndex": index,
                "riskType": finding.get("category"),
                "riskTitle": _clean_text(finding.get("title"), 255),
                "originalRiskLevel": finding.get("severity") or result.overall_level,
                "snapshot": finding,
            }
    return targets


def _fallback_target(source_type: str, item_fingerprint: str, request: dict[str, Any]) -> dict[str, Any]:
    return {
        "cardId": _clean_text(request.get("cardId"), 128),
        "riskId": _clean_text(request.get("riskId"), 128),
        "reviewKey": _clean_text(request.get("reviewKey"), 64),
        "findingIndex": _to_int(request.get("findingIndex")),
        "riskType": _clean_text(request.get("riskType"), 64),
        "riskTitle": _clean_text(request.get("riskTitle"), 255) or item_fingerprint,
        "originalRiskLevel": _clean_text(request.get("originalRiskLevel"), 32),
        "snapshot": {
            "sourceType": source_type,
            "itemFingerprint": item_fingerprint,
            "riskTitle": request.get("riskTitle"),
            "riskType": request.get("riskType"),
        },
    }


def rule_item_fingerprint(item: dict[str, Any]) -> str:
    evidence = _first_evidence(item)
    parts = [
        "RULE_REMINDER",
        item.get("ruleCode"),
        item.get("category"),
        _normalize_title(item.get("title")),
        _normalize_path(evidence.get("filePath")),
        _line_bucket(evidence.get("lineStart")),
    ]
    return _sha256(parts)


def ai_finding_fingerprint(
    result: CodeQualityReviewResult,
    finding: dict[str, Any],
    index: int,
) -> str:
    parts = [
        "AI_FINDING",
        result.review_key or "default",
        result.provider,
        result.profile_code,
        finding.get("severity"),
        finding.get("category"),
        _normalize_path(finding.get("filePath")),
        _line_bucket(finding.get("startLine")),
        _normalize_title(finding.get("title")),
        str(index) if not finding.get("title") and not finding.get("filePath") else "",
    ]
    return _sha256(parts)


def _first_evidence(item: dict[str, Any]) -> dict[str, Any]:
    for evidence in item.get("evidences") or []:
        if isinstance(evidence, dict):
            return evidence
    for artifact in item.get("maintenanceArtifacts") or []:
        if isinstance(artifact, dict):
            return {"filePath": artifact.get("sourceFilePath"), "lineStart": None}
    return {}


def _sha256(parts: list[Any]) -> str:
    value = "\n".join(str(part or "-").strip() for part in parts)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_path(value: Any) -> str:
    text = str(value or "").strip().replace("\\", "/")
    return re.sub(r"/+", "/", text).lower() or "-"


def _normalize_title(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    text = re.sub(r"^(风险|问题|提醒)[:：]\s*", "", text)
    return text.lower() or "-"


def _line_bucket(value: Any) -> str:
    line = _to_int(value)
    if line is None:
        return "-"
    return str((line // 10) * 10)


def _normalize_enum(value: Any, allowed: set[str], field: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in allowed:
        raise AppError("VALIDATION_ERROR", f"{field} is invalid", 400)
    return normalized


def _normalize_optional_enum(value: Any, allowed: set[str], field: str) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    return _normalize_enum(value, allowed, field)


def _normalize_missing_context_types(value: Any) -> list[str]:
    raw_items = value if isinstance(value, list) else ([value] if value else [])
    normalized: list[str] = []
    for item in raw_items:
        if item is None:
            continue
        normalized_item = _normalize_enum(item, MISSING_CONTEXT_TYPES, "missingContextTypes")
        if normalized_item not in normalized:
            normalized.append(normalized_item)
    return normalized[:10]


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
