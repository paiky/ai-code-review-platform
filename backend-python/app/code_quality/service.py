from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import os
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.code_quality import prompt
from app.code_quality.providers import run_provider
from app.code_quality.repository import (
    append_progress,
    delete_progress,
    find_result_response,
    get_profile,
    get_provider,
    get_settings_record,
    list_progress,
    list_provider_responses,
    mark_stale_running_as_failed,
    reset_default_prompt,
    save_result,
    set_default_provider,
    settings_to_dict,
    update_profile,
    update_provider,
    update_settings_record,
)
from app.core.database import SessionLocal
from app.core.errors import AppError
from app.core.json_utils import read_json
from app.notification.repository import list_webhooks
from app.project_integration.models import GitLabMergeRequestEvent, GitLabPushEvent, Project
from app.project_integration.repository import find_project_by_id
from app.notification.service import send_review_summary, send_test_notification
from app.review_record.models import ReviewTask
from app.review_record.repository import (
    create_review_task,
    mark_task_failed,
    mark_task_success,
    save_notification_records,
)


_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="code-quality-review")


def create_manual_review(db: Session, request: dict[str, Any]) -> dict[str, Any]:
    response = enqueue_manual_review(db, request)
    task_id = response["taskId"]
    if _inline_enabled():
        result = run_manual_review_now(db, task_id, request)
        db.commit()
        return {
            "taskId": task_id,
            "status": result["status"],
            "profileCode": response["profileCode"],
            "provider": response["provider"],
            "overallLevel": result.get("overallLevel"),
            "findingCount": len(result.get("findings") or []),
        }
    _executor.submit(run_manual_review_job, task_id, dict(request))
    return response


def enqueue_manual_review(db: Session, request: dict[str, Any]) -> dict[str, Any]:
    if not _enabled():
        raise AppError("BAD_REQUEST", "Code quality review is disabled", 400)
    project_id = request.get("projectId")
    if project_id is None:
        raise AppError("VALIDATION_ERROR", "projectId is required", 400)
    project = find_project_by_id(db, int(project_id))
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {project_id}", 404)
    profile = _resolve_profile(db, request.get("profileCode"), project)
    if not profile.enabled or not profile.trigger_on_manual:
        raise AppError(
            "BAD_REQUEST",
            f"Code quality review profile does not allow manual trigger: {profile.profile_code}",
            400,
        )
    provider = _resolve_provider(db, project, profile)
    task = create_review_task(
        db,
        project_id=project.id,
        trigger_type="CODE_QUALITY_MANUAL",
        external_source_id=None,
        external_url=None,
        source_branch=None,
        target_branch=None,
        commit_sha=request.get("commitSha"),
        before_sha=None,
        after_sha=None,
        author_name=None,
        author_username=None,
        template_code=profile.profile_code,
    )
    delete_progress(db, task.id)
    append_progress(
        db,
        task.id,
        "QUEUED",
        "INFO",
        "手动 AI Review 已创建",
        f"provider={provider.provider_code}, profile={profile.profile_code}",
    )
    review_request = _build_review_request(profile, request)
    save_result(
        db,
        task_id=task.id,
        project_id=project.id,
        profile_code=profile.profile_code,
        provider=provider.provider_code,
        model=review_request.get("model") or provider.model_name,
        result={
            "status": "RUNNING",
            "overallLevel": None,
            "summary": None,
            "findings": [],
            "rawOutput": None,
            "exitCode": None,
            "errorMessage": None,
            "startedAt": None,
            "finishedAt": None,
        },
    )
    db.commit()
    return {
        "taskId": task.id,
        "status": "RUNNING",
        "profileCode": profile.profile_code,
        "provider": provider.provider_code,
        "overallLevel": None,
        "findingCount": 0,
    }


def run_manual_review_job(task_id: int, request: dict[str, Any]) -> None:
    db = SessionLocal()
    try:
        run_manual_review_now(db, task_id, request)
        db.commit()
    except Exception as exception:
        task = db.get(ReviewTask, task_id)
        if task is not None:
            mark_task_failed(task, str(exception))
            append_progress(db, task_id, "FAILED", "ERROR", "手动 AI Review 后台执行失败", str(exception))
        db.commit()
    finally:
        db.close()


