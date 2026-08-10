from __future__ import annotations

import json
import logging
from pathlib import Path
import re
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agent_review import repository
from app.agent_review.runtime import DEFAULT_RUNTIME, runtime_review_key
from app.agent_review_spike.schema import ReviewSchemaError, validate_review_card
from app.agent_review_spike.workspace import ReviewToolError, validate_review_path
from app.code_quality.repository import append_progress, save_result
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.json_utils import utc_now
from app.project_integration.models import Project
from app.project_integration.repository import get_project_group_ai_review_policy
from app.project_review_policy.service import build_project_review_policy_prompt_context
from app.review_context.local_repo import prepare_local_repository_context, task_head_worktree_path
from app.review_record.models import ReviewTask


_LOGGER = logging.getLogger(__name__)
_AGENT_ACTIVITY_NAMES = {
    "list_files": "LIST_FILES",
    "search_code": "SEARCH_CODE",
    "read_file_range": "READ_FILE_RANGE",
    "read_diff_range": "READ_DIFF_RANGE",
    "submit_review": "SUBMIT_REVIEW",
}


def get_settings_response(db: Session) -> dict[str, Any]:
    return repository.agent_settings_response(db)


def update_settings(db: Session, request: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise AppError("VALIDATION_ERROR", "Agent settings request must be an object", 400)
    return repository.update_agent_settings(db, request)


def test_settings(db: Session) -> dict[str, Any]:
    return repository.request_configuration_test(db)


def list_runtimes(db: Session) -> list[dict[str, Any]]:
    response = repository.list_agent_runtime_responses(db)
    db.commit()
    return response


def create_runtime(db: Session, request: dict[str, Any]) -> dict[str, Any]:
    try:
        response = repository.create_agent_runtime(db, request)
        db.commit()
        return response
    except IntegrityError as exception:
        db.rollback()
        runtime_code = str(request.get("runtimeCode") or "").strip().upper()
        raise AppError(
            "AGENT_RUNTIME_ALREADY_EXISTS",
            f"Agent Runtime already exists: {runtime_code}",
            409,
        ) from exception
    except Exception:
        db.rollback()
        raise


def update_runtime(
    db: Session,
    runtime_code: str,
    request: dict[str, Any],
) -> dict[str, Any]:
    try:
        response = repository.update_agent_runtime(db, runtime_code, request)
        db.commit()
        return response
    except Exception:
        db.rollback()
        raise


def delete_runtime(db: Session, runtime_code: str) -> dict[str, Any]:
    try:
        response = repository.delete_agent_runtime(db, runtime_code)
        db.commit()
        return response
    except Exception:
        db.rollback()
        raise


def set_current_runtime(db: Session, runtime_code: str) -> dict[str, Any]:
    try:
        response = repository.set_current_agent_runtime(db, runtime_code)
        db.commit()
        return response
    except Exception:
        db.rollback()
        raise


def test_runtime(db: Session, runtime_code: str) -> dict[str, Any]:
    try:
        response = repository.request_runtime_configuration_test(db, runtime_code)
        db.commit()
        return response
    except Exception:
        db.rollback()
        raise


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
    settings_record = repository.assert_agent_available(db, require_worker=False)
    runtime = repository.selected_agent_runtime_snapshot(db)
    runtime_code = str(runtime.get("runtimeCode") or DEFAULT_RUNTIME)
    custom_runtime = runtime_code != DEFAULT_RUNTIME
    review_key = runtime_review_key(runtime_code)
    provider = "CUSTOM_OPENAI" if custom_runtime else "DEEPSEEK"
    model = str(runtime.get("model") or repository.AGENT_MODEL)
    display_name = (
        f"Agent · {runtime.get('displayName') or 'Custom OpenAI Agent'}"
        if custom_runtime
        else "Agent · Claude Code + DeepSeek"
    )
    budgets, _ = repository.effective_agent_budgets(settings_record)
    requested_files = _changed_file_paths(request)
    if not requested_files:
        raise AppError("VALIDATION_ERROR", "Agent Review requires changedFiles", 400)
    changed_files, excluded_files = _partition_review_paths(
        requested_files,
        forced_excluded=_changed_files_with_sensitive_aliases(request),
    )
    if not changed_files:
        raise AppError(
            "AGENT_NO_REVIEWABLE_FILES",
            f"All {len(requested_files)} changed files are excluded by the Agent Review path policy",
            409,
        )
    diff_text = str(request.get("diffText") or "")
    if excluded_files:
        diff_text = _filter_review_diff(request, changed_files)
        if not diff_text.strip():
            raise AppError(
                "AGENT_SAFE_DIFF_UNAVAILABLE",
                "Allowed changed files could not be separated from excluded sensitive diff content",
                409,
            )
    diff_bytes = len(diff_text.encode("utf-8"))
    if diff_bytes > repository.MAX_DIFF_BYTES:
        raise AppError(
            "AGENT_INPUT_TOO_LARGE",
            f"Agent Review diff exceeds {repository.MAX_DIFF_BYTES} bytes",
            409,
        )
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
        "diffMode": "INLINE" if diff_bytes <= budgets["inlineDiffBytes"] else "TOOL_PAGED",
        "reviewInstructions": review_instructions,
        "baselineContext": _bounded_context(request),
        "reviewCoverage": {
            "totalChangedFileCount": len(requested_files),
            "includedFileCount": len(changed_files),
            "excludedFileCount": len(excluded_files),
            "excludedPaths": excluded_files,
        },
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
        input_payload={
            "worktree": worktree_relative,
            "case": input_case,
            "budgets": budgets,
        },
        completion_context=completion_context,
        comparison_mode=comparison_mode,
        runtime=runtime,
    )
    result_payload = {
        "status": "RUNNING",
        "overallLevel": None,
        "summary": None,
        "findings": [],
        "rawOutput": None,
        "exitCode": None,
        "errorMessage": None,
        "startedAt": utc_now(),
        "finishedAt": None,
        "requestedEngine": "AGENT",
        "effectiveEngine": "AGENT",
        "agentRunId": run.id,
        "agentRunSummary": repository.run_to_summary(run),
    }
    save_result(
        db,
        task_id=int(task.id),
        review_key=review_key,
        project_id=int(project.id),
        profile_code=profile.profile_code,
        provider=provider,
        model=model,
        display_name=display_name,
        sort_order=5,
        result=result_payload,
    )
    if excluded_files:
        append_progress(
            db,
            int(task.id),
            "AGENT_SENSITIVE_PATHS_EXCLUDED",
            "WARN",
            "Agent Review 已排除敏感路径，其余文件继续审查",
            json.dumps(input_case["reviewCoverage"], ensure_ascii=False),
            review_key=review_key,
        )
    append_progress(
        db,
        int(task.id),
        "AGENT_QUEUED",
        "INFO",
        "Agent Review 已进入独立 Worker 队列",
        json.dumps(
            {
                "runId": run.id,
                "diffMode": input_case["diffMode"],
                "diffBytes": diff_bytes,
                **input_case["reviewCoverage"],
            },
            ensure_ascii=False,
        ),
        review_key=review_key,
    )
    db.commit()
    return {
        "taskId": task.id,
        "projectId": project.id,
        "status": "RUNNING",
        "profileCode": profile.profile_code,
        "provider": provider,
        "model": model,
        "reviewKey": review_key,
        "displayName": display_name,
        "requestedEngine": "AGENT",
        "effectiveEngine": "AGENT",
        "agentRunId": run.id,
        "findingCount": 0,
    }


