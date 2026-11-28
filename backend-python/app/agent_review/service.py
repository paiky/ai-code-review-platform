from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryFile
from time import perf_counter
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agent_review import repository
from app.agent_review.runtime import (
    ANTHROPIC_MESSAGES_RUNNER,
    CLAUDE_CODE_RUNNER,
    DEFAULT_RUNTIME,
    OPENAI_CHAT_RUNNER,
    OPENAI_RESPONSES_RUNNER,
    runtime_provider,
    runtime_review_key,
)
from app.agent_review.schemas import (
    GROUPED_RUNNER_CAPABILITIES,
    CONTEXT_REVIEW_CAPABILITY,
    AgentConversationTurnEvent,
    parse_agent_conversation_events,
)
from app.agent_review_spike.diff import DiffSection, diff_by_file, split_diff_sections, with_diff_section_header
from app.agent_review_spike.fact_check import attach_fact_checks
from app.agent_review_spike.finding_anchor import attach_finding_anchors
from app.agent_review_spike.grouped import validate_group_coverage
from app.agent_review_spike.schema import ReviewSchemaError, validate_review_card
from app.agent_review_spike.workspace import ReviewToolError, validate_review_path
from app.code_quality.models import CodeQualitySchedulerJob
from app.code_quality.repository import append_progress, save_result, scrub_sensitive
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.errors import AppError
from app.core.json_utils import utc_now
from app.project_integration import gitlab_client
from app.project_integration.models import Project
from app.project_integration.repository import get_project_review_policy
from app.project_review_policy.service import build_project_review_policy_prompt_context
from app.review_context.local_repo import prepare_local_repository_context, task_head_worktree_path
from app.review_record.models import AUTO_FIX_REVIEW_TRIGGER, ReviewTask
from app.review_record.repository import (
    parse_agent_completion_context,
    resolve_agent_completion_notification,
)
from app.review_memory.service import select_review_memories
from app.review_prompt_metadata import PlatformPromptMarker, review_profile_input
from app.review_rules.input import build_file_rule_input


_LOGGER = logging.getLogger(__name__)
_AGENT_PROMPT_PROTOCOLS = {
    OPENAI_RESPONSES_RUNNER: "OPENAI_RESPONSES",
    OPENAI_CHAT_RUNNER: "OPENAI_CHAT_COMPLETIONS",
    ANTHROPIC_MESSAGES_RUNNER: "ANTHROPIC_MESSAGES",
    CLAUDE_CODE_RUNNER: "ANTHROPIC_COMPATIBLE",
}
_DISPATCH_PROGRESS_SCHEMA_VERSION = "agent-dispatch-progress-v1"
_DISPATCH_OPERATION = "AGENT_ENQUEUE"
_PUSH_DIFF_TIMEOUT_SECONDS = 15
_COMMIT_SHA = re.compile(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}")
_NON_REGULAR_DIFF_MODE = re.compile(
    r"^(?:(?:old mode|new mode|new file mode|deleted file mode) |index [^\n ]+ )(?:120000|160000)$",
    re.MULTILINE,
)
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


def create_model_connection(db: Session, request: dict[str, Any]) -> dict[str, Any]:
    try:
        response = repository.create_agent_model_connection(db, request)
        db.commit()
        return response
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


