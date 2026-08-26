import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import and_, case, func, inspect, or_, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.code_quality.models import CodeQualityReviewResult
from app.core.errors import AppError
from app.core.json_utils import format_datetime, page_response, read_json
from app.project_integration.models import GitLabMergeRequestEvent, GitLabPushEvent, Project
from app.project_integration.repository import ensure_project_config_schema
from app.review_feedback.service import attach_rule_feedbacks
from app.review_record.models import NotificationRecord, ReviewResult, ReviewTask
from app.risk_engine.service import generate_risk_card
from app.rule_template.models import RuleTemplate
from app.rule_template.repository import normalize_rule_codes


RISK_WEIGHT = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
AI_REVIEW_STATUS_VALUES = {
    "NOT_TRIGGERED",
    "REVIEWING",
    "NO_RISK",
    "MINOR",
    "MAJOR",
    "CRITICAL",
    "SKIPPED",
    "REVIEW_FAILED",
    "TASK_FAILED",
}
_LOGGER = logging.getLogger(__name__)


def parse_agent_completion_context(
    value: Any,
    *,
    task_id: int,
) -> dict[str, Any]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return {}
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value) if isinstance(value, str) else None
    except json.JSONDecodeError:
        _LOGGER.warning(
            "Agent completion context JSON invalid taskId=%s",
            task_id,
        )
        return {}
    if not isinstance(parsed, dict):
        _LOGGER.warning(
            "Agent completion context shape invalid taskId=%s",
            task_id,
        )
        return {}
    return parsed


def find_review_result_for_notification(
    db: Session,
    result_id: int | None,
    task_id: int,
) -> dict[str, Any] | None:
    if (
        not isinstance(result_id, int)
        or isinstance(result_id, bool)
        or result_id <= 0
    ):
        return None
    result = db.scalars(
        select(ReviewResult)
        .where(ReviewResult.id == result_id, ReviewResult.task_id == task_id)
        .limit(1)
    ).first()
    if result is None:
        _LOGGER.warning(
            "Agent completion risk card reference unavailable taskId=%s resultId=%s",
            task_id,
            result_id,
        )
        return None
    try:
        risk_card = json.loads(result.risk_card_json)
    except (TypeError, json.JSONDecodeError):
        _LOGGER.warning(
            "Agent completion risk card JSON invalid taskId=%s resultId=%s",
            task_id,
            result_id,
        )
        return None
    if not isinstance(risk_card, dict):
        _LOGGER.warning(
            "Agent completion risk card shape invalid taskId=%s resultId=%s",
            task_id,
            result_id,
        )
        return None
    return {
        "riskCard": risk_card,
        "reminderCardEnabled": (
            bool(result.reminder_card_enabled)
            if result.reminder_card_enabled is not None
            else True
        ),
    }


def resolve_agent_completion_notification(
    db: Session,
    *,
    task_id: int,
    context: dict[str, Any],
) -> tuple[int | None, dict[str, Any] | None, bool]:
    raw_result_id = context.get("ruleResultId")
    result_id = (
        raw_result_id
        if isinstance(raw_result_id, int)
        and not isinstance(raw_result_id, bool)
        and raw_result_id > 0
        else None
    )
    reminder_value = context.get("reminderCardEnabled")
    legacy_risk_card = context.get("riskCard")
    if isinstance(legacy_risk_card, dict):
        return (
            result_id,
            legacy_risk_card,
            reminder_value if isinstance(reminder_value, bool) else True,
        )
    referenced = find_review_result_for_notification(db, result_id, task_id)
    if isinstance(reminder_value, bool):
        reminder_card_enabled = reminder_value
    elif referenced is not None:
        reminder_card_enabled = bool(referenced.get("reminderCardEnabled", True))
    else:
        reminder_card_enabled = True
    return (
        result_id,
        referenced.get("riskCard") if referenced is not None else None,
        reminder_card_enabled,
    )


AI_FINDING_WEIGHT = {"MINOR": 1, "MAJOR": 2, "CRITICAL": 3}


def _focus_indicators(risk_card_json: str | None) -> list:
    risk_card = read_json(risk_card_json, {})
    if isinstance(risk_card, dict) and isinstance(risk_card.get("focusIndicators"), list):
        return risk_card["focusIndicators"]
    return []