def worker_heartbeat(db: Session, request: dict[str, Any]) -> dict[str, Any]:
    worker_id = _required_worker_id(request)
    raw_state = request.get("state", "IDLE")
    if not isinstance(raw_state, str):
        raise AppError("VALIDATION_ERROR", "state must be a string", 400)
    state = raw_state.strip().upper()
    if state not in {"IDLE", "BUSY", "DRAINING"}:
        raise AppError(
            "VALIDATION_ERROR",
            "state must be IDLE, BUSY, or DRAINING",
            400,
        )
    capacity = request.get("capacity", 1)
    if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity != 1:
        raise AppError("VALIDATION_ERROR", "capacity must be the integer 1", 400)
    active_job_id = _optional_positive_integer(request.get("activeJobId"), "activeJobId")
    active_run_id = _optional_positive_integer(request.get("activeRunId"), "activeRunId")
    capabilities = repository.normalize_worker_capabilities(request.get("capabilities"))
    if state == "IDLE" and (active_job_id is not None or active_run_id is not None):
        raise AppError(
            "VALIDATION_ERROR",
            "IDLE workers cannot report active job or run references",
            400,
        )
    return repository.record_worker_heartbeat(
        db,
        worker_id=worker_id,
        worker_version=str(request.get("workerVersion") or repository.AGENT_RUNNER_VERSION),
        cli_version=str(request.get("cliVersion") or repository.AGENT_CLI_VERSION),
        capabilities=capabilities,
        responses_runner_version=(
            str(request.get("responsesRunnerVersion") or "").strip() or None
        ),
        state=state,
        capacity=capacity,
        active_job_id=active_job_id,
        active_run_id=active_run_id,
    )


