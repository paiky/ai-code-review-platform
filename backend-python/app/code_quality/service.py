from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from fnmatch import fnmatchcase
import hashlib
import json
import os
from itertools import count
from queue import PriorityQueue
from threading import Lock, Thread
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.code_quality import prompt
from app.code_quality.providers import run_fix_provider, run_provider, test_provider_connection
from app.code_quality.rule_gap_dashboard import get_rule_gap_dashboard
from app.code_quality.refinement_repository import (
    find_refinement,
    list_refinement_responses,
    refinement_to_response,
    upsert_refinement,
)
from app.code_quality.repository import (
    append_progress,
    cancel_active_scheduler_jobs_for_task,
    cancel_scheduler_job,
    create_provider,
    create_standard_model_connection,
    create_scheduler_job,
    delete_provider,
    delete_fix_previews,
    delete_progress,
    find_push_gate_decision,
    find_fix_preview_response,
    find_result_response,
    find_result_response_by_key,
    get_profile,
    get_provider,
    get_settings_record,
    has_recent_allowed_push_gate,
    list_ai_review_failure_notifications,
    list_result_responses,
    list_progress,
    list_fix_preview_responses,
    list_provider_responses,
    list_scheduler_queue_snapshot,
    mark_scheduler_job_finished,
    mark_scheduler_job_running,
    push_gate_to_dict,
    mark_stale_running_as_failed,
    normalize_auto_fix_preview_severities,
    progress_review_key,
    reset_default_prompt,
    save_fix_preview,
    save_push_gate_decision,
    save_result,
    scrub_sensitive,
    set_default_provider,
    settings_to_dict,
    update_profile,
    update_provider,
    update_settings_record,
)
from app.code_quality.scheduler_config import PROVIDER_SCHEDULER_CAPACITY
from app.core.database import SessionLocal
from app.core.errors import AppError
from app.core.json_utils import read_json, utc_now
from app.deterministic_checks.service import ensure_deterministic_preflight
from app.code_quality.models import (
    CodeQualityModelProvider,
    CodeQualityReviewResult,
    CodeQualitySchedulerJob,
)
from app.project_integration.models import GitLabMergeRequestEvent, GitLabPushEvent, Project
from app.project_integration.repository import (
    find_project_by_id,
    get_project_group_ai_review_policy,
    list_project_group_ai_review_models,
    make_ai_review_model_key,
    resolve_project_target_config,
)
from app.project_review_policy.service import build_project_review_policy_prompt_context
from app.review_context.service import build_review_context_pack
from app.notification.service import send_review_summary
from app.review_record.models import ReviewTask
from app.review_record.repository import (
    create_review_task,
    mark_task_failed,
    mark_task_success,
    refresh_review_status,
    save_notification_records,
)
from app.review_feedback.service import ai_finding_fingerprint


REVIEW_JOB_PRIORITY = 10
FIX_PREVIEW_JOB_PRIORITY = 50
REFINEMENT_ALLOWED_SEVERITIES = {"CRITICAL", "MAJOR", "HIGH"}
REFINEMENT_ALLOWED_CONTEXT_STATUSES = {"PARTIAL", "INSUFFICIENT"}
SCHEDULER_MAX_WORKERS = PROVIDER_SCHEDULER_CAPACITY


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
                    if not mark_scheduler_job_running(db, job_id):
                        db.commit()
                        continue
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


def _running_result_payload() -> dict[str, Any]:
    return {
        "status": "RUNNING",
        "overallLevel": None,
        "summary": None,
        "findings": [],
        "rawOutput": None,
        "exitCode": None,
        "errorMessage": None,
        "startedAt": None,
        "finishedAt": None,
    }


def _aggregate_review_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {"status": "SKIPPED", "findings": [], "overallLevel": None}
    if any(result.get("status") == "SUCCESS" for result in results):
        primary = next(result for result in results if result.get("status") == "SUCCESS")
        return {
            **primary,
            "status": "SUCCESS",
            "findings": [finding for result in results for finding in (result.get("findings") or [])],
        }
    return results[0]


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
    review_key: str | None = None,
) -> int:
    job = create_scheduler_job(
        db,
        job_type=job_type,
        task_id=task_id,
        project_id=project_id,
        review_key=review_key,
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
    preflight_summary = ensure_deterministic_preflight(
        db,
        task_id,
        changed_files=_manual_preflight_changed_files(request),
    )
    request = {**request, "_deterministicPreflightSummary": preflight_summary}
    if response.get("effectiveEngine") == "AGENT":
        from app.agent_review.service import enqueue_agent_review

        task = db.get(ReviewTask, task_id)
        project = find_project_by_id(db, int(response["projectId"]))
        profile = _resolve_profile(db, response["profileCode"], project)
        try:
            agent_response = enqueue_agent_review(
                db,
                task=task,
                project=project,
                profile=profile,
                request=_build_review_request(profile, request),
                comparison_mode=bool(request.get("comparisonMode")),
            )
            return {**agent_response, "reviews": list_result_responses(db, task_id)}
        except AppError as exception:
            if exception.code not in {"AGENT_NO_REVIEWABLE_FILES", "AGENT_SAFE_DIFF_UNAVAILABLE"}:
                raise
            _save_agent_sensitive_path_skip(
                db,
                task=task,
                project=project,
                profile=profile,
                changed_files=_changed_file_paths(request.get("changedFiles") or []),
                failure_code=exception.code,
            )
            return {
                "taskId": task.id,
                "projectId": project.id,
                "status": "SKIPPED",
                "profileCode": profile.profile_code,
                "provider": "DEEPSEEK",
                "reviewKey": "agent-claude-code-deepseek-v4-pro",
                "requestedEngine": "AGENT",
                "effectiveEngine": "AGENT",
                "overallLevel": None,
                "findingCount": 0,
                "reviews": list_result_responses(db, task_id),
            }
    if response.get("effectiveEngine") == "STANDARD_FALLBACK":
        request = {
            **request,
            "requestedEngine": "AGENT",
            "effectiveEngine": "STANDARD_FALLBACK",
        }
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
            "reviews": list_result_responses(db, task_id),
        }
    for review in response.get("reviews") or [response]:
        _submit_provider_job(
            db,
            run_manual_review_target_job,
            task_id,
            dict(request),
            review.get("reviewKey"),
            review.get("provider"),
            review.get("model"),
            review.get("displayName"),
            int(review.get("sortOrder") or 0),
            job_type="AI_REVIEW",
            task_id=task_id,
            project_id=request.get("projectId"),
            priority=REVIEW_JOB_PRIORITY,
            label=f"手动 AI Review - {review.get('displayName') or review.get('provider')}",
            review_key=review.get("reviewKey"),
        )
    db.commit()
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
    from app.agent_review.service import resolve_review_engine

    resolved_engine = resolve_review_engine(
        db,
        project,
        request.get("reviewEngine"),
        explicit="reviewEngine" in request,
    )
    fallback_to_standard = resolved_engine == "AGENT_UNAVAILABLE"
    requested_engine = "AGENT" if fallback_to_standard else resolved_engine
    effective_engine = "STANDARD_FALLBACK" if fallback_to_standard else resolved_engine
    execution_engine = "STANDARD" if fallback_to_standard else resolved_engine
    targets = (
        _resolve_review_targets(db, project, profile, target_config["targetType"])
        if execution_engine == "STANDARD"
        else []
    )
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
        f"engine={requested_engine}->{effective_engine}, models={len(targets)}, profile={profile.profile_code}",
    )
    queued_reviews = []
    for target in targets:
        review_request = _build_review_request(profile, {**request, "model": target["model"]})
        review_request["reviewKey"] = target["reviewKey"]
        save_result(
            db,
            task_id=task.id,
            review_key=target["reviewKey"],
            project_id=project.id,
            profile_code=profile.profile_code,
            provider=target["provider"].provider_code,
            model=review_request.get("model") or target["provider"].model_name,
            display_name=target["displayName"],
            sort_order=target["sortOrder"],
            result=_running_result_payload(),
        )
        queued_reviews.append(
            {
                "reviewKey": target["reviewKey"],
                "profileCode": profile.profile_code,
                "provider": target["provider"].provider_code,
                "model": review_request.get("model") or target["provider"].model_name,
                "displayName": target["displayName"],
                "sortOrder": target["sortOrder"],
                "status": "RUNNING",
                "findingCount": 0,
            }
        )
    db.commit()
    if execution_engine == "AGENT":
        return {
            "taskId": task.id,
            "projectId": project.id,
            "status": "RUNNING",
            "profileCode": profile.profile_code,
            "provider": "DEEPSEEK",
            "reviewKey": "agent:claude-code:deepseek-v4-pro",
            "requestedEngine": "AGENT",
            "effectiveEngine": "AGENT",
            "overallLevel": None,
            "findingCount": 0,
            "reviews": [],
        }
    first_review = queued_reviews[0]
    return {
        "taskId": task.id,
        "projectId": project.id,
        "status": "RUNNING",
        "profileCode": first_review["profileCode"],
        "provider": first_review["provider"],
        "reviewKey": first_review["reviewKey"],
        "overallLevel": None,
        "findingCount": 0,
        "requestedEngine": requested_engine,
        "effectiveEngine": effective_engine,
        "reviews": queued_reviews,
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


def run_manual_review_target_job(
    task_id: int,
    request: dict[str, Any],
    review_key: str | None,
    provider_code: str | None,
    model: str | None,
    display_name: str | None,
    sort_order: int,
) -> dict[str, Any]:
    db = SessionLocal()
    try:
        task = db.get(ReviewTask, task_id)
        if task is None:
            raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)
        project = find_project_by_id(db, task.project_id)
        if project is None:
            raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {task.project_id}", 404)
        profile = _resolve_profile(db, request.get("profileCode") or task.code_quality_profile_code, project)
        provider = get_provider(db, provider_code)
        review_request = _build_review_request(profile, {**request, "model": model})
        review_request["reviewKey"] = review_key
        result = _run_review(
            db,
            task.id,
            project,
            profile,
            provider,
            review_request,
            {"reviewKey": review_key, "displayName": display_name, "sortOrder": sort_order},
        )
        db.commit()
        return result
    except Exception as exception:
        task = db.get(ReviewTask, task_id)
        if task is not None:
            _sync_task_status_after_review(db, task_id, {"status": "FAILED", "errorMessage": str(exception)})
            append_progress(db, task_id, "FAILED", "ERROR", "手动 AI Review 后台执行失败", str(exception), review_key=review_key)
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
    targets = _resolve_review_targets(db, project, profile, task.target_type)
    results = []
    for target in targets:
        review_request = _build_review_request(profile, {**request, "model": target["model"]})
        review_request["reviewKey"] = target["reviewKey"]
        results.append(_run_review(db, task.id, project, profile, target["provider"], review_request, target))
    return _aggregate_review_results(results)


