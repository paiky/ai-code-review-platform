from __future__ import annotations

from datetime import timedelta
import json
from threading import Lock
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, inspect, or_, select, text
from sqlalchemy.orm import Session

from app.agent_review.crypto import decrypt_api_key, encrypt_api_key, encryption_available, mask_fingerprint
from app.agent_review.models import AgentReviewRun, AgentReviewSettings, AgentReviewWorker
from app.agent_review_spike.budgets import (
    AGENT_BUDGET_KEYS,
    AGENT_BUDGET_LIMITS,
    DEFAULT_AGENT_BUDGETS,
    AgentBudgetValidationError,
    agent_budget_limits,
    default_agent_budgets,
    validate_agent_budgets,
)
from app.code_quality.models import (
    CodeQualityReviewProgressEvent,
    CodeQualitySchedulerJob,
)
from app.code_quality.repository import ensure_result_schema, ensure_scheduler_job_schema, format_datetime
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.json_utils import utc_now


AGENT_REVIEW_KEY = "agent-claude-code-deepseek-v4-pro"
AGENT_MODEL = "deepseek-v4-pro[1m]"
AGENT_CLI_VERSION = "2.1.112"
AGENT_RUNNER_VERSION = "agent-worker-v1"
AGENT_ENDPOINT = "https://api.deepseek.com/anthropic"
AGENT_WORKER_ONLINE_SECONDS = 60
AGENT_WORKER_RETENTION_DAYS = 7
AGENT_WORKER_NODE_LIMIT = 100
MAX_TURNS = DEFAULT_AGENT_BUDGETS["maxTurns"]
MAX_TOOL_CALLS = DEFAULT_AGENT_BUDGETS["maxToolCalls"]
MAX_SOURCE_BYTES = DEFAULT_AGENT_BUDGETS["maxSourceBytes"]
MAX_DIFF_BYTES = 1_048_576
INLINE_DIFF_BYTES = DEFAULT_AGENT_BUDGETS["inlineDiffBytes"]
TIMEOUT_SECONDS = DEFAULT_AGENT_BUDGETS["timeoutSeconds"]
ABSOLUTE_MAX_TURNS = AGENT_BUDGET_LIMITS["maxTurns"]["max"]
ABSOLUTE_MAX_TOOL_CALLS = AGENT_BUDGET_LIMITS["maxToolCalls"]["max"]
ABSOLUTE_MAX_SOURCE_BYTES = AGENT_BUDGET_LIMITS["maxSourceBytes"]["max"]
ABSOLUTE_MAX_INLINE_DIFF_BYTES = AGENT_BUDGET_LIMITS["inlineDiffBytes"]["max"]
ABSOLUTE_MAX_TIMEOUT_SECONDS = AGENT_BUDGET_LIMITS["timeoutSeconds"]["max"]
ABSOLUTE_MAX_EVIDENCE_CALLS = AGENT_BUDGET_LIMITS["maxEvidenceCalls"]["max"]
AGENT_TRACE_PHASES = {
    "AGENT_ANALYZING",
    "AGENT_TOOL_ACTIVITY",
    "AGENT_CONVERGING",
    "AGENT_SUBMITTING",
}
AGENT_TRACE_TOOLS = {
    "list_files",
    "search_code",
    "read_file_range",
    "read_diff_range",
    "submit_review",
}

_SCHEMA_LOCK = Lock()
_SCHEMA_ENGINES: set[int] = set()


def _supports_skip_locked(db: Session) -> bool:
    dialect = db.get_bind().dialect
    if dialect.name != "mysql" or bool(getattr(dialect, "is_mariadb", False)):
        return False
    version = getattr(dialect, "server_version_info", None)
    if not version or len(version) < 2:
        return False
    try:
        return (int(version[0]), int(version[1])) >= (8, 0)
    except (TypeError, ValueError):
        return False


def ensure_agent_review_schema(db: Session) -> None:
    engine_id = id(db.get_bind())
    if engine_id in _SCHEMA_ENGINES:
        return
    with _SCHEMA_LOCK:
        if engine_id in _SCHEMA_ENGINES:
            return
        connection = db.connection()
        inspector = inspect(connection)
        AgentReviewSettings.__table__.create(connection, checkfirst=True)
        AgentReviewWorker.__table__.create(connection, checkfirst=True)
        AgentReviewRun.__table__.create(connection, checkfirst=True)
        _ensure_settings_columns(db, inspector)
        _ensure_worker_columns(db, inspector)
        _ensure_worker_indexes(db, inspector)
        ensure_result_schema(db)
        ensure_scheduler_job_schema(db)
        _ensure_result_columns(db, inspector)
        _ensure_scheduler_columns(db, inspector)
        _SCHEMA_ENGINES.add(engine_id)


def get_agent_settings_record(db: Session) -> AgentReviewSettings:
    ensure_agent_review_schema(db)
    record = db.get(AgentReviewSettings, 1)
    if record is None:
        now = utc_now()
        record = AgentReviewSettings(id=1, enabled=False, created_at=now, updated_at=now)
        db.add(record)
        db.flush()
    return record


