from __future__ import annotations

from datetime import datetime
from fnmatch import fnmatchcase
import hashlib
import os
from itertools import count
from queue import PriorityQueue
from threading import Lock, Thread
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.code_quality import prompt
from app.code_quality.providers import run_fix_provider, run_provider, test_provider_connection
from app.code_quality.repository import (
    append_progress,
    create_scheduler_job,
    delete_progress,
    find_push_gate_decision,
    find_fix_preview_response,
    find_result_response,
    get_profile,
    get_provider,
    get_settings_record,
    has_recent_allowed_push_gate,
    list_ai_review_failure_notifications,
    list_progress,
    list_fix_preview_responses,
    list_provider_responses,
    list_scheduler_queue_snapshot,
    mark_scheduler_job_finished,
    mark_scheduler_job_running,
    push_gate_to_dict,
    mark_stale_running_as_failed,
    normalize_auto_fix_preview_severities,
    reset_default_prompt,
    save_fix_preview,
    save_push_gate_decision,
    save_result,
    set_default_provider,
    settings_to_dict,
    update_profile,
    update_provider,
    update_settings_record,
)
from app.core.database import SessionLocal
from app.core.errors import AppError
from app.core.json_utils import read_json, read_json_array
from app.code_quality.models import CodeQualityModelProvider
from app.project_integration.models import GitLabMergeRequestEvent, GitLabPushEvent, Project
from app.project_integration.repository import find_project_by_id, get_project_group_ai_review_policy, resolve_project_target_config
from app.notification.service import send_review_summary
from app.review_record.models import ReviewTask
from app.review_record.repository import (
    create_review_task,
    mark_task_failed,
    mark_task_success,
    save_notification_records,
)


REVIEW_JOB_PRIORITY = 10
FIX_PREVIEW_JOB_PRIORITY = 50
SCHEDULER_MAX_WORKERS = 10


class _ProviderJobScheduler:
    def __init__(self, max_workers: int = SCHEDULER_MAX_WORKERS) -> None:
        self.max_workers = max_workers
        self._queue: PriorityQueue[tuple[int, int, int, Callable[..., Any], tuple[Any, ...], dict[str, Any]]] = PriorityQueue()
        self._counter = count()
        self._started = False
        self._lock = Lock()

    def submit(
        self,
        fn: Callable[..., Any],
        *args: Any,
        job_id: int | None = None,
        priority: int = FIX_PREVIEW_JOB_PRIORITY,
        **kwargs: Any,
    ) -> int | None:
        self._ensure_started()
        order = next(self._counter)
        self._queue.put((priority, order, int(job_id or 0), fn, args, kwargs))
        return job_id

    def _ensure_started(self) -> None:
        if self._started:
            return
        with self._lock:
            if self._started:
                return
            for index in range(self.max_workers):
                worker = Thread(
                    target=self._worker,
                    name=f"code-quality-provider-scheduler-{index + 1}",
                    daemon=True,
                )
                worker.start()
            self._started = True

    def _worker(self) -> None:
        while True:
            priority, _order, job_id, fn, args, kwargs = self._queue.get()
            db = SessionLocal()
            try:
                if job_id:
                    mark_scheduler_job_running(db, job_id)
                    db.commit()
                outcome = fn(*args, **kwargs)
                if job_id:
                    mark_scheduler_job_finished(db, job_id, _scheduler_outcome_status(outcome))
                    db.commit()
            except Exception as exception:
                if job_id:
                    mark_scheduler_job_finished(db, job_id, "FAILED", str(exception))
                    db.commit()
            finally:
                db.close()
                self._queue.task_done()


_executor = _ProviderJobScheduler()


def _scheduler_outcome_status(outcome: Any) -> str:
    if isinstance(outcome, dict):
        status = str(outcome.get("status") or "").upper()
        if status in {"SUCCESS", "FAILED", "SKIPPED"}:
            return status
    return "SUCCESS"


def _submit_provider_job(
    db: Session,
    fn: Callable[..., Any],
    *args: Any,
    job_type: str,
    task_id: int,
    project_id: int | None,
    priority: int,
    label: str | None = None,
    finding_index: int | None = None,
    file_path: str | None = None,
) -> int:
    job = create_scheduler_job(
        db,
        job_type=job_type,
        task_id=task_id,
        project_id=project_id,
        finding_index=finding_index,
        priority=priority,
        label=label,
        file_path=file_path,
    )
    db.commit()
    try:
        _executor.submit(fn, *args, job_id=job.id, priority=priority)
    except TypeError:
        _executor.submit(fn, *args)
    return int(job.id)


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
    _submit_provider_job(
        db,
        run_manual_review_job,
        task_id,
        dict(request),
        job_type="AI_REVIEW",
        task_id=task_id,
        project_id=request.get("projectId"),
        priority=REVIEW_JOB_PRIORITY,
        label="手动 AI Review",
    )
    return response


def enqueue_manual_review(db: Session, request: dict[str, Any]) -> dict[str, Any]:
    if not _enabled(db):
        raise AppError("BAD_REQUEST", "Code quality review is disabled", 400)
    project_id = request.get("projectId")
    if project_id is None:
        raise AppError("VALIDATION_ERROR", "projectId is required", 400)
    project = find_project_by_id(db, int(project_id))
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {project_id}", 404)
    changed_files = [
        item if isinstance(item, dict) else {"path": item}
        for item in request.get("changedFiles") or []
    ]
    target_config = resolve_project_target_config(
        db,
        project,
        changed_files,
        request.get("targetType"),
        request.get("targetTypes"),
    )
    profile = _resolve_profile(db, request.get("profileCode") or target_config["profileCode"], project)
    ai_policy = get_project_group_ai_review_policy(db, project)
    if not profile.enabled or not ai_policy.get("aiReviewEnabled") or not ai_policy.get("triggerOnManual"):
        raise AppError(
            "BAD_REQUEST",
            f"Project group AI Review policy does not allow manual trigger: {profile.profile_code}",
            400,
        )
    provider = _resolve_provider(db, project, profile, target_config["targetType"])
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
        template_code=target_config["templateCode"],
        target_type=target_config["targetType"],
        target_types=target_config["targetTypes"],
        code_quality_profile_code=profile.profile_code,
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
        "projectId": project.id,
        "status": "RUNNING",
        "profileCode": profile.profile_code,
        "provider": provider.provider_code,
        "overallLevel": None,
        "findingCount": 0,
    }