def claim_job(db: Session, request: dict[str, Any]) -> dict[str, Any] | None:
    worker_id = _required_worker_id(request)
    if not repository.worker_accepts_claim(db, worker_id=worker_id):
        return None
    try:
        config_test = repository.claim_configuration_test(db, worker_id=worker_id)
    except AppError as exception:
        if exception.code not in {
            "AGENT_REVIEW_UNAVAILABLE",
            "AGENT_RUNTIME_DISABLED",
            "AGENT_RUNTIME_NOT_FOUND",
            "AGENT_RUNTIME_CREDENTIAL_UNAVAILABLE",
        }:
            raise
        # 全局开关或当前 Runtime 在任务入队后发生变化时，配置测试不可领取，
        # 但已排队 Review 仍须进入凭据解析并稳定失败/fallback。
        db.rollback()
        config_test = None
    if config_test is not None:
        return config_test
    expired_run_ids = repository.expire_exhausted_agent_jobs(db)
    claimed = repository.claim_agent_job(db, worker_id=worker_id)
    db.commit()
    if claimed is not None and claimed.get("_fallbackRunId") is not None:
        from app.code_quality.service import schedule_agent_standard_fallback

        schedule_agent_standard_fallback(db, int(claimed["_fallbackRunId"]))
        return None
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
        expired_run_ids = repository.expire_exhausted_agent_jobs(db)
        db.commit()
        from app.code_quality.service import (
            list_unscheduled_agent_standard_fallback_run_ids,
            schedule_agent_standard_fallback,
        )

        run_ids = sorted(
            set(expired_run_ids) | set(list_unscheduled_agent_standard_fallback_run_ids(db))
        )
        for run_id in run_ids:
            schedule_agent_standard_fallback(db, run_id)
        return len(run_ids)
    finally:
        db.close()


def heartbeat_job(db: Session, job_id: int, request: dict[str, Any]) -> dict[str, Any]:
    run_summary = request.get("runSummary") if isinstance(request.get("runSummary"), dict) else {}
    heartbeat_sequence = _safe_heartbeat_sequence(request.get("heartbeatSequence"))
    claim_attempt = _required_claim_attempt(request)
    response = repository.heartbeat_agent_job(
        db,
        job_id=job_id,
        worker_id=_required(request, "workerId"),
        claim_attempt=claim_attempt,
        run_summary=run_summary or None,
    )
    run = repository.find_agent_run_by_job(db, job_id)
    if run is not None:
        _persist_agent_heartbeat_safely(
            db,
            run,
            run_summary,
            heartbeat_sequence=heartbeat_sequence,
            claim_attempt=claim_attempt,
        )
        _persist_agent_trace_safely(
            db,
            run,
            run_summary,
            claim_attempt=claim_attempt,
        )
    return response