def agent_settings_response(db: Session) -> dict[str, Any]:
    record = get_agent_settings_record(db)
    worker_pool = agent_worker_pool(db)
    if (
        worker_pool["totalCount"] == 0
        and _worker_online(record)
        and record.worker_id
    ):
        worker_pool = _legacy_worker_pool(record)
    has_registered_workers = worker_pool["totalCount"] > 0
    online = (
        worker_pool["onlineCount"] > 0
        if has_registered_workers
        else _worker_online(record)
    )
    budgets, budget_source = effective_agent_budgets(record)
    return {
        "enabled": bool(record.enabled),
        "runner": "CLAUDE_CODE",
        "cliVersion": AGENT_CLI_VERSION,
        "provider": "DEEPSEEK",
        "endpoint": AGENT_ENDPOINT,
        "model": AGENT_MODEL,
        "apiKeyConfigured": bool(record.api_key_ciphertext),
        "apiKeyMasked": mask_fingerprint(record.api_key_fingerprint),
        "encryptionAvailable": encryption_available(),
        "workerStatus": "ONLINE" if online else "OFFLINE",
        "workerId": record.worker_id,
        "workerVersion": record.worker_version,
        "lastWorkerHeartbeatAt": format_datetime(record.last_worker_heartbeat_at),
        "workerPool": worker_pool,
        "configurationTest": {
            "requestId": record.test_request_id,
            "status": record.test_status or "NOT_RUN",
            "message": record.test_message,
            "durationMs": record.test_duration_ms,
            "startedAt": format_datetime(record.test_started_at),
            "finishedAt": format_datetime(record.test_finished_at),
        },
        "budgets": {**budgets, "maxDiffBytes": MAX_DIFF_BYTES},
        "budgetDefaults": default_agent_budgets(),
        "budgetLimits": agent_budget_limits(),
        "budgetConfigSource": budget_source,
        "updatedAt": format_datetime(record.updated_at),
    }


def update_agent_settings(db: Session, request: dict[str, Any]) -> dict[str, Any]:
    record = get_agent_settings_record(db)
    if "resetBudgets" in request and not isinstance(request.get("resetBudgets"), bool):
        raise AppError("VALIDATION_ERROR", "resetBudgets must be a boolean", 400)
    reset_budgets = request.get("resetBudgets") is True
    if "resetBudgets" in request and "budgets" in request:
        raise AppError(
            "VALIDATION_ERROR",
            "budgets and resetBudgets cannot be submitted together",
            400,
        )
    next_budget_json = record.budget_config_json
    if reset_budgets:
        next_budget_json = None
    elif "budgets" in request:
        current_budgets, _ = effective_agent_budgets(record)
        try:
            next_budgets = validate_agent_budgets(
                request.get("budgets"),
                base=current_budgets,
            )
        except AgentBudgetValidationError as exception:
            raise AppError("VALIDATION_ERROR", str(exception), 400) from exception
        next_budget_json = (
            None
            if next_budgets == DEFAULT_AGENT_BUDGETS
            else json.dumps(next_budgets, ensure_ascii=False, sort_keys=True)
        )

    if request.get("clearApiKey") is True:
        record.api_key_ciphertext = None
        record.api_key_fingerprint = None
        record.enabled = False
    elif request.get("apiKey") is not None:
        ciphertext, fingerprint = encrypt_api_key(str(request.get("apiKey") or ""))
        record.api_key_ciphertext = ciphertext
        record.api_key_fingerprint = fingerprint
    if "enabled" in request:
        enabled = bool(request.get("enabled"))
        if enabled:
            decrypt_api_key(record.api_key_ciphertext)
        record.enabled = enabled
    record.budget_config_json = next_budget_json
    record.updated_at = utc_now()
    db.commit()
    return agent_settings_response(db)


def effective_agent_budgets(record: AgentReviewSettings) -> tuple[dict[str, int], str]:
    if not record.budget_config_json:
        return default_agent_budgets(), "DEFAULT"
    stored = _read_json(record.budget_config_json, None)
    if not isinstance(stored, dict) or set(stored) != AGENT_BUDGET_KEYS:
        return default_agent_budgets(), "DEFAULT"
    try:
        budgets = validate_agent_budgets(stored)
    except AgentBudgetValidationError:
        return default_agent_budgets(), "DEFAULT"
    return budgets, "CUSTOM"


def record_worker_heartbeat(
    db: Session,
    *,
    worker_id: str,
    worker_version: str,
    cli_version: str,
    state: str,
    capacity: int,
    active_job_id: int | None,
    active_run_id: int | None,
) -> dict[str, Any]:
    record = get_agent_settings_record(db)
    now = utc_now()
    record.worker_id = _bounded(worker_id, 128)
    record.worker_version = _bounded(worker_version, 64)
    record.cli_version = _bounded(cli_version, 64)
    record.last_worker_heartbeat_at = now
    record.updated_at = now
    worker = db.get(AgentReviewWorker, worker_id)
    if worker is None:
        worker = AgentReviewWorker(
            worker_id=worker_id,
            started_at=now,
        )
        db.add(worker)
    worker.worker_version = _bounded(worker_version, 64)
    worker.cli_version = _bounded(cli_version, 64)
    worker.state = state
    worker.capacity = capacity
    worker.active_job_id = active_job_id
    worker.active_run_id = active_run_id
    worker.last_heartbeat_at = now
    worker.updated_at = now
    cleanup_stale_agent_workers(db, now=now)
    db.commit()
    return {"accepted": True, "serverTime": format_datetime(now)}


