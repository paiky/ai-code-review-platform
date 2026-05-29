from __future__ import annotations

from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.change_analysis.service import analyze_changes
from app.code_quality.models import (
    CodeQualityFixPreview,
    CodeQualityPushReviewGateDecision,
    CodeQualityReviewProgressEvent,
    CodeQualityReviewResult,
    CodeQualitySchedulerJob,
)
from app.code_quality.repository import get_settings_record
from app.core.errors import AppError
from app.notification.service import dingtalk_skipped_result
from app.project_integration.repository import find_project_by_id, resolve_project_target_config
from app.project_integration.service import handle_gitlab_webhook, process_existing_review_task
from app.project_integration.models import GitLabMergeRequestEvent, GitLabPushEvent
from app.review_record.models import NotificationRecord, ReviewResult, ReviewTask
from app.review_record.repository import (
    create_review_task,
    get_review_task_detail,
    mark_task_failed,
    mark_task_success,
    save_notification_record,
    save_review_result,
)
from app.risk_engine.service import generate_risk_card
from app.rule_template.repository import get_enabled_template


def create_manual_review(db: Session, request: dict[str, Any]) -> dict:
    project_id = request.get("projectId")
    if project_id is None:
        raise AppError("VALIDATION_ERROR", "projectId is required", 400)
    project = find_project_by_id(db, int(project_id))
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {project_id}", 404)

    changed_files = request.get("changedFiles") or []
    target_config = resolve_project_target_config(
        db,
        project,
        changed_files,
        request.get("targetType"),
        request.get("targetTypes"),
    )
    template_code = request.get("templateCode") or target_config["templateCode"]
    profile_code = request.get("profileCode") or target_config["profileCode"]
    template = get_enabled_template(db, template_code)
    task = create_review_task(
        db,
        project_id=project.id,
        trigger_type="MANUAL",
        external_source_id=None,
        external_url=None,
        source_branch=request.get("sourceBranch"),
        target_branch=request.get("targetBranch"),
        commit_sha=None,
        before_sha=None,
        after_sha=None,
        author_name=request.get("authorName"),
        author_username=request.get("authorUsername"),
        template_code=template_code,
        target_type=target_config["targetType"],
        target_types=target_config["targetTypes"],
        code_quality_profile_code=profile_code,
    )

    try:
        analysis = analyze_changes(changed_files, request.get("diffText"))
        rule_codes = template.get("focusRuleCodes") or template.get("enabledRuleCodes", [])
        risk_card = generate_risk_card(
            analysis,
            rule_codes,
            template.get("recommendedChecks", []),
        )
        result = save_review_result(
            db,
            task=task,
            analysis=analysis,
            risk_card=risk_card,
            reminder_card_enabled=target_config["reminderCardEnabled"],
        )
        mark_task_success(task, risk_card["riskLevel"])
        notification = dingtalk_skipped_result(db, get_settings_record(db).dingtalk_notification_enabled)
        save_notification_record(
            db,
            task_id=task.id,
            result_id=result.id,
            target=notification["target"],
            status=notification["status"],
            request_digest=notification["requestDigest"],
            response_body=notification["responseBody"],
            error_message=notification["errorMessage"],
        )
        db.commit()
        return {
            "taskId": task.id,
            "status": "SUCCESS",
            "templateCode": template_code,
            "targetType": target_config["targetType"],
            "targetTypes": target_config["targetTypes"],
            "profileCode": profile_code,
            "reminderCardEnabled": target_config["reminderCardEnabled"],
            "riskLevel": risk_card["riskLevel"],
        }
    except Exception as exception:
        mark_task_failed(task, str(exception))
        db.commit()
        raise


def rerun_review_task(db: Session, source_task_id: int) -> dict:
    source = get_review_task_detail(db, source_task_id)
    if source["triggerType"] not in {"GITLAB_MR_WEBHOOK", "GITLAB_PUSH_WEBHOOK"}:
        raise AppError("BAD_REQUEST", "Only GitLab webhook tasks can be rerun", 400)
    raw_payload = source.get("rawPayload")
    if not isinstance(raw_payload, dict):
        raise AppError("BAD_REQUEST", "Source task raw payload is missing", 400)
    response = handle_gitlab_webhook(db, None, raw_payload)
    return {
        "sourceTaskId": source_task_id,
        "taskId": response.get("taskId"),
        "status": response.get("status"),
        "triggerType": source["triggerType"],
    }


def rerun_review_task_in_place(db: Session, task_id: int) -> dict:
    task = db.get(ReviewTask, task_id)
    if task is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)
    if task.trigger_type not in {"GITLAB_MR_WEBHOOK", "GITLAB_PUSH_WEBHOOK"}:
        raise AppError("BAD_REQUEST", "Only GitLab webhook tasks can be rerun in place", 400)
    changed_files = _changed_files_for_task(db, task)
    _reset_task_for_in_place_rerun(db, task)
    try:
        result = process_existing_review_task(db, task, changed_files, None)
        db.commit()
        return {
            "sourceTaskId": task_id,
            "taskId": task_id,
            "status": "SUCCESS",
            "triggerType": task.trigger_type,
            "riskLevel": result["riskCard"]["riskLevel"],
            "mode": "IN_PLACE",
        }
    except Exception as exception:
        mark_task_failed(task, str(exception))
        db.commit()
        raise


def _changed_files_for_task(db: Session, task: ReviewTask) -> list[dict[str, Any]]:
    event_record = None
    if task.trigger_type == "GITLAB_MR_WEBHOOK":
        event_record = db.query(GitLabMergeRequestEvent).filter_by(task_id=task.id).first()
    elif task.trigger_type == "GITLAB_PUSH_WEBHOOK":
        event_record = db.query(GitLabPushEvent).filter_by(task_id=task.id).first()
    summary = getattr(event_record, "changed_files_summary", None)
    if not summary:
        raise AppError("BAD_REQUEST", "Source task changed files summary is missing", 400)
    import json

    parsed = json.loads(summary)
    files = parsed.get("files") if isinstance(parsed, dict) else None
    if not isinstance(files, list) or not files:
        raise AppError("BAD_REQUEST", "Source task changed files are missing", 400)
    return files


def _reset_task_for_in_place_rerun(db: Session, task: ReviewTask) -> None:
    from datetime import datetime

    db.execute(delete(CodeQualitySchedulerJob).where(CodeQualitySchedulerJob.task_id == task.id))
    db.execute(delete(CodeQualityFixPreview).where(CodeQualityFixPreview.task_id == task.id))
    db.execute(delete(CodeQualityReviewProgressEvent).where(CodeQualityReviewProgressEvent.task_id == task.id))
    db.execute(delete(CodeQualityReviewResult).where(CodeQualityReviewResult.task_id == task.id))
    db.execute(delete(CodeQualityPushReviewGateDecision).where(CodeQualityPushReviewGateDecision.task_id == task.id))
    db.execute(delete(NotificationRecord).where(NotificationRecord.task_id == task.id))
    db.execute(delete(ReviewResult).where(ReviewResult.task_id == task.id))
    now = datetime.now()
    task.status = "RUNNING"
    task.risk_level = None
    task.error_message = None
    task.started_at = now
    task.finished_at = None
    task.updated_at = now
    db.flush()