def run_manual_review_job(task_id: int, request: dict[str, Any]) -> dict[str, Any]:
    db = SessionLocal()
    try:
        result = run_manual_review_now(db, task_id, request)
        db.commit()
        return result
    except Exception as exception:
        task = db.get(ReviewTask, task_id)
        if task is not None:
            mark_task_failed(task, str(exception))
            append_progress(db, task_id, "FAILED", "ERROR", "手动 AI Review 后台执行失败", str(exception))
        db.commit()
        return {"status": "FAILED", "errorMessage": str(exception)}
    finally:
        db.close()


def run_manual_review_now(db: Session, task_id: int, request: dict[str, Any]) -> dict[str, Any]:
    task = db.get(ReviewTask, task_id)
    if task is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)
    project = find_project_by_id(db, task.project_id)
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {task.project_id}", 404)
    profile = _resolve_profile(db, request.get("profileCode") or task.code_quality_profile_code, project)
    provider = _resolve_provider(db, project, profile, task.target_type)
    review_request = _build_review_request(profile, request)
    return _run_review(db, task.id, project, profile, provider, review_request)


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
    _submit_provider_job(
        db,
        run_retry_review_job,
        task_id,
        job_type="AI_REVIEW",
        task_id=task_id,
        project_id=response.get("projectId"),
        priority=REVIEW_JOB_PRIORITY,
        label="重试 AI Review",
    )
    return response


def enqueue_retry_review(db: Session, task_id: int) -> dict[str, Any]:
    if not _enabled(db):
        raise AppError("BAD_REQUEST", "Code quality review is disabled", 400)
    task = db.get(ReviewTask, task_id)
    if task is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)
    if task.trigger_type not in {"GITLAB_MR_WEBHOOK", "GITLAB_PUSH_WEBHOOK"}:
        raise AppError("BAD_REQUEST", f"Only GitLab webhook tasks can retry AI Review: {task_id}", 400)
    project = find_project_by_id(db, task.project_id)
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {task.project_id}", 404)
    profile = _resolve_profile(db, task.code_quality_profile_code, project)
    provider = _resolve_provider(db, project, profile, task.target_type)
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
        "projectId": project.id,
        "status": "RUNNING",
        "profileCode": profile.profile_code,
        "provider": provider.provider_code,
        "overallLevel": None,
        "findingCount": 0,
    }


def run_retry_review_job(task_id: int) -> dict[str, Any]:
    db = SessionLocal()
    try:
        result = run_retry_review_now(db, task_id)
        db.commit()
        return result
    except Exception as exception:
        task = db.get(ReviewTask, task_id)
        if task is not None:
            mark_task_failed(task, str(exception))
            append_progress(db, task_id, "FAILED", "ERROR", "AI Review 后台执行失败", str(exception))
        db.commit()
        return {"status": "FAILED", "errorMessage": str(exception)}
    finally:
        db.close()


def run_retry_review_now(db: Session, task_id: int) -> dict[str, Any]:
    task = db.get(ReviewTask, task_id)
    if task is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)
    project = find_project_by_id(db, task.project_id)
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {task.project_id}", 404)
    profile = _resolve_profile(db, task.code_quality_profile_code, project)
    provider = _resolve_provider(db, project, profile, task.target_type)
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
    reminder_card_enabled: bool = True,
) -> bool:
    task = db.get(ReviewTask, task_id)
    if task is None:
        return False
    if not _enabled(db):
        if task.trigger_type == "GITLAB_PUSH_WEBHOOK":
            _save_push_gate_rejection(
                db,
                task=task,
                changed_files=changed_files,
                risk_card=risk_card,
                focus_change_types=focus_change_types,
                focus_rule_codes=focus_rule_codes,
                reason_code="GLOBAL_DISABLED",
                reason_summary="代码质量 AI Review 全局能力未启用，Push 不会进入 AI Review。",
            )
        return False
    if task.trigger_type == "GITLAB_PUSH_WEBHOOK":
        return _trigger_push_auto_review(
            db,
            task=task,
            project=project,
            changed_files=changed_files,
            diff_text=diff_text,
            rule_result_id=rule_result_id,
            risk_card=risk_card,
            focus_change_types=focus_change_types or [],
            focus_rule_codes=focus_rule_codes or [],
            notification_context=notification_context or {},
            reminder_card_enabled=reminder_card_enabled,
        )
    if task.trigger_type != "GITLAB_MR_WEBHOOK":
        return False
    if find_result_response(db, task_id) is not None:
        return False
    profile = _resolve_auto_profile_or_save_failure(db, task, project)
    if profile is None:
        return False
    ai_policy = get_project_group_ai_review_policy(db, project)
    if not profile.enabled or not ai_policy.get("aiReviewEnabled") or not ai_policy.get("triggerOnMr"):
        return False
    provider = _resolve_provider(db, project, profile, task.target_type)
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
            reminder_card_enabled,
        )
    else:
        _submit_provider_job(
            db,
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
            reminder_card_enabled,
            job_type="AI_REVIEW",
            task_id=task.id,
            project_id=project.id,
            priority=REVIEW_JOB_PRIORITY,
            label="MR AI Review",
        )
    return True


