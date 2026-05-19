from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.change_analysis.service import analyze_changes
from app.core.errors import AppError
from app.notification.service import dingtalk_skipped_result
from app.code_quality.repository import get_settings_record
from app.project_integration.repository import find_project_by_id
from app.project_integration.service import handle_merge_request_webhook
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

    template_code = request.get("templateCode") or project.default_template_code
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
    )

    try:
        analysis = analyze_changes(request.get("changedFiles") or [], request.get("diffText"))
        risk_card = generate_risk_card(
            analysis,
            template.get("enabledRuleCodes", []),
            template.get("recommendedChecks", []),
        )
        result = save_review_result(db, task=task, analysis=analysis, risk_card=risk_card)
        mark_task_success(task, risk_card["riskLevel"])
        notification = dingtalk_skipped_result(get_settings_record(db).dingtalk_notification_enabled)
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
            "riskLevel": risk_card["riskLevel"],
        }
    except Exception as exception:
        mark_task_failed(task, str(exception))
        db.commit()
        raise


def rerun_review_task(db: Session, source_task_id: int) -> dict:
    source = get_review_task_detail(db, source_task_id)
    if source["triggerType"] != "GITLAB_MR_WEBHOOK":
        raise AppError("BAD_REQUEST", "Only GitLab MR webhook tasks can be rerun in stage 3", 400)
    raw_payload = source.get("rawPayload")
    if not isinstance(raw_payload, dict):
        raise AppError("BAD_REQUEST", "Source task raw payload is missing", 400)
    response = handle_merge_request_webhook(db, raw_payload)
    return {
        "sourceTaskId": source_task_id,
        "taskId": response.get("taskId"),
        "status": response.get("status"),
        "triggerType": source["triggerType"],
    }