def complete_job(db: Session, job_id: int, request: dict[str, Any]) -> dict[str, Any]:
    claim_attempt = _required_claim_attempt(request)
    job, run = repository.get_run_for_completion(
        db,
        job_id=job_id,
        worker_id=_required(request, "workerId"),
        idempotency_key=_required(request, "idempotencyKey"),
        claim_attempt=claim_attempt,
    )
    if run.status == "SUCCEEDED":
        return {"accepted": True, "idempotent": True, "run": repository.run_to_summary(run)}
    input_payload = _json_object(run.input_json)
    runtime_snapshot = (
        input_payload.get("runtime") if isinstance(input_payload.get("runtime"), dict) else {}
    )
    changed_files = ((input_payload.get("case") or {}).get("changedFiles") or [])
    try:
        card = validate_review_card(request.get("reviewCard"), changed_files)
    except (ReviewSchemaError, ValueError, TypeError) as exception:
        raise AppError("AGENT_REVIEW_SCHEMA_INVALID", str(exception), 400) from exception
    run_summary = request.get("runSummary") if isinstance(request.get("runSummary"), dict) else {}
    _persist_agent_trace_safely(
        db,
        run,
        run_summary,
        claim_attempt=claim_attempt,
    )
    run.cli_version = (
        str(run_summary.get("cliVersion") or repository.AGENT_CLI_VERSION)
        if str(run.runner_type or "CLAUDE_CODE") == "CLAUDE_CODE"
        else None
    )
    result = {
        "status": "SUCCESS",
        "overallLevel": card.get("overallLevel"),
        "summary": card.get("summary"),
        "findings": card.get("findings") or [],
        "rawOutput": None,
        "exitCode": 0,
        "errorMessage": None,
        "startedAt": run.started_at,
        "finishedAt": utc_now(),
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
        provider=str(run.provider or "DEEPSEEK"),
        model=str(run.model or repository.AGENT_MODEL),
        display_name=(
            f"Agent · {runtime_snapshot.get('displayName') or '自定义 OpenAI Agent'}"
            if str(run.runner_type or "") == "OPENAI_RESPONSES_AGENT"
            else "Agent · Claude Code + DeepSeek"
        ),
        sort_order=5,
        result=result,
    )
    result.update(
        {
            "_resultId": saved.id,
            "provider": saved.provider,
            "model": saved.model,
            "reviewKey": saved.review_key,
            "displayName": saved.display_name,
        }
    )
    append_progress(
        db,
        run.task_id,
        "AGENT_FINISHED",
        "INFO",
        "Agent Review 已完成并保存正式结果",
        json.dumps(
            {
                **result["agentRunSummary"],
                "claimAttempt": claim_attempt,
            },
            ensure_ascii=False,
        ),
        review_key=run.review_key,
    )
    _finish_existing_review_flow(db, run, result)
    db.commit()
    return {"accepted": True, "idempotent": False, "run": result["agentRunSummary"]}


def fail_job(db: Session, job_id: int, request: dict[str, Any]) -> dict[str, Any]:
    claim_attempt = _required_claim_attempt(request)
    job, run = repository.get_run_for_completion(
        db,
        job_id=job_id,
        worker_id=_required(request, "workerId"),
        idempotency_key=_required(request, "idempotencyKey"),
        claim_attempt=claim_attempt,
    )
    if run.status in {"FAILED", "CANCELLED", "TIMED_OUT"}:
        return {"accepted": True, "idempotent": True, "run": repository.run_to_summary(run)}
    failure_code = str(request.get("failureCode") or "AGENT_RUN_FAILED")[:64]
    failure_message = str(request.get("failureMessage") or "Agent Review failed")[:1024]
    run_summary = request.get("runSummary") if isinstance(request.get("runSummary"), dict) else {}
    _persist_agent_trace_safely(
        db,
        run,
        run_summary,
        claim_attempt=claim_attempt,
    )
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
        json.dumps(
            {
                **repository.run_to_summary(run),
                "claimAttempt": claim_attempt,
            },
            ensure_ascii=False,
        ),
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