def _trigger_push_auto_review(
    db: Session,
    *,
    task: ReviewTask,
    project: Project,
    changed_files: list[dict[str, Any]],
    diff_text: str | None,
    rule_result_id: int | None,
    risk_card: dict | None,
    focus_change_types: list[str],
    focus_rule_codes: list[str],
    notification_context: dict,
    reminder_card_enabled: bool,
) -> bool:
    if find_result_response(db, task.id) is not None:
        return False
    profile = _resolve_auto_profile_or_save_failure(db, task, project)
    if profile is None:
        return False
    ai_policy = get_project_group_ai_review_policy(db, project)
    if not profile.enabled or not ai_policy.get("aiReviewEnabled") or not ai_policy.get("triggerOnPush"):
        _save_push_gate_rejection(
            db,
            task=task,
            changed_files=changed_files,
            risk_card=risk_card,
            focus_change_types=focus_change_types,
            focus_rule_codes=focus_rule_codes,
            profile_code=profile.profile_code,
            reason_code="PROFILE_DISABLED",
            reason_summary="当前项目组 AI Review 策略未开启 Push 自动触发。",
        )
        return False
    provider = _resolve_provider(db, project, profile, task.target_type)
    gate = _evaluate_push_gate(
        db,
        task=task,
        profile=profile,
        push_policy=ai_policy,
        provider_code=provider.provider_code,
        changed_files=changed_files,
        diff_text=diff_text,
        risk_card=risk_card,
        focus_change_types=focus_change_types,
        focus_rule_codes=focus_rule_codes,
    )
    if gate["decision"] != "ALLOWED":
        save_push_gate_decision(db, **gate)
        return False

    request_diff_text = diff_text or _diff_text(changed_files)
    request = _build_review_request(
        profile,
        {
            "mode": "DIFF_TEXT",
            "baseRef": task.source_branch,
            "commitSha": task.commit_sha,
            "title": f"{task.trigger_type} {task.external_source_id or ''}".strip(),
            "diffText": request_diff_text,
            "changedFiles": [file.get("path") for file in changed_files if file.get("path")],
        },
    )
    delete_progress(db, task.id)
    append_progress(
        db,
        task.id,
        "QUEUED",
        "INFO",
        "Push AI Review 已通过自动审核并进入队列",
        f"reasonCode={gate['reason_code']}, provider={provider.provider_code}, profile={profile.profile_code}",
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
    gate["ai_review_scheduled"] = True
    save_push_gate_decision(db, **gate)
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
            reminder_card_enabled,
        )
    else:
        _submit_provider_job(
            db,
            run_auto_review_job,
            task.id,
            project.id,
            profile.profile_code,
            provider.provider_code,
            request,
            rule_result_id,
            risk_card,
            focus_change_types,
            focus_rule_codes,
            notification_context,
            reminder_card_enabled,
            job_type="AI_REVIEW",
            task_id=task.id,
            project_id=project.id,
            priority=REVIEW_JOB_PRIORITY,
            label="Push AI Review",
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
    reminder_card_enabled: bool = True,
) -> dict[str, Any]:
    db = SessionLocal()
    try:
        project = find_project_by_id(db, project_id)
        if project is None:
            task = db.get(ReviewTask, task_id)
            if task is not None:
                mark_task_failed(task, f"Project not found: {project_id}")
            append_progress(db, task_id, "FAILED", "ERROR", "AI Review 后台执行失败", f"Project not found: {project_id}")
            db.commit()
            return {"status": "FAILED", "errorMessage": f"Project not found: {project_id}"}
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
            reminder_card_enabled,
        )
        db.commit()
        return result
    except Exception as exception:
        review_result = find_result_response(db, task_id)
        task = db.get(ReviewTask, task_id)
        if task is not None and (review_result or {}).get("status") != "SUCCESS":
            mark_task_failed(task, str(exception))
        append_progress(db, task_id, "FAILED", "ERROR", "AI Review 后台执行失败", str(exception))
        db.commit()
        return {"status": "FAILED", "errorMessage": str(exception)}
    finally:
        db.close()


def get_push_gate_response(db: Session, task_id: int) -> dict[str, Any]:
    task = db.get(ReviewTask, task_id)
    if task is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)
    record = find_push_gate_decision(db, task_id)
    if record is not None:
        return push_gate_to_dict(record)
    return {
        "taskId": task_id,
        "projectId": task.project_id,
        "branchName": task.source_branch,
        "decision": "NOT_EVALUATED",
        "reasonCode": "NOT_EVALUATED",
        "reasonSummary": "该任务尚未进入 Push AI Review 自动审核，或不是 GitLab Push 任务。",
        "aiReviewScheduled": False,
        "profileCode": None,
        "provider": None,
        "metrics": {},
        "matchedRules": [],
        "createdAt": None,
        "updatedAt": None,
    }


def _save_push_gate_rejection(
    db: Session,
    *,
    task: ReviewTask,
    changed_files: list[dict[str, Any]],
    risk_card: dict | None,
    focus_change_types: list[str] | None,
    focus_rule_codes: list[str] | None,
    reason_code: str,
    reason_summary: str,
    profile_code: str | None = None,
    provider: str | None = None,
) -> None:
    metrics, matched_rules = _push_gate_metrics_and_rules(
        task=task,
        changed_files=changed_files,
        diff_text=None,
        risk_card=risk_card,
        focus_change_types=focus_change_types or [],
        focus_rule_codes=focus_rule_codes or [],
    )
    save_push_gate_decision(
        db,
        task_id=task.id,
        project_id=task.project_id,
        branch_name=task.source_branch,
        profile_code=profile_code,
        provider=provider,
        decision="REJECTED",
        ai_review_scheduled=False,
        reason_code=reason_code,
        reason_summary=reason_summary,
        metrics=metrics,
        matched_rules=matched_rules,
    )


