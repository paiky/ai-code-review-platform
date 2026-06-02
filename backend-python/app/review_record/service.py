from __future__ import annotations

from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.change_analysis.service import analyze_changes, summarize_changes_without_rule_matching
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
from app.project_integration.models import GitLabMergeRequestEvent, GitLabPushEvent, Project
from app.project_integration import gitlab_client
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
        reminder_card_enabled = target_config["reminderCardEnabled"]
        analysis = (
            analyze_changes(changed_files, request.get("diffText"))
            if reminder_card_enabled
            else summarize_changes_without_rule_matching(changed_files, request.get("diffText"))
        )
        rule_codes = template.get("focusRuleCodes") or template.get("enabledRuleCodes", [])
        risk_card = generate_risk_card(
            analysis,
            rule_codes if reminder_card_enabled else [],
            template.get("recommendedChecks", []),
        )
        result = save_review_result(
            db,
            task=task,
            analysis=analysis,
            risk_card=risk_card,
            reminder_card_enabled=reminder_card_enabled,
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
            "reminderCardEnabled": reminder_card_enabled,
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


def get_diff_context(db: Session, task_id: int, file_path: str, view_type: str = "DIFF") -> dict[str, Any]:
    task = db.get(ReviewTask, task_id)
    if task is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)
    if task.trigger_type not in {"GITLAB_MR_WEBHOOK", "GITLAB_PUSH_WEBHOOK"}:
        raise AppError("BAD_REQUEST", "Diff context is only available for GitLab webhook tasks", 400)
    project = db.get(Project, task.project_id)
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {task.project_id}", 404)
    normalized_view_type = str(view_type or "DIFF").strip().upper()
    if normalized_view_type not in {"DIFF", "FIX_PREVIEW"}:
        raise AppError("VALIDATION_ERROR", f"Unsupported viewType: {view_type}", 400)
    normalized_path = _normalize_file_path(file_path)
    if not normalized_path:
        raise AppError("VALIDATION_ERROR", "filePath is required", 400)
    changed_file = _find_changed_file(_changed_files_for_task(db, task), normalized_path)
    if changed_file is None:
        raise AppError("BAD_REQUEST", f"File path is not part of task changes: {file_path}", 400)
    if normalized_view_type == "FIX_PREVIEW":
        return _fix_preview_context(task, project.git_project_id, changed_file, normalized_path)
    return _diff_context(task, project.git_project_id, changed_file, normalized_path)


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


def _find_changed_file(changed_files: list[dict[str, Any]], requested_path: str) -> dict[str, Any] | None:
    for changed_file in changed_files:
        if not isinstance(changed_file, dict):
            continue
        candidates = {
            _normalize_file_path(changed_file.get("path")),
            _normalize_file_path(changed_file.get("oldPath")),
            _normalize_file_path(changed_file.get("newPath")),
        }
        if requested_path in candidates:
            return changed_file
    return None


def _normalize_file_path(value: Any) -> str:
    normalized = str(value or "").strip().replace("\\", "/").lstrip("/")
    if normalized.startswith("a/") or normalized.startswith("b/"):
        normalized = normalized[2:]
    return normalized


def _changed_file_is(changed_file: dict[str, Any], flag: str, change_type: str) -> bool:
    return bool(changed_file.get(flag) or str(changed_file.get("changeType") or "").upper() == change_type)


def _diff_context(
    task: ReviewTask,
    git_project_id: str,
    changed_file: dict[str, Any],
    requested_path: str,
) -> dict[str, Any]:
    left = None
    right = None
    if not _changed_file_is(changed_file, "newFile", "ADDED"):
        if not task.before_sha:
            raise AppError("BAD_REQUEST", "Diff context base ref is unavailable for this task", 400)
        left_path = _normalize_file_path(changed_file.get("oldPath") or changed_file.get("path") or requested_path)
        left = _source_side(git_project_id, left_path, task.before_sha)
    if not _changed_file_is(changed_file, "deletedFile", "DELETED"):
        head_ref = task.after_sha or task.commit_sha
        if not head_ref:
            raise AppError("BAD_REQUEST", "Diff context head ref is unavailable for this task", 400)
        right_path = _normalize_file_path(changed_file.get("newPath") or changed_file.get("path") or requested_path)
        right = _source_side(git_project_id, right_path, head_ref)
    return _context_payload(task, requested_path, "DIFF", left, right)


def _fix_preview_context(
    task: ReviewTask,
    git_project_id: str,
    changed_file: dict[str, Any],
    requested_path: str,
) -> dict[str, Any]:
    if _changed_file_is(changed_file, "deletedFile", "DELETED"):
        raise AppError("BAD_REQUEST", "Fix preview context is unavailable for deleted files", 400)
    head_ref = task.after_sha or task.commit_sha
    if not head_ref:
        raise AppError("BAD_REQUEST", "Fix preview context head ref is unavailable for this task", 400)
    current_path = _normalize_file_path(changed_file.get("newPath") or changed_file.get("path") or requested_path)
    return _context_payload(task, requested_path, "FIX_PREVIEW", _source_side(git_project_id, current_path, head_ref), None)


def _source_side(git_project_id: str, file_path: str, ref: str) -> dict[str, Any]:
    return {
        "path": file_path,
        "ref": ref,
        "lines": gitlab_client.get_raw_file(git_project_id, file_path, ref),
    }


def _context_payload(
    task: ReviewTask,
    file_path: str,
    view_type: str,
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "taskId": task.id,
        "filePath": file_path,
        "viewType": view_type,
        "language": _language_for_path(file_path),
        "left": left,
        "right": right,
    }


def _language_for_path(file_path: str) -> str:
    suffix = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
    return {
        "java": "java",
        "py": "python",
        "js": "javascript",
        "jsx": "jsx",
        "ts": "typescript",
        "tsx": "tsx",
        "sql": "sql",
        "xml": "xml",
        "json": "json",
        "yml": "yaml",
        "yaml": "yaml",
        "css": "css",
        "scss": "css",
        "sh": "shell",
        "bash": "shell",
        "md": "markdown",
    }.get(suffix, "text")


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
    task.review_status = "NOT_TRIGGERED"
    task.risk_level = None
    task.error_message = None
    task.started_at = now
    task.finished_at = None
    task.updated_at = now
    db.flush()