def _persist_agent_trace_safely(
    db: Session,
    run: Any,
    run_summary: dict[str, Any],
    *,
    claim_attempt: int,
) -> None:
    if "audit" not in run_summary or not isinstance(run_summary.get("audit"), dict):
        return
    try:
        locked_run = repository.lock_agent_run_for_trace(db, int(run.id))
        if locked_run is None:
            return
        audit = repository.sanitize_agent_audit(run_summary.get("audit"))
        existing = repository.agent_trace_sequences(
            db,
            task_id=int(locked_run.task_id),
            review_key=str(locked_run.review_key),
            run_id=int(locked_run.id),
            claim_attempt=claim_attempt,
        )
        if 0 not in existing:
            _append_agent_attempt_start(
                db,
                locked_run,
                claim_attempt=claim_attempt,
            )
            existing.add(0)
        for event in audit.get("events") or []:
            sequence = int(event.get("sequence") or 0)
            if sequence < 1 or sequence in existing:
                continue
            phase, message = _agent_trace_phase_and_message(event)
            detail = {
                "runId": int(locked_run.id),
                "claimAttempt": claim_attempt,
                "sequence": sequence,
                "activity": _AGENT_ACTIVITY_NAMES[str(event["tool"])],
                "status": event["status"],
                "durationMs": event["durationMs"],
                "itemCount": event["itemCount"],
                "sourceBytes": event["sourceBytes"],
                "pathSummary": event.get("pathSummary") or [],
                "reviewBudget": event.get("reviewBudget") or {},
            }
            if event.get("errorCode"):
                detail["errorCode"] = event["errorCode"]
            append_progress(
                db,
                int(locked_run.task_id),
                phase,
                "WARN" if event["status"] == "FAILED" else "INFO",
                message,
                json.dumps(detail, ensure_ascii=False),
                review_key=locked_run.review_key,
            )
            existing.add(sequence)
        db.commit()
    except Exception as exception:
        db.rollback()
        _LOGGER.warning(
            "Agent Review trace persistence failed runId=%s errorType=%s",
            getattr(run, "id", None),
            type(exception).__name__,
        )


def _persist_agent_heartbeat_safely(
    db: Session,
    run: Any,
    run_summary: dict[str, Any],
    *,
    heartbeat_sequence: int | None,
    claim_attempt: int,
) -> None:
    if heartbeat_sequence is None:
        return
    try:
        locked_run = repository.lock_agent_run_for_trace(db, int(run.id))
        if locked_run is None:
            return
        heartbeat_sequences = repository.agent_heartbeat_sequences(
            db,
            task_id=int(locked_run.task_id),
            review_key=str(locked_run.review_key),
            run_id=int(locked_run.id),
            claim_attempt=claim_attempt,
        )
        if heartbeat_sequence in heartbeat_sequences:
            return
        trace_sequences = repository.agent_trace_sequences(
            db,
            task_id=int(locked_run.task_id),
            review_key=str(locked_run.review_key),
            run_id=int(locked_run.id),
            claim_attempt=claim_attempt,
        )
        if 0 not in trace_sequences:
            _append_agent_attempt_start(
                db,
                locked_run,
                claim_attempt=claim_attempt,
            )
        audit = repository.sanitize_agent_audit(run_summary.get("audit"))
        effective_budgets = repository.run_to_summary(locked_run).get(
            "effectiveBudgets"
        )
        detail = {
            "runId": int(locked_run.id),
            "claimAttempt": claim_attempt,
            "heartbeatSequence": heartbeat_sequence,
            "activity": "HEARTBEAT",
            "status": "RUNNING",
            "phase": (audit.get("reviewBudget") or {}).get("phase") or "DISCOVERY",
            "toolCallCount": int(audit.get("toolCallCount") or 0),
            "evidenceCallsUsed": int(audit.get("evidenceCallsUsed") or 0),
            "sourceBytesReturned": int(audit.get("sourceBytesReturned") or 0),
            "diffBytesReturned": int(audit.get("diffBytesReturned") or 0),
            "reviewBudget": audit.get("reviewBudget") or {},
        }
        if effective_budgets:
            detail["effectiveBudgets"] = effective_budgets
        append_progress(
            db,
            int(locked_run.task_id),
            "AGENT_HEARTBEAT",
            "INFO",
            "Agent Worker 运行心跳",
            json.dumps(detail, ensure_ascii=False),
            review_key=locked_run.review_key,
        )
        db.commit()
    except Exception as exception:
        db.rollback()
        _LOGGER.warning(
            "Agent Review heartbeat trace persistence failed runId=%s errorType=%s",
            getattr(run, "id", None),
            type(exception).__name__,
        )