def _evaluate_push_gate(
    db: Session,
    *,
    task: ReviewTask,
    profile,
    push_policy: dict[str, Any],
    provider_code: str,
    changed_files: list[dict[str, Any]],
    diff_text: str | None,
    risk_card: dict | None,
    focus_change_types: list[str],
    focus_rule_codes: list[str],
) -> dict[str, Any]:
    request_diff_text = diff_text or _diff_text(changed_files)
    metrics, matched_rules = _push_gate_metrics_and_rules(
        task=task,
        changed_files=changed_files,
        diff_text=request_diff_text,
        risk_card=risk_card,
        focus_change_types=focus_change_types,
        focus_rule_codes=focus_rule_codes,
    )
    branch_patterns = push_policy.get("pushBranchPatterns") or []
    branch_matched = _branch_matches(task.source_branch, branch_patterns)
    matched_rules.append(
        {
            "code": "branch",
            "label": f"分支 {task.source_branch or '-'}",
            "matched": branch_matched,
            "detail": ",".join(branch_patterns),
        }
    )
    if not branch_matched:
        return _push_gate_payload(
            task,
            profile.profile_code,
            provider_code,
            "REJECTED",
            False,
            "BRANCH_NOT_MATCHED",
            "推送分支不在 Push AI Review 自动触发范围内。",
            metrics,
            matched_rules,
        )

    debounce_seconds = int(push_policy.get("pushDebounceSeconds") or 0)
    debounced = has_recent_allowed_push_gate(
        db,
        project_id=task.project_id,
        branch_name=task.source_branch,
        task_id=task.id,
        debounce_seconds=debounce_seconds,
    )
    matched_rules.append(
        {
            "code": "debounce",
            "label": f"{debounce_seconds} 秒内同项目同分支仅触发一次",
            "matched": not debounced,
        }
    )
    if debounced:
        return _push_gate_payload(
            task,
            profile.profile_code,
            provider_code,
            "REJECTED",
            False,
            "DEBOUNCED",
            "同项目同分支近期已有 Push AI Review，本次自动拦截以避免频繁触发。",
            metrics,
            matched_rules,
        )

    diff_available = bool(request_diff_text.strip())
    matched_rules.append({"code": "diffText", "label": "存在可审查 diff 文本", "matched": diff_available})
    if not diff_available:
        return _push_gate_payload(
            task,
            profile.profile_code,
            provider_code,
            "REJECTED",
            False,
            "NO_DIFF_TEXT",
            "本次 Push 没有可提供给模型审查的 diff 文本，仅保留规则提醒结果。",
            metrics,
            matched_rules,
        )

    too_large = (
        _over_limit(metrics["changedFileCount"], push_policy.get("pushMaxChangedFiles"))
        or _over_limit(metrics["diffBytes"], push_policy.get("pushMaxDiffBytes"))
    )
    matched_rules.append(
        {
            "code": "hardLimit",
            "label": "未超过 Push AI Review 硬上限",
            "matched": not too_large,
            "detail": f"files<={push_policy.get('pushMaxChangedFiles')}, diffBytes<={push_policy.get('pushMaxDiffBytes')}",
        }
    )
    if too_large:
        return _push_gate_payload(
            task,
            profile.profile_code,
            provider_code,
            "REJECTED",
            False,
            "DIFF_TOO_LARGE",
            "本次 Push 超出 AI Review 自动触发硬上限，避免模型输入失控。",
            metrics,
            matched_rules,
        )

    risk_matched = _risk_matched(metrics)
    large_change = (
        _reaches_threshold(metrics["changedFileCount"], push_policy.get("pushMinChangedFiles"))
        or _reaches_threshold(metrics["diffBytes"], push_policy.get("pushMinDiffBytes"))
        or _reaches_threshold(metrics["commitCount"], push_policy.get("pushMinCommitCount"))
    )
    matched_rules.append({"code": "riskMatched", "label": "命中高风险或重点提醒", "matched": risk_matched})
    matched_rules.append(
        {
            "code": "largeChange",
            "label": "达到 Push 大变更阈值",
            "matched": large_change,
            "detail": f"files>={push_policy.get('pushMinChangedFiles')}, diffBytes>={push_policy.get('pushMinDiffBytes')}, commits>={push_policy.get('pushMinCommitCount')}",
        }
    )
    if risk_matched:
        return _push_gate_payload(
            task,
            profile.profile_code,
            provider_code,
            "ALLOWED",
            False,
            "RISK_MATCHED",
            "Push 命中重点提醒或高风险变更，允许进入 AI Review。",
            metrics,
            matched_rules,
        )
    if large_change:
        return _push_gate_payload(
            task,
            profile.profile_code,
            provider_code,
            "ALLOWED",
            False,
            "LARGE_CHANGE",
            "Push 达到大变更阈值，允许进入 AI Review。",
            metrics,
            matched_rules,
        )
    return _push_gate_payload(
        task,
        profile.profile_code,
        provider_code,
        "REJECTED",
        False,
        "NOT_SIGNIFICANT",
        "本次 Push 未命中重点风险，也未达到大变更阈值。",
        metrics,
        matched_rules,
    )