def _filters(
    project_id: int | None,
    status: str | None,
    review_statuses: list[str] | None,
    risk_level: str | None,
    keyword: str | None,
    target_type: str | None,
    trigger_type: str | None,
):
    clauses = []
    if project_id is not None:
        clauses.append(ReviewTask.project_id == project_id)
    if status:
        clauses.append(ReviewTask.status == status)
    if review_statuses:
        clauses.append(ReviewTask.review_status.in_(review_statuses))
    if risk_level:
        clauses.append(ReviewTask.risk_level == risk_level)
    if target_type:
        clauses.append(
            or_(
                ReviewTask.target_type == target_type,
                ReviewTask.target_types_json.like(f"%{target_type}%"),
                Project.target_type == target_type,
            )
        )
    if trigger_type:
        clauses.append(ReviewTask.trigger_type == trigger_type)
    if keyword:
        like = f"%{keyword}%"
        clauses.append(
            or_(
                Project.name.like(like),
                ReviewTask.source_branch.like(like),
                ReviewTask.target_branch.like(like),
                ReviewTask.external_source_id.like(like),
            )
        )
    return clauses


def list_review_tasks(
    db: Session,
    project_id: int | None,
    status: str | None,
    review_statuses: list[str] | None,
    risk_level: str | None,
    keyword: str | None,
    target_type: str | None,
    trigger_type: str | None,
    page_no: int,
    page_size: int,
) -> dict:
    ensure_review_task_status_schema(db)
    ensure_project_config_schema(db)
    page_no = max(page_no, 1)
    page_size = max(page_size, 1)
    normalized_review_statuses = _normalize_review_statuses(review_statuses)
    filters = _filters(project_id, status, normalized_review_statuses, risk_level, keyword, target_type, trigger_type)

    total_stmt = select(func.count()).select_from(ReviewTask).join(Project, Project.id == ReviewTask.project_id)
    if filters:
        total_stmt = total_stmt.where(and_(*filters))
    total = db.scalar(total_stmt) or 0

    page_stmt = select(ReviewTask.id).join(Project, Project.id == ReviewTask.project_id)
    if filters:
        page_stmt = page_stmt.where(and_(*filters))
    task_ids = db.scalars(
        page_stmt.order_by(ReviewTask.created_at.desc()).limit(page_size).offset((page_no - 1) * page_size)
    ).all()
    if not task_ids:
        return page_response([], page_no, page_size, total)

    ordering = case({task_id: index for index, task_id in enumerate(task_ids)}, value=ReviewTask.id)
    code_quality_counts = {
        task_id: int(count or 0)
        for task_id, count in db.execute(
            select(CodeQualityReviewResult.task_id, func.coalesce(func.sum(CodeQualityReviewResult.finding_count), 0))
            .where(CodeQualityReviewResult.task_id.in_(task_ids))
            .group_by(CodeQualityReviewResult.task_id)
        ).all()
    }
    rows = db.execute(
        select(ReviewTask, Project, ReviewResult)
        .join(Project, Project.id == ReviewTask.project_id)
        .outerjoin(ReviewResult, ReviewResult.task_id == ReviewTask.id)
        .where(ReviewTask.id.in_(task_ids))
        .order_by(ordering)
    ).all()
    items = []
    for task, project, result in rows:
        list_risk_card = None
        reminder_card_enabled = (
            bool(result.reminder_card_enabled)
            if result is not None and result.reminder_card_enabled is not None
            else True
        )
        if result is not None and reminder_card_enabled:
            list_risk_card = _filter_risk_card_for_template(
                db,
                read_json(result.risk_card_json, None),
                read_json(result.change_analysis_json, None),
                result.template_code,
            )
        items.append(
            {
                "id": task.id,
                "projectId": task.project_id,
                "projectName": project.name,
                "triggerType": task.trigger_type,
                "externalSourceId": task.external_source_id,
                "externalUrl": task.external_url,
                "sourceBranch": task.source_branch,
                "targetBranch": task.target_branch,
                "authorName": task.author_name,
                "templateCode": task.template_code,
                "targetType": task.target_type,
                "targetTypes": read_json(task.target_types_json, []) if task.target_types_json else [],
                "codeQualityProfileCode": task.code_quality_profile_code,
                "status": task.status,
                "reviewStatus": task.review_status,
                "errorMessage": task.error_message,
                "riskLevel": list_risk_card.get("riskLevel") if isinstance(list_risk_card, dict) else task.risk_level,
                "riskItemCount": code_quality_counts.get(task.id, 0),
                "focusIndicators": (
                    list_risk_card.get("focusIndicators", [])
                    if isinstance(list_risk_card, dict)
                    else []
                ),
                "createdAt": format_datetime(task.created_at),
                "finishedAt": format_datetime(task.finished_at),
            }
        )
    return page_response(items, page_no, page_size, total)