def _append_agent_attempt_start(
    db: Session,
    run: Any,
    *,
    claim_attempt: int,
) -> None:
    if claim_attempt > 1:
        append_progress(
            db,
            int(run.task_id),
            "AGENT_RECLAIMED",
            "WARN",
            "Agent 任务租约过期，已由可用 Worker 重新领取",
            json.dumps(
                {
                    "runId": int(run.id),
                    "claimAttempt": claim_attempt,
                    "reasonCode": "LEASE_EXPIRED",
                },
                ensure_ascii=False,
            ),
            review_key=run.review_key,
        )
    append_progress(
        db,
        int(run.task_id),
        "AGENT_ANALYZING",
        "INFO",
        "Agent 正在分析代码变更",
        json.dumps(
            {
                "runId": int(run.id),
                "claimAttempt": claim_attempt,
                "sequence": 0,
                "activity": "ANALYZING",
            },
            ensure_ascii=False,
        ),
        review_key=run.review_key,
    )


def _safe_heartbeat_sequence(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        sequence = int(value)
    except (TypeError, ValueError):
        return None
    return sequence if 0 <= sequence <= 1_000 else None


def _agent_trace_phase_and_message(event: dict[str, Any]) -> tuple[str, str]:
    tool = str(event.get("tool") or "")
    budget_phase = str((event.get("reviewBudget") or {}).get("phase") or "")
    if tool == "submit_review" or budget_phase == "SUBMIT":
        return "AGENT_SUBMITTING", "Agent 正在提交 Review Card"
    if budget_phase == "CONVERGE":
        return "AGENT_CONVERGING", "Agent 已停止扩大范围，正在收敛结论"
    return "AGENT_TOOL_ACTIVITY", "Agent 正在补充审查证据"


def _ensure_worktree(task: ReviewTask, project: Project) -> Path:
    path = task_head_worktree_path(task.id)
    if path.is_dir():
        return path
    summaries: list[dict[str, Any]] = []
    for _attempt in range(2):
        outcome = prepare_local_repository_context(
            project_id=project.id,
            task_id=task.id,
            repository_url=project.repository_url,
            git_project_id=project.git_project_id,
            head_ref=task.after_sha or task.commit_sha,
        )
        nested_summary = outcome.get("summary") if isinstance(outcome, dict) else None
        summary = nested_summary if isinstance(nested_summary, dict) else outcome
        summary = dict(summary) if isinstance(summary, dict) else {}
        unavailable_contexts = (
            outcome.get("unavailableContexts") if isinstance(outcome, dict) else None
        )
        if (
            not summary.get("reason")
            and isinstance(unavailable_contexts, list)
            and unavailable_contexts
            and isinstance(unavailable_contexts[0], dict)
        ):
            summary["reason"] = unavailable_contexts[0].get("reason")
        summaries.append(summary)
        if str(summary.get("status") or "").upper() == "PREPARED" and path.is_dir():
            return path
    last_summary = summaries[-1] if summaries else {}
    reason = str(last_summary.get("reason") or "Agent Review task worktree is unavailable")
    failure_phase = str(last_summary.get("failurePhase") or "UNKNOWN")
    raise AppError(
        "AGENT_WORKTREE_UNAVAILABLE",
        f"{reason} (failurePhase={failure_phase}, attempts={len(summaries)})"[:500],
        409,
    )


def _changed_file_paths(request: dict[str, Any]) -> list[str]:
    values = request.get("changedFiles") or request.get("changedFileDetails") or []
    paths = []
    for item in values:
        path = (item.get("path") or item.get("newPath")) if isinstance(item, dict) else item
        text = str(path or "").strip().replace("\\", "/")
        if text and text not in paths:
            paths.append(text)
    return paths


def _partition_review_paths(
    paths: list[str],
    *,
    forced_excluded: set[str] | None = None,
) -> tuple[list[str], list[str]]:
    included: list[str] = []
    excluded: list[str] = []
    forced = forced_excluded or set()
    for path in paths:
        normalized = str(path or "").strip().replace("\\", "/")
        if normalized in forced:
            excluded.append(normalized)
            continue
        try:
            included.append(validate_review_path(path))
        except ReviewToolError as exception:
            if exception.code != "SENSITIVE_PATH_DENIED":
                raise AppError(exception.code, str(exception), 409) from exception
            if normalized and normalized not in excluded:
                excluded.append(normalized)
    return included, excluded


def _changed_files_with_sensitive_aliases(request: dict[str, Any]) -> set[str]:
    forced_excluded: set[str] = set()
    values: list[Any] = []
    for field in ("changedFiles", "changedFileDetails"):
        field_values = request.get(field) or []
        if isinstance(field_values, list):
            values.extend(field_values)
    for item in values:
        if not isinstance(item, dict):
            continue
        primary = str(
            item.get("path") or item.get("newPath") or item.get("oldPath") or ""
        ).strip().replace("\\", "/")
        candidates = [
            str(item.get(field) or "").strip().replace("\\", "/")
            for field in ("path", "newPath", "oldPath")
            if str(item.get(field) or "").strip()
        ]
        for candidate in candidates:
            try:
                validate_review_path(candidate)
            except ReviewToolError as exception:
                if exception.code == "SENSITIVE_PATH_DENIED":
                    if primary:
                        forced_excluded.add(primary)
                    break
                raise AppError(exception.code, str(exception), 409) from exception
    return forced_excluded


def _filter_review_diff(request: dict[str, Any], included_paths: list[str]) -> str:
    included = set(included_paths)
    sections = _split_unified_diff(str(request.get("diffText") or ""))
    selected: list[str] = []
    covered: set[str] = set()
    for path, section in sections:
        if path in included:
            selected.append(section)
            covered.add(path)
    details = request.get("changedFileDetails") or []
    if isinstance(details, list):
        for item in details:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or item.get("newPath") or item.get("oldPath") or "").strip().replace("\\", "/")
            diff = str(item.get("diffText") or "")
            if path not in included or path in covered or not diff.strip():
                continue
            selected.append(_ensure_file_diff_header(path, diff))
            covered.add(path)
    return "\n".join(section.rstrip("\n") for section in selected if section.strip())