def _push_gate_payload(
    task: ReviewTask,
    profile_code: str | None,
    provider_code: str | None,
    decision: str,
    ai_review_scheduled: bool,
    reason_code: str,
    reason_summary: str,
    metrics: dict[str, Any],
    matched_rules: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "task_id": task.id,
        "project_id": task.project_id,
        "branch_name": task.source_branch,
        "profile_code": profile_code,
        "provider": provider_code,
        "decision": decision,
        "ai_review_scheduled": ai_review_scheduled,
        "reason_code": reason_code,
        "reason_summary": reason_summary,
        "metrics": metrics,
        "matched_rules": matched_rules,
    }


def _push_gate_metrics_and_rules(
    *,
    task: ReviewTask,
    changed_files: list[dict[str, Any]],
    diff_text: str | None,
    risk_card: dict | None,
    focus_change_types: list[str],
    focus_rule_codes: list[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    risk_items = risk_card.get("riskItems") if isinstance(risk_card, dict) else []
    if not isinstance(risk_items, list):
        risk_items = []
    focus_indicators = risk_card.get("focusIndicators") if isinstance(risk_card, dict) else []
    if not isinstance(focus_indicators, list):
        focus_indicators = []
    matched_change_types = sorted(
        {
            item.get("category")
            for item in risk_items
            if isinstance(item, dict) and item.get("category")
        }
        | {
            change_type
            for indicator in focus_indicators
            if isinstance(indicator, dict) and indicator.get("matched")
            for change_type in (indicator.get("sourceChangeTypes") or [])
        }
    )
    focus_risk_items = [
        item
        for item in risk_items
        if isinstance(item, dict)
        and (
            item.get("category") in focus_change_types
            or item.get("ruleCode") in focus_rule_codes
            or item.get("riskLevel") in {"HIGH", "CRITICAL"}
        )
    ]
    metrics = {
        "changedFileCount": len(changed_files),
        "diffBytes": len((diff_text or "").encode("utf-8")),
        "commitCount": _push_commit_count(task, changed_files),
        "riskLevel": risk_card.get("riskLevel") if isinstance(risk_card, dict) else None,
        "focusRiskItemCount": len(focus_risk_items),
        "matchedChangeTypes": matched_change_types,
        "branch": task.source_branch,
        "compareSource": _changed_files_source(changed_files),
    }
    matched_rules = [
        {
            "code": "riskLevel",
            "label": f"风险等级 {metrics['riskLevel'] or '-'}",
            "matched": metrics["riskLevel"] in {"HIGH", "CRITICAL"},
        },
        {
            "code": "focusRiskItems",
            "label": f"重点提醒 {metrics['focusRiskItemCount']} 条",
            "matched": metrics["focusRiskItemCount"] > 0,
        },
    ]
    return metrics, matched_rules


def _push_commit_count(task: ReviewTask, changed_files: list[dict[str, Any]]) -> int:
    for file in changed_files:
        if isinstance(file, dict) and file.get("commitCount") is not None:
            try:
                return int(file["commitCount"])
            except (TypeError, ValueError):
                return 0
    return 0


def _changed_files_source(changed_files: list[dict[str, Any]]) -> str | None:
    for file in changed_files:
        if isinstance(file, dict) and file.get("source"):
            return str(file["source"])
    return None


def _branch_matches(branch_name: str | None, patterns: list[str]) -> bool:
    if not patterns:
        return True
    if not branch_name:
        return False
    return any(fnmatchcase(branch_name, pattern) for pattern in patterns)


def _over_limit(value: int, limit: int | None) -> bool:
    return limit is not None and limit >= 0 and value > limit


def _reaches_threshold(value: int, threshold: int | None) -> bool:
    return threshold is not None and value >= threshold


def _risk_matched(metrics: dict[str, Any]) -> bool:
    return metrics.get("riskLevel") in {"HIGH", "CRITICAL"} or int(metrics.get("focusRiskItemCount") or 0) > 0


def get_settings_response(db: Session) -> dict[str, Any]:
    return settings_to_dict(get_settings_record(db))


def update_settings(db: Session, request: dict[str, Any]) -> dict[str, Any]:
    response = update_settings_record(db, request)
    db.commit()
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


def test_provider_response(
    db: Session,
    provider_code: str,
    request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    provider = get_provider(db, provider_code)
    return test_provider_connection(provider, request or {})


def set_default_provider_response(db: Session, provider_code: str) -> dict[str, Any]:
    response = set_default_provider(db, provider_code)
    db.commit()
    return response


def get_result_response(db: Session, task_id: int) -> dict[str, Any] | None:
    result = find_result_response(db, task_id)
    if result is None:
        if db.get(ReviewTask, task_id) is None:
            raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)
        return None
    return result


def get_progress_response(db: Session, task_id: int) -> list[dict[str, Any]]:
    if db.get(ReviewTask, task_id) is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)
    return list_progress(db, task_id)


def get_job_queue_response(db: Session) -> dict[str, Any]:
    return list_scheduler_queue_snapshot(db)


def get_failure_notifications_response(db: Session) -> dict[str, Any]:
    return list_ai_review_failure_notifications(db)


def list_fix_previews_response(db: Session, task_id: int) -> list[dict[str, Any]]:
    if db.get(ReviewTask, task_id) is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)
    return list_fix_preview_responses(db, task_id)


def generate_fix_preview_response(db: Session, task_id: int, request: dict[str, Any]) -> dict[str, Any]:
    finding_index = request.get("findingIndex")
    if finding_index is None:
        raise AppError("VALIDATION_ERROR", "findingIndex is required", 400)
    try:
        finding_index = int(finding_index)
    except (TypeError, ValueError) as exception:
        raise AppError("VALIDATION_ERROR", "findingIndex must be an integer", 400) from exception
    if finding_index < 0:
        raise AppError("VALIDATION_ERROR", "findingIndex must be non-negative", 400)

    existing = find_fix_preview_response(db, task_id=task_id, finding_index=finding_index)
    if existing is not None and not request.get("forceRegenerate"):
        return existing
    if not _enabled(db):
        raise AppError("BAD_REQUEST", "Code quality review is disabled", 400)

    if _fix_preview_inline_enabled():
        response = _generate_fix_preview(db, task_id, finding_index, bool(request.get("forceRegenerate")))
        db.commit()
        return response
    return _queue_fix_preview(db, task_id, finding_index, bool(request.get("forceRegenerate")))