def agent_worker_pool(db: Session) -> dict[str, Any]:
    ensure_agent_review_schema(db)
    cutoff = utc_now() - timedelta(seconds=AGENT_WORKER_ONLINE_SECONDS)
    workers = db.scalars(
        select(AgentReviewWorker)
        .order_by(AgentReviewWorker.last_heartbeat_at.desc(), AgentReviewWorker.worker_id.asc())
        .limit(AGENT_WORKER_NODE_LIMIT)
    ).all()
    nodes: list[dict[str, Any]] = []
    online_count = 0
    busy_count = 0
    idle_count = 0
    draining_count = 0
    total_capacity = 0
    for worker in workers:
        state = (
            worker.state
            if worker.state in {"IDLE", "BUSY", "DRAINING"}
            else "IDLE"
        )
        capacity = 1
        is_online = bool(
            worker.last_heartbeat_at and worker.last_heartbeat_at >= cutoff
        )
        if is_online:
            online_count += 1
            total_capacity += capacity
            if state == "BUSY":
                busy_count += 1
            elif state == "DRAINING":
                draining_count += 1
            else:
                idle_count += 1
        nodes.append(
            {
                "workerId": worker.worker_id,
                "workerVersion": worker.worker_version,
                "cliVersion": worker.cli_version,
                "state": state,
                "capacity": capacity,
                "activeJobId": worker.active_job_id,
                "activeRunId": worker.active_run_id,
                "startedAt": format_datetime(worker.started_at),
                "lastHeartbeatAt": format_datetime(worker.last_heartbeat_at),
                "online": is_online,
            }
        )
    return {
        "status": "ONLINE" if online_count > 0 else "OFFLINE",
        "onlineCount": online_count,
        "busyCount": busy_count,
        "idleCount": idle_count,
        "drainingCount": draining_count,
        "totalCapacity": total_capacity,
        "totalCount": len(workers),
        "nodes": nodes,
    }


def cleanup_stale_agent_workers(db: Session, *, now=None) -> int:
    cutoff = (now or utc_now()) - timedelta(days=AGENT_WORKER_RETENTION_DAYS)
    result = db.execute(
        delete(AgentReviewWorker).where(
            AgentReviewWorker.last_heartbeat_at < cutoff
        )
    )
    return max(int(result.rowcount or 0), 0)


def _legacy_worker_pool(record: AgentReviewSettings) -> dict[str, Any]:
    return {
        "status": "ONLINE",
        "onlineCount": 1,
        "busyCount": 0,
        "idleCount": 1,
        "drainingCount": 0,
        "totalCapacity": 1,
        "totalCount": 1,
        "nodes": [
            {
                "workerId": record.worker_id,
                "workerVersion": record.worker_version,
                "cliVersion": record.cli_version,
                "state": "IDLE",
                "capacity": 1,
                "activeJobId": None,
                "activeRunId": None,
                "startedAt": None,
                "lastHeartbeatAt": format_datetime(
                    record.last_worker_heartbeat_at
                ),
                "online": True,
            }
        ],
    }


def assert_agent_available(db: Session, *, require_worker: bool = True) -> AgentReviewSettings:
    record = get_agent_settings_record(db)
    if not record.enabled:
        raise AppError("AGENT_REVIEW_UNAVAILABLE", "Agent Review is disabled", 409)
    decrypt_api_key(record.api_key_ciphertext)
    worker_pool = agent_worker_pool(db)
    registered_online = worker_pool["onlineCount"] > 0
    legacy_online = worker_pool["totalCount"] == 0 and _worker_online(record)
    if require_worker and not (registered_online or legacy_online):
        raise AppError("AGENT_REVIEW_UNAVAILABLE", "Agent Review Worker is offline", 409)
    return record


def request_configuration_test(db: Session) -> dict[str, Any]:
    record = assert_agent_available(db, require_worker=True)
    record.test_request_id = f"config-test:{uuid4().hex}"
    record.test_status = "QUEUED"
    record.test_message = None
    record.test_duration_ms = None
    record.test_started_at = None
    record.test_finished_at = None
    record.updated_at = utc_now()
    db.commit()
    return agent_settings_response(db)["configurationTest"]


def claim_configuration_test(db: Session, *, worker_id: str) -> dict[str, Any] | None:
    available = assert_agent_available(db, require_worker=False)
    record = db.scalars(
        select(AgentReviewSettings)
        .where(AgentReviewSettings.id == available.id)
        .execution_options(populate_existing=True)
        .with_for_update()
    ).first()
    if record is None:
        return None
    if record.test_status != "QUEUED" or not record.test_request_id:
        return None
    now = utc_now()
    record.test_status = "RUNNING"
    record.test_started_at = now
    record.test_finished_at = None
    record.test_message = None
    record.updated_at = now
    db.commit()
    return {
        "kind": "CONFIG_TEST",
        "requestId": record.test_request_id,
        "apiKey": decrypt_api_key(record.api_key_ciphertext),
        "budgets": {"maxTurns": 4, "maxToolCalls": 8, "maxSourceBytes": 10_000, "timeoutSeconds": 180},
    }