def run_manual_review_now(db: Session, task_id: int, request: dict[str, Any]) -> dict[str, Any]:
    task = db.get(ReviewTask, task_id)
    if task is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)
    project = find_project_by_id(db, task.project_id)
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {task.project_id}", 404)
    profile = _resolve_profile(db, request.get("profileCode"), project)
    provider = _resolve_provider(db, project, profile)
    review_request = _build_review_request(profile, request)
    result = _run_review(db, task.id, project, profile, provider, review_request)
    if result["status"] == "SUCCESS":
        mark_task_success(task, result.get("overallLevel") or "LOW")
    else:
        mark_task_failed(task, result.get("errorMessage") or "AI Review failed")
    return result


def retry_review_task(db: Session, task_id: int) -> dict[str, Any]:
    response = enqueue_retry_review(db, task_id)
    if _inline_enabled():
        result = run_retry_review_now(db, task_id)
        db.commit()
        return {
            "taskId": task_id,
            "status": result["status"],
            "profileCode": response["profileCode"],
            "provider": response["provider"],
            "overallLevel": result.get("overallLevel"),
            "findingCount": len(result.get("findings") or []),
        }
    _executor.submit(run_retry_review_job, task_id)
    return response


def enqueue_retry_review(db: Session, task_id: int) -> dict[str, Any]:
    if not _enabled():
        raise AppError("BAD_REQUEST", "Code quality review is disabled", 400)
    task = db.get(ReviewTask, task_id)
    if task is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)
    if task.trigger_type not in {"GITLAB_MR_WEBHOOK", "GITLAB_PUSH_WEBHOOK"}:
        raise AppError("BAD_REQUEST", f"Only GitLab webhook tasks can retry AI Review: {task_id}", 400)
    project = find_project_by_id(db, task.project_id)
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {task.project_id}", 404)
    profile = _resolve_profile(db, None, project)
    provider = _resolve_provider(db, project, profile)
    request = _request_from_task_event(db, task, profile)
    delete_progress(db, task.id)
    append_progress(
        db,
        task.id,
        "QUEUED",
        "INFO",
        "AI Review 已进入执行队列",
        f"provider={provider.provider_code}, profile={profile.profile_code}",
    )
    save_result(
        db,
        task_id=task.id,
        project_id=project.id,
        profile_code=profile.profile_code,
        provider=provider.provider_code,
        model=request.get("model") or provider.model_name,
        result={
            "status": "RUNNING",
            "overallLevel": None,
            "summary": None,
            "findings": [],
            "rawOutput": None,
            "exitCode": None,
            "errorMessage": None,
            "startedAt": None,
            "finishedAt": None,
        },
    )
    db.commit()
    return {
        "taskId": task.id,
        "status": "RUNNING",
        "profileCode": profile.profile_code,
        "provider": provider.provider_code,
        "overallLevel": None,
        "findingCount": 0,
    }


def run_retry_review_job(task_id: int) -> None:
    db = SessionLocal()
    try:
        run_retry_review_now(db, task_id)
        db.commit()
    except Exception as exception:
        task = db.get(ReviewTask, task_id)
        if task is not None:
            append_progress(db, task_id, "FAILED", "ERROR", "AI Review 后台执行失败", str(exception))
        db.commit()
    finally:
        db.close()


def run_retry_review_now(db: Session, task_id: int) -> dict[str, Any]:
    task = db.get(ReviewTask, task_id)
    if task is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)
    project = find_project_by_id(db, task.project_id)
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {task.project_id}", 404)
    profile = _resolve_profile(db, None, project)
    provider = _resolve_provider(db, project, profile)
    request = _request_from_task_event(db, task, profile)
    return _run_review(db, task.id, project, profile, provider, request)