def _queue_fix_preview(
    db: Session,
    task_id: int,
    finding_index: int,
    force_regenerate: bool,
) -> dict[str, Any]:
    task = db.get(ReviewTask, task_id)
    if task is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)
    project = find_project_by_id(db, task.project_id)
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {task.project_id}", 404)
    review_result = find_result_response(db, task_id)
    if review_result is None:
        raise AppError("BAD_REQUEST", f"AI Review result not found: {task_id}", 400)
    findings = review_result.get("findings") or []
    if finding_index >= len(findings):
        raise AppError("BAD_REQUEST", f"Finding index out of range: {finding_index}", 400)
    finding = findings[finding_index]
    if not isinstance(finding, dict):
        raise AppError("BAD_REQUEST", f"Finding is invalid: {finding_index}", 400)
    file_node = _find_changed_file_for_finding(_changed_files_from_task_event(db, task), finding)
    if file_node is None:
        response = _save_fix_preview_status(
            db,
            task,
            project,
            finding_index,
            finding.get("filePath") or "",
            review_result.get("provider") or "-",
            review_result.get("model"),
            "SKIPPED",
            "Changed file for finding was not found",
        )
        db.commit()
        return response
    file_path = file_node.get("path") or file_node.get("newPath") or finding.get("filePath") or ""
    if not _single_file_diff_text(file_node).strip():
        response = _save_fix_preview_status(
            db,
            task,
            project,
            finding_index,
            file_path,
            review_result.get("provider") or "-",
            review_result.get("model"),
            "SKIPPED",
            "Current task did not save diff text for this file",
        )
        db.commit()
        return response
    response = _save_fix_preview_status(
        db,
        task,
        project,
        finding_index,
        file_path,
        review_result.get("provider") or "-",
        review_result.get("model"),
        "QUEUED",
        "AI 修复预览已进入队列",
    )
    append_progress(
        db,
        task_id,
        "FIX_PREVIEW_QUEUED",
        "INFO",
        "AI 修复预览已进入队列",
        f"findingIndex={finding_index}, filePath={file_path}",
    )
    _submit_provider_job(
        db,
        run_auto_fix_preview_job,
        task_id,
        finding_index,
        job_type="FIX_PREVIEW",
        task_id=task_id,
        project_id=project.id,
        finding_index=finding_index,
        priority=FIX_PREVIEW_JOB_PRIORITY,
        label="AI 修复预览",
        file_path=file_path,
    )
    return response


def _generate_fix_preview(
    db: Session,
    task_id: int,
    finding_index: int,
    force_regenerate: bool,
) -> dict[str, Any]:
    task = db.get(ReviewTask, task_id)
    if task is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)
    project = find_project_by_id(db, task.project_id)
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {task.project_id}", 404)
    review_result = find_result_response(db, task_id)
    if review_result is None:
        raise AppError("BAD_REQUEST", f"AI Review result not found: {task_id}", 400)
    findings = review_result.get("findings") or []
    if finding_index >= len(findings):
        raise AppError("BAD_REQUEST", f"Finding index out of range: {finding_index}", 400)
    finding = findings[finding_index]
    if not isinstance(finding, dict):
        raise AppError("BAD_REQUEST", f"Finding is invalid: {finding_index}", 400)
    file_node = _find_changed_file_for_finding(_changed_files_from_task_event(db, task), finding)
    if file_node is None:
        return _save_fix_preview_status(
            db,
            task,
            project,
            finding_index,
            finding.get("filePath") or "",
            review_result.get("provider") or "-",
            review_result.get("model"),
            "SKIPPED",
            "Changed file for finding was not found",
        )
    diff_text = _single_file_diff_text(file_node)
    if not diff_text.strip():
        return _save_fix_preview_status(
            db,
            task,
            project,
            finding_index,
            file_node.get("path") or file_node.get("newPath") or finding.get("filePath") or "",
            review_result.get("provider") or "-",
            review_result.get("model"),
            "SKIPPED",
            "Current task did not save diff text for this file",
        )

    provider_code = review_result.get("provider")
    if not provider_code and task.code_quality_profile_code:
        provider_code = _resolve_provider(
            db,
            project,
            _resolve_profile(db, task.code_quality_profile_code, project),
            task.target_type,
        ).provider_code
    if not provider_code:
        provider_code = get_settings_record(db).default_provider_code
    provider = get_provider(db, provider_code)
    model = review_result.get("model") or provider.model_name
    file_path = file_node.get("path") or file_node.get("newPath") or finding.get("filePath") or ""
    _save_fix_preview_status(
        db,
        task,
        project,
        finding_index,
        file_path,
        provider.provider_code,
        model,
        "RUNNING",
        "AI 修复预览生成中",
    )
    append_progress(
        db,
        task_id,
        "FIX_PREVIEW_REQUEST_BUILT",
        "INFO",
        "AI 修复预览请求已构建",
        f"findingIndex={finding_index}, filePath={file_path}, provider={provider.provider_code}",
    )
    db.commit()
    result = run_fix_provider(
        db,
        task_id,
        provider,
        {
            "mode": "FIX_PREVIEW",
            "filePath": file_path,
            "model": model,
            "finding": finding,
            "diffText": diff_text,
            "changedFiles": [file_path],
        },
    )
    saved = save_fix_preview(
        db,
        task_id=task_id,
        project_id=project.id,
        finding_index=finding_index,
        file_path=file_path,
        provider=provider.provider_code,
        model=model,
        result=result,
    )
    append_progress(
        db,
        task_id,
        "FIX_PREVIEW_SAVED",
        "INFO" if result["status"] == "SUCCESS" else "ERROR",
        "AI 修复预览已保存" if result["status"] == "SUCCESS" else "AI 修复预览生成失败",
        f"status={result['status']}, findingIndex={finding_index}",
    )
    from app.code_quality.repository import fix_preview_to_dict

    return fix_preview_to_dict(saved)