def test_runtime(
    db: Session,
    runtime_code: str,
    request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        response = repository.request_runtime_configuration_test(
            db,
            runtime_code,
            request or {},
        )
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
    policy = get_project_review_policy(db, project)
    _LOGGER.info(
        "Agent review engine policy projectId=%s targetType=%s source=%s",
        project.id,
        project.target_type,
        policy.get("source"),
    )

    value = override if override is not None else policy.get("reviewEngine")
    engine = str(value or "STANDARD").strip().upper()
    if engine not in {"STANDARD", "AGENT"}:
        raise AppError("VALIDATION_ERROR", f"Unsupported reviewEngine: {value}", 400)
    if engine == "AGENT":
        if not bool(policy.get("agentSourceExportAllowed")):
            if explicit:
                raise AppError(
                    "AGENT_REVIEW_UNAVAILABLE",
                    "Project has not authorized source export for Agent Review",
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
    expected_runtime: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings_record = repository.assert_agent_available(db, require_worker=False)
    runtime = repository.selected_agent_runtime_snapshot(db)
    runner_type = runtime.get("runnerType")
    unified_review = runner_type in {OPENAI_CHAT_RUNNER, OPENAI_RESPONSES_RUNNER}
    if unified_review and not repository.worker_capability_online(db, CONTEXT_REVIEW_CAPABILITY, runner_type):
        raise AppError("AGENT_REVIEW_UNAVAILABLE", "No online Worker supports unified Agent Review for this Runtime", 409)
    runtime_code = str(runtime.get("runtimeCode") or DEFAULT_RUNTIME)
    review_key = runtime_review_key(runtime_code)
    provider = runtime_provider(runtime)
    model = str(runtime.get("model") or repository.AGENT_MODEL)
    review_snapshot = request.get("_reviewSnapshot")
    if review_snapshot:
        from app.code_quality.service import review_runtime_digest

        runtime_contract = {
            "runtimeCode": runtime_code,
            "runtimeDigest": review_runtime_digest(runtime),
            "reviewKey": review_key,
            "provider": provider,
            "model": model,
        }
        if expected_runtime is not None and runtime_contract != expected_runtime:
            raise AppError("AUTO_FIX_REVIEW_CONFIG_CHANGED", "Agent runtime changed since the original result", 409)
        review_snapshot = {**review_snapshot, **runtime_contract}
    display_name = f"Agent · {runtime.get('displayName') or 'Claude Code + DeepSeek'}"
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
    diff_text = _filter_review_diff(request, changed_files, allow_unheaded=not excluded_files)
    if task.trigger_type == "GITLAB_MR_WEBHOOK":
        diff_text = _complete_mr_diff(task, project, changed_files, diff_text)
    if excluded_files and not diff_text.strip():
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
    dispatch_attempt_id = f"agent-dispatch-{task.id}-{uuid4().hex}"
    mark_review_failed = not bool((completion_context or {}).get("autoNotification"))
    worktree = _prepare_agent_worktree_with_progress(
        db,
        task=task,
        project=project,
        review_key=review_key,
        dispatch_attempt_id=dispatch_attempt_id,
        changed_file_count=len(changed_files),
        diff_bytes=diff_bytes,
        mark_review_failed=mark_review_failed,
    )
    if task.trigger_type == "GITLAB_PUSH_WEBHOOK":
        diff_text = _complete_push_diff(
            task, worktree, changed_files, diff_text, changed_file_details=request.get("changedFileDetails"),
        )
        diff_bytes = len(diff_text.encode("utf-8"))
    if review_snapshot:
        # A reused worktree may predate an in-place rerun of the source review.
        worktree_matches = _worktree_matches_head(worktree, review_snapshot["headSha"])
        if expected_runtime is not None and not worktree_matches:
            raise AppError("AUTO_FIX_REVIEW_INPUT_INCOMPLETE", "Agent worktree does not match the repair commit", 409)
        review_snapshot["complete"] = bool(
            review_snapshot.get("complete")
            and worktree_matches
            and not excluded_files
            and diff_text == str(request.get("diffText") or "")
        )
    dispatch_detail = _dispatch_progress_base(
        review_key=review_key,
        dispatch_attempt_id=dispatch_attempt_id,
    )
    policy_started = perf_counter()
    _append_dispatch_progress(
        db,
        task_id=int(task.id),
        phase="PROJECT_POLICY_BUILD_STARTED",
        level="INFO",
        message="Agent Review 正在构建项目 Review 策略上下文",
        base_detail=dispatch_detail,
        status="STARTED",
        started_at=policy_started,
    )
    db.commit()
    try:
        policy_context = build_project_review_policy_prompt_context(db, int(project.id))
    except Exception as exception:
        wrapped = _persist_dispatch_failure(
            db,
            task_id=int(task.id),
            phase="PROJECT_POLICY_BUILD_FAILED",
            message="Agent Review 项目 Review 策略上下文构建失败",
            base_detail=dispatch_detail,
            started_at=policy_started,
            exception=exception,
            fallback_code="AGENT_POLICY_BUILD_FAILED",
            fallback_message="Agent Review project policy context build failed",
            mark_review_failed=mark_review_failed,
        )
        if wrapped is not None:
            raise wrapped from exception
        raise

    input_started = perf_counter()
    _append_dispatch_progress(
        db,
        task_id=int(task.id),
        phase="PROJECT_POLICY_BUILD_COMPLETED",
        level="INFO",
        message="Agent Review 项目 Review 策略上下文已构建",
        base_detail=dispatch_detail,
        status="COMPLETED",
        started_at=policy_started,
        extra=_policy_progress_summary(policy_context),
    )
    _append_dispatch_progress(
        db,
        task_id=int(task.id),
        phase="AGENT_INPUT_BUILD_STARTED",
        level="INFO",
        message="Agent Review 正在组装安全输入并校验 Worktree",
        base_detail=dispatch_detail,
        status="STARTED",
        started_at=input_started,
    )
    db.commit()

    try:
        memory = select_review_memories(
            db,
            project_id=int(project.id),
            target_type=task.target_type,
            changed_files=changed_files,
            diff_text=diff_text,
            issue_hints=repository.normalize_completion_context(completion_context).get(
                "focusChangeTypes", []
            ),
            policy_context=policy_context,
        )
        profile_instructions = str(getattr(profile, "review_instructions", None) or "").strip()
        profile_input = review_profile_input(profile.profile_code, profile_instructions)
        file_rules = (
            None if request.get("_skipFileRules") else build_file_rule_input(changed_files, diff_text)
        )
        if review_snapshot and file_rules:
            review_snapshot["fileRuleCatalogVersion"] = file_rules["summary"]["catalogVersion"]
        base_instructions = "\n\n".join(
            value for value in (profile_instructions, policy_context.get("promptText"))
            if str(value or "").strip()
        )
        review_instructions = "\n\n".join(
            value for value in (base_instructions, file_rules["text"] if file_rules else "") if value
        )
        diff_mode = "INLINE" if unified_review or diff_bytes <= budgets["inlineDiffBytes"] else "TOOL_PAGED"
        if review_snapshot and diff_mode != "INLINE":
            review_snapshot["complete"] = False
        preflight_summary = request.get("_deterministicPreflightSummary")
        baseline_context = _bounded_context(request)
        input_case = {
            "id": f"task-{task.id}",
            "title": request.get("title")
            or f"{task.trigger_type} {task.external_source_id or ''}".strip(),
            "baseRef": request.get("baseRef") or task.target_branch,
            "commitSha": request.get("commitSha") or task.after_sha or task.commit_sha,
            "changedFiles": changed_files,
            "diff": diff_text,
            "diffMode": diff_mode,
            "reviewInstructions": review_instructions,
            "baselineContext": baseline_context + memory.text,
            "reviewCoverage": {
                "totalChangedFileCount": len(requested_files),
                "includedFileCount": len(changed_files),
                "excludedFileCount": len(excluded_files),
                "excludedPaths": excluded_files,
            },
        }
        if unified_review:
            grouped = repository.effective_grouped_review_settings(settings_record)
            budgets = {**budgets, "maxTurns": grouped.maxTurns, "submitByTurn": grouped.maxTurns - 3}
            input_case["groupedReview"] = grouped.model_dump()
            if file_rules:
                input_case["groupRuleCatalogVersion"] = file_rules["summary"]["catalogVersion"]
                input_case["groupBaseInstructions"] = base_instructions
        input_case["inputSources"] = [
            {
                "source": "PROJECT_POLICY",
                "count": policy_context["meta"]["injectedCount"],
                "bytes": len(policy_context["promptText"].strip().encode("utf-8")),
                "truncated": policy_context["meta"]["truncated"],
            },
            {"source": "MEMORY", "count": len(memory.snapshot.selected), "bytes": memory.snapshot.injected_bytes},
        ]
        if profile_input is not None:
            input_case["profileInput"] = profile_input.model_dump(exclude_none=True)
        if preflight_summary and len(baseline_context) < 100_000:
            input_case["inputSources"].append({"source": "PREFLIGHT", "count": 1})
        workspace_root = (
            Path(get_settings().local_repo_workspace_root).expanduser().resolve(strict=False)
        )
        try:
            worktree_relative = str(
                worktree.resolve(strict=True).relative_to(workspace_root)
            ).replace("\\", "/")
        except (FileNotFoundError, ValueError) as exception:
            raise AppError(
                "AGENT_WORKTREE_UNAVAILABLE",
                "Agent Review worktree is outside the configured workspace root",
                409,
            ) from exception
    except Exception as exception:
        wrapped = _persist_dispatch_failure(
            db,
            task_id=int(task.id),
            phase="AGENT_INPUT_BUILD_FAILED",
            message="Agent Review 安全输入组装或 Worktree 校验失败",
            base_detail=dispatch_detail,
            started_at=input_started,
            exception=exception,
            fallback_code="AGENT_INPUT_BUILD_FAILED",
            fallback_message="Agent Review input build failed",
            mark_review_failed=mark_review_failed,
        )
        if wrapped is not None:
            raise wrapped from exception
        raise

    job_started = perf_counter()
    input_progress = {
        "changedFileCount": len(requested_files),
        "includedFileCount": len(changed_files),
        "excludedFileCount": len(excluded_files),
        "diffBytes": diff_bytes,
        "diffMode": input_case["diffMode"],
        "memoryLookupStatus": memory.snapshot.lookup_status,
        "memoryInjectedBytes": memory.snapshot.injected_bytes,
        "memorySelectedCount": len(memory.snapshot.selected),
    }
    _append_dispatch_progress(
        db,
        task_id=int(task.id),
        phase="AGENT_INPUT_BUILD_COMPLETED",
        level="INFO",
        message="Agent Review 安全输入已组装",
        base_detail=dispatch_detail,
        status="COMPLETED",
        started_at=input_started,
        extra=input_progress,
    )
    if file_rules:
        summary = file_rules["summary"]
        append_progress(
            db,
            int(task.id),
            "FILE_RULES_RESOLVED",
            "WARN" if summary["errorCount"] or summary["promptTruncated"] else "INFO",
            "文件审查规则已匹配",
            json.dumps(summary, ensure_ascii=True, separators=(",", ":")),
            review_key=review_key,
        )
    _append_dispatch_progress(
        db,
        task_id=int(task.id),
        phase="AGENT_JOB_CREATE_STARTED",
        level="INFO",
        message="Agent Review 正在持久化 Scheduler Job",
        base_detail=dispatch_detail,
        status="STARTED",
        started_at=job_started,
    )
    db.commit()

    try:
        input_payload = {
            "worktree": worktree_relative,
            "case": input_case,
            "budgets": budgets,
            "memorySnapshot": memory.snapshot.model_dump(mode="json", by_alias=True),
        }
        if file_rules:
            input_payload["fileRules"] = file_rules
        if review_snapshot:
            input_payload["reviewSnapshot"] = review_snapshot
        run = repository.create_agent_job(
            db,
            task_id=int(task.id),
            project_id=int(project.id),
            input_payload=input_payload,
            completion_context=completion_context,
            comparison_mode=comparison_mode,
            runtime=runtime,
            unified_review=unified_review,
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
            "reviewSnapshot": review_snapshot,
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
        _append_dispatch_progress(
            db,
            task_id=int(task.id),
            phase="AGENT_JOB_CREATE_COMPLETED",
            level="INFO",
            message="Agent Review Scheduler Job 已持久化",
            base_detail=dispatch_detail,
            status="COMPLETED",
            started_at=job_started,
            extra={
                "jobId": int(run.scheduler_job_id),
                "runId": int(run.id),
            },
        )
        _append_dispatch_progress(
            db,
            task_id=int(task.id),
            phase="AGENT_QUEUED",
            level="INFO",
            message="Agent Review 已进入独立 Worker 队列",
            base_detail=dispatch_detail,
            status="COMPLETED",
            started_at=job_started,
            extra={
                "jobId": int(run.scheduler_job_id),
                "runId": int(run.id),
                **input_progress,
            },
            review_key=review_key,
        )
        db.commit()
    except Exception as exception:
        wrapped = _persist_dispatch_failure(
            db,
            task_id=int(task.id),
            phase="AGENT_JOB_CREATE_FAILED",
            message="Agent Review Scheduler Job 持久化失败",
            base_detail=dispatch_detail,
            started_at=job_started,
            exception=exception,
            fallback_code="AGENT_JOB_CREATE_FAILED",
            fallback_message="Agent Review scheduler job persistence failed",
            mark_review_failed=mark_review_failed,
        )
        if wrapped is not None:
            raise wrapped from exception
        raise
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
    legacy_summary = {key: value for key, value in run_summary.items() if key != "conversationEvents"}
    heartbeat_sequence = _safe_heartbeat_sequence(request.get("heartbeatSequence"))
    claim_attempt = _required_claim_attempt(request)
    worker_id = _required(request, "workerId")
    response = repository.heartbeat_agent_job(
        db,
        job_id=job_id,
        worker_id=worker_id,
        claim_attempt=claim_attempt,
        run_summary=legacy_summary or None,
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
        _persist_agent_conversation_safely(
            db,
            job_id=job_id,
            run_id=int(run.id),
            worker_id=worker_id,
            claim_attempt=claim_attempt,
            value=run_summary.get("conversationEvents"),
        )
    return response


def complete_job(db: Session, job_id: int, request: dict[str, Any]) -> dict[str, Any]:
    claim_attempt = _required_claim_attempt(request)
    worker_id = _required(request, "workerId")
    idempotency_key = _required(request, "idempotencyKey")
    job, run = repository.get_run_for_completion(
        db,
        job_id=job_id,
        worker_id=worker_id,
        idempotency_key=idempotency_key,
        claim_attempt=claim_attempt,
    )
    run_summary = request.get("runSummary") if isinstance(request.get("runSummary"), dict) else {}
    if run.status == "SUCCEEDED":
        _persist_agent_conversation_safely(
            db,
            job_id=job_id,
            run_id=int(run.id),
            worker_id=worker_id,
            claim_attempt=claim_attempt,
            value=run_summary.get("conversationEvents"),
            terminal_status="SUCCEEDED",
            idempotency_key=idempotency_key,
        )
        return {"accepted": True, "idempotent": True, "run": repository.run_to_summary(run)}
    input_payload = _json_object(run.input_json)
    runtime_snapshot = (
        input_payload.get("runtimeSnapshot")
        if isinstance(input_payload.get("runtimeSnapshot"), dict)
        else {}
    )
    changed_files = ((input_payload.get("case") or {}).get("changedFiles") or [])
    if run.runner_version in GROUPED_RUNNER_CAPABILITIES:
        if run.status != "RUNNING" or job.status != "RUNNING":
            raise AppError("AGENT_JOB_LEASE_LOST", "Grouped Agent Review is no longer running", 409)
        if job.cancel_requested_at is not None:
            return fail_job(db, job_id, {**request, "failureCode": "AGENT_CANCELLED"})
    try:
        if run.runner_version in GROUPED_RUNNER_CAPABILITIES:
            validate_group_coverage(run_summary.get("groupCoverage"), changed_files)
        card = validate_review_card(request.get("reviewCard"), changed_files)
    except (ReviewSchemaError, ValueError, TypeError) as exception:
        raise AppError("AGENT_REVIEW_SCHEMA_INVALID", str(exception), 400) from exception
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
    review_snapshot = input_payload.get("reviewSnapshot")
    if isinstance(review_snapshot, dict):
        result["reviewSnapshot"] = {
            **review_snapshot,
            "complete": bool(
                review_snapshot.get("complete")
                and all(
                    finding.get("contextStatus") == "SUFFICIENT"
                    and not finding.get("missingContext")
                    for finding in result["findings"]
                )
                and (
                    request["reviewCard"]["overallLevel"] != "CRITICAL"
                    or any(finding["severity"] == "CRITICAL" for finding in result["findings"])
                )
            ),
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
    stored_result = result
    if run.runner_version in GROUPED_RUNNER_CAPABILITIES and run_summary.get("factCheckResults"):
        findings = attach_fact_checks(
            result["findings"], run_summary["factCheckResults"], run_summary["groupCoverage"],
            str((input_payload.get("case") or {}).get("diff") or ""),
        )
        for finding in findings:
            check = finding.get("factCheck")
            if check and "reason" in check:
                check["reason"] = scrub_sensitive(check["reason"])
        stored_result = {**result, "findings": findings}
    if run.runner_version == repository.CONTEXT_REVIEW_RUNNER_VERSION and run_summary.get("anchorResults"):
        stored_result = {**stored_result, "findings": attach_finding_anchors(
            stored_result["findings"], run_summary["anchorResults"], run_summary["groupCoverage"],
            str((input_payload.get("case") or {}).get("diff") or ""),
        )}
    saved = save_result(
        db,
        task_id=run.task_id,
        review_key=run.review_key,
        project_id=task.project_id,
        profile_code=task.code_quality_profile_code or "backend-default-ai-review",
        provider=str(run.provider or "DEEPSEEK"),
        model=str(run.model or repository.AGENT_MODEL),
        display_name=f"Agent · {runtime_snapshot.get('displayName') or 'Claude Code + DeepSeek'}",
        sort_order=5,
        result=stored_result,
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
        detail_limit=54000 if "groupProgress" in result["agentRunSummary"] else 4000,
    )
    _finish_existing_review_flow(db, run, result)
    if task.trigger_type == "GITLAB_MR_WEBHOOK" and not run.comparison_mode:
        from app.code_quality.service import record_auto_fix_candidate

        record_auto_fix_candidate(db, saved)
    run_id = int(run.id)
    db.commit()
    _persist_agent_conversation_safely(
        db,
        job_id=job_id,
        run_id=run_id,
        worker_id=worker_id,
        claim_attempt=claim_attempt,
        value=run_summary.get("conversationEvents"),
        terminal_status="SUCCEEDED",
        idempotency_key=idempotency_key,
    )
    return {"accepted": True, "idempotent": False, "run": result["agentRunSummary"]}


def fail_job(db: Session, job_id: int, request: dict[str, Any]) -> dict[str, Any]:
    claim_attempt = _required_claim_attempt(request)
    worker_id = _required(request, "workerId")
    idempotency_key = _required(request, "idempotencyKey")
    job, run = repository.get_run_for_completion(
        db,
        job_id=job_id,
        worker_id=worker_id,
        idempotency_key=idempotency_key,
        claim_attempt=claim_attempt,
    )
    failure_code = str(request.get("failureCode") or "AGENT_RUN_FAILED")[:64]
    cancelled = failure_code == "AGENT_CANCELLED"
    terminal_status = "CANCELLED" if cancelled else ("TIMED_OUT" if failure_code == "AGENT_TIMEOUT" else "FAILED")
    run_summary = request.get("runSummary") if isinstance(request.get("runSummary"), dict) else {}
    if run.runner_version in GROUPED_RUNNER_CAPABILITIES and run.status == "SUCCEEDED":
        return {"accepted": True, "idempotent": True, "run": repository.run_to_summary(run)}
    if run.status in {"FAILED", "CANCELLED", "TIMED_OUT"}:
        if run.status == terminal_status:
            _persist_agent_conversation_safely(
                db,
                job_id=job_id,
                run_id=int(run.id),
                worker_id=worker_id,
                claim_attempt=claim_attempt,
                value=run_summary.get("conversationEvents"),
                terminal_status=terminal_status,
                idempotency_key=idempotency_key,
            )
        return {"accepted": True, "idempotent": True, "run": repository.run_to_summary(run)}
    failure_message = str(request.get("failureMessage") or "Agent Review failed")[:1024]
    task = db.get(ReviewTask, run.task_id)
    is_fix_review = task is not None and task.trigger_type == AUTO_FIX_REVIEW_TRIGGER
    from app.code_quality.service import agent_standard_fallback_enabled, finish_agent_without_standard

    fallback_enabled = not cancelled and not is_fix_review and agent_standard_fallback_enabled(db)
    safe_audit = repository.sanitize_agent_audit(run_summary.get("audit"))
    _persist_agent_trace_safely(
        db,
        run,
        run_summary,
        claim_attempt=claim_attempt,
    )
    repository.finish_agent_records(
        db,
        job=job,
        run=run,
        status=terminal_status,
        effective_engine="STANDARD_FALLBACK" if fallback_enabled else "AGENT",
        summary=run_summary,
        failure_code=failure_code,
        failure_message=failure_message,
        clear_input=not fallback_enabled,
    )
    if failure_code == "AGENT_REVIEW_SCHEMA_RETRY_EXHAUSTED":
        append_progress(
            db,
            run.task_id,
            "AGENT_OUTPUT_CONVERGENCE_FAILED",
            "WARN",
            "Review Card 结构修正已达到安全上限",
            json.dumps(
                {
                    "runId": int(run.id),
                    "claimAttempt": claim_attempt,
                    "failureCode": failure_code,
                    "submitAttemptCount": safe_audit.get("submitAttemptCount", 0),
                    "schemaFailureCount": safe_audit.get("schemaFailureCount", 0),
                    "lastSchemaFailures": safe_audit.get("lastSchemaFailures") or [],
                    "failureChain": safe_audit.get("failureChain") or [],
                },
                ensure_ascii=False,
            ),
            review_key=run.review_key,
        )
    if cancelled:
        phase, message = "AGENT_CANCELLED", "Agent Review 已取消"
    elif is_fix_review:
        phase, message = "FAILED", "修复复审失败"
    elif fallback_enabled:
        phase, message = "AGENT_FALLBACK", "Agent Review 失败，准备执行普通 Review 降级"
    else:
        phase, message = "FAILED", "Agent Review 失败，Standard 降级不可用"
    append_progress(
        db,
        run.task_id,
        phase,
        "WARN" if not cancelled else "INFO",
        message,
        json.dumps(
            {
                **repository.run_to_summary(run),
                "claimAttempt": claim_attempt,
                "failureChain": safe_audit.get("failureChain") or [],
            },
            ensure_ascii=False,
        ),
        review_key=run.review_key,
        detail_limit=54000 if run.runner_version in GROUPED_RUNNER_CAPABILITIES else 4000,
    )
    if is_fix_review and not cancelled:
        from app.code_quality.service import fail_auto_fix_review

        fail_auto_fix_review(db, run.task_id, run.review_key, failure_message)
    elif not cancelled and not fallback_enabled and task is not None:
        finish_agent_without_standard(db, task, run)
    run_id = int(run.id)
    db.commit()
    _persist_agent_conversation_safely(
        db,
        job_id=job_id,
        run_id=run_id,
        worker_id=worker_id,
        claim_attempt=claim_attempt,
        value=run_summary.get("conversationEvents"),
        terminal_status=terminal_status,
        idempotency_key=idempotency_key,
    )
    if fallback_enabled:
        from app.code_quality.service import schedule_agent_standard_fallback

        schedule_agent_standard_fallback(db, run.id)
    return {"accepted": True, "idempotent": False, "run": repository.run_to_summary(run)}


def _finish_existing_review_flow(db: Session, run: Any, result: dict[str, Any]) -> None:
    from app.code_quality.service import _send_auto_review_notification, _sync_task_status_after_review

    _sync_task_status_after_review(db, run.task_id, result)
    task = db.get(ReviewTask, run.task_id)
    if task is not None and task.trigger_type == AUTO_FIX_REVIEW_TRIGGER:
        return
    context = parse_agent_completion_context(
        run.completion_context_json,
        task_id=run.task_id,
    )
    if run.comparison_mode or not context.get("autoNotification"):
        return
    rule_result_id, risk_card, reminder_card_enabled = resolve_agent_completion_notification(
        db,
        task_id=run.task_id,
        context=context,
    )
    _send_auto_review_notification(
        db,
        run.task_id,
        result,
        rule_result_id,
        risk_card,
        context.get("focusChangeTypes") or [],
        context.get("focusRuleCodes") or [],
        context.get("notificationContext") or {},
        reminder_card_enabled,
    )


def _persist_agent_conversation_safely(
    db: Session,
    *,
    job_id: int,
    run_id: int,
    worker_id: str,
    claim_attempt: int,
    value: Any,
    terminal_status: str | None = None,
    idempotency_key: str | None = None,
) -> None:
    expected_job_status = {
        None: "RUNNING",
        "SUCCEEDED": "SUCCESS",
        "FAILED": "FAILED",
        "TIMED_OUT": "FAILED",
        "CANCELLED": "SKIPPED",
    }[terminal_status]
    try:
        events = parse_agent_conversation_events(value)
        if not events:
            return
        # The scheduler's lease comes from the job row. Lock it before locking the Run,
        # as the claim path does, so a takeover cannot race this attempt's insert.
        with Session(bind=db.get_bind(), autoflush=False) as progress_db:
            job = progress_db.scalars(
                select(CodeQualitySchedulerJob)
                .where(CodeQualitySchedulerJob.id == job_id)
                .with_for_update()
            ).first()
            if (
                job is None
                or job.job_type != "AGENT_REVIEW"
                or job.lease_owner != worker_id
                or job.attempt != claim_attempt
                or job.status != expected_job_status
                or (
                    terminal_status is None
                    and (job.lease_expires_at is None or job.lease_expires_at <= utc_now())
                )
            ):
                return
            run = repository.lock_agent_run_for_trace(progress_db, run_id)
            if (
                run is None
                or run.scheduler_job_id != job_id
                or run.status != (terminal_status or "RUNNING")
                or (terminal_status is not None and run.idempotency_key != idempotency_key)
            ):
                return
            written = repository.agent_conversation_turns(
                progress_db, run=run, claim_attempt=claim_attempt
            )
            for event in events:
                is_turn = isinstance(event, AgentConversationTurnEvent)
                if isinstance(event, PlatformPromptMarker):
                    turn = -1
                    if turn in written or (
                        event.source == "STANDARD_HTTP"
                        or event.runId is not None
                        or event.protocol != _AGENT_PROMPT_PROTOCOLS.get(run.runner_type)
                        or event.submitByTurn != repository.agent_prompt_submit_by_turn(run)
                    ):
                        continue
                    message = "Agent 平台系统指令已记录"
                else:
                    turn = event.turn if is_turn else 0
                    message = "Agent 模型轮次已记录" if is_turn else "Agent 首轮输入清单已记录"
                    if not is_turn and event.protocol != _AGENT_PROMPT_PROTOCOLS.get(run.runner_type):
                        continue
                if turn in written:
                    continue
                detail = event.model_dump(exclude={"phase"}, exclude_none=True)
                if run.runner_type != OPENAI_RESPONSES_RUNNER:
                    detail.pop("summarySource", None)
                    detail.pop("summaryKind", None)
                detail["runId"] = run_id
                detail["claimAttempt"] = claim_attempt
                encoded = json.dumps(detail, separators=(",", ":"))
                if len(encoded) > 4000:
                    # Keep the identifying fields even if optional v1 fields grow later.
                    required = ("turn",) if is_turn else ("protocol", "diffMode")
                    detail = {
                        "schemaVersion": 1,
                        "runId": run_id,
                        "claimAttempt": claim_attempt,
                        "truncated": True,
                        **{field: detail[field] for field in required},
                    }
                    encoded = json.dumps(detail, separators=(",", ":"))
                append_progress(
                    progress_db,
                    run.task_id,
                    event.phase,
                    "INFO",
                    message,
                    encoded,
                    review_key=run.review_key,
                )
                written.add(turn)
            progress_db.commit()
    except Exception as exception:
        _LOGGER.warning(
            "Agent Review conversation progress persistence failed runId=%s errorType=%s",
            run_id,
            type(exception).__name__,
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
            if event.get("retrievalDetail"):
                detail["retrievalDetail"] = event["retrievalDetail"]
            if str(event.get("tool") or "") == "submit_review":
                detail.update(
                    {
                        "attempt": event.get("attempt", 0),
                        "maxAttempts": event.get("maxAttempts", 3),
                        "violations": event.get("violations") or [],
                        "violationCount": event.get("violationCount", 0),
                        "violationsTruncated": bool(
                            event.get("violationsTruncated")
                        ),
                    }
                )
            if str(event.get("tool") or "") == "submit_review":
                append_progress(
                    db,
                    int(locked_run.task_id),
                    "AGENT_SUBMITTING",
                    "INFO",
                    "Agent 正在提交 Review Card",
                    json.dumps(
                        {
                            **detail,
                            "status": "STARTED",
                            "submitAttemptCount": event.get("attempt", 0),
                        },
                        ensure_ascii=False,
                    ),
                    review_key=locked_run.review_key,
                )
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
        if locked_run.runner_version in GROUPED_RUNNER_CAPABILITIES:
            grouped = repository.sanitize_group_progress(run_summary.get("groupProgress"))
            if grouped:
                detail["groupProgress"] = grouped
        append_progress(
            db,
            int(locked_run.task_id),
            "AGENT_HEARTBEAT",
            "INFO",
            "Agent Worker 运行心跳",
            json.dumps(detail, ensure_ascii=False, separators=(",", ":")),
            review_key=locked_run.review_key,
            detail_limit=54000 if "groupProgress" in detail else 4000,
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
    if tool == "submit_review" and event.get("status") == "SUCCESS":
        return "AGENT_REVIEW_SUBMITTED", "Agent 已提交 Review Card"
    if (
        tool == "submit_review"
        and event.get("errorCode") == "REVIEW_SCHEMA_INVALID"
    ):
        return "AGENT_SUBMIT_VALIDATION_FAILED", "Review Card 结构校验失败"
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


def _worktree_matches_head(worktree: Path, head_sha: str) -> bool:
    try:
        commit = subprocess.run(
            ["git", "-C", str(worktree), "rev-parse", "--verify", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return commit.stdout.strip().lower() == head_sha


def _prepare_agent_worktree_with_progress(
    db: Session,
    *,
    task: ReviewTask,
    project: Project,
    review_key: str,
    dispatch_attempt_id: str,
    changed_file_count: int,
    diff_bytes: int,
    mark_review_failed: bool = False,
) -> Path:
    started = perf_counter()
    base_detail = _dispatch_progress_base(
        review_key=review_key,
        dispatch_attempt_id=dispatch_attempt_id,
    )
    worktree_detail = {
        "changedFileCount": max(int(changed_file_count), 0),
        "diffBytes": max(int(diff_bytes), 0),
        "maxAttempts": 2,
    }
    _append_dispatch_progress(
        db,
        task_id=int(task.id),
        phase="LOCAL_REPO_PREPARE_STARTED",
        level="INFO",
        message="Agent Review 正在准备本地仓库 Worktree",
        base_detail=base_detail,
        status="STARTED",
        started_at=started,
        extra=worktree_detail,
    )
    db.commit()
    try:
        worktree = _ensure_worktree(task, project)
    except Exception as exception:
        wrapped = _persist_dispatch_failure(
            db,
            task_id=int(task.id),
            phase="LOCAL_REPO_PREPARE_FAILED",
            message="Agent Review 本地仓库 Worktree 准备失败",
            base_detail=base_detail,
            started_at=started,
            exception=exception,
            fallback_code="AGENT_WORKTREE_PREPARE_FAILED",
            fallback_message="Agent Review worktree preparation failed",
            mark_review_failed=mark_review_failed,
            extra=worktree_detail,
        )
        if wrapped is not None:
            raise wrapped from exception
        raise
    _append_dispatch_progress(
        db,
        task_id=int(task.id),
        phase="LOCAL_REPO_PREPARED",
        level="INFO",
        message="Agent Review 本地仓库 Worktree 已准备",
        base_detail=base_detail,
        status="COMPLETED",
        started_at=started,
        extra=worktree_detail,
    )
    db.commit()
    return worktree


def _dispatch_progress_base(
    *,
    review_key: str,
    dispatch_attempt_id: str,
) -> dict[str, Any]:
    return {
        "schemaVersion": _DISPATCH_PROGRESS_SCHEMA_VERSION,
        "operation": _DISPATCH_OPERATION,
        "dispatchAttemptId": str(dispatch_attempt_id)[:128],
        "reviewKey": str(review_key)[:64],
        "requestedEngine": "AGENT",
    }


def _append_dispatch_progress(
    db: Session,
    *,
    task_id: int,
    phase: str,
    level: str,
    message: str,
    base_detail: dict[str, Any],
    status: str,
    started_at: float,
    extra: dict[str, Any] | None = None,
    review_key: str | None = None,
) -> None:
    detail = {
        **base_detail,
        **(extra or {}),
        "status": status,
        "durationMs": _elapsed_ms(started_at),
    }
    append_progress(
        db,
        task_id,
        phase,
        level,
        message,
        json.dumps(detail, ensure_ascii=False),
        review_key=review_key,
    )


def _persist_dispatch_failure(
    db: Session,
    *,
    task_id: int,
    phase: str,
    message: str,
    base_detail: dict[str, Any],
    started_at: float,
    exception: Exception,
    fallback_code: str,
    fallback_message: str,
    mark_review_failed: bool,
    extra: dict[str, Any] | None = None,
) -> AppError | None:
    try:
        db.rollback()
    except Exception as rollback_exception:
        _LOGGER.error(
            "Agent dispatch rollback failed taskId=%s phase=%s attemptId=%s "
            "exceptionType=%s",
            task_id,
            phase,
            base_detail.get("dispatchAttemptId"),
            type(rollback_exception).__name__,
        )
        return (
            None
            if isinstance(exception, AppError)
            else AppError(fallback_code, fallback_message, 500)
        )
    stable_error = (
        None
        if isinstance(exception, AppError)
        else AppError(fallback_code, fallback_message, 500)
    )
    raw_message = (
        exception.message if isinstance(exception, AppError) else fallback_message
    )
    failure_message = (
        scrub_sensitive(str(raw_message or fallback_message)) or fallback_message
    )[:1000]
    failure_code = (
        str(exception.code) if isinstance(exception, AppError) else fallback_code
    )[:64]
    failure_db: Session | None = None
    try:
        failure_db = SessionLocal(bind=db.get_bind())
        if mark_review_failed:
            persisted_task = failure_db.get(ReviewTask, task_id)
            if persisted_task is not None:
                persisted_task.review_status = "REVIEW_FAILED"
                persisted_task.updated_at = datetime.now()
        _append_dispatch_progress(
            failure_db,
            task_id=task_id,
            phase=phase,
            level="ERROR",
            message=message,
            base_detail=base_detail,
            status="FAILED",
            started_at=started_at,
            extra={
                **(extra or {}),
                "failureCode": failure_code,
                "failureMessage": failure_message,
            },
        )
        failure_db.commit()
    except Exception as persistence_exception:
        if failure_db is not None:
            try:
                failure_db.rollback()
            except Exception as failure_rollback_exception:
                _LOGGER.error(
                    "Agent dispatch failure session rollback failed taskId=%s phase=%s "
                    "attemptId=%s exceptionType=%s",
                    task_id,
                    phase,
                    base_detail.get("dispatchAttemptId"),
                    type(failure_rollback_exception).__name__,
                )
        _LOGGER.error(
            "Agent dispatch failure progress persistence failed taskId=%s phase=%s "
            "attemptId=%s exceptionType=%s",
            task_id,
            phase,
            base_detail.get("dispatchAttemptId"),
            type(persistence_exception).__name__,
        )
    finally:
        if failure_db is not None:
            try:
                failure_db.close()
            except Exception as close_exception:
                _LOGGER.error(
                    "Agent dispatch failure session close failed taskId=%s phase=%s "
                    "attemptId=%s exceptionType=%s",
                    task_id,
                    phase,
                    base_detail.get("dispatchAttemptId"),
                    type(close_exception).__name__,
                )
    _LOGGER.error(
        "Agent dispatch stage failed taskId=%s phase=%s failureCode=%s exceptionType=%s",
        task_id,
        phase,
        failure_code,
        type(exception).__name__,
    )
    return stable_error


def _policy_progress_summary(policy_context: dict[str, Any]) -> dict[str, Any]:
    meta = policy_context.get("meta") if isinstance(policy_context, dict) else {}
    safe_meta = meta if isinstance(meta, dict) else {}
    return {
        "totalAvailable": max(int(safe_meta.get("totalAvailable") or 0), 0),
        "injectedCount": max(int(safe_meta.get("injectedCount") or 0), 0),
        "promptLength": max(int(safe_meta.get("promptLength") or 0), 0),
        "truncated": bool(safe_meta.get("truncated")),
        "contentTruncatedCount": max(
            int(safe_meta.get("contentTruncatedCount") or 0),
            0,
        ),
    }


def _elapsed_ms(started_at: float) -> int:
    return max(int((perf_counter() - started_at) * 1000), 0)


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


def _filter_review_diff(
    request: dict[str, Any], included_paths: list[str], *, allow_unheaded: bool = False,
) -> str:
    included = set(included_paths)
    unheaded_path = included_paths[0] if allow_unheaded and len(included_paths) == 1 else None
    original = str(request.get("diffText") or "")
    sections = split_diff_sections(original, unheaded_path=unheaded_path)
    selected: dict[str, DiffSection] = {}
    for section in sections:
        path = section.changed_path(included)
        if path and (path not in selected or not selected[path].patch):
            selected[path] = section

    details = request.get("changedFileDetails") or []
    if isinstance(details, list):
        for item in details:
            if not isinstance(item, dict):
                continue
            deleted = item.get("deletedFile") is True or item.get("changeType") == "DELETED"
            path = item.get("oldPath") if deleted else item.get("path") or item.get("newPath")
            path = str(path or item.get("path") or item.get("oldPath") or "").strip().replace("\\", "/")
            if path not in included:
                continue
            existing = selected.get(path)
            if existing and existing.patch and (allow_unheaded or existing.patch.startswith("+++ ")):
                continue
            diff = str(item.get("diffText") or "").strip("\r\n")
            if not diff:
                continue
            old_path = str(item.get("oldPath") or "").strip().replace("\\", "/")
            file_sections = split_diff_sections(with_diff_section_header(
                path,
                diff,
                old_path=old_path,
                deleted=deleted and allow_unheaded,
                added=item.get("newFile") is True or item.get("changeType") == "ADDED",
            ))
            if len(file_sections) == 1:
                section = file_sections[0]
                if section.changed_path(included) == path and (section.patch or path not in selected):
                    selected[path] = section
    filtered = "\n".join(section.text for section in selected.values())
    # Preserve the byte-for-byte Review snapshot when filtering only changes blank separators.
    original_lines = [line for line in original.replace("\r\n", "\n").split("\n") if line]
    filtered_lines = [line for line in filtered.split("\n") if line]
    return original if original_lines == filtered_lines else filtered


def _complete_mr_diff(task: ReviewTask, project: Project, changed_files: list[str], diff_text: str) -> str:
    base_sha, head_sha = task.before_sha, task.after_sha
    project_id, mr_iid = project.git_project_id, task.external_source_id
    if not all((base_sha, head_sha, project_id, mr_iid)):
        return diff_text
    remaining_bytes = repository.MAX_DIFF_BYTES - len(diff_text.encode("utf-8"))
    if remaining_bytes <= 0:
        return diff_text
    missing = set(changed_files) - diff_by_file({"changedFiles": changed_files, "diff": diff_text}).keys()
    if not missing:
        return diff_text

    try:
        files = gitlab_client.list_merge_request_version_diffs(project_id, mr_iid, base_sha, head_sha)
    except (AppError, ValueError) as exception:
        _LOGGER.warning("Agent MR Diff completion unavailable taskId=%s errorType=%s", task.id, type(exception).__name__)
        return diff_text

    parts = [diff_text] if diff_text else []
    for item in files:
        deleted = item.get("deletedFile") is True
        old_path = item.get("oldPath")
        path = old_path if deleted else item.get("path")
        patch = item.get("diffText")
        if path not in missing or not isinstance(patch, str) or not patch.strip():
            continue
        try:
            for alias in (old_path, item.get("newPath")):
                if alias:
                    validate_review_path(alias)
        except ReviewToolError:
            continue
        sections = split_diff_sections(with_diff_section_header(
            path, patch, old_path=old_path, deleted=deleted, added=item.get("newFile") is True,
        ))
        if len(sections) != 1 or not sections[0].patch or (sections[0].new_path or sections[0].old_path) != path:
            continue
        section = sections[0].text
        byte_count = len(section.encode("utf-8")) + int(bool(parts))
        if byte_count > remaining_bytes:
            continue
        parts.append(section)
        remaining_bytes -= byte_count
        missing.remove(path)
        if not missing:
            break
    return "\n".join(parts)


def _complete_push_diff(
    task: ReviewTask,
    worktree: Path,
    changed_files: list[str],
    diff_text: str,
    *,
    changed_file_details: list[Any] | None = None,
) -> str:
    before, after = task.before_sha or "", task.after_sha or ""
    if not all(_COMMIT_SHA.fullmatch(ref) and ref.strip("0") for ref in (before, after)):
        return diff_text
    remaining_bytes = repository.MAX_DIFF_BYTES - len(diff_text.encode("utf-8"))
    if remaining_bytes <= 0:
        return diff_text
    existing = diff_by_file({"changedFiles": changed_files, "diff": diff_text})
    missing = [path for path in changed_files if path not in existing]
    if not missing:
        return diff_text
    renames = {
        item["path"].strip().replace("\\", "/"): item.get("oldPath")
        for item in changed_file_details or []
        if isinstance(item, dict) and (item.get("renamedFile") is True or item.get("changeType") == "RENAMED")
        and isinstance(item.get("path"), str)
    }

    env = {name: value for name, value in os.environ.items() if not name.upper().startswith("GIT_")}
    env.update(GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    git = [
        "git", "--no-replace-objects", "--literal-pathspecs", "-C", str(worktree),
        "-c", f"core.bigFileThreshold={repository.MAX_DIFF_BYTES}", "diff",
        "--no-ext-diff", "--no-textconv", "--no-color", "--ignore-submodules=all",
        "--src-prefix=a/", "--dst-prefix=b/", "--unified=3",
    ]
    deadline = perf_counter() + _PUSH_DIFF_TIMEOUT_SECONDS
    parts = [diff_text] if diff_text else []
    for path in missing:
        old_path = renames.get(path, path)
        try:
            old_path = validate_review_path(old_path)
        except ReviewToolError:
            continue
        renamed = old_path != path
        pathspecs = [old_path, path] if renamed else [path]
        timeout = deadline - perf_counter()
        patch_limit = remaining_bytes - int(bool(parts))
        if timeout <= 0 or patch_limit <= 0:
            break
        try:
            with TemporaryFile() as output:
                subprocess.run(
                    [*git, "--find-renames" if renamed else "--no-renames",
                     f"{before}^{{commit}}", f"{after}^{{commit}}", "--", *pathspecs],
                    stdout=output, stderr=subprocess.DEVNULL,
                    env=env, timeout=timeout, check=True,
                )
                output.seek(0)
                data = output.read(patch_limit + 2)
        except (OSError, subprocess.SubprocessError) as exception:
            _LOGGER.warning("Agent Push Diff completion unavailable taskId=%s errorType=%s", task.id, type(exception).__name__)
            break
        if len(data.rstrip(b"\n")) > patch_limit or len(data) == patch_limit + 2 or b"\0" in data:
            continue
        try:
            sections = split_diff_sections(data.decode("utf-8"))
        except UnicodeDecodeError:
            continue
        if len(sections) != 1:
            continue
        candidate = sections[0]
        if not candidate.patch or (candidate.new_path or candidate.old_path) != path:
            continue
        if renamed and (candidate.old_path, candidate.new_path) != (old_path, path):
            continue
        section = candidate.text
        header = section.partition("\n+++ ")[0]
        if _NON_REGULAR_DIFF_MODE.search(header):
            continue
        parts.append(section)
        remaining_bytes -= len(section.encode("utf-8")) + int(len(parts) > 1)
    return "\n".join(parts)


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
