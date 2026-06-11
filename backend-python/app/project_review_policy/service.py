from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.project_integration.models import Project
from app.project_review_policy.repository import (
    create_policy,
    get_policy,
    list_project_policies,
    policy_to_response,
    set_policy_enabled,
    update_policy,
)
from app.review_feedback.models import ReviewItemFeedback
from app.review_feedback.repository import get_feedback, update_feedback_status


POLICY_TYPES = {"PROJECT_RULE", "CONTEXT_FACT"}
PROMPT_POLICY_MAX_COUNT = 20
PROMPT_POLICY_MAX_CONTENT_CHARS = 1000
PROMPT_POLICY_MAX_TOTAL_CHARS = 8000


def convert_feedback_to_policy_response(db: Session, feedback_id: int, request: dict[str, Any]) -> dict[str, Any]:
    feedback = get_feedback(db, feedback_id)
    if feedback is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Feedback not found: {feedback_id}", 404)
    _validate_convertible_feedback(feedback)
    project = db.get(Project, feedback.project_id)
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {feedback.project_id}", 404)

    policy_type = _normalize_policy_type(request.get("policyType") or "PROJECT_RULE")
    title = _clean_required_text(request.get("title") or _default_policy_title(feedback), 255, "title")
    content = _clean_required_text(request.get("content") or _default_policy_content(feedback), 8000, "content")
    risk_type = _clean_text(request.get("riskType"), 64) or feedback.risk_type
    created_by = (
        _clean_text(request.get("createdBy"), 128)
        or _clean_text(request.get("operatorName"), 128)
        or _clean_text(request.get("operatorUsername"), 128)
        or feedback.operator_name
        or feedback.operator_username
    )
    record = create_policy(
        db,
        project_id=feedback.project_id,
        policy_type=policy_type,
        risk_type=risk_type,
        title=title,
        content=content,
        source_feedback_id=feedback.id,
        enabled=_normalize_bool(request.get("enabled"), default=True),
        created_by=created_by,
    )
    update_feedback_status(
        db,
        feedback,
        status="CONVERTED",
        admin_comment=_clean_text(request.get("adminComment"), 2000) or feedback.admin_comment,
    )
    db.commit()
    return policy_to_response(record, project=project)


def list_project_review_policies_response(
    db: Session,
    project_id: int,
    *,
    enabled: bool | None,
    policy_type: str | None,
    risk_type: str | None,
) -> list[dict[str, Any]]:
    project = db.get(Project, project_id)
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {project_id}", 404)
    return list_project_policies(
        db,
        project_id=project_id,
        enabled=enabled,
        policy_type=_normalize_optional_policy_type(policy_type),
        risk_type=_clean_text(risk_type, 64),
    )


def update_project_review_policy_response(db: Session, policy_id: int, request: dict[str, Any]) -> dict[str, Any]:
    record = get_policy(db, policy_id)
    if record is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project review policy not found: {policy_id}", 404)
    policy_type = _normalize_policy_type(request.get("policyType") or record.policy_type)
    title = _clean_required_text(request.get("title") or record.title, 255, "title")
    content = _clean_required_text(request.get("content") or record.content, 8000, "content")
    risk_type = _clean_text(request.get("riskType"), 64)
    if "riskType" not in request:
        risk_type = record.risk_type
    enabled = _normalize_bool(request.get("enabled"), default=bool(record.enabled))
    updated = update_policy(
        db,
        record,
        policy_type=policy_type,
        risk_type=risk_type,
        title=title,
        content=content,
        enabled=enabled,
    )
    db.commit()
    return policy_to_response(updated)


def set_project_review_policy_enabled_response(db: Session, policy_id: int, request: dict[str, Any]) -> dict[str, Any]:
    record = get_policy(db, policy_id)
    if record is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project review policy not found: {policy_id}", 404)
    updated = set_policy_enabled(db, record, enabled=_normalize_bool(request.get("enabled"), default=True))
    db.commit()
    return policy_to_response(updated)