def trigger_auto_review(
    db: Session,
    *,
    task_id: int,
    project: Project,
    changed_files: list[dict[str, Any]],
    diff_text: str | None = None,
    rule_result_id: int | None = None,
    risk_card: dict | None = None,
    focus_change_types: list[str] | None = None,
    focus_rule_codes: list[str] | None = None,
    notification_context: dict | None = None,
) -> bool:
    if not _enabled():
        return False
    settings = get_settings_record(db)
    if not settings.mr_auto_review_enabled:
        return False
    task = db.get(ReviewTask, task_id)
    if task is None or task.trigger_type != "GITLAB_MR_WEBHOOK":
        return False
    if find_result_response(db, task_id) is not None:
        return False
    profile = _resolve_profile(db, None, project)
    if not profile.enabled or not profile.trigger_on_mr:
        return False
    provider = _resolve_provider(db, project, profile)
    request = _build_review_request(
        profile,
        {
            "mode": "DIFF_TEXT",
            "baseRef": task.target_branch,
            "commitSha": task.commit_sha,
            "title": f"{task.trigger_type} {task.external_source_id or ''}".strip(),
            "diffText": diff_text or _diff_text(changed_files),
            "changedFiles": [file.get("path") for file in changed_files if file.get("path")],
        },
    )
    delete_progress(db, task.id)
    append_progress(
        db,
        task.id,
        "QUEUED",
        "INFO",
        "AI Review 已进入执行队列",
        f"provider={provider.provider_code}, profile={profile.profile_code}",
    )
    save_result(
        db,
        task_id=task.id,
        project_id=project.id,
        profile_code=profile.profile_code,
        provider=provider.provider_code,
        model=request.get("model") or provider.model_name,
        result={
            "status": "RUNNING",
            "overallLevel": None,
            "summary": None,
            "findings": [],
            "rawOutput": None,
            "exitCode": None,
            "errorMessage": None,
            "startedAt": None,
            "finishedAt": None,
        },
    )
    if _inline_enabled():
        result = _run_review(db, task.id, project, profile, provider, request)
        _send_auto_review_notification(
            db,
            task.id,
            result,
            rule_result_id,
            risk_card,
            focus_change_types,
            focus_rule_codes,
            notification_context,
        )
    else:
        _executor.submit(
            run_auto_review_job,
            task.id,
            project.id,
            profile.profile_code,
            provider.provider_code,
            request,
            rule_result_id,
            risk_card,
            focus_change_types or [],
            focus_rule_codes or [],
            notification_context or {},
        )
    return True


def run_auto_review_job(
    task_id: int,
    project_id: int,
    profile_code: str,
    provider_code: str,
    request: dict[str, Any],
    rule_result_id: int | None,
    risk_card: dict | None,
    focus_change_types: list[str],
    focus_rule_codes: list[str],
    notification_context: dict,
) -> None:
    db = SessionLocal()
    try:
        project = find_project_by_id(db, project_id)
        if project is None:
            append_progress(db, task_id, "FAILED", "ERROR", "AI Review 后台执行失败", f"Project not found: {project_id}")
            db.commit()
            return
        profile = get_profile(db, profile_code)
        provider = get_provider(db, provider_code)
        result = _run_review(db, task_id, project, profile, provider, request)
        _send_auto_review_notification(
            db,
            task_id,
            result,
            rule_result_id,
            risk_card,
            focus_change_types,
            focus_rule_codes,
            notification_context,
        )
        db.commit()
    except Exception as exception:
        append_progress(db, task_id, "FAILED", "ERROR", "AI Review 后台执行失败", str(exception))
        db.commit()
    finally:
        db.close()


def get_settings_response(db: Session) -> dict[str, Any]:
    return settings_to_dict(get_settings_record(db))


def update_settings(db: Session, request: dict[str, Any]) -> dict[str, Any]:
    test_candidates = []
    if isinstance(request.get("dingtalkWebhooks"), list):
        existing_records = {record.id: record for record in list_webhooks(db)}
        for item in request["dingtalkWebhooks"]:
            if not isinstance(item, dict):
                continue
            enabled = bool(item.get("enabled", True))
            name = str(item.get("name") or "").strip()
            webhook_url = str(item.get("webhookUrl") or "").strip()
            record_id = item.get("id")
            if not enabled or not webhook_url:
                continue
            if record_id is None:
                test_candidates.append({"name": name, "webhookUrl": webhook_url})
                continue
            try:
                numeric_id = int(record_id)
            except (TypeError, ValueError):
                continue
            existing = existing_records.get(numeric_id)
            if existing is None:
                continue
            was_enabled = bool(existing.enabled) and existing.status == "ENABLED"
            url_changed = existing.webhook_url.strip() != webhook_url
            if not was_enabled or url_changed:
                test_candidates.append({"name": name, "webhookUrl": webhook_url})
    response = update_settings_record(db, request)
    db.commit()
    if test_candidates:
        saved_by_url = {
            str(item.get("webhookUrl") or "").strip(): item
            for item in response.get("dingtalkWebhooks") or []
            if str(item.get("webhookUrl") or "").strip()
        }
        test_results = []
        seen_urls: set[str] = set()
        for item in test_candidates:
            normalized_url = item["webhookUrl"].lower()
            if normalized_url in seen_urls:
                continue
            seen_urls.add(normalized_url)
            saved = saved_by_url.get(item["webhookUrl"])
            if not saved:
                continue
            result = send_test_notification(saved["webhookUrl"], saved.get("name"))
            test_results.append(
                {
                    "id": saved.get("id"),
                    "name": saved.get("name"),
                    "webhookUrl": saved.get("webhookUrl"),
                    "status": result.get("status"),
                    "errorMessage": result.get("errorMessage"),
                }
            )
        response["webhookTestResults"] = test_results
    return response