def get_review_task_detail(db: Session, task_id: int) -> dict:
    ensure_review_task_status_schema(db)
    ensure_project_config_schema(db)
    row = db.execute(
        select(ReviewTask, Project, GitLabMergeRequestEvent, GitLabPushEvent)
        .join(Project, Project.id == ReviewTask.project_id)
        .outerjoin(GitLabMergeRequestEvent, GitLabMergeRequestEvent.task_id == ReviewTask.id)
        .outerjoin(GitLabPushEvent, GitLabPushEvent.task_id == ReviewTask.id)
        .where(ReviewTask.id == task_id)
    ).first()
    if row is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)

    task, project, mr_event, push_event = row
    event_action = mr_event.event_action if mr_event else ("push" if push_event else None)
    event_time = mr_event.event_time if mr_event else (push_event.event_time if push_event else None)
    changed_files_summary = (
        mr_event.changed_files_summary
        if mr_event
        else (push_event.changed_files_summary if push_event else None)
    )
    raw_payload = mr_event.raw_payload if mr_event else (push_event.raw_payload if push_event else None)
    mr_id = mr_event.mr_id if mr_event else task.external_source_id
    return {
        "id": task.id,
        "projectId": task.project_id,
        "projectName": project.name,
        "gitProjectId": project.git_project_id,
        "triggerType": task.trigger_type,
        "mrId": mr_id,
        "externalUrl": task.external_url,
        "sourceBranch": task.source_branch,
        "targetBranch": task.target_branch,
        "commitSha": task.commit_sha,
        "beforeSha": task.before_sha,
        "afterSha": task.after_sha,
        "authorName": task.author_name,
        "authorUsername": task.author_username,
        "templateCode": task.template_code,
        "targetType": task.target_type,
        "targetTypes": read_json(task.target_types_json, []) if task.target_types_json else [],
        "codeQualityProfileCode": task.code_quality_profile_code,
        "status": task.status,
        "reviewStatus": task.review_status,
        "errorMessage": task.error_message,
        "riskLevel": task.risk_level,
        "eventAction": event_action,
        "eventTime": format_datetime(event_time),
        "changedFilesSummary": read_json(changed_files_summary, None),
        "diffContextCapabilities": _diff_context_capabilities(task),
        "rawPayload": read_json(raw_payload, None),
        "createdAt": format_datetime(task.created_at),
        "updatedAt": format_datetime(task.updated_at),
    }


def _diff_context_capabilities(task: ReviewTask) -> dict[str, bool]:
    settings = get_settings()
    api_ready = bool(
        settings.gitlab_api_enabled
        and settings.gitlab_base_url.strip()
        and settings.gitlab_token.strip()
    )
    is_gitlab_task = task.trigger_type in {"GITLAB_MR_WEBHOOK", "GITLAB_PUSH_WEBHOOK"}
    head_ref = task.after_sha or task.commit_sha
    return {
        "diff": bool(api_ready and is_gitlab_task and task.before_sha and head_ref),
        "fixPreview": bool(api_ready and is_gitlab_task and head_ref),
    }


def get_review_task_result(db: Session, task_id: int) -> dict:
    result = db.scalars(select(ReviewResult).where(ReviewResult.task_id == task_id)).first()
    if result is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review result not found: {task_id}", 404)
    change_analysis = read_json(result.change_analysis_json, None)
    risk_card = _filter_risk_card_for_template(
        db,
        read_json(result.risk_card_json, None),
        change_analysis,
        result.template_code,
    )
    risk_card = attach_rule_feedbacks(db, task_id, risk_card)
    return {
        "taskId": result.task_id,
        "targetType": result.target_type,
        "reminderCardEnabled": bool(result.reminder_card_enabled) if result.reminder_card_enabled is not None else True,
        "riskLevel": risk_card.get("riskLevel") if isinstance(risk_card, dict) else result.risk_level,
        "riskItemCount": len(risk_card.get("riskItems", [])) if isinstance(risk_card, dict) else result.risk_item_count,
        "summary": risk_card.get("summary") if isinstance(risk_card, dict) else result.summary,
        "changeAnalysis": change_analysis,
        "riskCard": risk_card,
    }