def _save_fix_preview_status(
    db: Session,
    task: ReviewTask,
    project: Project,
    finding_index: int,
    file_path: str,
    provider: str,
    model: str | None,
    status: str,
    message: str,
) -> dict[str, Any]:
    saved = save_fix_preview(
        db,
        task_id=task.id,
        project_id=project.id,
        finding_index=finding_index,
        file_path=file_path or "-",
        provider=provider,
        model=model,
        result={
            "status": status,
            "summary": message if status == "SKIPPED" else None,
            "patchText": None,
            "warnings": [message] if status == "SKIPPED" else [],
            "errorMessage": message if status in {"FAILED", "SKIPPED"} else None,
        },
    )
    from app.code_quality.repository import fix_preview_to_dict

    return fix_preview_to_dict(saved)


def _enqueue_auto_fix_previews(
    db: Session,
    task_id: int,
    project: Project,
    provider,
    model: str | None,
    result: dict[str, Any],
) -> None:
    ai_policy = get_project_group_ai_review_policy(db, project)
    if not ai_policy.get("autoFixPreviewEnabled"):
        return
    enabled_severities = set(
        normalize_auto_fix_preview_severities(ai_policy.get("autoFixPreviewSeverities"))
    )
    findings = result.get("findings") or []
    if result.get("status") != "SUCCESS" or not findings:
        return
    if _inline_enabled() and not _fix_preview_inline_enabled():
        return
    task = db.get(ReviewTask, task_id)
    if task is None:
        return
    changed_files = _changed_files_from_task_event(db, task)
    queued_indexes: list[int] = []
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            continue
        if not _should_auto_generate_fix_preview(finding, enabled_severities):
            continue
        existing = find_fix_preview_response(db, task_id=task_id, finding_index=index)
        if existing and existing.get("status") == "SUCCESS":
            continue
        file_node = _find_changed_file_for_finding(changed_files, finding)
        if file_node is None:
            _save_fix_preview_status(
                db,
                task,
                project,
                index,
                finding.get("filePath") or "",
                provider.provider_code,
                model,
                "SKIPPED",
                "Changed file for finding was not found",
            )
            continue
        file_path = file_node.get("path") or file_node.get("newPath") or finding.get("filePath") or ""
        if not _single_file_diff_text(file_node).strip():
            _save_fix_preview_status(
                db,
                task,
                project,
                index,
                file_path,
                provider.provider_code,
                model,
                "SKIPPED",
                "Current task did not save diff text for this file",
            )
            continue
        _save_fix_preview_status(
            db,
            task,
            project,
            index,
            file_path,
            provider.provider_code,
            model,
            "QUEUED",
            "AI 修复预览已进入后台队列",
        )
        queued_indexes.append(index)
    if not queued_indexes:
        return
    append_progress(
        db,
        task_id,
        "FIX_PREVIEW_AUTO_QUEUED",
        "INFO",
        "AI 修复预览已进入后台队列",
        f"findingIndexes={queued_indexes}",
    )
    db.commit()
    if _fix_preview_inline_enabled():
        for index in queued_indexes:
            _generate_fix_preview(db, task_id, index, True)
        db.commit()
    else:
        for index in queued_indexes:
            finding = findings[index]
            file_node = _find_changed_file_for_finding(changed_files, finding)
            file_path = (
                file_node.get("path")
                or file_node.get("newPath")
                or finding.get("filePath")
                or ""
                if file_node
                else finding.get("filePath") or ""
            )
            _submit_provider_job(
                db,
                run_auto_fix_preview_job,
                task_id,
                index,
                job_type="FIX_PREVIEW",
                task_id=task_id,
                project_id=project.id,
                finding_index=index,
                priority=FIX_PREVIEW_JOB_PRIORITY,
                label="AI 修复预览",
                file_path=file_path,
            )


def _should_auto_generate_fix_preview(
    finding: dict[str, Any],
    enabled_severities: set[str],
) -> bool:
    return str(finding.get("severity") or "").strip().upper() in enabled_severities


def run_auto_fix_preview_job(task_id: int, finding_index: int) -> dict[str, Any]:
    db = SessionLocal()
    try:
        result = _generate_fix_preview(db, task_id, finding_index, True)
        db.commit()
        return result
    except Exception as exception:
        append_progress(
            db,
            task_id,
            "FIX_PREVIEW_AUTO_FAILED",
            "ERROR",
            "AI 修复预览后台任务失败",
            f"findingIndex={finding_index}, error={exception}",
        )
        db.commit()
        return {"status": "FAILED", "errorMessage": str(exception)}
    finally:
        db.close()


