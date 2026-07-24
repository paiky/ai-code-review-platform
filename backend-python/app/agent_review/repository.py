from __future__ import annotations

from datetime import datetime, timedelta
import json
from threading import Lock
from typing import Any
from uuid import uuid4

from sqlalchemy import inspect, or_, select, text
from sqlalchemy.orm import Session

from app.agent_review.crypto import decrypt_api_key, encrypt_api_key, encryption_available, mask_fingerprint
from app.agent_review.models import AgentReviewRun, AgentReviewSettings
from app.code_quality.models import CodeQualitySchedulerJob
from app.code_quality.repository import ensure_result_schema, ensure_scheduler_job_schema, format_datetime
from app.core.config import get_settings
from app.core.errors import AppError


AGENT_REVIEW_KEY = "agent-claude-code-deepseek-v4-pro"
AGENT_MODEL = "deepseek-v4-pro[1m]"
AGENT_CLI_VERSION = "2.1.112"
AGENT_RUNNER_VERSION = "agent-worker-v1"
AGENT_ENDPOINT = "https://api.deepseek.com/anthropic"
MAX_TURNS = 8
MAX_TOOL_CALLS = 40
MAX_SOURCE_BYTES = 200_000
MAX_DIFF_BYTES = 1_048_576
INLINE_DIFF_BYTES = 200_000
TIMEOUT_SECONDS = 600

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
        AgentReviewRun.__table__.create(connection, checkfirst=True)
        _ensure_settings_columns(db, inspector)
        ensure_result_schema(db)
        ensure_scheduler_job_schema(db)
        _ensure_result_columns(db, inspector)
        _ensure_scheduler_columns(db, inspector)
        _SCHEMA_ENGINES.add(engine_id)


def get_agent_settings_record(db: Session) -> AgentReviewSettings:
    ensure_agent_review_schema(db)
    record = db.get(AgentReviewSettings, 1)
    if record is None:
        now = datetime.now()
        record = AgentReviewSettings(id=1, enabled=False, created_at=now, updated_at=now)
        db.add(record)
        db.flush()
    return record


def agent_settings_response(db: Session) -> dict[str, Any]:
    record = get_agent_settings_record(db)
    online = _worker_online(record)
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
        "configurationTest": {
            "requestId": record.test_request_id,
            "status": record.test_status or "NOT_RUN",
            "message": record.test_message,
            "durationMs": record.test_duration_ms,
            "startedAt": format_datetime(record.test_started_at),
            "finishedAt": format_datetime(record.test_finished_at),
        },
        "budgets": {
            "maxTurns": MAX_TURNS,
            "maxToolCalls": MAX_TOOL_CALLS,
            "maxSourceBytes": MAX_SOURCE_BYTES,
            "inlineDiffBytes": INLINE_DIFF_BYTES,
            "maxDiffBytes": MAX_DIFF_BYTES,
            "timeoutSeconds": TIMEOUT_SECONDS,
        },
        "updatedAt": format_datetime(record.updated_at),
    }


def update_agent_settings(db: Session, request: dict[str, Any]) -> dict[str, Any]:
    record = get_agent_settings_record(db)
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
    record.updated_at = datetime.now()
    db.commit()
    return agent_settings_response(db)


def record_worker_heartbeat(
    db: Session, *, worker_id: str, worker_version: str, cli_version: str
) -> dict[str, Any]:
    record = get_agent_settings_record(db)
    now = datetime.now()
    record.worker_id = _bounded(worker_id, 128)
    record.worker_version = _bounded(worker_version, 64)
    record.cli_version = _bounded(cli_version, 64)
    record.last_worker_heartbeat_at = now
    record.updated_at = now
    db.commit()
    return {"accepted": True, "serverTime": format_datetime(now)}


def assert_agent_available(db: Session, *, require_worker: bool = True) -> AgentReviewSettings:
    record = get_agent_settings_record(db)
    if not record.enabled:
        raise AppError("AGENT_REVIEW_UNAVAILABLE", "Agent Review is disabled", 409)
    decrypt_api_key(record.api_key_ciphertext)
    if require_worker and not _worker_online(record):
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
    record.updated_at = datetime.now()
    db.commit()
    return agent_settings_response(db)["configurationTest"]