def get_profile_response(db: Session, profile_code: str) -> dict[str, Any]:
    from app.code_quality.repository import profile_to_dict

    return profile_to_dict(get_profile(db, profile_code))


def update_profile_response(db: Session, profile_code: str, request: dict[str, Any]) -> dict[str, Any]:
    response = update_profile(db, profile_code, request)
    db.commit()
    return response


def reset_default_prompt_response(db: Session, profile_code: str) -> dict[str, Any]:
    response = reset_default_prompt(db, profile_code)
    db.commit()
    return response


def rendered_prompt(db: Session, profile_code: str) -> dict[str, Any]:
    profile = get_profile(db, profile_code)
    provider_code = profile.provider_code or get_settings_record(db).default_provider_code
    provider = get_provider(db, provider_code)
    request = _build_review_request(
        profile,
        {
            "mode": "DIFF_TEXT",
            "baseRef": "origin/main",
            "title": "Agent Prompt preview",
            "diffText": (
                "diff --git a/src/main/java/com/demo/OrderService.java "
                "b/src/main/java/com/demo/OrderService.java\n+ public void createOrder() {}"
            ),
            "changedFiles": ["src/main/java/com/demo/OrderService.java"],
        },
    )
    rendered = prompt.render_instructions(request)
    return {
        "profileCode": profile.profile_code,
        "provider": provider.provider_code,
        "model": request.get("model") or provider.model_name,
        "prompt": rendered,
        "promptHash": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
        "promptLength": len(rendered),
    }


def list_provider_response(db: Session) -> list[dict[str, Any]]:
    return list_provider_responses(db)


def update_provider_response(db: Session, provider_code: str, request: dict[str, Any]) -> list[dict[str, Any]]:
    response = update_provider(db, provider_code, request)
    db.commit()
    return response


def set_default_provider_response(db: Session, provider_code: str) -> dict[str, Any]:
    response = set_default_provider(db, provider_code)
    db.commit()
    return response


def get_result_response(db: Session, task_id: int) -> dict[str, Any]:
    result = find_result_response(db, task_id)
    if result is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Code quality review result not found: {task_id}", 404)
    return result


def get_progress_response(db: Session, task_id: int) -> list[dict[str, Any]]:
    if db.get(ReviewTask, task_id) is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)
    return list_progress(db, task_id)


def recover_stale_running_reviews_on_startup() -> None:
    if not _enabled():
        return
    from app.core.config import get_settings

    settings = get_settings()
    timeout = max(
        settings.openai_code_review_timeout_seconds,
        settings.anthropic_code_review_timeout_seconds,
        120,
    )
    db = SessionLocal()
    try:
        mark_stale_running_as_failed(db, timeout)
        db.commit()
    finally:
        db.close()


def _run_review(
    db: Session,
    task_id: int,
    project: Project,
    profile,
    provider,
    request: dict[str, Any],
) -> dict[str, Any]:
    append_progress(
        db,
        task_id,
        "REQUEST_BUILT",
        "INFO",
        "AI Review 请求已构建",
        f"profileCode={profile.profile_code}, provider={provider.provider_code}, model={request.get('model') or provider.model_name}, mode={request.get('mode')}",
    )
    db.commit()
    try:
        result = run_provider(db, task_id, provider, request)
    except Exception as exception:
        append_progress(
            db,
            task_id,
            "PROVIDER_FAILED",
            "ERROR",
            "代码质量 Review Provider 调用失败",
            str(exception),
        )
        result = {
            "status": "FAILED",
            "provider": provider.provider_code,
            "overallLevel": None,
            "summary": None,
            "findings": [],
            "rawOutput": None,
            "exitCode": None,
            "errorMessage": str(exception) or "Code quality review failed",
            "startedAt": datetime.now(),
            "finishedAt": datetime.now(),
        }
    append_progress(
        db,
        task_id,
        "SAVE_RESULT",
        "INFO",
        "Provider 执行完成，开始保存结果",
        f"status={result['status']}, findingCount={len(result.get('findings') or [])}",
    )
    saved_result = save_result(
        db,
        task_id=task_id,
        project_id=project.id,
        profile_code=profile.profile_code,
        provider=provider.provider_code,
        model=request.get("model") or provider.model_name,
        result=result,
    )
    result["_resultId"] = saved_result.id
    append_progress(
        db,
        task_id,
        "RESULT_SAVED",
        "INFO" if result["status"] == "SUCCESS" else "ERROR",
        "AI Review 结果已保存",
        f"status={result['status']}, resultId={saved_result.id}",
    )
    append_progress(
        db,
        task_id,
        "FINISHED",
        "INFO" if result["status"] == "SUCCESS" else "ERROR",
        "AI Review 已完成" if result["status"] == "SUCCESS" else "AI Review 执行失败",
        f"status={result['status']}, overallLevel={result.get('overallLevel') or '-'}",
    )
    db.commit()
    return result