def retry_review_task(db: Session, task_id: int, request: dict[str, Any] | None = None) -> dict[str, Any]:
    request = request or {}
    task = db.get(ReviewTask, task_id)
    if task is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)
    project = find_project_by_id(db, task.project_id)
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {task.project_id}", 404)
    from app.agent_review.service import enqueue_agent_review, resolve_review_engine

    requested_engine = resolve_review_engine(
        db,
        project,
        request.get("reviewEngine"),
        explicit=request.get("reviewEngine") is not None,
    )
    if requested_engine == "AGENT":
        profile = _resolve_profile(db, task.code_quality_profile_code, project)
        preflight_summary = ensure_deterministic_preflight(db, task_id)
        review_request = _request_from_task_event(db, task, profile)
        review_request["_deterministicPreflightSummary"] = preflight_summary
        response = enqueue_agent_review(
            db,
            task=task,
            project=project,
            profile=profile,
            request=review_request,
            comparison_mode=True,
        )
        return {**response, "reviews": list_result_responses(db, task_id)}
    review_key = (request or {}).get("reviewKey")
    response = enqueue_retry_review(db, task_id, review_key=review_key)
    preflight_summary = ensure_deterministic_preflight(db, task_id, review_key=review_key)
    if _inline_enabled():
        result = run_retry_review_now(
            db,
            task_id,
            review_key=review_key,
            preflight_summary=preflight_summary,
        )
        db.commit()
        return {
            "taskId": task_id,
            "status": result["status"],
            "profileCode": response["profileCode"],
            "provider": response["provider"],
            "overallLevel": result.get("overallLevel"),
            "findingCount": len(result.get("findings") or []),
            "reviews": list_result_responses(db, task_id),
        }
    for review in response.get("reviews") or [response]:
        _submit_provider_job(
            db,
            run_retry_review_target_job,
            task_id,
            review.get("reviewKey"),
            review.get("provider"),
            review.get("model"),
            review.get("displayName"),
            int(review.get("sortOrder") or 0),
            preflight_summary,
            job_type="AI_REVIEW",
            task_id=task_id,
            project_id=response.get("projectId"),
            priority=REVIEW_JOB_PRIORITY,
            label=f"重试 AI Review - {review.get('displayName') or review.get('provider')}",
            review_key=review.get("reviewKey"),
        )
    db.commit()
    return response