def recover_stale_running_reviews_on_startup() -> None:
    from app.core.config import get_settings

    settings = get_settings()
    timeout = max(
        settings.openai_code_review_timeout_seconds,
        settings.anthropic_code_review_timeout_seconds,
        settings.deepseek_code_review_timeout_seconds,
        settings.xiaomimo_code_review_timeout_seconds,
        120,
    )
    db = SessionLocal()
    try:
        if not _enabled(db):
            return
        provider_timeout = db.scalar(select(CodeQualityModelProvider.timeout_seconds).order_by(CodeQualityModelProvider.timeout_seconds.desc()))
        mark_stale_running_as_failed(db, max(timeout, int(provider_timeout or 0)))
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
    _sync_task_status_after_review(db, task_id, result)
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
    _enqueue_auto_fix_previews(
        db,
        task_id,
        project,
        provider,
        request.get("model") or provider.model_name,
        result,
    )
    return result


def _sync_task_status_after_review(db: Session, task_id: int, result: dict[str, Any]) -> None:
    task = db.get(ReviewTask, task_id)
    if task is None:
        return
    status = str(result.get("status") or "").upper()
    if status == "FAILED":
        mark_task_failed(task, result.get("errorMessage") or "AI Review failed")
        return
    if status == "SUCCESS" and (task.trigger_type == "CODE_QUALITY_MANUAL" or task.status == "FAILED"):
        mark_task_success(task, result.get("overallLevel") or task.risk_level or "LOW")


def _send_auto_review_notification(
    db: Session,
    task_id: int,
    result: dict[str, Any],
    rule_result_id: int | None,
    risk_card: dict | None,
    focus_change_types: list[str] | None,
    focus_rule_codes: list[str] | None,
    notification_context: dict | None,
    reminder_card_enabled: bool = True,
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
        reminder_card_enabled=reminder_card_enabled,
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
    selected = profile_code
    if not selected:
        raise AppError("CODE_QUALITY_PROFILE_NOT_CONFIGURED", "项目所属项目组未设置 AI Review 模板", 400)
    profile = get_profile(db, selected)
    return profile


def _resolve_auto_profile_or_save_failure(db: Session, task: ReviewTask, project: Project):
    try:
        return _resolve_profile(db, task.code_quality_profile_code, project)
    except AppError as exception:
        message = (
            "项目所属项目组未设置 AI Review 模板"
            if not task.code_quality_profile_code
            else f"项目所属项目组设置的 AI Review 模板不可用：{task.code_quality_profile_code}"
        )
        _save_missing_profile_failure(db, task, project, message or exception.message)
        return None


def _save_missing_profile_failure(db: Session, task: ReviewTask, project: Project, message: str) -> None:
    now = datetime.now()
    delete_progress(db, task.id)
    append_progress(
        db,
        task.id,
        "PROFILE_NOT_CONFIGURED",
        "WARN",
        "AI Review 模板未配置",
        message,
    )
    save_result(
        db,
        task_id=task.id,
        project_id=project.id,
        profile_code=task.code_quality_profile_code or "UNCONFIGURED",
        provider="-",
        model=None,
        result={
            "status": "SKIPPED",
            "overallLevel": None,
            "summary": None,
            "findings": [],
            "rawOutput": None,
            "exitCode": None,
            "errorMessage": message,
            "startedAt": now,
            "finishedAt": now,
        },
    )
    db.flush()


def _resolve_provider(db: Session, project: Project, profile, target_type: str | None = None):
    provider_code = None
    if target_type:
        from app.project_integration.repository import find_target_config

        target_config = find_target_config(db, project.id, target_type)
        provider_code = target_config.provider_code if target_config else None
    if not provider_code:
        provider_code = project.default_code_quality_provider_code
    if not provider_code:
        from app.project_integration.models import ProjectGroup

        group = db.get(ProjectGroup, project.group_id) if project.group_id else None
        provider_code = group.default_provider_code if group else None
    if not provider_code:
        provider_code = profile.provider_code
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
    files = _changed_files_from_task_event(db, task)
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


def _changed_files_from_task_event(db: Session, task: ReviewTask) -> list[dict[str, Any]]:
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
    return files if isinstance(files, list) else []


def _find_changed_file_for_finding(changed_files: list[dict[str, Any]], finding: dict[str, Any]) -> dict[str, Any] | None:
    target = _normalize_path(finding.get("filePath"))
    if not target:
        return None
    for file in changed_files:
        if not isinstance(file, dict):
            continue
        candidates = [
            _normalize_path(file.get("path")),
            _normalize_path(file.get("newPath")),
            _normalize_path(file.get("oldPath")),
        ]
        if any(candidate == target or candidate.endswith(f"/{target}") or target.endswith(f"/{candidate}") for candidate in candidates if candidate):
            return file
    return None


def _normalize_path(value: Any) -> str:
    text = str(value or "").replace("\\", "/").lstrip("/")
    if text.startswith("a/") or text.startswith("b/"):
        text = text[2:]
    return text


def _single_file_diff_text(file: dict[str, Any]) -> str:
    diff = file.get("diffText") or ""
    if not diff:
        return ""
    path = file.get("path") or file.get("newPath") or file.get("oldPath") or "file"
    old_path = file.get("oldPath") or path
    new_path = file.get("newPath") or path
    if str(diff).lstrip().startswith("diff --git "):
        return str(diff)
    header = f"diff --git a/{old_path} b/{new_path}\n--- a/{old_path}\n+++ b/{new_path}"
    return f"{header}\n{diff}"


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


def _enabled(db: Session | None = None) -> bool:
    if db is None:
        from app.core.config import get_settings

        return get_settings().code_quality_review_enabled
    return bool(get_settings_record(db).review_enabled)


def _inline_enabled() -> bool:
    return (
        os.getenv("CODE_QUALITY_REVIEW_INLINE", "false").lower() == "true"
        or os.getenv("CODE_QUALITY_RETRY_INLINE", "false").lower() == "true"
    )


def _fix_preview_inline_enabled() -> bool:
    return os.getenv("CODE_QUALITY_FIX_PREVIEW_INLINE", "false").lower() == "true"
