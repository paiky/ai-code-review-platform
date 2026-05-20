import json
from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.json_utils import format_datetime, page_response, read_json
from app.project_integration.models import GitLabMergeRequestEvent, GitLabPushEvent, Project
from app.review_record.models import NotificationRecord, ReviewResult, ReviewTask


def _focus_indicators(risk_card_json: str | None) -> list:
    risk_card = read_json(risk_card_json, {})
    if isinstance(risk_card, dict) and isinstance(risk_card.get("focusIndicators"), list):
        return risk_card["focusIndicators"]
    return []


def _filters(project_id: int | None, status: str | None, risk_level: str | None, keyword: str | None):
    clauses = []
    if project_id is not None:
        clauses.append(ReviewTask.project_id == project_id)
    if status:
        clauses.append(ReviewTask.status == status)
    if risk_level:
        clauses.append(ReviewTask.risk_level == risk_level)
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
    risk_level: str | None,
    keyword: str | None,
    page_no: int,
    page_size: int,
) -> dict:
    page_no = max(page_no, 1)
    page_size = max(page_size, 1)
    filters = _filters(project_id, status, risk_level, keyword)

    base = select(ReviewTask, Project, ReviewResult).join(Project, Project.id == ReviewTask.project_id).outerjoin(
        ReviewResult, ReviewResult.task_id == ReviewTask.id
    )
    if filters:
        base = base.where(and_(*filters))

    total_stmt = select(func.count()).select_from(ReviewTask).join(Project, Project.id == ReviewTask.project_id)
    if filters:
        total_stmt = total_stmt.where(and_(*filters))
    total = db.scalar(total_stmt) or 0

    rows = db.execute(
        base.order_by(ReviewTask.created_at.desc()).limit(page_size).offset((page_no - 1) * page_size)
    ).all()
    items = []
    for task, project, result in rows:
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
                "status": task.status,
                "riskLevel": task.risk_level,
                "riskItemCount": result.risk_item_count if result else None,
                "focusIndicators": _focus_indicators(result.risk_card_json if result else None),
                "createdAt": format_datetime(task.created_at),
                "finishedAt": format_datetime(task.finished_at),
            }
        )
    return page_response(items, page_no, page_size, total)


def get_review_task_detail(db: Session, task_id: int) -> dict:
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
        "authorName": task.author_name,
        "authorUsername": task.author_username,
        "templateCode": task.template_code,
        "status": task.status,
        "riskLevel": task.risk_level,
        "eventAction": event_action,
        "eventTime": format_datetime(event_time),
        "changedFilesSummary": read_json(changed_files_summary, None),
        "rawPayload": read_json(raw_payload, None),
        "createdAt": format_datetime(task.created_at),
        "updatedAt": format_datetime(task.updated_at),
    }


def get_review_task_result(db: Session, task_id: int) -> dict:
    result = db.scalars(select(ReviewResult).where(ReviewResult.task_id == task_id)).first()
    if result is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review result not found: {task_id}", 404)
    return {
        "taskId": result.task_id,
        "riskLevel": result.risk_level,
        "riskItemCount": result.risk_item_count,
        "summary": result.summary,
        "changeAnalysis": read_json(result.change_analysis_json, None),
        "riskCard": read_json(result.risk_card_json, None),
    }


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
) -> ReviewTask:
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
        status="RUNNING",
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
    task.risk_level = risk_level
    task.error_message = None
    task.finished_at = now
    task.updated_at = now


def mark_task_failed(task: ReviewTask, error_message: str) -> None:
    now = datetime.now()
    task.status = "FAILED"
    task.error_message = (error_message or "")[:1024]
    task.finished_at = now
    task.updated_at = now


def save_review_result(
    db: Session,
    *,
    task: ReviewTask,
    analysis: dict,
    risk_card: dict,
) -> ReviewResult:
    now = datetime.now()
    result = ReviewResult(
        task_id=task.id,
        project_id=task.project_id,
        template_code=task.template_code,
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