def enqueue_retry_review(db: Session, task_id: int, review_key: str | None = None) -> dict[str, Any]:
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
    targets = _resolve_review_targets(db, project, profile, task.target_type)
    if review_key:
        targets = [target for target in targets if target["reviewKey"] == review_key]
        if not targets:
            raise AppError("BAD_REQUEST", f"Review model not found for task {task_id}: {review_key}", 400)
    delete_progress(db, task.id, review_key=review_key)
    delete_fix_previews(db, task.id, review_key=review_key)
    queued_reviews = []
    for target in targets:
        provider = target["provider"]
        request = _request_from_task_event(db, task, profile)
        request["model"] = target["model"]
        request["reviewKey"] = target["reviewKey"]
        append_progress(
            db,
            task.id,
            "QUEUED",
            "INFO",
            "AI Review 已进入执行队列",
            f"provider={provider.provider_code}, profile={profile.profile_code}",
            review_key=target["reviewKey"],
        )
        save_result(
            db,
            task_id=task.id,
            review_key=target["reviewKey"],
            project_id=project.id,
            profile_code=profile.profile_code,
            provider=provider.provider_code,
            model=request.get("model") or provider.model_name,
            display_name=target["displayName"],
            sort_order=target["sortOrder"],
            result=_running_result_payload(),
        )
        queued_reviews.append(
            {
                "reviewKey": target["reviewKey"],
                "profileCode": profile.profile_code,
                "provider": provider.provider_code,
                "model": request.get("model") or provider.model_name,
                "displayName": target["displayName"],
                "sortOrder": target["sortOrder"],
                "status": "RUNNING",
                "findingCount": 0,
            }
        )
    db.commit()
    first_review = queued_reviews[0]
    return {
        "taskId": task.id,
        "projectId": project.id,
        "status": "RUNNING",
        "profileCode": first_review["profileCode"],
        "provider": first_review["provider"],
        "reviewKey": first_review["reviewKey"],
        "overallLevel": None,
        "findingCount": 0,
        "reviews": queued_reviews,
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


def run_retry_review_target_job(
    task_id: int,
    review_key: str | None,
    provider_code: str | None,
    model: str | None,
    display_name: str | None,
    sort_order: int,
    preflight_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    db = SessionLocal()
    try:
        task = db.get(ReviewTask, task_id)
        if task is None:
            raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)
        project = find_project_by_id(db, task.project_id)
        if project is None:
            raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {task.project_id}", 404)
        profile = _resolve_profile(db, task.code_quality_profile_code, project)
        provider = get_provider(db, provider_code)
        request = _request_from_task_event(db, task, profile)
        request["model"] = model
        request["reviewKey"] = review_key
        request["_deterministicPreflightSummary"] = preflight_summary
        result = _run_review(
            db,
            task.id,
            project,
            profile,
            provider,
            request,
            {
                "reviewKey": review_key,
                "displayName": display_name,
                "sortOrder": sort_order,
            },
        )
        db.commit()
        return result
    except Exception as exception:
        task = db.get(ReviewTask, task_id)
        review_result = find_result_response_by_key(db, task_id, review_key)
        if task is not None and (review_result or {}).get("status") != "SUCCESS":
            _sync_task_status_after_review(db, task_id, {"status": "FAILED", "errorMessage": str(exception)})
            append_progress(db, task_id, "FAILED", "ERROR", "AI Review 后台执行失败", str(exception), review_key=review_key)
        db.commit()
        return {"status": "FAILED", "errorMessage": str(exception)}
    finally:
        db.close()


def run_retry_review_now(
    db: Session,
    task_id: int,
    review_key: str | None = None,
    preflight_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task = db.get(ReviewTask, task_id)
    if task is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)
    project = find_project_by_id(db, task.project_id)
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {task.project_id}", 404)
    profile = _resolve_profile(db, task.code_quality_profile_code, project)
    targets = _resolve_review_targets(db, project, profile, task.target_type)
    if review_key:
        targets = [target for target in targets if target["reviewKey"] == review_key]
        if not targets:
            raise AppError("BAD_REQUEST", f"Review model not found for task {task_id}: {review_key}", 400)
    results = []
    for target in targets:
        request = _request_from_task_event(db, task, profile)
        request["model"] = target["model"]
        request["reviewKey"] = target["reviewKey"]
        request["_deterministicPreflightSummary"] = preflight_summary
        results.append(_run_review(db, task.id, project, profile, target["provider"], request, target))
    return _aggregate_review_results(results)


def _agent_preflight_fallback_metadata(
    db: Session,
    *,
    task_id: int,
    exception: AppError,
) -> dict[str, Any]:
    failure_code = str(exception.code or "AGENT_UNAVAILABLE")[:64]
    failure_message = (
        scrub_sensitive(str(exception.message or "Agent Review preflight failed"))
        or "Agent Review preflight failed"
    )[:1000]
    summary = {
        "status": "UNAVAILABLE",
        "fallbackTriggered": True,
        "failureCode": failure_code,
        "failureMessage": failure_message,
    }
    append_progress(
        db,
        task_id,
        "AGENT_PREFLIGHT_FAILED",
        "WARN",
        "Agent Review 入队前检查失败，准备执行普通 Review 降级",
        json.dumps(summary, ensure_ascii=False),
    )
    return {
        "requestedEngine": "AGENT",
        "effectiveEngine": "STANDARD_FALLBACK",
        "agentRunSummary": summary,
    }


@contextmanager
def _auto_fallback_failure_guard(
    db: Session,
    task: ReviewTask,
    *,
    enabled: bool,
):
    try:
        yield
    except Exception:
        if enabled:
            _mark_auto_fallback_schedule_failed(db, int(task.id))
        raise


def _mark_auto_fallback_schedule_failed(db: Session, task_id: int) -> None:
    db.rollback()
    try:
        persisted_fallback_result = db.scalar(
            select(CodeQualityReviewResult.id)
            .where(CodeQualityReviewResult.task_id == task_id)
            .where(CodeQualityReviewResult.requested_engine == "AGENT")
            .where(CodeQualityReviewResult.effective_engine == "STANDARD_FALLBACK")
            .limit(1)
        )
        if persisted_fallback_result is not None:
            return
        task = db.get(ReviewTask, task_id)
        if task is not None:
            task.review_status = "REVIEW_FAILED"
            task.updated_at = datetime.now()
        db.commit()
    except Exception:
        db.rollback()


def _save_agent_sensitive_path_skip(
    db: Session,
    *,
    task: ReviewTask,
    project: Project,
    profile: Any,
    changed_files: list[str],
    failure_code: str,
) -> None:
    from app.agent_review.repository import AGENT_MODEL, AGENT_REVIEW_KEY

    excluded_paths = [
        str(path or "").strip().replace("\\", "/")
        for path in changed_files
        if str(path or "").strip()
    ]
    summary = {
        "status": "SKIPPED",
        "fallbackTriggered": False,
        "failureCode": failure_code,
        "failureMessage": "没有可安全发送给 Agent 的变更文件，已停止外部模型审查",
        "totalChangedFileCount": len(excluded_paths),
        "includedFileCount": 0,
        "excludedFileCount": len(excluded_paths),
        "excludedPaths": excluded_paths,
    }
    save_result(
        db,
        task_id=task.id,
        review_key=AGENT_REVIEW_KEY,
        project_id=project.id,
        profile_code=profile.profile_code,
        provider="DEEPSEEK",
        model=AGENT_MODEL,
        display_name="Agent · 安全跳过",
        sort_order=5,
        result={
            "status": "SKIPPED",
            "overallLevel": None,
            "summary": summary["failureMessage"],
            "findings": [],
            "rawOutput": None,
            "exitCode": None,
            "errorMessage": summary["failureMessage"],
            "startedAt": utc_now(),
            "finishedAt": utc_now(),
            "requestedEngine": "AGENT",
            "effectiveEngine": "AGENT",
            "agentRunSummary": summary,
        },
    )
    append_progress(
        db,
        task.id,
        "AGENT_ALL_PATHS_EXCLUDED",
        "WARN",
        "全部变更文件均被敏感路径策略排除，未发送给外部模型",
        json.dumps(summary, ensure_ascii=False),
        review_key=AGENT_REVIEW_KEY,
    )
    refresh_review_status(db, task.id)
    db.commit()


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
    if list_result_responses(db, task_id):
        return False
    profile = _resolve_auto_profile_or_save_failure(db, task, project)
    if profile is None:
        return False
    ai_policy = get_project_group_ai_review_policy(db, project)
    if not profile.enabled or not ai_policy.get("aiReviewEnabled") or not ai_policy.get("triggerOnMr"):
        return False
    targets = _resolve_review_targets(db, project, profile, task.target_type)
    base_request = {
        "mode": "DIFF_TEXT",
        "baseRef": task.target_branch,
        "commitSha": task.commit_sha,
        "title": f"{task.trigger_type} {task.external_source_id or ''}".strip(),
        "diffText": diff_text or _diff_text(changed_files),
        "changedFiles": [file.get("path") for file in changed_files if file.get("path")],
        "changedFileDetails": changed_files,
    }
    delete_progress(db, task.id)
    task.review_status = "REVIEWING"
    task.updated_at = datetime.now()
    preflight_summary = ensure_deterministic_preflight(db, task.id, changed_files=changed_files)
    from app.agent_review.service import enqueue_agent_review, resolve_review_engine

    selected_engine = resolve_review_engine(db, project, explicit=False)
    fallback_metadata: dict[str, Any] = {}
    if selected_engine == "AGENT":
        agent_request = _build_review_request(profile, base_request)
        agent_request["_deterministicPreflightSummary"] = preflight_summary
        try:
            enqueue_agent_review(
                db,
                task=task,
                project=project,
                profile=profile,
                request=agent_request,
                completion_context={
                    "autoNotification": True,
                    "ruleResultId": rule_result_id,
                    "riskCard": risk_card,
                    "focusChangeTypes": focus_change_types,
                    "focusRuleCodes": focus_rule_codes,
                    "notificationContext": notification_context,
                    "reminderCardEnabled": reminder_card_enabled,
                },
            )
            return True
        except AppError as exception:
            if exception.code in {"AGENT_NO_REVIEWABLE_FILES", "AGENT_SAFE_DIFF_UNAVAILABLE"}:
                _save_agent_sensitive_path_skip(
                    db,
                    task=task,
                    project=project,
                    profile=profile,
                    changed_files=base_request["changedFiles"],
                    failure_code=exception.code,
                )
                return True
            fallback_metadata = _agent_preflight_fallback_metadata(
                db,
                task_id=task.id,
                exception=exception,
            )
    with _auto_fallback_failure_guard(db, task, enabled=bool(fallback_metadata)):
        for target in targets:
            provider = target["provider"]
            request = _build_review_request(
                profile,
                {**base_request, "model": target["model"]},
            )
            request["reviewKey"] = target["reviewKey"]
            request["_deterministicPreflightSummary"] = preflight_summary
            request.update(fallback_metadata)
            append_progress(
                db,
                task.id,
                "QUEUED",
                "INFO",
                "AI Review 已进入执行队列",
                f"provider={provider.provider_code}, profile={profile.profile_code}",
                review_key=target["reviewKey"],
            )
            save_result(
                db,
                task_id=task.id,
                review_key=target["reviewKey"],
                project_id=project.id,
                profile_code=profile.profile_code,
                provider=provider.provider_code,
                model=request.get("model") or provider.model_name,
                display_name=target["displayName"],
                sort_order=target["sortOrder"],
                result=_running_result_payload(),
            )
            if _inline_enabled():
                result = _run_review(db, task.id, project, profile, provider, request, target)
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
                continue
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
                target,
                job_type="AI_REVIEW",
                task_id=task.id,
                project_id=project.id,
                priority=REVIEW_JOB_PRIORITY,
                label=f"MR AI Review - {target['displayName']}",
                review_key=target["reviewKey"],
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
    if list_result_responses(db, task.id):
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
    targets = _resolve_review_targets(db, project, profile, task.target_type)
    primary_provider = targets[0]["provider"]
    gate = _evaluate_push_gate(
        db,
        task=task,
        profile=profile,
        push_policy=ai_policy,
        provider_code=primary_provider.provider_code,
        changed_files=changed_files,
        diff_text=diff_text,
        risk_card=risk_card,
        focus_change_types=focus_change_types,
        focus_rule_codes=focus_rule_codes,
    )
    if gate["decision"] != "ALLOWED":
        save_push_gate_decision(db, **gate)
        task.review_status = "SKIPPED"
        return False

    request_diff_text = diff_text or _diff_text(changed_files)
    base_request = {
        "mode": "DIFF_TEXT",
        "baseRef": task.source_branch,
        "commitSha": task.commit_sha,
        "title": f"{task.trigger_type} {task.external_source_id or ''}".strip(),
        "diffText": request_diff_text,
        "changedFiles": [file.get("path") for file in changed_files if file.get("path")],
        "changedFileDetails": changed_files,
    }
    delete_progress(db, task.id)
    task.review_status = "REVIEWING"
    task.updated_at = datetime.now()
    preflight_summary = ensure_deterministic_preflight(db, task.id, changed_files=changed_files)
    gate["ai_review_scheduled"] = True
    save_push_gate_decision(db, **gate)
    from app.agent_review.service import enqueue_agent_review, resolve_review_engine

    selected_engine = resolve_review_engine(db, project, explicit=False)
    fallback_metadata: dict[str, Any] = {}
    if selected_engine == "AGENT":
        agent_request = _build_review_request(profile, base_request)
        agent_request["_deterministicPreflightSummary"] = preflight_summary
        try:
            enqueue_agent_review(
                db,
                task=task,
                project=project,
                profile=profile,
                request=agent_request,
                completion_context={
                    "autoNotification": True,
                    "ruleResultId": rule_result_id,
                    "riskCard": risk_card,
                    "focusChangeTypes": focus_change_types,
                    "focusRuleCodes": focus_rule_codes,
                    "notificationContext": notification_context,
                    "reminderCardEnabled": reminder_card_enabled,
                },
            )
            return True
        except AppError as exception:
            if exception.code in {"AGENT_NO_REVIEWABLE_FILES", "AGENT_SAFE_DIFF_UNAVAILABLE"}:
                _save_agent_sensitive_path_skip(
                    db,
                    task=task,
                    project=project,
                    profile=profile,
                    changed_files=base_request["changedFiles"],
                    failure_code=exception.code,
                )
                return True
            fallback_metadata = _agent_preflight_fallback_metadata(
                db,
                task_id=task.id,
                exception=exception,
            )
    with _auto_fallback_failure_guard(db, task, enabled=bool(fallback_metadata)):
        for target in targets:
            provider = target["provider"]
            request = _build_review_request(
                profile,
                {**base_request, "model": target["model"]},
            )
            request["reviewKey"] = target["reviewKey"]
            request["_deterministicPreflightSummary"] = preflight_summary
            request.update(fallback_metadata)
            append_progress(
                db,
                task.id,
                "QUEUED",
                "INFO",
                "Push AI Review 已通过自动审核并进入队列",
                f"reasonCode={gate['reason_code']}, provider={provider.provider_code}, profile={profile.profile_code}",
                review_key=target["reviewKey"],
            )
            save_result(
                db,
                task_id=task.id,
                review_key=target["reviewKey"],
                project_id=project.id,
                profile_code=profile.profile_code,
                provider=provider.provider_code,
                model=request.get("model") or provider.model_name,
                display_name=target["displayName"],
                sort_order=target["sortOrder"],
                result=_running_result_payload(),
            )
            if _inline_enabled():
                result = _run_review(db, task.id, project, profile, provider, request, target)
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
                continue
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
                target,
                job_type="AI_REVIEW",
                task_id=task.id,
                project_id=project.id,
                priority=REVIEW_JOB_PRIORITY,
                label=f"Push AI Review - {target['displayName']}",
                review_key=target["reviewKey"],
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
    target: dict[str, Any] | None = None,
) -> dict[str, Any]:
    db = SessionLocal()
    try:
        project = find_project_by_id(db, project_id)
        if project is None:
            task = db.get(ReviewTask, task_id)
            if task is not None:
                mark_task_failed(task, f"Project not found: {project_id}")
            append_progress(db, task_id, "FAILED", "ERROR", "AI Review 后台执行失败", f"Project not found: {project_id}", review_key=request.get("reviewKey"))
            db.commit()
            return {"status": "FAILED", "errorMessage": f"Project not found: {project_id}"}
        profile = get_profile(db, profile_code)
        provider = get_provider(db, provider_code)
        result = _run_review(db, task_id, project, profile, provider, request, target)
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
        task = db.get(ReviewTask, task_id)
        if task is not None:
            _sync_task_status_after_review(db, task_id, {"status": "FAILED", "errorMessage": str(exception)})
        append_progress(db, task_id, "FAILED", "ERROR", "AI Review 后台执行失败", str(exception), review_key=request.get("reviewKey"))
        db.commit()
        return {"status": "FAILED", "errorMessage": str(exception)}
    finally:
        db.close()


def schedule_agent_standard_fallback(db: Session, run_id: int) -> None:
    """Queue the existing STANDARD pipeline for a failed Agent run."""
    from app.agent_review.models import AgentReviewRun

    run = db.get(AgentReviewRun, run_id)
    if run is None or run.status == "CANCELLED":
        return
    task = db.get(ReviewTask, run.task_id)
    if task is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Agent fallback task not found: {run.task_id}", 404)
    existing_job_id = db.scalar(
        select(CodeQualitySchedulerJob.id)
        .where(CodeQualitySchedulerJob.job_type == "AI_REVIEW")
        .where(CodeQualitySchedulerJob.task_id == run.task_id)
        .where(CodeQualitySchedulerJob.review_key == run.review_key)
        .where(CodeQualitySchedulerJob.label == "Agent Review 降级 - Standard")
        .limit(1)
    )
    if existing_job_id is not None:
        return
    _submit_provider_job(
        db,
        run_agent_standard_fallback_job,
        run_id,
        job_type="AI_REVIEW",
        task_id=run.task_id,
        project_id=task.project_id,
        priority=REVIEW_JOB_PRIORITY,
        label="Agent Review 降级 - Standard",
        review_key=run.review_key,
    )
    append_progress(
        db,
        run.task_id,
        "AGENT_FALLBACK_QUEUED",
        "WARN",
        "Agent Review 租约或执行失败，已进入普通 Review 降级队列",
        json.dumps({"runId": run.id, "failureCode": run.failure_code}, ensure_ascii=False),
        review_key=run.review_key,
    )
    db.commit()