def claim_configuration_test(db: Session, *, worker_id: str) -> dict[str, Any] | None:
    record = assert_agent_available(db, require_worker=False)
    if record.test_status != "QUEUED" or not record.test_request_id:
        return None
    now = datetime.now()
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
    record.test_finished_at = datetime.now()
    record.updated_at = datetime.now()
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
    now = datetime.now()
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
    now = datetime.now()
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
        "budgets": {
            "maxTurns": MAX_TURNS,
            "maxToolCalls": MAX_TOOL_CALLS,
            "maxSourceBytes": MAX_SOURCE_BYTES,
            "timeoutSeconds": TIMEOUT_SECONDS,
        },
        "leaseSeconds": lease_seconds,
    }


def heartbeat_agent_job(
    db: Session, *, job_id: int, worker_id: str, run_summary: dict[str, Any] | None = None
) -> dict[str, Any]:
    ensure_agent_review_schema(db)
    job = db.get(CodeQualitySchedulerJob, job_id)
    if job is None or job.job_type != "AGENT_REVIEW":
        raise AppError("RESOURCE_NOT_FOUND", f"Agent Review job not found: {job_id}", 404)
    if job.status != "RUNNING" or job.lease_owner != worker_id:
        raise AppError("AGENT_JOB_LEASE_LOST", "Agent Review job lease is no longer owned", 409)
    now = datetime.now()
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
    now = datetime.now()
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
    db: Session, *, job_id: int, worker_id: str, idempotency_key: str
) -> tuple[CodeQualitySchedulerJob, AgentReviewRun]:
    ensure_agent_review_schema(db)
    job = db.get(CodeQualitySchedulerJob, job_id)
    run = db.scalars(select(AgentReviewRun).where(AgentReviewRun.scheduler_job_id == job_id)).first()
    if job is None or run is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Agent Review job not found: {job_id}", 404)
    if run.idempotency_key != idempotency_key:
        raise AppError("AGENT_IDEMPOTENCY_MISMATCH", "Agent Review idempotency key mismatch", 409)
    if run.status in {"SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT"}:
        return job, run
    if job.lease_owner != worker_id:
        raise AppError("AGENT_JOB_LEASE_LOST", "Agent Review job lease is no longer owned", 409)
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
    now = datetime.now()
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
    return {
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


def _apply_safe_run_summary(run: AgentReviewRun, value: dict[str, Any]) -> None:
    run.cli_version = _bounded(value.get("cliVersion") or run.cli_version, 64)
    run.session_id = _bounded(value.get("sessionId") or run.session_id, 128)
    run.turn_count = _non_negative(value.get("turnCount") or value.get("numTurns"))
    audit = value.get("audit") if isinstance(value.get("audit"), dict) else {}
    run.tool_call_count = _non_negative(value.get("toolCallCount") or audit.get("toolCallCount"))
    run.source_bytes_returned = _non_negative(value.get("sourceBytesReturned") or audit.get("sourceBytesReturned"))
    run.diff_bytes_returned = _non_negative(value.get("diffBytesReturned") or audit.get("diffBytesReturned"))
    run.duration_ms = _non_negative(value.get("durationMs")) or run.duration_ms
    run.usage_json = json.dumps(value.get("usage") or {}, ensure_ascii=False)
    run.tool_summary_json = json.dumps(audit, ensure_ascii=False)


def _ensure_result_columns(db: Session, inspector) -> None:
    columns = {column["name"] for column in inspector.get_columns("code_quality_review_results")}
    _add_column(db, columns, "code_quality_review_results", "requested_engine", "VARCHAR(32) NOT NULL DEFAULT 'STANDARD'")
    _add_column(db, columns, "code_quality_review_results", "effective_engine", "VARCHAR(32) NOT NULL DEFAULT 'STANDARD'")
    _add_column(db, columns, "code_quality_review_results", "agent_run_id", "BIGINT NULL")
    _add_column(db, columns, "code_quality_review_results", "agent_summary_json", "TEXT NULL")


def _ensure_settings_columns(db: Session, inspector) -> None:
    columns = {column["name"] for column in inspector.get_columns("code_quality_agent_settings")}
    definitions = {
        "test_request_id": "VARCHAR(128) NULL",
        "test_status": "VARCHAR(32) NULL",
        "test_message": "VARCHAR(512) NULL",
        "test_duration_ms": "BIGINT NULL",
        "test_started_at": "DATETIME NULL",
        "test_finished_at": "DATETIME NULL",
    }
    for name, definition in definitions.items():
        _add_column(db, columns, "code_quality_agent_settings", name, definition)


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
    return bool(heartbeat and heartbeat >= datetime.now() - timedelta(seconds=60))


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