def _send_auto_review_notification(
    db: Session,
    task_id: int,
    result: dict[str, Any],
    rule_result_id: int | None,
    risk_card: dict | None,
    focus_change_types: list[str] | None,
    focus_rule_codes: list[str] | None,
    notification_context: dict | None,
) -> None:
    notification = send_review_summary(
        db,
        task_id,
        risk_card,
        focus_change_types or [],
        result,
        notification_context or {},
        get_settings_record(db).dingtalk_notification_enabled,
        focus_rule_codes or [],
    )
    save_notification_records(
        db,
        task_id=task_id,
        result_id=rule_result_id or result.get("_resultId"),
        notifications=notification["records"],
    )
    append_progress(
        db,
        task_id,
        "NOTIFICATION_SENT",
        "INFO",
        "AI Review 钉钉通知已处理",
        f"status={notification['status']}",
    )


def _resolve_profile(db: Session, profile_code: str | None, project: Project):
    selected = profile_code or project.default_code_quality_profile_code or "backend-default-ai-review"
    profile = get_profile(db, selected)
    return profile


def _resolve_provider(db: Session, project: Project, profile):
    provider_code = profile.provider_code or project.default_code_quality_provider_code
    if not provider_code:
        provider_code = get_settings_record(db).default_provider_code
    return get_provider(db, provider_code)


def _build_review_request(profile, request: dict[str, Any]) -> dict[str, Any]:
    instructions = _join_instructions(profile.review_instructions, request.get("instructions"))
    return {
        "repositoryPath": request.get("repositoryPath"),
        "mode": request.get("mode") or "DIFF_TEXT",
        "baseRef": request.get("baseRef"),
        "commitSha": request.get("commitSha"),
        "title": request.get("title"),
        "model": request.get("model") or profile.model,
        "instructions": instructions,
        "diffText": request.get("diffText"),
        "changedFiles": request.get("changedFiles") or [],
    }


def _request_from_task_event(db: Session, task: ReviewTask, profile) -> dict[str, Any]:
    event = db.scalars(
        select(GitLabMergeRequestEvent).where(GitLabMergeRequestEvent.task_id == task.id)
    ).first()
    if event is None:
        push_event = db.scalars(
            select(GitLabPushEvent).where(GitLabPushEvent.task_id == task.id)
        ).first()
        event_summary = read_json(push_event.changed_files_summary, {}) if push_event else {}
    else:
        event_summary = read_json(event.changed_files_summary, {})
    files = event_summary.get("files") if isinstance(event_summary, dict) else []
    if not isinstance(files, list):
        files = []
    return _build_review_request(
        profile,
        {
            "mode": "DIFF_TEXT",
            "baseRef": task.target_branch,
            "commitSha": task.commit_sha,
            "title": f"{task.trigger_type} {task.external_source_id or ''}".strip(),
            "diffText": _diff_text(files),
            "changedFiles": [file.get("path") for file in files if isinstance(file, dict) and file.get("path")],
        },
    )


def _diff_text(changed_files: list[dict[str, Any]]) -> str:
    parts = []
    for file in changed_files:
        if not isinstance(file, dict):
            continue
        diff = file.get("diffText")
        if diff:
            parts.append(f"diff -- {file.get('path') or file.get('newPath') or ''}\n{diff}")
    return "\n\n".join(parts)


def _join_instructions(profile_prompt: str | None, request_instructions: str | None) -> str | None:
    if profile_prompt and request_instructions:
        return f"{profile_prompt}\n\nAdditional manual instructions:\n{request_instructions}"
    return request_instructions or profile_prompt


def _enabled() -> bool:
    from app.core.config import get_settings

    return get_settings().code_quality_review_enabled


def _inline_enabled() -> bool:
    return (
        os.getenv("CODE_QUALITY_REVIEW_INLINE", "false").lower() == "true"
        or os.getenv("CODE_QUALITY_RETRY_INLINE", "false").lower() == "true"
    )