def list_unscheduled_agent_standard_fallback_run_ids(db: Session) -> list[int]:
    """Find terminal Agent runs whose persisted STANDARD fallback job was never created."""
    from app.agent_review.models import AgentReviewRun

    runs = db.scalars(
        select(AgentReviewRun)
        .where(AgentReviewRun.status.in_(["FAILED", "TIMED_OUT"]))
        .where(AgentReviewRun.effective_engine == "STANDARD_FALLBACK")
        .where(AgentReviewRun.input_json.is_not(None))
        .order_by(AgentReviewRun.id.asc())
    ).all()
    pending: list[int] = []
    for run in runs:
        existing_job_id = db.scalar(
            select(CodeQualitySchedulerJob.id)
            .where(CodeQualitySchedulerJob.job_type == "AI_REVIEW")
            .where(CodeQualitySchedulerJob.task_id == run.task_id)
            .where(CodeQualitySchedulerJob.review_key == run.review_key)
            .where(CodeQualitySchedulerJob.label == "Agent Review 降级 - Standard")
            .limit(1)
        )
        if existing_job_id is None:
            pending.append(int(run.id))
    return pending


def run_agent_standard_fallback_job(run_id: int) -> dict[str, Any]:
    from app.agent_review.models import AgentReviewRun
    from app.agent_review.repository import run_to_summary

    db = SessionLocal()
    try:
        run = db.get(AgentReviewRun, run_id)
        if run is None:
            raise AppError("RESOURCE_NOT_FOUND", f"Agent Review run not found: {run_id}", 404)
        task = db.get(ReviewTask, run.task_id)
        if task is None:
            raise AppError("RESOURCE_NOT_FOUND", "Agent fallback task or project no longer exists", 404)
        project = find_project_by_id(db, task.project_id)
        if project is None:
            raise AppError("RESOURCE_NOT_FOUND", "Agent fallback task or project no longer exists", 404)
        profile = _resolve_profile(db, task.code_quality_profile_code, project)
        target = _resolve_review_targets(db, project, profile, task.target_type)[0]
        input_payload = read_json(run.input_json, {})
        case = input_payload.get("case") if isinstance(input_payload, dict) else {}
        request = _build_review_request(
            profile,
            {
                "mode": "DIFF_TEXT",
                "baseRef": case.get("baseRef") or task.target_branch,
                "commitSha": case.get("commitSha") or task.commit_sha,
                "title": case.get("title"),
                "diffText": case.get("diff") or "",
                "changedFiles": case.get("changedFiles") or [],
                "model": target["model"],
            },
        )
        request.update(
            {
                "reviewKey": run.review_key,
                "requestedEngine": "AGENT",
                "effectiveEngine": "STANDARD_FALLBACK",
                "agentRunId": run.id,
                "agentRunSummary": run_to_summary(run, fallback_triggered=True),
            }
        )
        result = _run_review(
            db,
            task.id,
            project,
            profile,
            target["provider"],
            request,
            {**target, "reviewKey": run.review_key, "displayName": "Agent 降级 · Standard"},
        )
        context = read_json(run.completion_context_json, {})
        if not run.comparison_mode and context.get("autoNotification"):
            _send_auto_review_notification(
                db,
                task.id,
                result,
                context.get("ruleResultId"),
                context.get("riskCard"),
                context.get("focusChangeTypes") or [],
                context.get("focusRuleCodes") or [],
                context.get("notificationContext") or {},
                bool(context.get("reminderCardEnabled", True)),
            )
        run.input_json = None
        db.commit()
        return result
    except Exception as exception:
        db.rollback()
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
    task.review_status = "SKIPPED"
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
            "label": "Debounce 不限制" if debounce_seconds <= 0 else f"{debounce_seconds} 秒内同项目同分支仅触发一次",
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
            "detail": _push_hard_limit_detail(push_policy),
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
    large_change = _matches_push_size_policy(metrics, push_policy)
    large_change_detail = _push_large_change_detail(metrics, push_policy)
    matched_rules.append({"code": "riskMatched", "label": "命中高风险或重点提醒", "matched": risk_matched})
    matched_rules.append(
        {
            "code": "largeChange",
            "label": "满足 Push 策略指标",
            "matched": large_change,
            "detail": large_change_detail,
        }
    )
    if large_change:
        return _push_gate_payload(
            task,
            profile.profile_code,
            provider_code,
            "ALLOWED",
            False,
            "LARGE_CHANGE",
            f"Push 审核策略已满足，允许进入 AI Review：{_push_large_change_summary(metrics, push_policy)}。",
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
        f"本次 Push 未满足自动 AI Review 的 Push 审核策略：{large_change_detail}",
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
        "newBranchPush": _changed_files_bool_metadata(changed_files, "newBranchPush"),
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
    return _changed_files_metadata(changed_files, "source")


def _changed_files_metadata(changed_files: list[dict[str, Any]], field: str) -> str | None:
    for file in changed_files:
        if isinstance(file, dict) and file.get(field):
            return str(file[field])
    return None


def _changed_files_bool_metadata(changed_files: list[dict[str, Any]], field: str) -> bool:
    return any(isinstance(file, dict) and bool(file.get(field)) for file in changed_files)


def _branch_matches(branch_name: str | None, patterns: list[str]) -> bool:
    if not patterns:
        return True
    if not branch_name:
        return False
    return any(fnmatchcase(branch_name, pattern) for pattern in patterns)


def _over_limit(value: int, limit: int | None) -> bool:
    return limit is not None and limit >= 0 and value > limit


def _reaches_threshold(value: int, threshold: int | None) -> bool:
    return threshold is None or threshold < 0 or value >= threshold


def _matches_push_size_policy(metrics: dict[str, Any], push_policy: dict[str, Any]) -> bool:
    return (
        _reaches_threshold(int(metrics.get("changedFileCount") or 0), push_policy.get("pushMinChangedFiles"))
        and _reaches_threshold(int(metrics.get("diffBytes") or 0), push_policy.get("pushMinDiffBytes"))
        and _reaches_threshold(int(metrics.get("commitCount") or 0), push_policy.get("pushMinCommitCount"))
        and not _over_limit(int(metrics.get("changedFileCount") or 0), push_policy.get("pushMaxChangedFiles"))
        and not _over_limit(int(metrics.get("diffBytes") or 0), push_policy.get("pushMaxDiffBytes"))
    )


def _push_large_change_detail(metrics: dict[str, Any], push_policy: dict[str, Any]) -> str:
    return (
        f"当前：文件数={metrics.get('changedFileCount', 0)}，"
        f"Diff字节={metrics.get('diffBytes', 0)}，"
        f"Commit数={metrics.get('commitCount', 0)}；"
        f"阈值：文件数>={_threshold_label(push_policy.get('pushMinChangedFiles'))}，"
        f"Diff字节>={_threshold_label(push_policy.get('pushMinDiffBytes'))}，"
        f"Commit数>={_threshold_label(push_policy.get('pushMinCommitCount'))}，"
        f"文件数<={_threshold_label(push_policy.get('pushMaxChangedFiles'))}，"
        f"Diff字节<={_threshold_label(push_policy.get('pushMaxDiffBytes'))}；"
        "最小文件数、最小Diff、最小Commit、最大文件数、最大Diff、Debounce全部满足才可放行"
    )


def _push_hard_limit_detail(push_policy: dict[str, Any]) -> str:
    return (
        f"文件数<={_threshold_label(push_policy.get('pushMaxChangedFiles'))}，"
        f"Diff字节<={_threshold_label(push_policy.get('pushMaxDiffBytes'))}"
    )


def _push_large_change_summary(metrics: dict[str, Any], push_policy: dict[str, Any]) -> str:
    checks = [
        ("文件数", metrics.get("changedFileCount", 0), push_policy.get("pushMinChangedFiles")),
        ("Diff字节", metrics.get("diffBytes", 0), push_policy.get("pushMinDiffBytes")),
        ("Commit数", metrics.get("commitCount", 0), push_policy.get("pushMinCommitCount")),
    ]
    matched = [
        f"{label} {value} >= {threshold}"
        for label, value, threshold in checks
        if threshold is not None and threshold >= 0 and _reaches_threshold(int(value or 0), threshold)
    ]
    if push_policy.get("pushMaxChangedFiles", -1) is not None and push_policy.get("pushMaxChangedFiles", -1) >= 0:
        matched.append(f"文件数 {metrics.get('changedFileCount', 0)} <= {push_policy.get('pushMaxChangedFiles')}")
    else:
        matched.append("最大文件数不限制")
    if push_policy.get("pushMaxDiffBytes", -1) is not None and push_policy.get("pushMaxDiffBytes", -1) >= 0:
        matched.append(f"Diff字节 {metrics.get('diffBytes', 0)} <= {push_policy.get('pushMaxDiffBytes')}")
    else:
        matched.append("最大Diff字节不限制")
    debounce_seconds = int(push_policy.get("pushDebounceSeconds") or 0)
    matched.append("Debounce不限制" if debounce_seconds <= 0 else "Debounce已满足")
    return "、".join(matched) if matched else _push_large_change_detail(metrics, push_policy)


def _threshold_label(value: int | None) -> str:
    if value is None or value < 0:
        return "不限制"
    return str(value)


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


def rendered_prompt(db: Session, profile_code: str, project_id: int | None = None) -> dict[str, Any]:
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
    project = find_project_by_id(db, project_id) if project_id is not None else None
    if project_id is not None and project is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {project_id}", 404)
    policy_context = _attach_project_review_policies(db, project, request) if project is not None else None
    rendered = prompt.render_instructions(request)
    return {
        "profileCode": profile.profile_code,
        "projectId": project_id,
        "provider": provider.provider_code,
        "model": request.get("model") or provider.model_name,
        "projectPolicyCount": (policy_context or {}).get("meta", {}).get("injectedCount", 0),
        "projectReviewPolicies": (policy_context or {}).get("summaries", []),
        "prompt": rendered,
        "promptHash": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
        "promptLength": len(rendered),
    }


def list_provider_response(db: Session) -> list[dict[str, Any]]:
    return list_provider_responses(db)


def create_provider_response(db: Session, request: dict[str, Any]) -> dict[str, Any]:
    response = create_provider(db, request)
    db.commit()
    return response


def create_standard_model_connection_response(
    db: Session,
    request: dict[str, Any],
) -> dict[str, Any]:
    try:
        response = create_standard_model_connection(db, request)
        db.commit()
        return response
    except Exception:
        db.rollback()
        raise


def delete_provider_response(db: Session, provider_code: str) -> dict[str, Any]:
    response = delete_provider(db, provider_code)
    db.commit()
    return response


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


def list_results_response(db: Session, task_id: int) -> list[dict[str, Any]]:
    if db.get(ReviewTask, task_id) is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)
    return list_result_responses(db, task_id)