def _split_unified_diff(diff_text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_path: str | None = None
    current_lines: list[str] = []
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            if current_path and current_lines:
                sections.append((current_path, "\n".join(current_lines)))
            current_path = _path_from_diff_header(line)
            current_lines = [line]
        elif current_path:
            current_lines.append(line)
    if current_path and current_lines:
        sections.append((current_path, "\n".join(current_lines)))
    return sections


def _path_from_diff_header(line: str) -> str | None:
    parts = line.split()
    if len(parts) < 4:
        return None
    candidate = parts[3]
    if candidate.startswith("b/"):
        candidate = candidate[2:]
    if candidate == "/dev/null" and parts[2].startswith("a/"):
        candidate = parts[2][2:]
    return candidate.strip().replace("\\", "/") or None


def _ensure_file_diff_header(path: str, diff_text: str) -> str:
    if diff_text.lstrip().startswith("diff --git "):
        return diff_text
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n{diff_text}"


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


def _required_worker_id(request: dict[str, Any]) -> str:
    raw_value = request.get("workerId")
    if not isinstance(raw_value, str):
        raise AppError("VALIDATION_ERROR", "workerId must be a string", 400)
    value = raw_value.strip()
    if not value:
        raise AppError("VALIDATION_ERROR", "workerId is required", 400)
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", value):
        raise AppError(
            "VALIDATION_ERROR",
            "workerId contains unsupported characters or exceeds 128 characters",
            400,
        )
    return value


def _optional_positive_integer(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 1
        or value > 9_223_372_036_854_775_807
    ):
        raise AppError(
            "VALIDATION_ERROR",
            f"{field} must be a positive integer or null",
            400,
        )
    return value


def _required_claim_attempt(request: dict[str, Any]) -> int:
    value = request.get("claimAttempt")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise AppError(
            "VALIDATION_ERROR",
            "claimAttempt must be a positive integer",
            400,
        )
    return value