def _filter_risk_card_for_template(
    db: Session,
    risk_card: dict | None,
    change_analysis: dict | None,
    template_code: str | None,
) -> dict | None:
    if not isinstance(risk_card, dict) or not template_code:
        return risk_card
    template = db.scalars(
        select(RuleTemplate)
        .where(RuleTemplate.status == "ENABLED", RuleTemplate.template_code == template_code)
        .order_by(RuleTemplate.version.desc())
        .limit(1)
    ).first()
    if template is None:
        return risk_card
    config = read_json(template.config_json, {})
    if not isinstance(config, dict):
        return risk_card
    focus_rule_codes = config.get("focusRuleCodes")
    recommended_checks = config.get("recommendedChecks")
    if not isinstance(focus_rule_codes, list) or not focus_rule_codes:
        return risk_card
    raw_allowed = {str(code or "").strip().upper() for code in focus_rule_codes if str(code or "").strip()}
    normalized_rule_codes = normalize_rule_codes(focus_rule_codes)
    normalized_allowed = set(normalized_rule_codes)
    if not raw_allowed and not normalized_allowed:
        return risk_card
    if isinstance(change_analysis, dict):
        return generate_risk_card(
            change_analysis,
            normalized_rule_codes,
            recommended_checks if isinstance(recommended_checks, list) else [],
        )
    clone = dict(risk_card)
    clone["riskItems"] = [
        item
        for item in risk_card.get("riskItems", [])
        if _item_rule_allowed(item, raw_allowed, normalized_allowed)
    ]
    clone["riskLevel"] = max(
        (item.get("riskLevel") or "LOW" for item in clone["riskItems"]),
        key=lambda level: RISK_WEIGHT.get(level, 0),
        default="LOW",
    )
    return clone


def _item_rule_allowed(item: dict, raw_allowed: set[str], normalized_allowed: set[str]) -> bool:
    rule_code = str(item.get("ruleCode") or "").strip().upper()
    if rule_code in raw_allowed:
        return True
    return rule_code in normalized_allowed and rule_code not in raw_allowed


def list_notifications(db: Session, task_id: int) -> list[dict]:
    if db.get(ReviewTask, task_id) is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)

    records = db.scalars(
        select(NotificationRecord)
        .where(NotificationRecord.task_id == task_id)
        .order_by(NotificationRecord.id.asc())
    ).all()
    return [
        {
            "id": record.id,
            "taskId": record.task_id,
            "resultId": record.result_id,
            "channel": record.channel,
            "target": record.target,
            "status": record.status,
            "requestDigest": record.request_digest,
            "responseBody": record.response_body,
            "errorMessage": record.error_message,
            "sentAt": format_datetime(record.sent_at),
            "createdAt": format_datetime(record.created_at),
        }
        for record in records
    ]