def get_progress_response(db: Session, task_id: int, review_key: str | None = None) -> list[dict[str, Any]]:
    if db.get(ReviewTask, task_id) is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)
    return list_progress(db, task_id, review_key)


def get_rule_gap_dashboard_response(
    db: Session,
    *,
    project_id: int | None = None,
    gap_type: str | None = None,
    signal: str | None = None,
    recent_days: int | None = 30,
    limit: int = 50,
) -> dict[str, Any]:
    return get_rule_gap_dashboard(
        db,
        project_id=project_id,
        gap_type=gap_type,
        signal=signal,
        recent_days=recent_days,
        limit=limit,
    )


def get_job_queue_response(db: Session) -> dict[str, Any]:
    return list_scheduler_queue_snapshot(db)


def cancel_job_response(db: Session, job_id: int) -> dict[str, Any]:
    response = cancel_scheduler_job(db, job_id, "用户手动中断调度任务")
    _sync_cancelled_agent_run(db, response)
    append_progress(
        db,
        response["taskId"],
        "JOB_INTERRUPTED",
        "WARNING",
        "调度任务已手动中断",
        f"jobId={job_id}, jobType={response.get('jobType')}, status={response.get('status')}",
        review_key=response.get("reviewKey"),
    )
    db.commit()
    return response


def cancel_task_jobs_response(db: Session, task_id: int, request: dict[str, Any] | None = None) -> dict[str, Any]:
    if db.get(ReviewTask, task_id) is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)
    request = request or {}
    job_type = str(request.get("jobType") or "").strip().upper() or None
    if job_type and job_type not in {"AI_REVIEW", "AGENT_REVIEW", "FIX_PREVIEW"}:
        raise AppError("VALIDATION_ERROR", f"Unsupported jobType: {job_type}", 400)
    finding_index = request.get("findingIndex")
    if finding_index is not None:
        try:
            finding_index = int(finding_index)
        except (TypeError, ValueError) as exception:
            raise AppError("VALIDATION_ERROR", "findingIndex must be an integer", 400) from exception
    review_key = request.get("reviewKey")
    reason = "用户手动中断 AI Review" if job_type in {"AI_REVIEW", "AGENT_REVIEW"} else "用户手动中断修复预览"
    jobs = cancel_active_scheduler_jobs_for_task(
        db,
        task_id,
        job_type=job_type,
        review_key=review_key,
        finding_index=finding_index,
        reason=reason,
    )
    for job in jobs:
        _sync_cancelled_agent_run(db, job)
    append_progress(
        db,
        task_id,
        "JOB_INTERRUPTED",
        "WARNING",
        "调度任务已手动中断",
        f"jobType={job_type or '-'}, reviewKey={review_key or '-'}, findingIndex={finding_index if finding_index is not None else '-'}, affectedJobs={len(jobs)}",
        review_key=review_key,
    )
    db.commit()
    return {"taskId": task_id, "status": "SKIPPED", "affectedJobs": len(jobs), "jobs": jobs}


def _sync_cancelled_agent_run(db: Session, job: dict[str, Any]) -> None:
    if job.get("jobType") != "AGENT_REVIEW" or job.get("status") != "SKIPPED":
        return
    from app.agent_review.models import AgentReviewRun

    run = db.scalars(select(AgentReviewRun).where(AgentReviewRun.scheduler_job_id == job.get("id"))).first()
    if run is None:
        return
    now = datetime.now()
    run.status = "CANCELLED"
    run.effective_engine = "AGENT"
    run.failure_code = "AGENT_CANCELLED"
    run.input_json = None
    run.finished_at = now
    run.updated_at = now


def get_failure_notifications_response(db: Session) -> dict[str, Any]:
    return list_ai_review_failure_notifications(db)


def list_fix_previews_response(db: Session, task_id: int, review_key: str | None = None) -> list[dict[str, Any]]:
    if db.get(ReviewTask, task_id) is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)
    return list_fix_preview_responses(db, task_id, review_key)


def list_finding_refinements_response(
    db: Session,
    task_id: int,
    review_key: str | None = None,
) -> list[dict[str, Any]]:
    if db.get(ReviewTask, task_id) is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)
    return list_refinement_responses(db, task_id=task_id, review_key=review_key)


def run_finding_refinement_response(db: Session, task_id: int, request: dict[str, Any]) -> dict[str, Any]:
    target = _resolve_refinement_target(db, task_id, request)
    existing = find_refinement(
        db,
        task_id=task_id,
        review_key=target["result"].review_key,
        finding_index=target["findingIndex"],
    )
    if existing is not None and not request.get("forceRegenerate"):
        return refinement_to_response(existing)
    _validate_refinement_candidate(target["finding"])
    record = _run_finding_refinement(db, target)
    db.commit()
    return refinement_to_response(record)


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

    review_key = request.get("reviewKey")
    existing = find_fix_preview_response(db, task_id=task_id, finding_index=finding_index, review_key=review_key)
    if existing is not None and not request.get("forceRegenerate"):
        return existing
    if not _enabled(db):
        raise AppError("BAD_REQUEST", "Code quality review is disabled", 400)

    if _fix_preview_inline_enabled():
        response = _generate_fix_preview(db, task_id, finding_index, bool(request.get("forceRegenerate")), review_key)
        db.commit()
        return response
    return _queue_fix_preview(db, task_id, finding_index, bool(request.get("forceRegenerate")), review_key)


def _queue_fix_preview(
    db: Session,
    task_id: int,
    finding_index: int,
    force_regenerate: bool,
    review_key: str | None,
) -> dict[str, Any]:
    task = db.get(ReviewTask, task_id)
    if task is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)
    project = find_project_by_id(db, task.project_id)
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {task.project_id}", 404)
    review_result = find_result_response_by_key(db, task_id, review_key) if review_key else find_result_response(db, task_id)
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
            review_result.get("reviewKey"),
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
            review_result.get("reviewKey"),
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
        review_result.get("reviewKey"),
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
        review_key=review_result.get("reviewKey"),
    )
    _submit_provider_job(
        db,
        run_auto_fix_preview_job,
        task_id,
        finding_index,
        review_result.get("reviewKey"),
        job_type="FIX_PREVIEW",
        task_id=task_id,
        project_id=project.id,
        finding_index=finding_index,
        priority=FIX_PREVIEW_JOB_PRIORITY,
        label="AI 修复预览",
        file_path=file_path,
        review_key=review_result.get("reviewKey"),
    )
    return response


def _generate_fix_preview(
    db: Session,
    task_id: int,
    finding_index: int,
    force_regenerate: bool,
    review_key: str | None,
) -> dict[str, Any]:
    task = db.get(ReviewTask, task_id)
    if task is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)
    project = find_project_by_id(db, task.project_id)
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {task.project_id}", 404)
    review_result = find_result_response_by_key(db, task_id, review_key) if review_key else find_result_response(db, task_id)
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
            review_result.get("reviewKey"),
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
            review_result.get("reviewKey"),
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
        review_result.get("reviewKey"),
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
        review_key=review_result.get("reviewKey"),
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
            "reviewKey": review_result.get("reviewKey"),
        },
    )
    interrupted = find_fix_preview_response(
        db,
        task_id=task_id,
        finding_index=finding_index,
        review_key=review_result.get("reviewKey"),
    )
    if interrupted and interrupted.get("status") == "SKIPPED":
        return interrupted
    saved = save_fix_preview(
        db,
        task_id=task_id,
        review_key=review_result.get("reviewKey"),
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
        review_key=review_result.get("reviewKey"),
    )
    from app.code_quality.repository import fix_preview_to_dict

    return fix_preview_to_dict(saved)


def _save_fix_preview_status(
    db: Session,
    task: ReviewTask,
    project: Project,
    finding_index: int,
    review_key: str | None,
    file_path: str,
    provider: str,
    model: str | None,
    status: str,
    message: str,
) -> dict[str, Any]:
    saved = save_fix_preview(
        db,
        task_id=task.id,
        review_key=review_key,
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
    review_key = result.get("reviewKey") or "default"
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
        existing = find_fix_preview_response(db, task_id=task_id, finding_index=index, review_key=review_key)
        if existing and existing.get("status") == "SUCCESS":
            continue
        file_node = _find_changed_file_for_finding(changed_files, finding)
        if file_node is None:
            _save_fix_preview_status(
                db,
                task,
                project,
                index,
                review_key,
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
                review_key,
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
            review_key,
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
        review_key=review_key,
    )
    db.commit()
    if _fix_preview_inline_enabled():
        for index in queued_indexes:
            _generate_fix_preview(db, task_id, index, True, review_key)
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
                review_key,
                job_type="FIX_PREVIEW",
                task_id=task_id,
                project_id=project.id,
                finding_index=index,
                priority=FIX_PREVIEW_JOB_PRIORITY,
                label="AI 修复预览",
                file_path=file_path,
                review_key=review_key,
            )


def _should_auto_generate_fix_preview(
    finding: dict[str, Any],
    enabled_severities: set[str],
) -> bool:
    return str(finding.get("severity") or "").strip().upper() in enabled_severities


def run_auto_fix_preview_job(task_id: int, finding_index: int, review_key: str | None = None) -> dict[str, Any]:
    db = SessionLocal()
    try:
        result = _generate_fix_preview(db, task_id, finding_index, True, review_key)
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
            review_key=review_key,
        )
        db.commit()
        return {"status": "FAILED", "errorMessage": str(exception)}
    finally:
        db.close()