def complete_configuration_test(
    db: Session, *, request_id: str, status: str, message: str | None, duration_ms: int | None
) -> dict[str, Any]:
    record = get_agent_settings_record(db)
    if record.test_request_id != request_id:
        raise AppError("AGENT_CONFIG_TEST_STALE", "Agent configuration test request is stale", 409)
    if record.test_status in {"SUCCESS", "FAILED"}:
        return agent_settings_response(db)["configurationTest"]
    normalized = str(status or "FAILED").upper()
    record.test_status = "SUCCESS" if normalized == "SUCCESS" else "FAILED"
    record.test_message = _bounded(message, 512)
    record.test_duration_ms = _non_negative(duration_ms)
    record.test_finished_at = utc_now()
    record.updated_at = utc_now()
    db.commit()
    return agent_settings_response(db)["configurationTest"]


def create_agent_job(
    db: Session,
    *,
    task_id: int,
    project_id: int,
    input_payload: dict[str, Any],
    completion_context: dict[str, Any] | None,
    comparison_mode: bool,
) -> AgentReviewRun:
    ensure_agent_review_schema(db)
    now = utc_now()
    idempotency_key = f"agent:{task_id}:{uuid4().hex}"
    job = CodeQualitySchedulerJob(
        job_type="AGENT_REVIEW",
        task_id=task_id,
        review_key=AGENT_REVIEW_KEY,
        project_id=project_id,
        status="QUEUED",
        priority=80,
        label="Agent Review - Claude Code + DeepSeek",
        error_message=None,
        lease_owner=None,
        lease_expires_at=None,
        heartbeat_at=None,
        attempt=0,
        max_attempts=2,
        cancel_requested_at=None,
        idempotency_key=idempotency_key,
        queued_at=now,
        started_at=None,
        finished_at=None,
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.flush()
    run = AgentReviewRun(
        task_id=task_id,
        review_key=AGENT_REVIEW_KEY,
        scheduler_job_id=job.id,
        idempotency_key=idempotency_key,
        requested_engine="AGENT",
        effective_engine=None,
        runner_version=AGENT_RUNNER_VERSION,
        model=AGENT_MODEL,
        status="PENDING",
        input_json=json.dumps(input_payload, ensure_ascii=False),
        completion_context_json=json.dumps(completion_context or {}, ensure_ascii=False),
        comparison_mode=bool(comparison_mode),
        created_at=now,
        updated_at=now,
    )
    db.add(run)
    db.flush()
    return run


def claim_agent_job(db: Session, *, worker_id: str) -> dict[str, Any] | None:
    settings_record = assert_agent_available(db, require_worker=False)
    ensure_agent_review_schema(db)
    now = utc_now()
    stmt = (
        select(CodeQualitySchedulerJob)
        .where(CodeQualitySchedulerJob.job_type == "AGENT_REVIEW")
        .where(
            or_(
                CodeQualitySchedulerJob.status == "QUEUED",
                (
                    (CodeQualitySchedulerJob.status == "RUNNING")
                    & (CodeQualitySchedulerJob.lease_expires_at < now)
                    & (CodeQualitySchedulerJob.attempt < CodeQualitySchedulerJob.max_attempts)
                ),
            )
        )
        .order_by(CodeQualitySchedulerJob.priority.desc(), CodeQualitySchedulerJob.queued_at.asc())
        .limit(1)
    )
    if _supports_skip_locked(db):
        stmt = stmt.with_for_update(skip_locked=True)
    else:
        stmt = stmt.with_for_update()
    job = db.scalars(stmt).first()
    if job is None:
        return None
    run = db.scalars(select(AgentReviewRun).where(AgentReviewRun.scheduler_job_id == job.id)).first()
    if run is None:
        job.status = "FAILED"
        job.error_message = "AGENT_RUN_NOT_FOUND"
        job.finished_at = now
        job.updated_at = now
        db.commit()
        return None
    lease_seconds = max(get_settings().agent_review_lease_seconds, 30)
    job.status = "RUNNING"
    job.lease_owner = _bounded(worker_id, 128)
    job.lease_expires_at = now + timedelta(seconds=lease_seconds)
    job.heartbeat_at = now
    job.attempt = int(job.attempt or 0) + 1
    job.started_at = job.started_at or now
    job.updated_at = now
    run.status = "RUNNING"
    run.started_at = run.started_at or now
    run.heartbeat_at = now
    run.updated_at = now
    input_payload = _read_json(run.input_json, {})
    raw_budgets = input_payload.get("budgets")
    if raw_budgets is None:
        # 兼容配置化上线前已排队的 Run；旧任务必须使用原默认值，而不是后来保存的全局配置。
        budgets: dict[str, Any] = default_agent_budgets()
    else:
        try:
            budgets = validate_agent_budgets(raw_budgets)
        except AgentBudgetValidationError:
            # 不把损坏的持久化原文返回给 Worker；安全哨兵会触发 Worker 的严格拒绝。
            budgets = {"invalidBudgetContract": 1}
    db.commit()
    return {
        "jobId": job.id,
        "runId": run.id,
        "idempotencyKey": run.idempotency_key,
        "taskId": run.task_id,
        "reviewKey": run.review_key,
        "worktree": input_payload.get("worktree"),
        "input": input_payload.get("case") or {},
        "apiKey": decrypt_api_key(settings_record.api_key_ciphertext),
        "budgets": budgets,
        "leaseSeconds": lease_seconds,
        "claimAttempt": int(job.attempt or 0),
    }


def heartbeat_agent_job(
    db: Session,
    *,
    job_id: int,
    worker_id: str,
    claim_attempt: int,
    run_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_agent_review_schema(db)
    job = db.get(CodeQualitySchedulerJob, job_id)
    if job is None or job.job_type != "AGENT_REVIEW":
        raise AppError("RESOURCE_NOT_FOUND", f"Agent Review job not found: {job_id}", 404)
    if job.status != "RUNNING" or job.lease_owner != worker_id:
        raise AppError("AGENT_JOB_LEASE_LOST", "Agent Review job lease is no longer owned", 409)
    _assert_claim_attempt(job, claim_attempt)
    now = utc_now()
    job.heartbeat_at = now
    job.lease_expires_at = now + timedelta(seconds=max(get_settings().agent_review_lease_seconds, 30))
    job.updated_at = now
    run = db.scalars(select(AgentReviewRun).where(AgentReviewRun.scheduler_job_id == job.id)).first()
    if run is not None:
        run.heartbeat_at = now
        run.updated_at = now
        if run_summary:
            _apply_safe_run_summary(run, run_summary)
    cancelled = job.cancel_requested_at is not None
    db.commit()
    return {"accepted": True, "cancelRequested": cancelled}


def expire_exhausted_agent_jobs(db: Session) -> list[int]:
    """Fail stale jobs that cannot currently be recovered, allowing explicit fallback."""
    ensure_agent_review_schema(db)
    now = utc_now()
    settings_record = get_agent_settings_record(db)
    worker_online = _worker_online(settings_record)
    jobs = db.scalars(
        select(CodeQualitySchedulerJob)
        .where(CodeQualitySchedulerJob.job_type == "AGENT_REVIEW")
        .where(CodeQualitySchedulerJob.status.in_(["QUEUED", "RUNNING"]))
    ).all()
    run_ids: list[int] = []
    for job in jobs:
        running_expired = bool(
            job.status == "RUNNING"
            and job.lease_expires_at
            and job.lease_expires_at < now
            and (int(job.attempt or 0) >= int(job.max_attempts or 0) or not worker_online)
        )
        queued_offline = bool(
            job.status == "QUEUED"
            and not worker_online
            and job.queued_at
            and job.queued_at < now - timedelta(seconds=60)
        )
        if not running_expired and not queued_offline:
            continue
        run = db.scalars(select(AgentReviewRun).where(AgentReviewRun.scheduler_job_id == job.id)).first()
        job.status = "FAILED"
        job.error_message = "AGENT_LEASE_EXHAUSTED"
        job.finished_at = now
        job.lease_expires_at = None
        job.updated_at = now
        if run is not None and run.status not in {"SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT"}:
            run.status = "FAILED"
            run.effective_engine = "STANDARD_FALLBACK"
            run.failure_code = "AGENT_LEASE_EXHAUSTED"
            run.failure_message = "Agent Worker was unavailable after the lease or queue grace period"
            run.finished_at = now
            run.updated_at = now
            run_ids.append(int(run.id))
    db.flush()
    return run_ids


def get_run_for_completion(
    db: Session,
    *,
    job_id: int,
    worker_id: str,
    idempotency_key: str,
    claim_attempt: int,
) -> tuple[CodeQualitySchedulerJob, AgentReviewRun]:
    ensure_agent_review_schema(db)
    job = db.get(CodeQualitySchedulerJob, job_id)
    run = db.scalars(select(AgentReviewRun).where(AgentReviewRun.scheduler_job_id == job_id)).first()
    if job is None or run is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Agent Review job not found: {job_id}", 404)
    if run.idempotency_key != idempotency_key:
        raise AppError("AGENT_IDEMPOTENCY_MISMATCH", "Agent Review idempotency key mismatch", 409)
    if job.lease_owner != worker_id:
        raise AppError("AGENT_JOB_LEASE_LOST", "Agent Review job lease is no longer owned", 409)
    _assert_claim_attempt(job, claim_attempt)
    if run.status in {"SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT"}:
        return job, run
    return job, run


def finish_agent_records(
    db: Session,
    *,
    job: CodeQualitySchedulerJob,
    run: AgentReviewRun,
    status: str,
    effective_engine: str,
    summary: dict[str, Any],
    failure_code: str | None = None,
    failure_message: str | None = None,
    clear_input: bool = True,
) -> None:
    now = utc_now()
    run.status = status
    run.effective_engine = effective_engine
    run.failure_code = _bounded(failure_code, 64)
    run.failure_message = _bounded(failure_message, 1024)
    run.finished_at = now
    run.updated_at = now
    _apply_safe_run_summary(run, summary)
    if clear_input:
        run.input_json = None
    job.status = "SUCCESS" if status == "SUCCEEDED" else ("SKIPPED" if status == "CANCELLED" else "FAILED")
    job.error_message = _bounded(failure_message or failure_code, 1024)
    job.finished_at = now
    job.lease_expires_at = None
    job.updated_at = now
    db.flush()


def run_to_summary(run: AgentReviewRun, *, fallback_triggered: bool | None = None) -> dict[str, Any]:
    tool_summary = _read_json(run.tool_summary_json, {})
    effective_budgets = _safe_effective_budgets(
        tool_summary.get("effectiveBudgets") if isinstance(tool_summary, dict) else None
    )
    if not effective_budgets:
        input_payload = _read_json(run.input_json, {})
        if isinstance(input_payload, dict):
            effective_budgets = _safe_effective_budgets(input_payload.get("budgets"))
    result = {
        "runId": run.id,
        "runnerVersion": run.runner_version,
        "cliVersion": run.cli_version or AGENT_CLI_VERSION,
        "model": run.model,
        "status": run.status,
        "turnCount": int(run.turn_count or 0),
        "toolCallCount": int(run.tool_call_count or 0),
        "sourceBytesReturned": int(run.source_bytes_returned or 0),
        "diffBytesReturned": int(run.diff_bytes_returned or 0),
        "durationMs": run.duration_ms,
        "fallbackTriggered": bool(fallback_triggered) if fallback_triggered is not None else run.effective_engine == "STANDARD_FALLBACK",
        "failureCode": run.failure_code,
    }
    if effective_budgets:
        result["effectiveBudgets"] = effective_budgets
    return result


def sanitize_agent_audit(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    events: list[dict[str, Any]] = []
    raw_events = source.get("events") if isinstance(source.get("events"), list) else []
    for index, raw_event in enumerate(raw_events[:ABSOLUTE_MAX_TOOL_CALLS], 1):
        if not isinstance(raw_event, dict):
            continue
        tool = str(raw_event.get("tool") or "")
        if tool not in AGENT_TRACE_TOOLS:
            continue
        sequence = _safe_trace_sequence(raw_event.get("sequence"), index)
        if sequence is None:
            continue
        status = str(raw_event.get("status") or "FAILED").upper()
        event: dict[str, Any] = {
            "sequence": sequence,
            "tool": tool,
            "status": status if status in {"SUCCESS", "FAILED"} else "FAILED",
            "durationMs": _limited_non_negative(
                raw_event.get("durationMs"), ABSOLUTE_MAX_TIMEOUT_SECONDS * 1000
            ),
            "itemCount": _limited_non_negative(raw_event.get("itemCount"), 100_000),
            "sourceBytes": _limited_non_negative(
                raw_event.get("sourceBytes"), ABSOLUTE_MAX_SOURCE_BYTES
            ),
            "pathSummary": _safe_path_summaries(raw_event.get("pathSummary"), 5),
            "reviewBudget": _safe_review_budget(raw_event.get("reviewBudget")),
        }
        error_code = str(raw_event.get("errorCode") or "")
        if error_code and error_code.replace("_", "").isalnum():
            event["errorCode"] = error_code[:80]
        events.append(event)
    events.sort(key=lambda item: item["sequence"])
    phase = str(source.get("phase") or "ANALYZING").upper()
    if phase not in {"ANALYZING", "TOOL_ACTIVITY", "CONVERGING", "SUBMITTING"}:
        phase = "ANALYZING"
    return {
        "phase": phase,
        "toolCallCount": _limited_non_negative(
            source.get("toolCallCount"), ABSOLUTE_MAX_TOOL_CALLS
        ),
        "evidenceCallsUsed": _limited_non_negative(
            source.get("evidenceCallsUsed"), ABSOLUTE_MAX_EVIDENCE_CALLS
        ),
        "sourceBytesReturned": _limited_non_negative(
            source.get("sourceBytesReturned"), ABSOLUTE_MAX_SOURCE_BYTES
        ),
        "diffBytesReturned": _limited_non_negative(
            source.get("diffBytesReturned"), ABSOLUTE_MAX_INLINE_DIFF_BYTES
        ),
        "blockedAccessCount": _limited_non_negative(
            source.get("blockedAccessCount"), ABSOLUTE_MAX_TOOL_CALLS
        ),
        "reviewSubmitted": bool(source.get("reviewSubmitted")),
        "reviewBudget": _safe_review_budget(source.get("reviewBudget")),
        "topPathSummaries": _safe_path_summaries(source.get("topPathSummaries"), 20),
        "events": events,
    }


def lock_agent_run_for_trace(db: Session, run_id: int) -> AgentReviewRun | None:
    return db.scalars(
        select(AgentReviewRun)
        .where(AgentReviewRun.id == run_id)
        .with_for_update()
    ).first()


def find_agent_run_by_job(db: Session, job_id: int) -> AgentReviewRun | None:
    return db.scalars(
        select(AgentReviewRun).where(AgentReviewRun.scheduler_job_id == job_id)
    ).first()


def agent_trace_sequences(
    db: Session,
    *,
    task_id: int,
    review_key: str,
    run_id: int,
    claim_attempt: int,
) -> set[int]:
    records = db.scalars(
        select(CodeQualityReviewProgressEvent)
        .where(CodeQualityReviewProgressEvent.task_id == task_id)
        .where(CodeQualityReviewProgressEvent.review_key == review_key)
        .where(CodeQualityReviewProgressEvent.phase.in_(AGENT_TRACE_PHASES))
    ).all()
    sequences: set[int] = set()
    for record in records:
        detail = _read_json(record.detail, {})
        if not isinstance(detail, dict):
            continue
        if _non_negative(detail.get("runId")) != int(run_id):
            continue
        if _non_negative(detail.get("claimAttempt")) != int(claim_attempt):
            continue
        try:
            sequence = int(detail.get("sequence"))
        except (TypeError, ValueError):
            continue
        if 0 <= sequence <= ABSOLUTE_MAX_TOOL_CALLS:
            sequences.add(sequence)
    return sequences


def agent_heartbeat_sequences(
    db: Session,
    *,
    task_id: int,
    review_key: str,
    run_id: int,
    claim_attempt: int,
) -> set[int]:
    records = db.scalars(
        select(CodeQualityReviewProgressEvent)
        .where(CodeQualityReviewProgressEvent.task_id == task_id)
        .where(CodeQualityReviewProgressEvent.review_key == review_key)
        .where(CodeQualityReviewProgressEvent.phase == "AGENT_HEARTBEAT")
    ).all()
    sequences: set[int] = set()
    for record in records:
        detail = _read_json(record.detail, {})
        if not isinstance(detail, dict):
            continue
        if _non_negative(detail.get("runId")) != int(run_id):
            continue
        if _non_negative(detail.get("claimAttempt")) != int(claim_attempt):
            continue
        try:
            sequence = int(detail.get("heartbeatSequence"))
        except (TypeError, ValueError):
            continue
        if 0 <= sequence <= 1_000:
            sequences.add(sequence)
    return sequences


def _apply_safe_run_summary(run: AgentReviewRun, value: dict[str, Any]) -> None:
    run.cli_version = _bounded(value.get("cliVersion") or run.cli_version, 64)
    run.session_id = _bounded(value.get("sessionId") or run.session_id, 128)
    run.turn_count = _limited_non_negative(
        value.get("turnCount") or value.get("numTurns"), ABSOLUTE_MAX_TURNS + 1
    )
    audit = sanitize_agent_audit(value.get("audit"))
    run.tool_call_count = _limited_non_negative(
        value.get("toolCallCount") or audit.get("toolCallCount"),
        ABSOLUTE_MAX_TOOL_CALLS,
    )
    run.source_bytes_returned = _limited_non_negative(
        value.get("sourceBytesReturned") or audit.get("sourceBytesReturned"),
        ABSOLUTE_MAX_SOURCE_BYTES,
    )
    run.diff_bytes_returned = _limited_non_negative(
        value.get("diffBytesReturned") or audit.get("diffBytesReturned"),
        ABSOLUTE_MAX_INLINE_DIFF_BYTES,
    )
    run.duration_ms = (
        _limited_non_negative(
            value.get("durationMs"), ABSOLUTE_MAX_TIMEOUT_SECONDS * 1000
        )
        or run.duration_ms
    )
    effective_budgets = _safe_effective_budgets(value.get("effectiveBudgets"))
    if effective_budgets:
        audit["effectiveBudgets"] = effective_budgets
    run.usage_json = json.dumps(_safe_usage(value.get("usage")), ensure_ascii=False)
    run.tool_summary_json = json.dumps(audit, ensure_ascii=False)


def _safe_usage(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key in (
        "input_tokens",
        "output_tokens",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    ):
        if key in value:
            result[key] = _limited_non_negative(value.get(key), 10_000_000_000)
    return result


def _safe_effective_budgets(value: Any) -> dict[str, int]:
    if not isinstance(value, dict) or set(value) != AGENT_BUDGET_KEYS:
        return {}
    try:
        return validate_agent_budgets(value)
    except AgentBudgetValidationError:
        return {}


def _safe_review_budget(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    phase = str(source.get("phase") or "DISCOVERY").upper()
    if phase not in {"DISCOVERY", "CONVERGE", "SUBMIT"}:
        phase = "DISCOVERY"
    return {
        "phase": phase,
        "evidenceCallsUsed": _limited_non_negative(
            source.get("evidenceCallsUsed"), ABSOLUTE_MAX_EVIDENCE_CALLS
        ),
        "evidenceCallsRemaining": _limited_non_negative(
            source.get("evidenceCallsRemaining"), ABSOLUTE_MAX_EVIDENCE_CALLS
        ),
        "sourceBytesRemaining": _limited_non_negative(
            source.get("sourceBytesRemaining"), ABSOLUTE_MAX_SOURCE_BYTES
        ),
        "mustSubmit": bool(source.get("mustSubmit")) or phase == "SUBMIT",
    }


def _safe_path_summaries(value: Any, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for raw in value[:limit]:
        if not isinstance(raw, dict):
            continue
        suffix = str(raw.get("suffix") or "").casefold()
        if len(suffix) > 20 or any(
            character not in ".abcdefghijklmnopqrstuvwxyz0123456789"
            for character in suffix
        ):
            suffix = ""
        result.append(
            {
                "suffix": suffix,
                "depth": _limited_non_negative(raw.get("depth"), 100),
            }
        )
    return result


def _safe_trace_sequence(value: Any, fallback: int) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        sequence = int(value if value is not None else fallback)
    except (TypeError, ValueError):
        return None
    return sequence if 1 <= sequence <= ABSOLUTE_MAX_TOOL_CALLS else None


def _assert_claim_attempt(job: CodeQualitySchedulerJob, claim_attempt: int) -> None:
    if int(job.attempt or 0) != int(claim_attempt):
        raise AppError(
            "AGENT_JOB_CLAIM_STALE",
            "Agent Review claim attempt is stale",
            409,
        )


def _ensure_result_columns(db: Session, inspector) -> None:
    columns = {column["name"] for column in inspector.get_columns("code_quality_review_results")}
    _add_column(db, columns, "code_quality_review_results", "requested_engine", "VARCHAR(32) NOT NULL DEFAULT 'STANDARD'")
    _add_column(db, columns, "code_quality_review_results", "effective_engine", "VARCHAR(32) NOT NULL DEFAULT 'STANDARD'")
    _add_column(db, columns, "code_quality_review_results", "agent_run_id", "BIGINT NULL")
    _add_column(db, columns, "code_quality_review_results", "agent_summary_json", "TEXT NULL")


def _ensure_settings_columns(db: Session, inspector) -> None:
    columns = {column["name"] for column in inspector.get_columns("code_quality_agent_settings")}
    definitions = {
        "budget_config_json": "TEXT NULL",
        "test_request_id": "VARCHAR(128) NULL",
        "test_status": "VARCHAR(32) NULL",
        "test_message": "VARCHAR(512) NULL",
        "test_duration_ms": "BIGINT NULL",
        "test_started_at": "DATETIME NULL",
        "test_finished_at": "DATETIME NULL",
    }
    for name, definition in definitions.items():
        _add_column(db, columns, "code_quality_agent_settings", name, definition)


def _ensure_worker_columns(db: Session, inspector) -> None:
    columns = {
        column["name"]
        for column in inspector.get_columns("code_quality_agent_workers")
    }
    definitions = {
        "worker_version": "VARCHAR(64) NULL",
        "cli_version": "VARCHAR(64) NULL",
        "state": "VARCHAR(16) NOT NULL DEFAULT 'IDLE'",
        "capacity": "INT NOT NULL DEFAULT 1",
        "active_job_id": "BIGINT NULL",
        "active_run_id": "BIGINT NULL",
        "started_at": "DATETIME NULL",
        "last_heartbeat_at": "DATETIME NULL",
        "updated_at": "DATETIME NULL",
    }
    for name, definition in definitions.items():
        _add_column(db, columns, "code_quality_agent_workers", name, definition)


def _ensure_worker_indexes(db: Session, inspector) -> None:
    indexes = {
        str(index.get("name") or "")
        for index in inspector.get_indexes("code_quality_agent_workers")
    }
    index_name = "idx_code_quality_agent_workers_heartbeat"
    if index_name not in indexes:
        db.execute(
            text(
                f"CREATE INDEX {index_name} "
                "ON code_quality_agent_workers (last_heartbeat_at)"
            )
        )
        db.flush()


def _ensure_scheduler_columns(db: Session, inspector) -> None:
    columns = {column["name"] for column in inspector.get_columns("code_quality_scheduler_jobs")}
    definitions = {
        "lease_owner": "VARCHAR(128) NULL",
        "lease_expires_at": "DATETIME NULL",
        "heartbeat_at": "DATETIME NULL",
        "attempt": "INT NOT NULL DEFAULT 0",
        "max_attempts": "INT NOT NULL DEFAULT 2",
        "cancel_requested_at": "DATETIME NULL",
        "idempotency_key": "VARCHAR(128) NULL",
    }
    for name, definition in definitions.items():
        _add_column(db, columns, "code_quality_scheduler_jobs", name, definition)


def _add_column(db: Session, columns: set[str], table: str, column: str, definition: str) -> None:
    if column in columns:
        return
    db.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
    columns.add(column)
    db.flush()


def _worker_online(record: AgentReviewSettings) -> bool:
    heartbeat = record.last_worker_heartbeat_at
    return bool(
        heartbeat
        and heartbeat
        >= utc_now() - timedelta(seconds=AGENT_WORKER_ONLINE_SECONDS)
    )


def _read_json(value: str | None, default: Any) -> Any:
    try:
        parsed = json.loads(value or "")
        return parsed
    except (TypeError, json.JSONDecodeError):
        return default


def _bounded(value: Any, maximum: int) -> str | None:
    text_value = str(value or "").strip()
    return text_value[:maximum] if text_value else None


def _non_negative(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _limited_non_negative(value: Any, maximum: int) -> int:
    return min(_non_negative(value), max(int(maximum), 0))