def create_review_task(
    db: Session,
    *,
    project_id: int,
    trigger_type: str,
    external_source_id: str | None,
    external_url: str | None,
    source_branch: str | None,
    target_branch: str | None,
    commit_sha: str | None,
    before_sha: str | None,
    after_sha: str | None,
    author_name: str | None,
    author_username: str | None,
    template_code: str,
    target_type: str | None = None,
    target_types: list[str] | None = None,
    code_quality_profile_code: str | None = None,
) -> ReviewTask:
    ensure_review_task_status_schema(db)
    now = datetime.now()
    task = ReviewTask(
        project_id=project_id,
        trigger_type=trigger_type,
        external_source_id=external_source_id,
        external_url=external_url,
        source_branch=source_branch,
        target_branch=target_branch,
        commit_sha=commit_sha,
        before_sha=before_sha,
        after_sha=after_sha,
        author_name=author_name,
        author_username=author_username,
        template_code=template_code,
        target_type=target_type,
        target_types_json=json.dumps(target_types or ([target_type] if target_type else []), ensure_ascii=False),
        code_quality_profile_code=code_quality_profile_code,
        status="RUNNING",
        review_status="NOT_TRIGGERED",
        started_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(task)
    db.flush()
    return task


def mark_task_success(task: ReviewTask, risk_level: str) -> None:
    now = datetime.now()
    task.status = "SUCCESS"
    if not task.review_status or task.review_status == "TASK_FAILED":
        task.review_status = "NOT_TRIGGERED"
    task.risk_level = risk_level
    task.error_message = None
    task.finished_at = now
    task.updated_at = now


def mark_task_failed(task: ReviewTask, error_message: str) -> None:
    now = datetime.now()
    task.status = "FAILED"
    task.review_status = "TASK_FAILED"
    task.error_message = (error_message or "")[:1024]
    task.finished_at = now
    task.updated_at = now


def ensure_review_task_status_schema(db: Session) -> None:
    connection = db.connection()
    inspector = inspect(connection)
    if not inspector.has_table("review_tasks"):
        return
    columns = {column["name"] for column in inspector.get_columns("review_tasks")}
    if "review_status" in columns:
        return
    db.execute(text("ALTER TABLE review_tasks ADD COLUMN review_status VARCHAR(32) NOT NULL DEFAULT 'NOT_TRIGGERED'"))
    existing_indexes = {index["name"] for index in inspect(connection).get_indexes("review_tasks")}
    if "idx_review_status_created" not in existing_indexes:
        db.execute(text("CREATE INDEX idx_review_status_created ON review_tasks (review_status, created_at)"))
    db.flush()
    if inspect(connection).has_table("code_quality_review_results"):
        for task_id in db.scalars(select(ReviewTask.id)).all():
            refresh_review_status(db, task_id, ensure_schema=False)
    db.flush()


def refresh_review_status(db: Session, task_id: int, *, ensure_schema: bool = True) -> str | None:
    if ensure_schema:
        ensure_review_task_status_schema(db)
    task = db.get(ReviewTask, task_id)
    if task is None:
        return None
    results = db.scalars(
        select(CodeQualityReviewResult).where(CodeQualityReviewResult.task_id == task_id)
    ).all()
    task.review_status = _derive_review_status(task, results)
    task.updated_at = datetime.now()
    db.flush()
    return task.review_status


def _derive_review_status(task: ReviewTask, results: list[CodeQualityReviewResult]) -> str:
    if not results:
        return "TASK_FAILED" if task.status == "FAILED" else "NOT_TRIGGERED"
    if any(result.status == "RUNNING" for result in results):
        return "REVIEWING"
    successful = [result for result in results if result.status == "SUCCESS"]
    if successful:
        highest = max((_result_risk_weight(result) for result in successful), default=0)
        return {1: "MINOR", 2: "MAJOR", 3: "CRITICAL"}.get(highest, "NO_RISK")
    if any(result.status == "FAILED" for result in results):
        return "REVIEW_FAILED"
    if any(result.status == "SKIPPED" for result in results):
        return "SKIPPED"
    return "NOT_TRIGGERED"


def _result_risk_weight(result: CodeQualityReviewResult) -> int:
    findings = read_json(result.findings_json, [])
    weights = [
        AI_FINDING_WEIGHT.get(str(item.get("severity") or "").strip().upper(), 0)
        for item in findings
        if isinstance(item, dict)
    ] if isinstance(findings, list) else []
    if weights and max(weights) > 0:
        return max(weights)
    return {"MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}.get(str(result.overall_level or "").upper(), 0)


def _normalize_review_statuses(values: list[str] | None) -> list[str]:
    return [
        status
        for status in dict.fromkeys(str(value or "").strip().upper() for value in values or [])
        if status in AI_REVIEW_STATUS_VALUES
    ]


def save_review_result(
    db: Session,
    *,
    task: ReviewTask,
    analysis: dict,
    risk_card: dict,
    reminder_card_enabled: bool = True,
) -> ReviewResult:
    now = datetime.now()
    result = ReviewResult(
        task_id=task.id,
        project_id=task.project_id,
        template_code=task.template_code,
        target_type=task.target_type,
        reminder_card_enabled=reminder_card_enabled,
        risk_level=risk_card["riskLevel"],
        risk_item_count=len(risk_card["riskItems"]),
        change_analysis_json=json.dumps(analysis, ensure_ascii=False),
        risk_card_json=json.dumps(risk_card, ensure_ascii=False),
        summary=risk_card["summary"],
        created_at=now,
        updated_at=now,
    )
    db.add(result)
    db.flush()
    return result


def save_notification_record(
    db: Session,
    *,
    task_id: int,
    result_id: int | None,
    target: str | None,
    status: str,
    request_digest: str | None = None,
    response_body: str | None = None,
    error_message: str | None = None,
) -> NotificationRecord:
    now = datetime.now()
    record = NotificationRecord(
        task_id=task_id,
        result_id=result_id,
        channel="DINGTALK",
        target=target,
        status=status,
        request_digest=request_digest,
        response_body=response_body,
        error_message=error_message,
        sent_at=now if status in {"SUCCESS", "FAILED"} else None,
        created_at=now,
        updated_at=now,
    )
    db.add(record)
    db.flush()
    return record


def save_notification_records(
    db: Session,
    *,
    task_id: int,
    result_id: int | None,
    notifications: list[dict],
) -> list[NotificationRecord]:
    return [
        save_notification_record(
            db,
            task_id=task_id,
            result_id=result_id,
            target=item.get("target"),
            status=item.get("status") or "SKIPPED",
            request_digest=item.get("requestDigest"),
            response_body=item.get("responseBody"),
            error_message=item.get("errorMessage"),
        )
        for item in notifications
    ]