def recover_stale_running_reviews_on_startup() -> None:
    from app.core.config import get_settings
    from app.review_record.repository import ensure_review_task_status_schema

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
        ensure_review_task_status_schema(db)
        db.commit()
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
    target: dict[str, Any] | None = None,
) -> dict[str, Any]:
    review_key = request.get("reviewKey") or (target or {}).get("reviewKey")
    preflight_summary = request.get("_deterministicPreflightSummary")
    if preflight_summary:
        append_progress(
            db,
            task_id,
            "DETERMINISTIC_PRECHECK_REUSED",
            "WARN" if preflight_summary.get("status") in {"FAILED", "UNAVAILABLE"} else "INFO",
            "当前模型复用本次调度的确定性检查摘要",
            json.dumps(
                {
                    "runId": preflight_summary.get("runId"),
                    "status": preflight_summary.get("status"),
                    "trigger": preflight_summary.get("trigger"),
                    "freshness": preflight_summary.get("freshness"),
                    "failureReason": preflight_summary.get("failureReason"),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            review_key=review_key,
        )
    policy_context = _attach_project_review_policies(db, project, request)
    review_context = _attach_review_context_pack(db, task_id, project, request)
    append_progress(
        db,
        task_id,
        "REQUEST_BUILT",
        "INFO",
        "AI Review 请求已构建",
        f"profileCode={profile.profile_code}, provider={provider.provider_code}, model={request.get('model') or provider.model_name}, mode={request.get('mode')}",
        review_key=review_key,
    )
    append_progress(
        db,
        task_id,
        "CONTEXT_PACK_BUILT",
        "INFO",
        "AI Review Context Pack 已构建",
        _review_context_progress_detail(review_context),
        review_key=review_key,
    )
    _append_local_repo_progress(db, task_id, review_context, review_key)
    _append_local_context_progress(db, task_id, review_context, review_key)
    append_progress(
        db,
        task_id,
        "PROJECT_POLICIES_INJECTED",
        "INFO",
        "项目 Review 策略已注入 Prompt",
        _project_policy_progress_detail(policy_context),
        review_key=review_key,
    )
    db.commit()
    try:
        with progress_review_key(review_key):
            result = run_provider(db, task_id, provider, request)
    except Exception as exception:
        append_progress(
            db,
            task_id,
            "PROVIDER_FAILED",
            "ERROR",
            "代码质量 Review Provider 调用失败",
            str(exception),
            review_key=review_key,
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
    interrupted = find_result_response_by_key(db, task_id, review_key)
    if interrupted and interrupted.get("status") == "SKIPPED":
        return interrupted
    append_progress(
        db,
        task_id,
        "SAVE_RESULT",
        "INFO",
        "Provider 执行完成，开始保存结果",
        f"status={result['status']}, findingCount={len(result.get('findings') or [])}",
        review_key=review_key,
    )
    result["reviewKey"] = review_key
    result["requestedEngine"] = request.get("requestedEngine") or "STANDARD"
    result["effectiveEngine"] = request.get("effectiveEngine") or result["requestedEngine"]
    result["agentRunId"] = request.get("agentRunId")
    result["agentRunSummary"] = request.get("agentRunSummary")
    saved_result = save_result(
        db,
        task_id=task_id,
        review_key=review_key,
        project_id=project.id,
        profile_code=profile.profile_code,
        provider=provider.provider_code,
        model=request.get("model") or provider.model_name,
        display_name=(target or {}).get("displayName"),
        sort_order=int((target or {}).get("sortOrder") or 0),
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
        review_key=review_key,
    )
    append_progress(
        db,
        task_id,
        "FINISHED",
        "INFO" if result["status"] == "SUCCESS" else "ERROR",
        "AI Review 已完成" if result["status"] == "SUCCESS" else "AI Review 执行失败",
        f"status={result['status']}, overallLevel={result.get('overallLevel') or '-'}",
        review_key=review_key,
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
        results = list_result_responses(db, task_id)
        if not any(item.get("status") in {"SUCCESS", "RUNNING"} for item in results):
            mark_task_failed(task, result.get("errorMessage") or "AI Review failed")
            refresh_review_status(db, task_id)
        return
    if status == "SUCCESS" and (task.trigger_type == "CODE_QUALITY_MANUAL" or task.status == "FAILED"):
        mark_task_success(task, result.get("overallLevel") or task.risk_level or "LOW")
        refresh_review_status(db, task_id)


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


def _resolve_review_targets(db: Session, project: Project, profile, target_type: str | None = None) -> list[dict[str, Any]]:
    provider_override = None
    if target_type:
        from app.project_integration.repository import find_target_config

        target_config = find_target_config(db, project.id, target_type)
        provider_override = target_config.provider_code if target_config else None
    if not provider_override:
        provider_override = project.default_code_quality_provider_code
    if provider_override:
        provider = get_provider(db, provider_override)
        model = profile.model or provider.model_name
        return [_review_target(provider, make_ai_review_model_key(provider.provider_code, model), model, None, 10)]

    from app.project_integration.models import ProjectGroup

    group = db.get(ProjectGroup, project.group_id) if project.group_id else None
    group_models = [
        item for item in list_project_group_ai_review_models(db, int(group.id), include_fallback=False)
        if item.get("enabled") is not False
    ] if group is not None else []
    if group_models:
        targets: list[dict[str, Any]] = []
        for index, item in enumerate(group_models):
            provider = get_provider(db, item["providerCode"])
            model = item.get("modelName") or profile.model or provider.model_name
            targets.append(
                _review_target(
                    provider,
                    item.get("reviewKey") or make_ai_review_model_key(provider.provider_code, model, index),
                    model,
                    item.get("displayName"),
                    int(item.get("sortOrder") or (index + 1) * 10),
                )
            )
        return targets

    provider = _resolve_provider(db, project, profile, target_type)
    model = profile.model or provider.model_name
    return [_review_target(provider, make_ai_review_model_key(provider.provider_code, model), model, None, 10)]


def _review_target(provider: CodeQualityModelProvider, review_key: str, model: str | None, display_name: str | None, sort_order: int) -> dict[str, Any]:
    return {
        "provider": provider,
        "reviewKey": review_key,
        "model": model,
        "displayName": _review_display_name(provider.provider_code, display_name or provider.provider_name),
        "sortOrder": sort_order,
    }


def _review_display_name(provider_code: str | None, display_name: str | None) -> str:
    short_names = {
        "OPENAI": "OpenAI",
        "ANTHROPIC": "Claude",
        "DEEPSEEK": "DeepSeek",
        "XIAOMIMO": "XiaoMIMO",
        "GLM": "GLM",
        "CUSTOM": "自定义",
    }
    provider_key = str(provider_code or "").strip().upper()
    raw_name = str(display_name or "").strip()
    if not raw_name or "Xiaomi MiMo" in raw_name or raw_name == provider_code:
        return short_names.get(provider_key, provider_code or "-")
    return raw_name


def _build_review_request(profile, request: dict[str, Any]) -> dict[str, Any]:
    instructions = _join_instructions(profile.review_instructions, request.get("instructions"))
    changed_files = request.get("changedFiles") or []
    changed_file_details = request.get("changedFileDetails") or changed_files
    return {
        "repositoryPath": request.get("repositoryPath"),
        "mode": request.get("mode") or "DIFF_TEXT",
        "baseRef": request.get("baseRef"),
        "commitSha": request.get("commitSha"),
        "title": request.get("title"),
        "model": request.get("model") or profile.model,
        "instructions": instructions,
        "diffText": request.get("diffText"),
        "changedFiles": _changed_file_paths(changed_files),
        "changedFileDetails": changed_file_details,
        "projectReviewPolicies": request.get("projectReviewPolicies") or [],
        "projectReviewPoliciesText": request.get("projectReviewPoliciesText"),
        "reviewContext": request.get("reviewContext"),
        "contextPack": request.get("contextPack"),
        "reviewContextText": request.get("reviewContextText"),
        "reviewContextMeta": request.get("reviewContextMeta"),
        "reviewContextSummary": request.get("reviewContextSummary"),
        "_deterministicPreflightSummary": request.get("_deterministicPreflightSummary"),
    }


def _attach_project_review_policies(
    db: Session,
    project: Project | None,
    request: dict[str, Any],
) -> dict[str, Any]:
    if project is None:
        context = {
            "items": [],
            "summaries": [],
            "promptText": "",
            "meta": {"projectId": None, "totalAvailable": 0, "injectedCount": 0, "promptLength": 0},
        }
    else:
        context = build_project_review_policy_prompt_context(db, int(project.id))
    request["projectReviewPolicies"] = context["items"]
    request["projectReviewPoliciesText"] = context["promptText"]
    request["projectReviewPolicyMeta"] = context["meta"]
    request["projectReviewPolicySummaries"] = context["summaries"]
    return context


def _attach_review_context_pack(
    db: Session,
    task_id: int,
    project: Project | None,
    request: dict[str, Any],
) -> dict[str, Any]:
    task = db.get(ReviewTask, task_id)
    head_ref = None
    if task is not None:
        head_ref = task.after_sha or task.commit_sha
    context = build_review_context_pack(
        db,
        task_id=task_id,
        project_id=int(project.id) if project is not None else None,
        changed_files=request.get("changedFileDetails") or request.get("changedFiles") or [],
        diff_text=request.get("diffText"),
        mode=request.get("mode"),
        repository_url=project.repository_url if project is not None else None,
        git_project_id=project.git_project_id if project is not None else None,
        head_ref=head_ref or request.get("commitSha"),
        deterministic_security_summary=request.get("_deterministicPreflightSummary"),
        target_type=task.target_type if task is not None else None,
    )
    request["reviewContext"] = context["reviewContext"]
    request["contextPack"] = context["contextPack"]
    request["reviewContextText"] = context["promptText"]
    request["reviewContextMeta"] = context["meta"]
    request["reviewContextSummary"] = context["summary"]
    return context


def _project_policy_progress_detail(context: dict[str, Any]) -> str:
    meta = context.get("meta") or {}
    summaries = []
    for item in context.get("summaries") or []:
        summaries.append(
            {
                "id": item.get("id"),
                "policyType": item.get("policyType"),
                "riskType": item.get("riskType"),
                "title": str(item.get("title") or "")[:120],
                "sourceFeedbackId": item.get("sourceFeedbackId"),
            }
        )
    return json.dumps(
        {
            "projectId": meta.get("projectId"),
            "totalAvailable": meta.get("totalAvailable", 0),
            "injectedCount": meta.get("injectedCount", 0),
            "promptLength": meta.get("promptLength", 0),
            "truncated": bool(meta.get("truncated", False)),
            "policies": summaries,
        },
        ensure_ascii=False,
    )


def _review_context_progress_detail(context: dict[str, Any]) -> str:
    payload = {
        "meta": context.get("meta") or {},
        "summary": _bounded_review_context_summary(context.get("summary") or {}),
    }
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(text) <= 3800:
        return text
    summary = dict(payload["summary"])
    requested_availability = dict(summary.get("requestedContextAvailability") or {})
    requested_availability["items"] = (requested_availability.get("items") or [])[:6]
    summary["requestedContextAvailability"] = requested_availability
    summary["ruleGapItems"] = (summary.get("ruleGapItems") or [])[:3]
    summary["sourceWorkspaceSummary"] = _bounded_source_workspace_summary(
        summary.get("sourceWorkspaceSummary") or {},
        include_cleanup_errors=False,
    )
    payload["summary"] = summary
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(text) <= 3800:
        return text
    requested_availability.pop("items", None)
    summary["requestedContextAvailability"] = requested_availability
    summary["ruleGapItems"] = (summary.get("ruleGapItems") or [])[:1]
    summary["progressSummaryTruncated"] = True
    payload["summary"] = summary
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(text) <= 3800:
        return text
    payload["summary"] = _minimal_review_context_progress_summary(summary)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(text) <= 3800:
        return text
    payload["meta"] = _minimal_review_context_progress_meta(payload.get("meta") or {})
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(text) <= 3800:
        return text
    return json.dumps(
        {
            "meta": _minimal_review_context_progress_meta(payload.get("meta") or {}),
            "summary": {"progressSummaryTruncated": True},
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _bounded_review_context_summary(summary: dict[str, Any]) -> dict[str, Any]:
    result = dict(summary)
    local_repository = dict(result.get("localRepository") or {})
    local_repository.pop("sourceWorkspaceSummary", None)
    result["localRepository"] = local_repository
    local_repository_source = summary.get("localRepository") if isinstance(summary.get("localRepository"), dict) else {}
    source_workspace_summary = _bounded_source_workspace_summary(
        summary.get("sourceWorkspaceSummary") or local_repository_source.get("sourceWorkspaceSummary") or {}
    )
    if source_workspace_summary:
        result["sourceWorkspaceSummary"] = source_workspace_summary
    else:
        result.pop("sourceWorkspaceSummary", None)
    result["plannerSignalTypeCounts"] = (summary.get("plannerSignalTypeCounts") or [])[:8]
    result["retrieverUnsupportedSignalTypeCounts"] = (summary.get("retrieverUnsupportedSignalTypeCounts") or [])[:8]
    availability = dict(summary.get("requestedContextAvailability") or {})
    availability["items"] = (availability.get("items") or [])[:10]
    availability["unavailableReasonCounts"] = (availability.get("unavailableReasonCounts") or [])[:8]
    result["requestedContextAvailability"] = availability
    rule_gap_summary = dict(summary.get("ruleGapSummary") or {})
    rule_gap_summary["topSignals"] = (rule_gap_summary.get("topSignals") or [])[:5]
    rule_gap_summary["byGapType"] = (rule_gap_summary.get("byGapType") or [])[:6]
    result["ruleGapSummary"] = rule_gap_summary
    result["ruleGapItems"] = (summary.get("ruleGapItems") or [])[:6]
    return result


def _bounded_source_workspace_summary(
    summary: dict[str, Any],
    *,
    include_cleanup_errors: bool = True,
) -> dict[str, Any]:
    if not isinstance(summary, dict) or not summary:
        return {}
    result = _pick_dict(
        summary,
        (
            "enabled",
            "status",
            "mode",
            "failurePhase",
            "remoteUrl",
            "lastPreparedAt",
        ),
    )
    mirror = _pick_dict(
        summary.get("mirror") if isinstance(summary.get("mirror"), dict) else {},
        (
            "exists",
            "status",
            "lastFetchedAt",
            "lastModifiedAt",
        ),
    )
    if mirror:
        result["mirror"] = mirror
    worktree = _pick_dict(
        summary.get("worktree") if isinstance(summary.get("worktree"), dict) else {},
        (
            "exists",
            "status",
            "lastCheckedOutAt",
            "lastModifiedAt",
        ),
    )
    if worktree:
        result["worktree"] = worktree
    cleanup_policy = _pick_dict(
        summary.get("cleanupPolicy") if isinstance(summary.get("cleanupPolicy"), dict) else {},
        (
            "enabled",
            "worktreeRetentionHours",
            "mirrorRetentionDays",
        ),
    )
    if cleanup_policy:
        result["cleanupPolicy"] = cleanup_policy
    cleanup = _pick_dict(
        summary.get("cleanup") if isinstance(summary.get("cleanup"), dict) else {},
        (
            "enabled",
            "status",
            "deletedWorktreeCount",
            "deletedMirrorCount",
            "errorCount",
            "durationMs",
        ),
    )
    if include_cleanup_errors and cleanup and int(cleanup.get("errorCount") or 0) > 0:
        errors = summary.get("cleanup", {}).get("errors") if isinstance(summary.get("cleanup"), dict) else []
        cleanup["errors"] = [str(item)[:160] for item in (errors or [])[:2]]
    if cleanup:
        result["cleanup"] = cleanup
    return result


def _pick_dict(source: Any, keys: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(source, dict):
        return {}
    return {key: source[key] for key in keys if key in source and source.get(key) is not None}


def _minimal_review_context_progress_summary(summary: dict[str, Any]) -> dict[str, Any]:
    local_repository = dict(summary.get("localRepository") or {})
    if local_repository:
        local_repository = _pick_dict(
            local_repository,
            (
                "enabled",
                "status",
                "projectId",
                "taskId",
                "mirrorStatus",
                "worktreeStatus",
                "failurePhase",
                "sourceIncluded",
            ),
        )
    availability = dict(summary.get("requestedContextAvailability") or {})
    availability = _pick_dict(
        availability,
        (
            "total",
            "available",
            "unavailable",
            "unknown",
        ),
    )
    return {
        "version": summary.get("version"),
        "projectId": summary.get("projectId"),
        "changedFileCount": summary.get("changedFileCount"),
        "includedChangedFileCount": summary.get("includedChangedFileCount"),
        "sameFileSourceSnippetCount": summary.get("sameFileSourceSnippetCount"),
        "sameFileSourceFileCount": summary.get("sameFileSourceFileCount"),
        "deterministicChecks": summary.get("deterministicChecks") or {},
        "contextMissingFeedbackTotal": summary.get("contextMissingFeedbackTotal"),
        "plannerSignalCount": summary.get("plannerSignalCount"),
        "plannerTargetType": summary.get("plannerTargetType"),
        "detectedLanguages": (summary.get("detectedLanguages") or [])[:12],
        "extractorVersions": (summary.get("extractorVersions") or [])[:12],
        "plannerCoverageSummary": summary.get("plannerCoverageSummary") or {},
        "plannerSignalTypeCounts": (summary.get("plannerSignalTypeCounts") or [])[:4],
        "requestedContextTypeCounts": (summary.get("requestedContextTypeCounts") or [])[:4],
        "retrieverSupportedSignalTypes": (summary.get("retrieverSupportedSignalTypes") or [])[:12],
        "requestedContextAvailability": availability,
        "unavailableContextCount": summary.get("unavailableContextCount"),
        "localRepository": local_repository,
        "sourceWorkspaceSummary": _bounded_source_workspace_summary(
            summary.get("sourceWorkspaceSummary") or {},
            include_cleanup_errors=False,
        ),
        "localReferenceSearch": summary.get("localReferenceSearch") or {},
        "budgetCutSummary": summary.get("budgetCutSummary") or {},
        "ruleGapSummary": summary.get("ruleGapSummary") or {},
        "ruleGapItems": (summary.get("ruleGapItems") or [])[:1],
        "promptLength": summary.get("promptLength"),
        "truncated": bool(summary.get("truncated", False)),
        "progressSummaryTruncated": True,
    }


def _minimal_review_context_progress_meta(meta: dict[str, Any]) -> dict[str, Any]:
    return _pick_dict(
        meta,
        (
            "version",
            "projectId",
            "mode",
            "promptLength",
            "truncated",
            "localRepositoryEnabled",
            "localRepositoryStatus",
            "localReferenceSnippetCount",
        ),
    )


def _append_local_repo_progress(
    db: Session,
    task_id: int,
    context: dict[str, Any],
    review_key: str | None,
) -> None:
    progress_summary = context.get("summary") or {}
    local_repository = dict(progress_summary.get("localRepository") or {})
    if not local_repository.get("enabled"):
        return
    source_workspace_summary = _bounded_source_workspace_summary(
        progress_summary.get("sourceWorkspaceSummary") or {}
    )
    if source_workspace_summary:
        local_repository["sourceWorkspaceSummary"] = source_workspace_summary
    prepared = str(local_repository.get("status") or "").upper() == "PREPARED"
    append_progress(
        db,
        task_id,
        "LOCAL_REPO_PREPARED" if prepared else "LOCAL_REPO_PREPARE_FAILED",
        "INFO" if prepared else "WARN",
        "本地仓库工作区已准备" if prepared else "本地仓库工作区不可用",
        json.dumps(local_repository, ensure_ascii=False),
        review_key=review_key,
    )


def _append_local_context_progress(
    db: Session,
    task_id: int,
    context: dict[str, Any],
    review_key: str | None,
) -> None:
    retrieval = context.get("localReferenceRetrieval") or {}
    status = str(retrieval.get("status") or "").upper()
    if status in {"", "SKIPPED"}:
        return
    summary = retrieval.get("summary") or {}
    unavailable_contexts = [
        item
        for item in (retrieval.get("unavailableContexts") or [])
        if isinstance(item, dict)
    ]
    detail = json.dumps(
        {
            "status": status,
            "queryCount": int(summary.get("queryCount") or 0),
            "matchedFileCount": int(summary.get("matchedFileCount") or 0),
            "includedSnippetCount": int(summary.get("includedSnippetCount") or 0),
            "evidenceCandidateCount": int(summary.get("evidenceCandidateCount") or 0),
            "truncated": bool(summary.get("truncated", False)),
            "unavailableContexts": unavailable_contexts[:3],
        },
        ensure_ascii=False,
    )
    failed = status == "UNAVAILABLE"
    append_progress(
        db,
        task_id,
        "LOCAL_CONTEXT_RETRIEVE_FAILED" if failed else "LOCAL_CONTEXT_RETRIEVED",
        "WARN" if failed else "INFO",
        "本地引用检索不可用" if failed else "本地引用检索已完成",
        detail,
        review_key=review_key,
    )


def _resolve_refinement_target(db: Session, task_id: int, request: dict[str, Any]) -> dict[str, Any]:
    task = db.get(ReviewTask, task_id)
    if task is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)
    review_key = _clean_optional_text(request.get("reviewKey"), 64)
    requested_fingerprint = _clean_optional_text(request.get("fingerprint"), 128)
    finding_index = request.get("findingIndex")
    if finding_index is not None:
        try:
            finding_index = int(finding_index)
        except (TypeError, ValueError) as exception:
            raise AppError("VALIDATION_ERROR", "findingIndex must be an integer", 400) from exception
        if finding_index < 0:
            raise AppError("VALIDATION_ERROR", "findingIndex must be non-negative", 400)
    if finding_index is None and not requested_fingerprint:
        raise AppError("VALIDATION_ERROR", "findingIndex or fingerprint is required", 400)

    stmt = select(CodeQualityReviewResult).where(CodeQualityReviewResult.task_id == task_id)
    if review_key:
        stmt = stmt.where(CodeQualityReviewResult.review_key == review_key)
    records = db.scalars(stmt.order_by(CodeQualityReviewResult.sort_order.asc(), CodeQualityReviewResult.id.asc())).all()
    for result in records:
        findings = read_json(result.findings_json, [])
        if not isinstance(findings, list):
            continue
        for index, finding in enumerate(findings):
            if finding_index is not None and index != finding_index:
                continue
            if not isinstance(finding, dict):
                continue
            fingerprint = ai_finding_fingerprint(result, finding, index)
            if requested_fingerprint and requested_fingerprint != fingerprint:
                continue
            return {
                "task": task,
                "result": result,
                "finding": finding,
                "findingIndex": index,
                "fingerprint": fingerprint,
            }
    raise AppError("RESOURCE_NOT_FOUND", "AI finding for refinement not found", 404)


def _validate_refinement_candidate(finding: dict[str, Any]) -> None:
    severity = _normalize_refinement_enum(finding.get("severity"))
    context_status = _normalize_refinement_enum(finding.get("contextStatus"))
    if severity not in REFINEMENT_ALLOWED_SEVERITIES:
        raise AppError(
            "VALIDATION_ERROR",
            "finding refinement only supports CRITICAL / MAJOR / HIGH severity",
            400,
        )
    if context_status not in REFINEMENT_ALLOWED_CONTEXT_STATUSES:
        raise AppError(
            "VALIDATION_ERROR",
            "finding refinement only supports PARTIAL / INSUFFICIENT contextStatus",
            400,
        )


def _run_finding_refinement(db: Session, target: dict[str, Any]):
    task: ReviewTask = target["task"]
    result: CodeQualityReviewResult = target["result"]
    finding: dict[str, Any] = target["finding"]
    finding_index = int(target["findingIndex"])
    fingerprint = target["fingerprint"]
    project = find_project_by_id(db, task.project_id)
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {task.project_id}", 404)

    started_at = datetime.now()
    trigger_conditions = _refinement_trigger_conditions(finding)
    changed_files = _changed_files_from_task_event(db, task)
    file_node = _find_changed_file_for_finding(changed_files, finding)
    finding_id = _clean_optional_text(finding.get("findingId") or finding.get("id"), 128)
    if file_node is None:
        return upsert_refinement(
            db,
            task_id=task.id,
            review_key=result.review_key,
            finding_index=finding_index,
            fingerprint=fingerprint,
            finding_id=finding_id,
            project_id=project.id,
            status="FAILED",
            trigger_reason="HIGH_IMPACT_CONTEXT_INSUFFICIENT",
            trigger_conditions=trigger_conditions,
            retrieval_plan={"status": "SKIPPED", "reason": "CHANGED_FILE_NOT_FOUND"},
            evidence_summary=None,
            missing_context=[{"type": "CHANGED_FILE", "reason": "Changed file for finding was not found."}],
            failure_reason="Changed file for finding was not found",
            started_at=started_at,
            finished_at=datetime.now(),
        )

    try:
        context = build_review_context_pack(
            db,
            task_id=task.id,
            project_id=project.id,
            changed_files=[file_node],
            diff_text=_single_file_diff_text(file_node),
            mode="FINDING_REFINEMENT",
            repository_url=project.repository_url,
            git_project_id=project.git_project_id,
            head_ref=task.commit_sha or task.after_sha or task.target_branch,
            target_type=task.target_type,
        )
        retrieval_plan = _refinement_retrieval_plan(context)
        evidence_summary = _refinement_evidence_summary(context)
        missing_context = _refinement_missing_context(context)
        local_repository = ((context.get("summary") or {}).get("localRepository") or {})
        if str(local_repository.get("status") or "").upper() != "PREPARED":
            reason = _local_repository_failure_reason(local_repository, missing_context)
            status = "FAILED"
            failure_reason = reason
        else:
            status = "COMPLETED"
            failure_reason = None
        return upsert_refinement(
            db,
            task_id=task.id,
            review_key=result.review_key,
            finding_index=finding_index,
            fingerprint=fingerprint,
            finding_id=finding_id,
            project_id=project.id,
            status=status,
            trigger_reason="HIGH_IMPACT_CONTEXT_INSUFFICIENT",
            trigger_conditions=trigger_conditions,
            retrieval_plan=retrieval_plan,
            evidence_summary=evidence_summary,
            missing_context=missing_context,
            failure_reason=failure_reason,
            started_at=started_at,
            finished_at=datetime.now(),
        )
    except Exception as exception:
        return upsert_refinement(
            db,
            task_id=task.id,
            review_key=result.review_key,
            finding_index=finding_index,
            fingerprint=fingerprint,
            finding_id=finding_id,
            project_id=project.id,
            status="FAILED",
            trigger_reason="HIGH_IMPACT_CONTEXT_INSUFFICIENT",
            trigger_conditions=trigger_conditions,
            retrieval_plan={"status": "FAILED"},
            evidence_summary=None,
            missing_context=[],
            failure_reason=str(exception),
            started_at=started_at,
            finished_at=datetime.now(),
        )


def _refinement_trigger_conditions(finding: dict[str, Any]) -> dict[str, Any]:
    return {
        "severity": _normalize_refinement_enum(finding.get("severity")),
        "contextStatus": _normalize_refinement_enum(finding.get("contextStatus")),
        "allowedSeverities": sorted(REFINEMENT_ALLOWED_SEVERITIES),
        "allowedContextStatuses": sorted(REFINEMENT_ALLOWED_CONTEXT_STATUSES),
    }


def _refinement_retrieval_plan(context: dict[str, Any]) -> dict[str, Any]:
    context_pack = context.get("contextPack") or {}
    plan = context_pack.get("contextPlan") or {}
    return {
        "contextPackVersion": context_pack.get("version") or context.get("version"),
        "mode": ((context.get("reviewContext") or {}).get("mode")) or "FINDING_REFINEMENT",
        "plannerSignalCount": int(plan.get("plannerSignalCount") or 0),
        "plannerSignalTotal": int(plan.get("plannerSignalTotal") or 0),
        "requestedContextCount": int(plan.get("requestedContextCount") or 0),
        "requestedContextTypeCounts": plan.get("requestedContextTypeCounts") or [],
        "plannerSignalTypeCounts": context_pack.get("plannerSignalTypeCounts") or [],
        "retrieverSupportedSignalTypes": context_pack.get("retrieverSupportedSignalTypes") or [],
        "retrieverUnsupportedSignalTypeCounts": context_pack.get("retrieverUnsupportedSignalTypeCounts") or [],
        "requestedContextAvailability": context_pack.get("requestedContextAvailability") or {},
    }


def _refinement_evidence_summary(context: dict[str, Any]) -> dict[str, Any]:
    context_pack = context.get("contextPack") or {}
    local_reference = context_pack.get("localReferenceContext") or {}
    searches = []
    for item in (local_reference.get("searches") or [])[:8]:
        if not isinstance(item, dict):
            continue
        searches.append(
            {
                "query": item.get("query"),
                "signalTypes": item.get("signalTypes") or [],
                "matchedFileCount": int(item.get("matchedFileCount") or 0),
                "candidateSnippetCount": int(item.get("candidateSnippetCount") or 0),
                "includedSnippetCount": int(item.get("includedSnippetCount") or 0),
                "truncated": bool(item.get("truncated", False)),
                "topRelativePaths": item.get("topMatchedPaths") or [],
            }
        )
    return {
        "changedFilesSummary": context_pack.get("changedFilesSummary") or {},
        "localRepository": (context.get("summary") or {}).get("localRepository") or {},
        "localReferenceSearch": context_pack.get("localReferenceSearch") or {},
        "searches": searches,
        "budgetCutSummary": context_pack.get("budgetCutSummary") or {},
        "notInjectedEvidence": context_pack.get("notInjectedEvidence") or {},
        "ruleGapSummary": context_pack.get("ruleGapSummary") or {},
        "ruleGapItems": (context_pack.get("ruleGapItems") or [])[:8],
    }


def _refinement_missing_context(context: dict[str, Any]) -> list[dict[str, Any]]:
    context_pack = context.get("contextPack") or {}
    items = []
    for item in context_pack.get("unavailableContexts") or []:
        if isinstance(item, dict):
            items.append(
                {
                    "type": str(item.get("type") or "")[:120],
                    "reason": str(item.get("reason") or "")[:500],
                }
            )
    for item in context_pack.get("requestedContexts") or []:
        if not isinstance(item, dict) or bool(item.get("available")):
            continue
        items.append(
            {
                "type": str(item.get("type") or "")[:120],
                "reason": str(item.get("reason") or "Requested context is unavailable.")[:500],
            }
        )
    return items[:20]


def _local_repository_failure_reason(
    local_repository: dict[str, Any],
    missing_context: list[dict[str, Any]],
) -> str:
    for item in missing_context:
        if str(item.get("type") or "").upper() == "LOCAL_REPOSITORY" and item.get("reason"):
            return str(item["reason"])[:1024]
    status = str(local_repository.get("status") or "UNAVAILABLE")
    phase = str(local_repository.get("failurePhase") or "")
    return f"Local repository context is not prepared: status={status}" + (f", failurePhase={phase}" if phase else "")


def _normalize_refinement_enum(value: Any) -> str:
    return str(value or "").strip().upper().replace("-", "_")


def _clean_optional_text(value: Any, max_length: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:max_length] if text else None


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
            "changedFileDetails": files,
        },
    )


def _changed_file_paths(changed_files: list[Any]) -> list[str]:
    paths: list[str] = []
    for item in changed_files:
        if isinstance(item, dict):
            path = item.get("path") or item.get("newPath") or item.get("oldPath")
        else:
            path = item
        normalized = _normalize_path(path)
        if normalized:
            paths.append(normalized)
    return paths


def _manual_preflight_changed_files(request: dict[str, Any]) -> list[dict[str, Any]]:
    changed_files = request.get("changedFileDetails") or request.get("changedFiles") or []
    normalized = [item if isinstance(item, dict) else {"path": item} for item in changed_files]
    if any(str(item.get("diffText") or "").strip() for item in normalized):
        return normalized
    diff_text = str(request.get("diffText") or "")
    if not diff_text.strip():
        return normalized
    first_path = next((item.get("path") for item in normalized if item.get("path")), "manual-review.diff")
    return [{"path": first_path, "diffText": diff_text}]


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
