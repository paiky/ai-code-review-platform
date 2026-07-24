from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.agent_review import repository
from app.agent_review.repository import AGENT_REVIEW_KEY
from app.agent_review_spike.schema import ReviewSchemaError, validate_review_card
from app.agent_review_spike.workspace import ReviewToolError, validate_review_path
from app.code_quality.repository import append_progress, save_result
from app.core.config import get_settings
from app.core.errors import AppError
from app.project_integration.models import Project
from app.project_integration.repository import get_project_group_ai_review_policy
from app.project_review_policy.service import build_project_review_policy_prompt_context
from app.review_context.local_repo import prepare_local_repository_context, task_head_worktree_path
from app.review_record.models import ReviewTask


def get_settings_response(db: Session) -> dict[str, Any]:
    return repository.agent_settings_response(db)


def update_settings(db: Session, request: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise AppError("VALIDATION_ERROR", "Agent settings request must be an object", 400)
    return repository.update_agent_settings(db, request)


def test_settings(db: Session) -> dict[str, Any]:
    return repository.request_configuration_test(db)


def resolve_review_engine(
    db: Session,
    project: Project,
    override: Any = None,
    *,
    explicit: bool = False,
) -> str:
    policy = get_project_group_ai_review_policy(db, project)
    value = override if override is not None else policy.get("reviewEngine")
    engine = str(value or "STANDARD").strip().upper()
    if engine not in {"STANDARD", "AGENT"}:
        raise AppError("VALIDATION_ERROR", f"Unsupported reviewEngine: {value}", 400)
    if engine == "AGENT":
        if not bool(policy.get("agentSourceExportAllowed")):
            if explicit:
                raise AppError(
                    "AGENT_REVIEW_UNAVAILABLE",
                    "Project group has not authorized source export for Agent Review",
                    409,
                )
            return "AGENT_UNAVAILABLE"
        try:
            repository.assert_agent_available(db, require_worker=False)
            if repository.agent_settings_response(db).get("workerStatus") != "ONLINE":
                if explicit:
                    repository.assert_agent_available(db, require_worker=True)
                return "AGENT_UNAVAILABLE"
        except AppError:
            if explicit:
                raise
            return "AGENT_UNAVAILABLE"
    return engine


def enqueue_agent_review(
    db: Session,
    *,
    task: ReviewTask,
    project: Project,
    profile: Any,
    request: dict[str, Any],
    comparison_mode: bool = False,
    completion_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    repository.assert_agent_available(db, require_worker=False)
    diff_text = str(request.get("diffText") or "")
    diff_bytes = len(diff_text.encode("utf-8"))
    if diff_bytes > repository.MAX_DIFF_BYTES:
        raise AppError(
            "AGENT_INPUT_TOO_LARGE",
            f"Agent Review diff exceeds {repository.MAX_DIFF_BYTES} bytes",
            409,
        )
    changed_files = _changed_file_paths(request)
    if not changed_files:
        raise AppError("VALIDATION_ERROR", "Agent Review requires changedFiles", 400)
    try:
        changed_files = [validate_review_path(path) for path in changed_files]
    except ReviewToolError as exception:
        raise AppError(exception.code, str(exception), 409) from exception
    worktree = _ensure_worktree(task, project)
    policy_context = build_project_review_policy_prompt_context(db, int(project.id))
    review_instructions = "\n\n".join(
        value
        for value in (
            getattr(profile, "review_instructions", None),
            policy_context.get("promptText"),
        )
        if str(value or "").strip()
    )
    input_case = {
        "id": f"task-{task.id}",
        "title": request.get("title") or f"{task.trigger_type} {task.external_source_id or ''}".strip(),
        "baseRef": request.get("baseRef") or task.target_branch,
        "commitSha": request.get("commitSha") or task.after_sha or task.commit_sha,
        "changedFiles": changed_files,
        "diff": diff_text,
        "diffMode": "INLINE" if diff_bytes <= repository.INLINE_DIFF_BYTES else "TOOL_PAGED",
        "reviewInstructions": review_instructions,
        "baselineContext": _bounded_context(request),
    }
    workspace_root = Path(get_settings().local_repo_workspace_root).expanduser().resolve(strict=False)
    try:
        worktree_relative = str(worktree.resolve(strict=True).relative_to(workspace_root)).replace("\\", "/")
    except (FileNotFoundError, ValueError) as exception:
        raise AppError(
            "AGENT_WORKTREE_UNAVAILABLE",
            "Agent Review worktree is outside the configured workspace root",
            409,
        ) from exception
    run = repository.create_agent_job(
        db,
        task_id=int(task.id),
        project_id=int(project.id),
        input_payload={"worktree": worktree_relative, "case": input_case},
        completion_context=completion_context,
        comparison_mode=comparison_mode,
    )
    result_payload = {
        "status": "RUNNING",
        "overallLevel": None,
        "summary": None,
        "findings": [],
        "rawOutput": None,
        "exitCode": None,
        "errorMessage": None,
        "startedAt": datetime.now(),
        "finishedAt": None,
        "requestedEngine": "AGENT",
        "effectiveEngine": "AGENT",
        "agentRunId": run.id,
        "agentRunSummary": repository.run_to_summary(run),
    }
    save_result(
        db,
        task_id=int(task.id),
        review_key=AGENT_REVIEW_KEY,
        project_id=int(project.id),
        profile_code=profile.profile_code,
        provider="DEEPSEEK",
        model=repository.AGENT_MODEL,
        display_name="Agent · Claude Code + DeepSeek",
        sort_order=5,
        result=result_payload,
    )
    append_progress(
        db,
        int(task.id),
        "AGENT_QUEUED",
        "INFO",
        "Agent Review 已进入独立 Worker 队列",
        json.dumps(
            {"runId": run.id, "diffMode": input_case["diffMode"], "diffBytes": diff_bytes},
            ensure_ascii=False,
        ),
        review_key=AGENT_REVIEW_KEY,
    )
    db.commit()
    return {
        "taskId": task.id,
        "projectId": project.id,
        "status": "RUNNING",
        "profileCode": profile.profile_code,
        "provider": "DEEPSEEK",
        "model": repository.AGENT_MODEL,
        "reviewKey": AGENT_REVIEW_KEY,
        "displayName": "Agent · Claude Code + DeepSeek",
        "requestedEngine": "AGENT",
        "effectiveEngine": "AGENT",
        "agentRunId": run.id,
        "findingCount": 0,
    }


def worker_heartbeat(db: Session, request: dict[str, Any]) -> dict[str, Any]:
    return repository.record_worker_heartbeat(
        db,
        worker_id=_required(request, "workerId"),
        worker_version=str(request.get("workerVersion") or repository.AGENT_RUNNER_VERSION),
        cli_version=str(request.get("cliVersion") or repository.AGENT_CLI_VERSION),
    )


def claim_job(db: Session, request: dict[str, Any]) -> dict[str, Any] | None:
    worker_id = _required(request, "workerId")
    config_test = repository.claim_configuration_test(db, worker_id=worker_id)
    if config_test is not None:
        return config_test
    expired_run_ids = repository.expire_exhausted_agent_jobs(db)
    claimed = repository.claim_agent_job(db, worker_id=worker_id)
    db.commit()
    if expired_run_ids:
        from app.code_quality.service import schedule_agent_standard_fallback

        for run_id in expired_run_ids:
            schedule_agent_standard_fallback(db, run_id)
    return claimed


def complete_configuration_test(db: Session, request: dict[str, Any]) -> dict[str, Any]:
    _required(request, "workerId")
    return repository.complete_configuration_test(
        db,
        request_id=_required(request, "requestId"),
        status=str(request.get("status") or "FAILED"),
        message=str(request.get("message") or "") or None,
        duration_ms=request.get("durationMs"),
    )


def recover_unavailable_agent_jobs() -> int:
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        run_ids = repository.expire_exhausted_agent_jobs(db)
        db.commit()
        if run_ids:
            from app.code_quality.service import schedule_agent_standard_fallback

            for run_id in run_ids:
                schedule_agent_standard_fallback(db, run_id)
        return len(run_ids)
    finally:
        db.close()


def heartbeat_job(db: Session, job_id: int, request: dict[str, Any]) -> dict[str, Any]:
    return repository.heartbeat_agent_job(
        db,
        job_id=job_id,
        worker_id=_required(request, "workerId"),
        run_summary=request.get("runSummary") if isinstance(request.get("runSummary"), dict) else None,
    )


def complete_job(db: Session, job_id: int, request: dict[str, Any]) -> dict[str, Any]:
    job, run = repository.get_run_for_completion(
        db,
        job_id=job_id,
        worker_id=_required(request, "workerId"),
        idempotency_key=_required(request, "idempotencyKey"),
    )
    if run.status == "SUCCEEDED":
        return {"accepted": True, "idempotent": True, "run": repository.run_to_summary(run)}
    input_payload = _json_object(run.input_json)
    changed_files = ((input_payload.get("case") or {}).get("changedFiles") or [])
    try:
        card = validate_review_card(request.get("reviewCard"), changed_files)
    except (ReviewSchemaError, ValueError, TypeError) as exception:
        raise AppError("AGENT_REVIEW_SCHEMA_INVALID", str(exception), 400) from exception
    run_summary = request.get("runSummary") if isinstance(request.get("runSummary"), dict) else {}
    run.cli_version = str(run_summary.get("cliVersion") or repository.AGENT_CLI_VERSION)
    result = {
        "status": "SUCCESS",
        "overallLevel": card.get("overallLevel"),
        "summary": card.get("summary"),
        "findings": card.get("findings") or [],
        "rawOutput": None,
        "exitCode": 0,
        "errorMessage": None,
        "startedAt": run.started_at,
        "finishedAt": datetime.now(),
        "requestedEngine": "AGENT",
        "effectiveEngine": "AGENT",
        "agentRunId": run.id,
    }
    repository.finish_agent_records(
        db,
        job=job,
        run=run,
        status="SUCCEEDED",
        effective_engine="AGENT",
        summary=run_summary,
    )
    result["agentRunSummary"] = repository.run_to_summary(run, fallback_triggered=False)
    task = db.get(ReviewTask, run.task_id)
    if task is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {run.task_id}", 404)
    saved = save_result(
        db,
        task_id=run.task_id,
        review_key=run.review_key,
        project_id=task.project_id,
        profile_code=task.code_quality_profile_code or "backend-default-ai-review",
        provider="DEEPSEEK",
        model=repository.AGENT_MODEL,
        display_name="Agent · Claude Code + DeepSeek",
        sort_order=5,
        result=result,
    )
    result["_resultId"] = saved.id
    append_progress(
        db,
        run.task_id,
        "AGENT_FINISHED",
        "INFO",
        "Agent Review 已完成并保存正式结果",
        json.dumps(result["agentRunSummary"], ensure_ascii=False),
        review_key=run.review_key,
    )
    _finish_existing_review_flow(db, run, result)
    db.commit()
    return {"accepted": True, "idempotent": False, "run": result["agentRunSummary"]}


def fail_job(db: Session, job_id: int, request: dict[str, Any]) -> dict[str, Any]:
    job, run = repository.get_run_for_completion(
        db,
        job_id=job_id,
        worker_id=_required(request, "workerId"),
        idempotency_key=_required(request, "idempotencyKey"),
    )
    if run.status in {"FAILED", "CANCELLED", "TIMED_OUT"}:
        return {"accepted": True, "idempotent": True, "run": repository.run_to_summary(run)}
    failure_code = str(request.get("failureCode") or "AGENT_RUN_FAILED")[:64]
    failure_message = str(request.get("failureMessage") or "Agent Review failed")[:1024]
    run_summary = request.get("runSummary") if isinstance(request.get("runSummary"), dict) else {}
    cancelled = failure_code == "AGENT_CANCELLED"
    repository.finish_agent_records(
        db,
        job=job,
        run=run,
        status="CANCELLED" if cancelled else ("TIMED_OUT" if failure_code == "AGENT_TIMEOUT" else "FAILED"),
        effective_engine="AGENT" if cancelled else "STANDARD_FALLBACK",
        summary=run_summary,
        failure_code=failure_code,
        failure_message=failure_message,
        clear_input=cancelled,
    )
    append_progress(
        db,
        run.task_id,
        "AGENT_CANCELLED" if cancelled else "AGENT_FALLBACK",
        "WARN" if not cancelled else "INFO",
        "Agent Review 已取消" if cancelled else "Agent Review 失败，准备执行普通 Review 降级",
        json.dumps(repository.run_to_summary(run), ensure_ascii=False),
        review_key=run.review_key,
    )
    db.commit()
    if not cancelled:
        from app.code_quality.service import schedule_agent_standard_fallback

        schedule_agent_standard_fallback(db, run.id)
    return {"accepted": True, "idempotent": False, "run": repository.run_to_summary(run)}


def _finish_existing_review_flow(db: Session, run: Any, result: dict[str, Any]) -> None:
    from app.code_quality.service import _send_auto_review_notification, _sync_task_status_after_review

    _sync_task_status_after_review(db, run.task_id, result)
    context = _json_object(run.completion_context_json)
    if run.comparison_mode or not context.get("autoNotification"):
        return
    _send_auto_review_notification(
        db,
        run.task_id,
        result,
        context.get("ruleResultId"),
        context.get("riskCard"),
        context.get("focusChangeTypes") or [],
        context.get("focusRuleCodes") or [],
        context.get("notificationContext") or {},
        bool(context.get("reminderCardEnabled", True)),
    )


def _ensure_worktree(task: ReviewTask, project: Project) -> Path:
    path = task_head_worktree_path(task.id)
    if path.is_dir():
        return path
    outcome = prepare_local_repository_context(
        project_id=project.id,
        task_id=task.id,
        repository_url=project.repository_url,
        git_project_id=project.git_project_id,
        head_ref=task.after_sha or task.commit_sha,
    )
    if str(outcome.get("status") or "").upper() != "PREPARED" or not path.is_dir():
        raise AppError(
            "AGENT_WORKTREE_UNAVAILABLE",
            str(outcome.get("reason") or "Agent Review task worktree is unavailable")[:500],
            409,
        )
    return path


def _changed_file_paths(request: dict[str, Any]) -> list[str]:
    values = request.get("changedFiles") or request.get("changedFileDetails") or []
    paths = []
    for item in values:
        path = (item.get("path") or item.get("newPath")) if isinstance(item, dict) else item
        text = str(path or "").strip().replace("\\", "/")
        if text and text not in paths:
            paths.append(text)
    return paths


def _bounded_context(request: dict[str, Any]) -> str:
    value = {
        "deterministicPreflight": request.get("_deterministicPreflightSummary") or {},
        "projectPolicies": request.get("projectPolicies") or [],
    }
    return json.dumps(value, ensure_ascii=False)[:100_000]


def _json_object(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _required(request: dict[str, Any], field: str) -> str:
    value = str(request.get(field) or "").strip()
    if not value:
        raise AppError("VALIDATION_ERROR", f"{field} is required", 400)
    return value