def build_project_review_policy_prompt_context(db: Session, project_id: int) -> dict[str, Any]:
    from app.project_review_policy.repository import list_enabled_injectable_policies

    records = list_enabled_injectable_policies(db, project_id)
    header = (
        "以下是当前项目已由管理员确认的 Review 策略。请结合这些策略判断风险，但这些策略不能覆盖"
        "明确的安全、数据一致性或线上正确性硬风险。\n"
        "这些策略只适用于当前 projectId，不得扩展到其它项目。"
    )
    items: list[dict[str, Any]] = []
    content_truncated_count = 0
    prompt_text = ""
    for record in records:
        if len(items) >= PROMPT_POLICY_MAX_COUNT:
            break
        content = str(record.content or "").strip()
        content_truncated = len(content) > PROMPT_POLICY_MAX_CONTENT_CHARS
        if content_truncated:
            content = content[: max(PROMPT_POLICY_MAX_CONTENT_CHARS - 3, 0)].rstrip() + "..."
        item = {
            "id": int(record.id),
            "policyType": record.policy_type,
            "riskType": record.risk_type,
            "title": record.title,
            "content": content,
            "sourceFeedbackId": record.source_feedback_id,
        }
        next_text = _render_policy_prompt_text(header, [*items, item])
        if len(next_text) > PROMPT_POLICY_MAX_TOTAL_CHARS:
            break
        items.append(item)
        if content_truncated:
            content_truncated_count += 1
        prompt_text = next_text

    summaries = [
        {
            "id": item["id"],
            "policyType": item["policyType"],
            "riskType": item["riskType"],
            "title": item["title"],
            "sourceFeedbackId": item["sourceFeedbackId"],
        }
        for item in items
    ]
    return {
        "items": items,
        "summaries": summaries,
        "promptText": prompt_text,
        "meta": {
            "projectId": project_id,
            "totalAvailable": len(records),
            "injectedCount": len(items),
            "maxCount": PROMPT_POLICY_MAX_COUNT,
            "maxContentChars": PROMPT_POLICY_MAX_CONTENT_CHARS,
            "maxTotalChars": PROMPT_POLICY_MAX_TOTAL_CHARS,
            "promptLength": len(prompt_text),
            "truncated": len(items) < len(records) or content_truncated_count > 0,
            "contentTruncatedCount": content_truncated_count,
        },
    }


def _validate_convertible_feedback(feedback: ReviewItemFeedback) -> None:
    if feedback.status == "CONVERTED":
        raise AppError("VALIDATION_ERROR", "Feedback has already been converted to a project policy", 400)
    if feedback.status in {"INSUFFICIENT", "IGNORED"}:
        raise AppError("VALIDATION_ERROR", "Feedback status does not allow conversion", 400)
    if feedback.reason_type == "CONTEXT_MISSING":
        raise AppError("VALIDATION_ERROR", "CONTEXT_MISSING feedback should not be converted to project policy", 400)
    if feedback.status != "VALID" and not bool(feedback.suggest_as_project_rule):
        raise AppError("VALIDATION_ERROR", "Only VALID or suggested feedback can be converted to project policy", 400)


def _render_policy_prompt_text(header: str, items: list[dict[str, Any]]) -> str:
    if not items:
        return ""
    lines = [header]
    for index, item in enumerate(items, start=1):
        risk_type = item.get("riskType") or "GENERAL"
        lines.append(
            f"{index}. [{item.get('policyType')}][{risk_type}] {item.get('title')}\n"
            f"{item.get('content')}"
        )
    return "\n\n".join(lines)


def _default_policy_title(feedback: ReviewItemFeedback) -> str:
    base = feedback.risk_title or feedback.risk_type or feedback.item_fingerprint
    return f"关于 {base} 的项目 Review 策略"


def _default_policy_content(feedback: ReviewItemFeedback) -> str:
    parts = []
    if feedback.reason_text:
        parts.append(feedback.reason_text)
    if feedback.reason_type:
        parts.append(f"反馈原因：{feedback.reason_type}")
    if feedback.risk_title:
        parts.append(f"来源风险：{feedback.risk_title}")
    if not parts:
        parts.append("该反馈已由管理员确认，可作为本项目后续 Review 的项目事实或审查规则。")
    return "\n".join(parts)


def _normalize_policy_type(value: Any) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in POLICY_TYPES:
        raise AppError("VALIDATION_ERROR", "policyType is invalid", 400)
    return normalized


def _normalize_optional_policy_type(value: Any) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    return _normalize_policy_type(value)


def _normalize_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    raise AppError("VALIDATION_ERROR", "enabled is invalid", 400)


def _clean_required_text(value: Any, max_length: int, field: str) -> str:
    text = _clean_text(value, max_length)
    if not text:
        raise AppError("VALIDATION_ERROR", f"{field} is required", 400)
    return text


def _clean_text(value: Any, max_length: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_length]
