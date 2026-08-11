from __future__ import annotations

from datetime import datetime, timedelta
import json
import logging
import re
from threading import Lock
from typing import Any
from uuid import uuid4

from sqlalchemy import case, delete, func, inspect, or_, select, text
from sqlalchemy.orm import Session

from app.agent_review.crypto import decrypt_api_key, encrypt_api_key, encryption_available, mask_fingerprint
from app.agent_review.models import (
    AgentReviewRun,
    AgentReviewRuntime,
    AgentReviewSettings,
    AgentReviewWorker,
)
from app.agent_review.runtime import (
    ANTHROPIC_MESSAGES_RUNNER_VERSION,
    CHAT_COMPLETIONS_RUNNER_VERSION,
    CUSTOM_DEFAULT_DISPLAY_NAME,
    CUSTOM_DEFAULT_MODEL,
    CUSTOM_REASONING_EFFORTS,
    CUSTOM_RUNTIME,
    DEFAULT_REVIEW_KEY,
    DEFAULT_RUNTIME,
    RESPONSES_RUNNER_VERSION,
    RUNTIME_TYPES,
    custom_base_url_host,
    normalize_custom_base_url,
    normalize_runtime_type,
    normalize_worker_capabilities,
    runtime_record_snapshot,
    runtime_provider,
    runtime_review_key,
    runtime_snapshot,
    worker_supports,
)
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


AGENT_REVIEW_KEY = DEFAULT_REVIEW_KEY
AGENT_MODEL = "deepseek-v4-pro[1m]"
AGENT_CLI_VERSION = "2.1.112"
AGENT_RUNNER_VERSION = "agent-worker-v1"
AGENT_ENDPOINT = "https://api.deepseek.com/anthropic"
AGENT_WORKER_ONLINE_SECONDS = 60
AGENT_WORKER_RETENTION_HOURS = 48
AGENT_WORKER_NODE_LIMIT = 100
CONFIGURATION_TEST_TIMEOUT_SECONDS = 90
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
AGENT_COMPLETION_CONTEXT_SCHEMA_VERSION = "agent-completion-context-v2"
AGENT_COMPLETION_CONTEXT_MAX_BYTES = 16 * 1024
_COMPLETION_CONTEXT_NOTIFICATION_KEYS = (
    "title",
    "projectName",
    "triggerType",
    "authorName",
    "authorUsername",
    "sourceBranch",
    "targetBranch",
)
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
_LOGGER = logging.getLogger(__name__)
_RUNTIME_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,39}$")
_PROTOCOL_RUNNERS = {
    "ANTHROPIC_COMPATIBLE": "CLAUDE_CODE",
    "OPENAI_RESPONSES": "OPENAI_RESPONSES_AGENT",
    "OPENAI_CHAT_COMPLETIONS": "OPENAI_CHAT_AGENT",
    "ANTHROPIC_MESSAGES": "ANTHROPIC_MESSAGES_AGENT",
}
_OPEN_AGENT_RUNTIME_PROTOCOLS = frozenset(
    {
        "ANTHROPIC_COMPATIBLE",
        "OPENAI_RESPONSES",
        "OPENAI_CHAT_COMPLETIONS",
        "ANTHROPIC_MESSAGES",
    }
)


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
        AgentReviewRuntime.__table__.create(connection, checkfirst=True)
        AgentReviewWorker.__table__.create(connection, checkfirst=True)
        AgentReviewRun.__table__.create(connection, checkfirst=True)
        _ensure_settings_columns(db, inspector)
        _ensure_worker_columns(db, inspector)
        _ensure_run_columns(db, inspector)
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
    ensure_legacy_agent_runtime_records(db, record)
    return record


def ensure_legacy_agent_runtime_records(
    db: Session,
    settings: AgentReviewSettings | None = None,
) -> tuple[AgentReviewRuntime, AgentReviewRuntime | None]:
    """Seed the two V47 runtimes without overwriting already migrated records."""
    if settings is None:
        settings = get_agent_settings_record(db)
    existing_count = int(db.scalar(select(func.count()).select_from(AgentReviewRuntime)) or 0)
    default_runtime = db.get(AgentReviewRuntime, DEFAULT_RUNTIME)
    if default_runtime is None:
        default_runtime = _legacy_runtime_record(settings, DEFAULT_RUNTIME)
        db.add(default_runtime)
    custom_runtime = db.get(AgentReviewRuntime, CUSTOM_RUNTIME)
    if custom_runtime is None and (
        existing_count == 0
        or _legacy_custom_configuration_exists(settings)
        or normalize_runtime_type(settings.runtime_type) == CUSTOM_RUNTIME
        or str(settings.selected_runtime_code or "").strip().upper() == CUSTOM_RUNTIME
    ):
        custom_runtime = _legacy_runtime_record(settings, CUSTOM_RUNTIME)
        db.add(custom_runtime)
    db.flush()

    selected_code = str(settings.selected_runtime_code or "").strip().upper()
    if not _RUNTIME_CODE.fullmatch(selected_code) or db.get(AgentReviewRuntime, selected_code) is None:
        selected_code = normalize_runtime_type(settings.runtime_type)
    if db.get(AgentReviewRuntime, selected_code) is None:
        selected_code = DEFAULT_RUNTIME
    settings.selected_runtime_code = selected_code
    settings.runtime_type = selected_code if selected_code in RUNTIME_TYPES else DEFAULT_RUNTIME
    return default_runtime, custom_runtime


def sync_legacy_agent_runtime_records(
    db: Session,
    settings: AgentReviewSettings,
) -> tuple[AgentReviewRuntime, AgentReviewRuntime | None]:
    """Dual-write legacy settings into the two compatibility runtime records."""
    default_runtime, custom_runtime = ensure_legacy_agent_runtime_records(db, settings)
    now = utc_now()
    default_runtime.api_key_ciphertext = settings.api_key_ciphertext
    default_runtime.api_key_fingerprint = settings.api_key_fingerprint
    default_runtime.updated_at = now
    if custom_runtime is not None:
        custom_runtime.display_name = (
            settings.custom_display_name or CUSTOM_DEFAULT_DISPLAY_NAME
        )
        custom_runtime.base_url = settings.custom_base_url
        custom_runtime.model_name = settings.custom_model or CUSTOM_DEFAULT_MODEL
        custom_runtime.reasoning_effort = settings.custom_reasoning_effort or "high"
        custom_runtime.tls_verify = settings.custom_tls_verify is not False
        custom_runtime.api_key_ciphertext = settings.custom_api_key_ciphertext
        custom_runtime.api_key_fingerprint = settings.custom_api_key_fingerprint
        custom_runtime.updated_at = now
    db.flush()
    return default_runtime, custom_runtime


def list_agent_runtime_records(db: Session) -> list[AgentReviewRuntime]:
    settings = get_agent_settings_record(db)
    ensure_legacy_agent_runtime_records(db, settings)
    return list(
        db.scalars(
            select(AgentReviewRuntime).order_by(
                AgentReviewRuntime.sort_order,
                AgentReviewRuntime.runtime_code,
            )
        ).all()
    )


def agent_runtime_record_response(runtime: AgentReviewRuntime) -> dict[str, Any]:
    return {
        "runtimeCode": runtime.runtime_code,
        "displayName": runtime.display_name,
        "protocol": runtime.protocol,
        "runnerType": runtime.runner_type,
        "baseUrl": runtime.base_url,
        "model": runtime.model_name,
        "reasoningEffort": runtime.reasoning_effort,
        "tlsVerify": runtime.tls_verify is not False,
        "enabled": bool(runtime.enabled),
        "builtIn": bool(runtime.built_in),
        "sortOrder": int(runtime.sort_order),
        "apiKeyConfigured": bool(runtime.api_key_ciphertext),
        "apiKeyMasked": mask_fingerprint(runtime.api_key_fingerprint),
        "updatedAt": format_datetime(runtime.updated_at),
    }


def list_agent_runtime_responses(db: Session) -> list[dict[str, Any]]:
    _expire_runtime_configuration_tests(db)
    settings = get_agent_settings_record(db)
    worker_pool = agent_worker_pool(db)
    return [
        _agent_runtime_response(runtime, settings=settings, worker_pool=worker_pool)
        for runtime in list_agent_runtime_records(db)
    ]


def create_agent_runtime(db: Session, request: dict[str, Any]) -> dict[str, Any]:
    settings = get_agent_settings_record(db)
    runtime_code = _normalize_runtime_code(request.get("runtimeCode"))
    if db.get(AgentReviewRuntime, runtime_code) is not None:
        raise AppError(
            "AGENT_RUNTIME_ALREADY_EXISTS",
            f"Agent Runtime already exists: {runtime_code}",
            409,
        )
    protocol = str(request.get("protocol") or "").strip().upper()
    runner_type = _protocol_runner(protocol)
    worker_pool = agent_worker_pool(db)
    _assert_runtime_protocol_available(protocol, worker_pool, require_worker=True)
    ciphertext = None
    fingerprint = None
    if request.get("apiKey") is not None:
        ciphertext, fingerprint = encrypt_api_key(str(request.get("apiKey") or ""))
    max_sort_order = db.scalar(select(func.max(AgentReviewRuntime.sort_order))) or 0
    runtime = AgentReviewRuntime(
        runtime_code=runtime_code,
        display_name=str(request.get("displayName") or "").strip(),
        protocol=protocol,
        runner_type=runner_type,
        base_url=normalize_custom_base_url(request.get("baseUrl")),
        model_name=str(request.get("model") or "").strip(),
        reasoning_effort=(
            str(request.get("reasoningEffort") or "high").strip().lower()
            if protocol == "OPENAI_RESPONSES"
            else None
        ),
        tls_verify=request.get("tlsVerify") is not False,
        enabled=bool(request.get("enabled", False)),
        built_in=False,
        sort_order=int(max_sort_order) + 10,
        api_key_ciphertext=ciphertext,
        api_key_fingerprint=fingerprint,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    if runtime.enabled:
        _assert_runtime_configuration_complete(runtime)
    db.add(runtime)
    db.flush()
    return _agent_runtime_response(runtime, settings=settings, worker_pool=worker_pool)


def create_agent_model_connection(db: Session, request: dict[str, Any]) -> dict[str, Any]:
    from app.code_quality.model_presets import list_review_model_presets

    preset_code = str(request.get("presetCode") or "").strip().upper()
    preset = next(
        (
            item
            for item in list_review_model_presets("AGENT")
            if item["presetCode"] == preset_code
        ),
        None,
    )
    if preset is None:
        raise AppError(
            "REVIEW_MODEL_PRESET_NOT_FOUND",
            f"Agent Review model preset does not exist: {preset_code}",
            400,
        )
    protocol = str(request.get("protocol") or "").strip().upper()
    matching_variant = next(
        (
            item
            for item in preset["variants"]
            if str(item.get("protocol") or "").upper() == protocol
        ),
        None,
    )
    if not preset["custom"] and matching_variant is None:
        raise AppError(
            "REVIEW_MODEL_PRESET_PROTOCOL_MISMATCH",
            f"Protocol {protocol} does not belong to preset {preset_code}",
            400,
        )
    _protocol_runner(protocol)
    reasoning_effort = request.get("reasoningEffort")
    supported_efforts = (
        list(matching_variant.get("reasoningEfforts") or [])
        if matching_variant is not None
        else (["low", "medium", "high"] if protocol in {"ANTHROPIC_COMPATIBLE", "OPENAI_RESPONSES"} else [])
    )
    if reasoning_effort is None and matching_variant is not None:
        reasoning_effort = matching_variant.get("defaultReasoningEffort")
    if reasoning_effort is not None and reasoning_effort not in supported_efforts:
        raise AppError(
            "VALIDATION_ERROR",
            f"reasoningEffort is not supported by protocol {protocol}",
            400,
        )
    runtime_code = _generated_runtime_code(db, str(preset["vendorCode"]))
    display_name = _generated_runtime_display_name(
        db,
        str(preset["vendorName"]),
        str(request.get("model") or "").strip(),
    )
    return create_agent_runtime(
        db,
        {
            "runtimeCode": runtime_code,
            "displayName": display_name,
            "protocol": protocol,
            "baseUrl": request.get("baseUrl"),
            "model": request.get("model"),
            "reasoningEffort": reasoning_effort,
            "tlsVerify": request.get("tlsVerify") is not False,
            "apiKey": request.get("apiKey"),
            "enabled": True,
        },
    )


def update_agent_runtime(
    db: Session,
    runtime_code: str,
    request: dict[str, Any],
) -> dict[str, Any]:
    settings = get_agent_settings_record(db)
    runtime = _get_agent_runtime(db, runtime_code, lock=True)
    if runtime.built_in:
        immutable_fields = {
            "displayName",
            "baseUrl",
            "model",
            "reasoningEffort",
            "tlsVerify",
        }
        if immutable_fields.intersection(request):
            raise AppError(
                "AGENT_RUNTIME_BUILT_IN_IMMUTABLE",
                f"Built-in Agent Runtime connection is immutable: {runtime.runtime_code}",
                409,
            )
    if "displayName" in request:
        runtime.display_name = str(request.get("displayName") or "").strip()
    if "baseUrl" in request:
        runtime.base_url = normalize_custom_base_url(request.get("baseUrl"))
    if "model" in request:
        runtime.model_name = str(request.get("model") or "").strip()
    if "reasoningEffort" in request:
        if runtime.protocol not in {"ANTHROPIC_COMPATIBLE", "OPENAI_RESPONSES"}:
            raise AppError(
                "VALIDATION_ERROR",
                "reasoningEffort is only supported by ANTHROPIC_COMPATIBLE or OPENAI_RESPONSES",
                400,
            )
        runtime.reasoning_effort = str(request.get("reasoningEffort") or "").lower()
    if "tlsVerify" in request:
        runtime.tls_verify = request.get("tlsVerify") is not False
    if request.get("clearApiKey") is True:
        runtime.api_key_ciphertext = None
        runtime.api_key_fingerprint = None
        runtime.enabled = False
        _fail_active_runtime_configuration_test(
            runtime,
            "Agent Runtime credential was cleared before configuration test completion",
        )
        if settings.selected_runtime_code == runtime.runtime_code:
            settings.enabled = False
    elif request.get("apiKey") is not None:
        runtime.api_key_ciphertext, runtime.api_key_fingerprint = encrypt_api_key(
            str(request.get("apiKey") or "")
        )
    if "enabled" in request:
        runtime.enabled = bool(request.get("enabled"))
        if not runtime.enabled:
            _fail_active_runtime_configuration_test(
                runtime,
                "Agent Runtime was disabled before configuration test completion",
            )
        if not runtime.enabled and settings.selected_runtime_code == runtime.runtime_code:
            settings.enabled = False
    worker_pool = agent_worker_pool(db)
    if runtime.enabled:
        _assert_runtime_protocol_available(
            runtime.protocol,
            worker_pool,
            require_worker=True,
        )
        _assert_runtime_configuration_complete(runtime)
    runtime.updated_at = utc_now()
    _sync_runtime_to_legacy_settings(settings, runtime)
    if settings.selected_runtime_code == runtime.runtime_code:
        _sync_runtime_test_to_legacy_settings(settings, runtime)
    db.flush()
    return _agent_runtime_response(runtime, settings=settings, worker_pool=worker_pool)


def set_current_agent_runtime(db: Session, runtime_code: str) -> dict[str, Any]:
    settings = db.scalars(
        select(AgentReviewSettings)
        .where(AgentReviewSettings.id == 1)
        .with_for_update()
    ).first()
    if settings is None:
        settings = get_agent_settings_record(db)
    runtime = _get_agent_runtime(db, runtime_code, lock=True)
    if not runtime.enabled:
        raise AppError(
            "AGENT_RUNTIME_DISABLED",
            f"Disabled Agent Runtime cannot be selected: {runtime.runtime_code}",
            409,
        )
    worker_pool = agent_worker_pool(db)
    _assert_runtime_protocol_available(
        runtime.protocol,
        worker_pool,
        require_worker=True,
    )
    _assert_runtime_configuration_complete(runtime)
    settings.selected_runtime_code = runtime.runtime_code
    settings.runtime_type = (
        runtime.runtime_code
        if runtime.runtime_code in RUNTIME_TYPES
        else DEFAULT_RUNTIME
    )
    _sync_runtime_to_legacy_settings(settings, runtime)
    settings.updated_at = utc_now()
    db.flush()
    return {
        "selectedRuntimeCode": runtime.runtime_code,
        "runtime": _agent_runtime_response(
            runtime,
            settings=settings,
            worker_pool=worker_pool,
        ),
    }


def selected_agent_runtime_record(db: Session) -> AgentReviewRuntime:
    settings = get_agent_settings_record(db)
    runtime_code = str(settings.selected_runtime_code or "").strip().upper()
    runtime = db.get(AgentReviewRuntime, runtime_code)
    if runtime is None:
        runtime = db.get(AgentReviewRuntime, normalize_runtime_type(settings.runtime_type))
    if runtime is None:
        raise AppError("AGENT_RUNTIME_NOT_FOUND", "Selected Agent Runtime no longer exists", 409)
    return runtime


def selected_agent_runtime_snapshot(db: Session) -> dict[str, Any]:
    return runtime_record_snapshot(selected_agent_runtime_record(db))


def delete_agent_runtime(db: Session, runtime_code: str) -> dict[str, Any]:
    settings = db.scalars(
        select(AgentReviewSettings)
        .where(AgentReviewSettings.id == 1)
        .with_for_update()
    ).first()
    if settings is None:
        settings = get_agent_settings_record(db)
    runtime = _get_agent_runtime(db, runtime_code, lock=True)
    if runtime.built_in:
        raise AppError(
            "AGENT_RUNTIME_BUILT_IN",
            f"Built-in Agent Runtime cannot be deleted: {runtime.runtime_code}",
            409,
        )
    if settings.selected_runtime_code == runtime.runtime_code:
        raise AppError(
            "AGENT_RUNTIME_IS_CURRENT",
            f"Current Agent Runtime cannot be deleted: {runtime.runtime_code}",
            409,
        )
    if str(runtime.test_status or "").upper() in {"QUEUED", "RUNNING"}:
        raise AppError(
            "AGENT_RUNTIME_TEST_ACTIVE",
            f"Agent Runtime has an active configuration test: {runtime.runtime_code}",
            409,
        )
    if _active_agent_run_references_runtime(db, runtime.runtime_code):
        raise AppError(
            "AGENT_RUNTIME_IN_USE",
            f"Agent Runtime is referenced by an active task: {runtime.runtime_code}",
            409,
        )
    if runtime.runtime_code == CUSTOM_RUNTIME:
        settings.custom_display_name = None
        settings.custom_base_url = None
        settings.custom_model = None
        settings.custom_reasoning_effort = None
        settings.custom_tls_verify = True
        settings.custom_api_key_ciphertext = None
        settings.custom_api_key_fingerprint = None
    db.delete(runtime)
    db.flush()
    return {"runtimeCode": runtime.runtime_code, "deleted": True}


def _get_agent_runtime(
    db: Session,
    runtime_code: str,
    *,
    lock: bool = False,
) -> AgentReviewRuntime:
    normalized = _normalize_runtime_code(runtime_code)
    statement = select(AgentReviewRuntime).where(
        AgentReviewRuntime.runtime_code == normalized
    )
    if lock:
        statement = statement.with_for_update()
    runtime = db.scalars(statement).first()
    if runtime is None:
        raise AppError(
            "RESOURCE_NOT_FOUND",
            f"Agent Runtime not found: {normalized}",
            404,
        )
    return runtime


def _normalize_runtime_code(value: Any) -> str:
    runtime_code = str(value or "").strip().upper()
    if not _RUNTIME_CODE.fullmatch(runtime_code):
        raise AppError("VALIDATION_ERROR", "runtimeCode is invalid", 400)
    return runtime_code


def _generated_runtime_code(db: Session, vendor_code: str) -> str:
    vendor = re.sub(r"[^A-Z0-9]+", "_", vendor_code.strip().upper()).strip("_")
    prefix = f"AGENT_{vendor or 'CUSTOM'}"[:27].rstrip("_")
    for _attempt in range(10):
        runtime_code = f"{prefix}_{uuid4().hex[:12].upper()}"
        if db.get(AgentReviewRuntime, runtime_code) is None:
            return runtime_code
    raise AppError(
        "AGENT_RUNTIME_ID_GENERATION_FAILED",
        "Unable to allocate a unique Agent Runtime identifier",
        409,
    )


def _generated_runtime_display_name(
    db: Session,
    vendor_name: str,
    model_name: str,
) -> str:
    base_name = f"{vendor_name.strip()} · {model_name.strip()}"
    existing_names = set(
        db.scalars(select(AgentReviewRuntime.display_name).with_for_update()).all()
    )
    first_candidate = base_name[:64]
    if first_candidate not in existing_names:
        return first_candidate
    index = 2
    while index <= 10_000:
        suffix = f"（{index}）"
        candidate = f"{base_name[:64 - len(suffix)]}{suffix}"
        if candidate not in existing_names:
            return candidate
        index += 1
    raise AppError(
        "AGENT_RUNTIME_NAME_GENERATION_FAILED",
        "Unable to allocate a unique Agent Runtime display name",
        409,
    )


def _protocol_runner(protocol: str) -> str:
    runner = _PROTOCOL_RUNNERS.get(protocol)
    if runner is None:
        raise AppError("VALIDATION_ERROR", f"Unsupported Agent Runtime protocol: {protocol}", 400)
    return runner


def _assert_runtime_protocol_available(
    protocol: str,
    worker_pool: dict[str, Any],
    *,
    require_worker: bool,
) -> None:
    if protocol not in _OPEN_AGENT_RUNTIME_PROTOCOLS:
        raise AppError(
            "AGENT_RUNTIME_PROTOCOL_UNAVAILABLE",
            f"Agent Runtime protocol is not open: {protocol}",
            409,
        )
    if require_worker and not _worker_pool_supports(
        worker_pool, _protocol_runner(protocol)
    ):
        runner_type = _protocol_runner(protocol)
        raise AppError(
            "AGENT_RUNTIME_RUNNER_UNAVAILABLE",
            f"No online Worker supports {runner_type}",
            409,
        )


def _assert_runtime_configuration_complete(runtime: AgentReviewRuntime) -> None:
    safe_url = custom_base_url_host(runtime.base_url) is not None
    if not (
        runtime.base_url
        and runtime.model_name
        and runtime.api_key_ciphertext
        and safe_url
    ):
        raise AppError(
            "AGENT_RUNTIME_CONFIGURATION_INCOMPLETE",
            f"Agent Runtime configuration is incomplete: {runtime.runtime_code}",
            409,
        )


def _runtime_protocol_availability(
    runtime: AgentReviewRuntime,
    worker_pool: dict[str, Any],
) -> tuple[bool, str | None]:
    if runtime.runner_type == "CLAUDE_CODE":
        supported = _worker_pool_supports(worker_pool, runtime.runner_type)
        return supported, None if supported else "No online Worker supports CLAUDE_CODE"
    if runtime.protocol not in _OPEN_AGENT_RUNTIME_PROTOCOLS:
        return False, f"Protocol {runtime.protocol} is not open"
    supported = _worker_pool_supports(worker_pool, runtime.runner_type)
    return (
        supported,
        None if supported else f"No online Worker supports {runtime.runner_type}",
    )


def _agent_runtime_response(
    runtime: AgentReviewRuntime,
    *,
    settings: AgentReviewSettings,
    worker_pool: dict[str, Any],
) -> dict[str, Any]:
    available, unavailable_reason = _runtime_protocol_availability(runtime, worker_pool)
    response = agent_runtime_record_response(runtime)
    response.update(
        {
            "selected": settings.selected_runtime_code == runtime.runtime_code,
            "protocolAvailable": available,
            "unavailableReason": unavailable_reason,
            "configurationComplete": bool(
                runtime.base_url
                and runtime.model_name
                and runtime.api_key_ciphertext
                and custom_base_url_host(runtime.base_url) is not None
            ),
            "configurationTest": {
                "requestId": runtime.test_request_id,
                "status": runtime.test_status or "NOT_RUN",
                "message": runtime.test_message,
                "durationMs": runtime.test_duration_ms,
                "startedAt": format_datetime(runtime.test_started_at),
                "finishedAt": format_datetime(runtime.test_finished_at),
            },
        }
    )
    return response


def _runtime_configuration_test_response(runtime: AgentReviewRuntime) -> dict[str, Any]:
    return {
        "runtimeCode": runtime.runtime_code,
        "requestId": runtime.test_request_id,
        "status": runtime.test_status or "NOT_RUN",
        "message": runtime.test_message,
        "durationMs": runtime.test_duration_ms,
        "startedAt": format_datetime(runtime.test_started_at),
        "finishedAt": format_datetime(runtime.test_finished_at),
        "protocol": runtime.protocol,
        "runnerType": runtime.runner_type,
        "model": runtime.model_name,
    }


def _sync_runtime_test_to_legacy_settings(
    settings: AgentReviewSettings,
    runtime: AgentReviewRuntime,
) -> None:
    settings.test_request_id = runtime.test_request_id
    settings.test_status = runtime.test_status
    settings.test_message = runtime.test_message
    settings.test_duration_ms = runtime.test_duration_ms
    settings.test_started_at = runtime.test_started_at
    settings.test_finished_at = runtime.test_finished_at
    settings.updated_at = utc_now()


def _fail_active_runtime_configuration_test(
    runtime: AgentReviewRuntime,
    message: str,
) -> bool:
    if str(runtime.test_status or "").upper() not in {"QUEUED", "RUNNING"}:
        return False
    now = utc_now()
    runtime.test_status = "FAILED"
    runtime.test_message = _bounded(message, 512)
    runtime.test_duration_ms = None
    runtime.test_finished_at = now
    runtime.updated_at = now
    return True


def _expire_runtime_configuration_tests(db: Session) -> int:
    now = utc_now()
    cutoff = now - timedelta(seconds=CONFIGURATION_TEST_TIMEOUT_SECONDS)
    runtimes = db.scalars(
        select(AgentReviewRuntime).where(
            AgentReviewRuntime.test_status.in_(["QUEUED", "RUNNING"])
        )
    ).all()
    settings = get_agent_settings_record(db)
    expired = 0
    for runtime in runtimes:
        reference = (
            runtime.test_started_at
            if runtime.test_status == "RUNNING"
            else runtime.updated_at
        )
        if reference is None or reference > cutoff:
            continue
        if _fail_active_runtime_configuration_test(
            runtime,
            "Agent Runtime configuration test timed out",
        ):
            expired += 1
            if settings.selected_runtime_code == runtime.runtime_code:
                _sync_runtime_test_to_legacy_settings(settings, runtime)
    if expired:
        db.flush()
    return expired


def _sync_runtime_to_legacy_settings(
    settings: AgentReviewSettings,
    runtime: AgentReviewRuntime,
) -> None:
    if runtime.runtime_code == DEFAULT_RUNTIME:
        settings.api_key_ciphertext = runtime.api_key_ciphertext
        settings.api_key_fingerprint = runtime.api_key_fingerprint
    elif runtime.runtime_code == CUSTOM_RUNTIME:
        settings.custom_display_name = runtime.display_name
        settings.custom_base_url = runtime.base_url
        settings.custom_model = runtime.model_name
        settings.custom_reasoning_effort = runtime.reasoning_effort
        settings.custom_tls_verify = runtime.tls_verify is not False
        settings.custom_api_key_ciphertext = runtime.api_key_ciphertext
        settings.custom_api_key_fingerprint = runtime.api_key_fingerprint
    settings.updated_at = utc_now()


def _active_agent_run_references_runtime(db: Session, runtime_code: str) -> bool:
    runs = db.scalars(
        select(AgentReviewRun)
        .where(AgentReviewRun.status.in_(["PENDING", "RUNNING"]))
        .with_for_update()
    ).all()
    for run in runs:
        payload = _read_json(run.input_json, {})
        snapshot = payload.get("runtimeSnapshot") if isinstance(payload, dict) else None
        if not isinstance(snapshot, dict):
            continue
        referenced = str(
            snapshot.get("runtimeCode") or snapshot.get("runtimeType") or ""
        ).strip().upper()
        if referenced == runtime_code:
            return True
    return False


def _legacy_custom_configuration_exists(settings: AgentReviewSettings) -> bool:
    return any(
        value not in {None, ""}
        for value in (
            settings.custom_display_name,
            settings.custom_base_url,
            settings.custom_model,
            settings.custom_reasoning_effort,
            settings.custom_api_key_ciphertext,
            settings.custom_api_key_fingerprint,
        )
    )


def _compatible_selected_runtime_code(settings: AgentReviewSettings) -> str:
    selected = str(settings.selected_runtime_code or "").strip().upper()
    if selected in RUNTIME_TYPES:
        return selected
    return normalize_runtime_type(settings.runtime_type)


def _legacy_runtime_record(
    settings: AgentReviewSettings,
    runtime_code: str,
) -> AgentReviewRuntime:
    now = utc_now()
    selected = _compatible_selected_runtime_code(settings)
    test_fields = {
        "test_request_id": settings.test_request_id if selected == runtime_code else None,
        "test_status": settings.test_status if selected == runtime_code else None,
        "test_message": settings.test_message if selected == runtime_code else None,
        "test_duration_ms": settings.test_duration_ms if selected == runtime_code else None,
        "test_started_at": settings.test_started_at if selected == runtime_code else None,
        "test_finished_at": settings.test_finished_at if selected == runtime_code else None,
    }
    if runtime_code == CUSTOM_RUNTIME:
        return AgentReviewRuntime(
            runtime_code=CUSTOM_RUNTIME,
            display_name=settings.custom_display_name or CUSTOM_DEFAULT_DISPLAY_NAME,
            protocol="OPENAI_RESPONSES",
            runner_type="OPENAI_RESPONSES_AGENT",
            base_url=settings.custom_base_url,
            model_name=settings.custom_model or CUSTOM_DEFAULT_MODEL,
            reasoning_effort=settings.custom_reasoning_effort or "high",
            tls_verify=settings.custom_tls_verify is not False,
            enabled=True,
            built_in=False,
            sort_order=20,
            api_key_ciphertext=settings.custom_api_key_ciphertext,
            api_key_fingerprint=settings.custom_api_key_fingerprint,
            created_at=now,
            updated_at=now,
            **test_fields,
        )
    return AgentReviewRuntime(
        runtime_code=DEFAULT_RUNTIME,
        display_name="Claude Code + DeepSeek",
        protocol="ANTHROPIC_COMPATIBLE",
        runner_type="CLAUDE_CODE",
        base_url=AGENT_ENDPOINT,
        model_name=AGENT_MODEL,
        reasoning_effort="high",
        tls_verify=True,
        enabled=True,
        built_in=True,
        sort_order=10,
        api_key_ciphertext=settings.api_key_ciphertext,
        api_key_fingerprint=settings.api_key_fingerprint,
        created_at=now,
        updated_at=now,
        **test_fields,
    )


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
    try:
        queue_metrics = agent_queue_metrics(
            db,
            worker_pool=worker_pool,
            legacy_heartbeat=record.last_worker_heartbeat_at,
        )
    except Exception:
        # 运行指标是旁路观测；聚合失败不得改变 Agent 可用性、任务状态或 fallback。
        _LOGGER.warning("Agent queue metrics unavailable; returning safe fallback")
        queue_metrics = _empty_agent_queue_metrics(
            worker_pool,
            legacy_heartbeat=record.last_worker_heartbeat_at,
        )
    budgets, budget_source = effective_agent_budgets(record)
    selected_runtime = normalize_runtime_type(record.runtime_type)
    custom_url_safe = custom_base_url_host(record.custom_base_url) is not None
    custom_api_key_configured = bool(record.custom_api_key_ciphertext)
    custom_configuration_complete = bool(
        record.custom_base_url
        and record.custom_model
        and record.custom_reasoning_effort
        and custom_api_key_configured
        and custom_url_safe
    )
    selected_is_custom = selected_runtime == CUSTOM_RUNTIME
    selected_key_configured = (
        custom_api_key_configured if selected_is_custom else bool(record.api_key_ciphertext)
    )
    selected_key_masked = (
        mask_fingerprint(record.custom_api_key_fingerprint)
        if selected_is_custom
        else mask_fingerprint(record.api_key_fingerprint)
    )
    selected_model = (
        str(record.custom_model or CUSTOM_DEFAULT_MODEL) if selected_is_custom else AGENT_MODEL
    )
    selected_endpoint = (
        f"{str(record.custom_base_url or '').rstrip('/')}/responses"
        if selected_is_custom and record.custom_base_url
        else AGENT_ENDPOINT
    )
    return {
        "enabled": bool(record.enabled),
        "selectedRuntime": selected_runtime,
        "runtimeOptions": [
            {"value": DEFAULT_RUNTIME, "label": "Claude Code + DeepSeek", "isDefault": True},
            {
                "value": CUSTOM_RUNTIME,
                "label": "自定义 OpenAI Responses Agent",
                "isDefault": False,
            },
        ],
        "runner": "OPENAI_RESPONSES_AGENT" if selected_is_custom else "CLAUDE_CODE",
        "cliVersion": None if selected_is_custom else AGENT_CLI_VERSION,
        "provider": "CUSTOM_OPENAI" if selected_is_custom else "DEEPSEEK",
        "endpoint": selected_endpoint,
        "model": selected_model,
        "apiKeyConfigured": selected_key_configured,
        "apiKeyMasked": selected_key_masked,
        "defaultRuntime": {
            "runtimeType": DEFAULT_RUNTIME,
            "provider": "DEEPSEEK",
            "model": AGENT_MODEL,
            "endpoint": AGENT_ENDPOINT,
            "apiKeyConfigured": bool(record.api_key_ciphertext),
            "apiKeyMasked": mask_fingerprint(record.api_key_fingerprint),
        },
        "customRuntime": {
            "runtimeType": CUSTOM_RUNTIME,
            "protocol": "OPENAI_RESPONSES",
            "displayName": record.custom_display_name or CUSTOM_DEFAULT_DISPLAY_NAME,
            "baseUrl": record.custom_base_url,
            "model": record.custom_model or CUSTOM_DEFAULT_MODEL,
            "reasoningEffort": record.custom_reasoning_effort or "high",
            "tlsVerify": record.custom_tls_verify is not False,
            "reasoningEffortOptions": list(CUSTOM_REASONING_EFFORTS),
            "apiKeyConfigured": custom_api_key_configured,
            "apiKeyMasked": mask_fingerprint(record.custom_api_key_fingerprint),
            "egressAllowed": custom_url_safe,
            "urlSafetyValidated": custom_url_safe,
            "configurationComplete": custom_configuration_complete,
            "workerSupported": _worker_pool_supports(worker_pool, CUSTOM_RUNTIME),
        },
        "encryptionAvailable": encryption_available(),
        "workerStatus": "ONLINE" if online else "OFFLINE",
        "workerId": record.worker_id,
        "workerVersion": record.worker_version,
        "lastWorkerHeartbeatAt": (
            worker_pool.get("lastHeartbeatAt")
            or _safe_format_worker_time(record.last_worker_heartbeat_at)
        ),
        "workerPool": worker_pool,
        "queueMetrics": queue_metrics,
        "configurationTest": {
            "requestId": record.test_request_id,
            "status": record.test_status or "NOT_RUN",
            "message": record.test_message,
            "durationMs": record.test_duration_ms,
            "startedAt": format_datetime(record.test_started_at),
            "finishedAt": format_datetime(record.test_finished_at),
            "runtimeType": selected_runtime,
            "protocol": "OPENAI_RESPONSES" if selected_is_custom else "ANTHROPIC_COMPATIBLE",
            "model": selected_model,
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

    selected_runtime_requested = "selectedRuntime" in request
    next_runtime = normalize_runtime_type(
        request.get("selectedRuntime", record.runtime_type), strict=True
    )
    next_selected_runtime_code = (
        next_runtime
        if selected_runtime_requested
        else str(record.selected_runtime_code or next_runtime).strip().upper()
    )
    custom_request = request.get("customRuntime")
    if custom_request is not None and not isinstance(custom_request, dict):
        raise AppError("VALIDATION_ERROR", "customRuntime must be an object", 400)
    custom_request = custom_request or {}
    if "displayName" in custom_request:
        display_name = str(custom_request.get("displayName") or "").strip()
        if len(display_name) > 64:
            raise AppError("VALIDATION_ERROR", "customRuntime.displayName is too long", 400)
        record.custom_display_name = display_name or CUSTOM_DEFAULT_DISPLAY_NAME
    if "baseUrl" in custom_request:
        raw_base_url = str(custom_request.get("baseUrl") or "").strip()
        record.custom_base_url = (
            normalize_custom_base_url(raw_base_url) if raw_base_url else None
        )
    if "model" in custom_request:
        model = str(custom_request.get("model") or "").strip()
        if len(model) > 128:
            raise AppError("VALIDATION_ERROR", "customRuntime.model is invalid", 400)
        record.custom_model = model or None
    if "reasoningEffort" in custom_request:
        effort = str(custom_request.get("reasoningEffort") or "").strip().lower()
        if effort not in CUSTOM_REASONING_EFFORTS:
            raise AppError("VALIDATION_ERROR", "customRuntime.reasoningEffort is invalid", 400)
        record.custom_reasoning_effort = effort
    if "tlsVerify" in custom_request:
        tls_verify = custom_request.get("tlsVerify")
        if not isinstance(tls_verify, bool):
            raise AppError("VALIDATION_ERROR", "customRuntime.tlsVerify must be a boolean", 400)
        record.custom_tls_verify = tls_verify
    if custom_request.get("clearApiKey") is True:
        record.custom_api_key_ciphertext = None
        record.custom_api_key_fingerprint = None
        if next_runtime == CUSTOM_RUNTIME:
            record.enabled = False
    elif "apiKey" in custom_request:
        if custom_request.get("apiKey") is None:
            pass
        else:
            ciphertext, fingerprint = encrypt_api_key(str(custom_request.get("apiKey") or ""))
            record.custom_api_key_ciphertext = ciphertext
            record.custom_api_key_fingerprint = fingerprint

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
            if next_selected_runtime_code not in RUNTIME_TYPES:
                _assert_selected_runtime_ready(db, next_selected_runtime_code, require_worker=True)
            else:
                _assert_runtime_ready(
                    db, record, next_runtime, require_worker=next_runtime == CUSTOM_RUNTIME
                )
        record.enabled = enabled
    elif (
        record.enabled
        and selected_runtime_requested
        and next_runtime != normalize_runtime_type(record.runtime_type)
    ):
        _assert_runtime_ready(db, record, next_runtime, require_worker=next_runtime == CUSTOM_RUNTIME)
    record.runtime_type = next_runtime
    record.selected_runtime_code = next_selected_runtime_code
    record.budget_config_json = next_budget_json
    record.updated_at = utc_now()
    sync_legacy_agent_runtime_records(db, record)
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
    capabilities: list[str],
    responses_runner_version: str | None,
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
    worker.capabilities_json = json.dumps(
        normalize_worker_capabilities(capabilities), ensure_ascii=False
    )
    worker.responses_runner_version = _bounded(responses_runner_version, 64)
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
    online_capacity = 0
    for worker in workers:
        state = (
            worker.state
            if worker.state in {"IDLE", "BUSY", "DRAINING"}
            else "IDLE"
        )
        capacity = 1
        is_online = _worker_time_is_online(worker.last_heartbeat_at, cutoff)
        if is_online:
            online_count += 1
            total_capacity += capacity
            if state == "BUSY":
                busy_count += 1
                online_capacity += capacity
            elif state == "DRAINING":
                draining_count += 1
            else:
                idle_count += 1
                online_capacity += capacity
        nodes.append(
            {
                "workerId": worker.worker_id,
                "workerVersion": worker.worker_version,
                "cliVersion": worker.cli_version,
                "capabilities": normalize_worker_capabilities(worker.capabilities_json),
                "responsesRunnerVersion": worker.responses_runner_version,
                "state": state,
                "capacity": capacity,
                "activeJobId": worker.active_job_id,
                "activeRunId": worker.active_run_id,
                "startedAt": _safe_format_worker_time(worker.started_at),
                "lastHeartbeatAt": _safe_format_worker_time(
                    worker.last_heartbeat_at
                ),
                "online": is_online,
            }
        )
    busy_capacity = busy_count
    return {
        "status": "ONLINE" if online_count > 0 else "OFFLINE",
        "onlineCount": online_count,
        "busyCount": busy_count,
        "idleCount": idle_count,
        "drainingCount": draining_count,
        "totalCapacity": total_capacity,
        "onlineCapacity": online_capacity,
        "busyCapacity": busy_capacity,
        "utilizationPercent": _utilization_percent(
            busy_capacity,
            online_capacity,
        ),
        "totalCount": len(workers),
        "lastHeartbeatAt": (
            _safe_format_worker_time(workers[0].last_heartbeat_at)
            if workers
            else None
        ),
        "nodes": nodes,
    }


def cleanup_stale_agent_workers(db: Session, *, now=None) -> int:
    cutoff = (now or utc_now()) - timedelta(hours=AGENT_WORKER_RETENTION_HOURS)
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
        "onlineCapacity": 1,
        "busyCapacity": 0,
        "utilizationPercent": 0,
        "totalCount": 1,
        "lastHeartbeatAt": _safe_format_worker_time(
            record.last_worker_heartbeat_at
        ),
        "nodes": [
            {
                "workerId": record.worker_id,
                "workerVersion": record.worker_version,
                "cliVersion": record.cli_version,
                "capabilities": [DEFAULT_RUNTIME],
                "responsesRunnerVersion": None,
                "state": "IDLE",
                "capacity": 1,
                "activeJobId": None,
                "activeRunId": None,
                "startedAt": None,
                "lastHeartbeatAt": _safe_format_worker_time(
                    record.last_worker_heartbeat_at
                ),
                "online": True,
            }
        ],
    }


def agent_queue_metrics(
    db: Session,
    *,
    worker_pool: dict[str, Any],
    legacy_heartbeat: object | None = None,
    now=None,
) -> dict[str, Any]:
    ensure_agent_review_schema(db)
    current = now or utc_now()
    row = db.execute(
        select(
            func.sum(
                case(
                    (CodeQualitySchedulerJob.status == "QUEUED", 1),
                    else_=0,
                )
            ).label("queued"),
            func.sum(
                case(
                    (CodeQualitySchedulerJob.status == "RUNNING", 1),
                    else_=0,
                )
            ).label("running"),
            func.sum(
                case(
                    (
                        (CodeQualitySchedulerJob.status == "RUNNING")
                        & (CodeQualitySchedulerJob.lease_expires_at < current),
                        1,
                    ),
                    else_=0,
                )
            ).label("expired_lease"),
            func.min(
                case(
                    (
                        CodeQualitySchedulerJob.status == "QUEUED",
                        CodeQualitySchedulerJob.queued_at,
                    ),
                    else_=None,
                )
            ).label("oldest_queued_at"),
        )
        .where(CodeQualitySchedulerJob.job_type == "AGENT_REVIEW")
        .where(CodeQualitySchedulerJob.status.in_(["QUEUED", "RUNNING"]))
    ).one()
    oldest_queued_seconds = 0
    if row.oldest_queued_at is not None:
        try:
            oldest_queued_seconds = max(
                int((current - row.oldest_queued_at).total_seconds()),
                0,
            )
        except (AttributeError, OverflowError, TypeError, ValueError):
            oldest_queued_seconds = 0
    capacity = _queue_capacity_metrics(
        worker_pool,
        legacy_heartbeat=legacy_heartbeat,
    )
    return {
        "queued": _non_negative(row.queued),
        "running": _non_negative(row.running),
        "expiredLease": _non_negative(row.expired_lease),
        "oldestQueuedSeconds": oldest_queued_seconds,
        **capacity,
    }


def worker_accepts_claim(db: Session, *, worker_id: str) -> bool:
    """Reject a registered draining process while keeping legacy callers compatible."""
    ensure_agent_review_schema(db)
    worker = db.get(AgentReviewWorker, worker_id)
    return worker is None or str(worker.state or "").upper() != "DRAINING"


def assert_agent_available(db: Session, *, require_worker: bool = True) -> AgentReviewSettings:
    record = get_agent_settings_record(db)
    if not record.enabled:
        raise AppError("AGENT_REVIEW_UNAVAILABLE", "Agent Review is disabled", 409)
    runtime = selected_agent_runtime_record(db)
    _assert_selected_runtime_ready(db, runtime.runtime_code, require_worker=False)
    worker_pool = agent_worker_pool(db)
    legacy_online = worker_pool["totalCount"] == 0 and _worker_online(record)
    runtime_online = _worker_pool_supports(worker_pool, runtime.runner_type)
    if require_worker and not (
        runtime_online or (runtime.runtime_code == DEFAULT_RUNTIME and legacy_online)
    ):
        raise AppError("AGENT_REVIEW_UNAVAILABLE", "Agent Review Worker is offline", 409)
    return record


def request_configuration_test(db: Session) -> dict[str, Any]:
    record = assert_agent_available(db, require_worker=True)
    runtime = selected_agent_runtime_record(db)
    response = request_runtime_configuration_test(db, runtime.runtime_code)
    _sync_runtime_test_to_legacy_settings(record, runtime)
    db.commit()
    return {**response, "runtimeType": normalize_runtime_type(record.runtime_type)}


def request_runtime_configuration_test(
    db: Session,
    runtime_code: str,
) -> dict[str, Any]:
    _expire_runtime_configuration_tests(db)
    runtime = _get_agent_runtime(db, runtime_code, lock=True)
    if str(runtime.test_status or "").upper() in {"QUEUED", "RUNNING"}:
        raise AppError(
            "AGENT_RUNTIME_TEST_ACTIVE",
            f"Agent Runtime already has an active configuration test: {runtime.runtime_code}",
            409,
        )
    _assert_selected_runtime_ready(db, runtime.runtime_code, require_worker=True)
    now = utc_now()
    runtime.test_request_id = f"runtime-test:{runtime.runtime_code}:{uuid4().hex}"
    runtime.test_status = "QUEUED"
    runtime.test_message = None
    runtime.test_duration_ms = None
    runtime.test_started_at = None
    runtime.test_finished_at = None
    runtime.updated_at = now
    settings = get_agent_settings_record(db)
    if settings.selected_runtime_code == runtime.runtime_code:
        _sync_runtime_test_to_legacy_settings(settings, runtime)
    db.flush()
    return _runtime_configuration_test_response(runtime)


def claim_configuration_test(db: Session, *, worker_id: str) -> dict[str, Any] | None:
    ensure_agent_review_schema(db)
    _expire_runtime_configuration_tests(db)
    worker = db.get(AgentReviewWorker, worker_id)
    capabilities = normalize_worker_capabilities(
        worker.capabilities_json if worker is not None else None
    )
    supported_runners = [
        runner
        for runner in (
            "CLAUDE_CODE",
            "OPENAI_RESPONSES_AGENT",
            "OPENAI_CHAT_AGENT",
            "ANTHROPIC_MESSAGES_AGENT",
        )
        if worker_supports(capabilities, runner)
    ]
    statement = (
        select(AgentReviewRuntime)
        .where(AgentReviewRuntime.test_status == "QUEUED")
        .where(AgentReviewRuntime.enabled.is_(True))
        .where(AgentReviewRuntime.runner_type.in_(supported_runners))
        .order_by(AgentReviewRuntime.updated_at.asc(), AgentReviewRuntime.runtime_code.asc())
        .limit(1)
    )
    if _supports_skip_locked(db):
        statement = statement.with_for_update(skip_locked=True)
    else:
        statement = statement.with_for_update()
    runtime = db.scalars(statement).first()
    if runtime is None or not runtime.test_request_id:
        return None
    now = utc_now()
    runtime.test_status = "RUNNING"
    runtime.test_started_at = now
    runtime.test_finished_at = None
    runtime.test_message = None
    runtime.updated_at = now
    settings = get_agent_settings_record(db)
    if settings.selected_runtime_code == runtime.runtime_code:
        _sync_runtime_test_to_legacy_settings(settings, runtime)
    db.commit()
    snapshot = runtime_record_snapshot(runtime)
    api_key = _decrypt_runtime_code_api_key(db, settings, runtime.runtime_code)
    return {
        "kind": "CONFIG_TEST",
        "requestId": runtime.test_request_id,
        "runtime": {
            **snapshot,
            "apiKey": api_key,
        },
        "apiKey": api_key,
        "budgets": {
            "maxTurns": 6,
            "maxToolCalls": 10,
            "maxSourceBytes": 10_000,
            "timeoutSeconds": CONFIGURATION_TEST_TIMEOUT_SECONDS,
            "inlineDiffBytes": 10_000,
            "maxEvidenceCalls": 4,
            "convergeAtCalls": 2,
            "submitByTurn": 3,
        },
    }


def complete_configuration_test(
    db: Session, *, request_id: str, status: str, message: str | None, duration_ms: int | None
) -> dict[str, Any]:
    runtime = db.scalars(
        select(AgentReviewRuntime)
        .where(AgentReviewRuntime.test_request_id == request_id)
        .with_for_update()
    ).first()
    if runtime is None:
        raise AppError("AGENT_CONFIG_TEST_STALE", "Agent configuration test request is stale", 409)
    if runtime.test_status in {"SUCCESS", "FAILED"}:
        return _runtime_configuration_test_response(runtime)
    if runtime.test_status != "RUNNING":
        raise AppError("AGENT_CONFIG_TEST_STALE", "Agent configuration test request is stale", 409)
    normalized = str(status or "FAILED").upper()
    runtime.test_status = "SUCCESS" if normalized == "SUCCESS" else "FAILED"
    runtime.test_message = _bounded(message, 512)
    runtime.test_duration_ms = _non_negative(duration_ms)
    runtime.test_finished_at = utc_now()
    runtime.updated_at = utc_now()
    settings = get_agent_settings_record(db)
    if settings.selected_runtime_code == runtime.runtime_code:
        _sync_runtime_test_to_legacy_settings(settings, runtime)
    db.commit()
    return _runtime_configuration_test_response(runtime)


def create_agent_job(
    db: Session,
    *,
    task_id: int,
    project_id: int,
    input_payload: dict[str, Any],
    completion_context: dict[str, Any] | None,
    comparison_mode: bool,
    runtime: dict[str, Any] | None = None,
) -> AgentReviewRun:
    ensure_agent_review_schema(db)
    now = utc_now()
    idempotency_key = f"agent:{task_id}:{uuid4().hex}"
    snapshot = runtime or selected_agent_runtime_snapshot(db)
    runtime_code = str(
        snapshot.get("runtimeCode") or snapshot.get("runtimeType") or DEFAULT_RUNTIME
    ).strip().upper()
    runner_type = str(snapshot.get("runnerType") or "").strip().upper()
    review_key = runtime_review_key(runtime_code)
    custom = runtime_code != DEFAULT_RUNTIME
    model = str(snapshot.get("model") or (CUSTOM_DEFAULT_MODEL if custom else AGENT_MODEL))
    input_payload = {**input_payload, "runtimeSnapshot": snapshot}
    normalized_completion_context = normalize_completion_context(
        completion_context,
        task_id=task_id,
    )
    job = CodeQualitySchedulerJob(
        job_type="AGENT_REVIEW",
        task_id=task_id,
        review_key=review_key,
        project_id=project_id,
        status="QUEUED",
        priority=80,
        label=(
            f"Agent Review - {snapshot.get('displayName') or CUSTOM_DEFAULT_DISPLAY_NAME}"
            if custom
            else "Agent Review - Claude Code + DeepSeek"
        ),
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
        review_key=review_key,
        scheduler_job_id=job.id,
        idempotency_key=idempotency_key,
        requested_engine="AGENT",
        effective_engine=None,
        runner_version=(
            RESPONSES_RUNNER_VERSION
            if runner_type == "OPENAI_RESPONSES_AGENT"
            else CHAT_COMPLETIONS_RUNNER_VERSION
            if runner_type == "OPENAI_CHAT_AGENT"
            else ANTHROPIC_MESSAGES_RUNNER_VERSION
            if runner_type == "ANTHROPIC_MESSAGES_AGENT"
            else AGENT_RUNNER_VERSION
        ),
        runner_type=runner_type or ("OPENAI_RESPONSES_AGENT" if custom else "CLAUDE_CODE"),
        provider=runtime_provider(snapshot),
        model=model,
        status="PENDING",
        input_json=json.dumps(input_payload, ensure_ascii=False),
        completion_context_json=json.dumps(
            normalized_completion_context,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        comparison_mode=bool(comparison_mode),
        created_at=now,
        updated_at=now,
    )
    db.add(run)
    db.flush()
    return run


def normalize_completion_context(
    completion_context: dict[str, Any] | None,
    *,
    task_id: int | None = None,
) -> dict[str, Any]:
    source = completion_context if isinstance(completion_context, dict) else {}
    truncated_fields: list[str] = []
    focus_change_types, change_types_truncated = _bounded_completion_context_list(
        source.get("focusChangeTypes"),
        max_items=32,
    )
    focus_rule_codes, rule_codes_truncated = _bounded_completion_context_list(
        source.get("focusRuleCodes"),
        max_items=64,
    )
    if change_types_truncated:
        truncated_fields.append("focusChangeTypes")
    if rule_codes_truncated:
        truncated_fields.append("focusRuleCodes")

    notification_source = source.get("notificationContext")
    notification_context: dict[str, str] = {}
    notification_truncated = False
    if isinstance(notification_source, dict):
        for key in _COMPLETION_CONTEXT_NOTIFICATION_KEYS:
            raw_value = notification_source.get(key)
            if raw_value is None:
                continue
            if not isinstance(raw_value, str):
                notification_truncated = True
                continue
            value = raw_value.strip()
            if len(value) > 512:
                value = value[:512]
                notification_truncated = True
            if value:
                notification_context[key] = value
    elif notification_source is not None:
        notification_truncated = True
    if notification_truncated:
        truncated_fields.append("notificationContext")

    raw_result_id = source.get("ruleResultId")
    rule_result_id = (
        raw_result_id
        if isinstance(raw_result_id, int)
        and not isinstance(raw_result_id, bool)
        and raw_result_id > 0
        else None
    )
    context = {
        "schemaVersion": AGENT_COMPLETION_CONTEXT_SCHEMA_VERSION,
        "autoNotification": (
            source.get("autoNotification")
            if isinstance(source.get("autoNotification"), bool)
            else False
        ),
        "ruleResultId": rule_result_id,
        "focusChangeTypes": focus_change_types,
        "focusRuleCodes": focus_rule_codes,
        "notificationContext": notification_context,
        "reminderCardEnabled": (
            source.get("reminderCardEnabled")
            if isinstance(source.get("reminderCardEnabled"), bool)
            else True
        ),
    }
    serialized_bytes = len(
        json.dumps(context, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    if serialized_bytes > AGENT_COMPLETION_CONTEXT_MAX_BYTES:
        _LOGGER.warning(
            "Agent completion context truncated code=AGENT_COMPLETION_CONTEXT_TRUNCATED "
            "taskId=%s serializedBytes=%s maxBytes=%s",
            task_id,
            serialized_bytes,
            AGENT_COMPLETION_CONTEXT_MAX_BYTES,
        )
        return {
            "schemaVersion": AGENT_COMPLETION_CONTEXT_SCHEMA_VERSION,
            "autoNotification": False,
            "ruleResultId": rule_result_id,
            "reminderCardEnabled": context["reminderCardEnabled"],
        }
    if truncated_fields:
        _LOGGER.warning(
            "Agent completion context fields truncated taskId=%s fields=%s serializedBytes=%s",
            task_id,
            ",".join(truncated_fields),
            serialized_bytes,
        )
    return context


def _bounded_completion_context_list(
    value: Any,
    *,
    max_items: int,
) -> tuple[list[str], bool]:
    if value is None:
        return [], False
    if not isinstance(value, list):
        return [], True
    normalized: list[str] = []
    seen: set[str] = set()
    truncated = len(value) > max_items
    for raw_item in value:
        if len(normalized) >= max_items:
            break
        if not isinstance(raw_item, str):
            truncated = True
            continue
        item = raw_item.strip()
        if len(item) > 64:
            item = item[:64]
            truncated = True
        if not item or item in seen:
            if not item:
                truncated = True
            continue
        seen.add(item)
        normalized.append(item)
    return normalized, truncated


def claim_agent_job(db: Session, *, worker_id: str) -> dict[str, Any] | None:
    # 已入队任务使用自己的不可变快照；全局开关只控制新任务，不阻断旧任务进入
    # 凭据解析或稳定 fallback。
    settings_record = get_agent_settings_record(db)
    ensure_agent_review_schema(db)
    now = utc_now()
    worker = db.get(AgentReviewWorker, worker_id)
    capabilities = normalize_worker_capabilities(
        worker.capabilities_json if worker is not None else None
    )
    allowed_runner_types = [
        runner
        for runner in (
            "CLAUDE_CODE",
            "OPENAI_RESPONSES_AGENT",
            "OPENAI_CHAT_AGENT",
            "ANTHROPIC_MESSAGES_AGENT",
        )
        if worker_supports(capabilities, runner)
    ]
    stmt = (
        select(CodeQualitySchedulerJob)
        .join(AgentReviewRun, AgentReviewRun.scheduler_job_id == CodeQualitySchedulerJob.id)
        .where(CodeQualitySchedulerJob.job_type == "AGENT_REVIEW")
        .where(AgentReviewRun.runner_type.in_(allowed_runner_types))
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
    snapshot = input_payload.get("runtimeSnapshot")
    if not isinstance(snapshot, dict):
        snapshot = runtime_snapshot(object())
    runtime_code = str(
        snapshot.get("runtimeCode") or snapshot.get("runtimeType") or DEFAULT_RUNTIME
    ).strip().upper()
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
    try:
        api_key = _decrypt_runtime_code_api_key(db, settings_record, runtime_code)
    except AppError as exception:
        _fail_unclaimable_runtime_job(job, run, exception.code, exception.message, now)
        db.commit()
        return {"_fallbackRunId": run.id}
    db.commit()
    return {
        "jobId": job.id,
        "runId": run.id,
        "idempotencyKey": run.idempotency_key,
        "taskId": run.task_id,
        "reviewKey": run.review_key,
        "worktree": input_payload.get("worktree"),
        "input": input_payload.get("case") or {},
        "apiKey": api_key,
        "runtime": {**snapshot, "apiKey": api_key},
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
        "runnerType": run.runner_type or "CLAUDE_CODE",
        "provider": run.provider or "DEEPSEEK",
        "cliVersion": (
            run.cli_version or AGENT_CLI_VERSION
            if (run.runner_type or "CLAUDE_CODE") == "CLAUDE_CODE"
            else None
        ),
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
        if tool == "submit_review":
            event["attempt"] = _limited_non_negative(raw_event.get("attempt"), 3)
            event["maxAttempts"] = 3
            event["violations"] = _safe_schema_failures(
                raw_event.get("violations")
            )
            event["violationCount"] = _limited_non_negative(
                raw_event.get("violationCount"), 50
            )
            event["violationsTruncated"] = bool(
                raw_event.get("violationsTruncated")
            )
        events.append(event)
    events.sort(key=lambda item: item["sequence"])
    phase = str(source.get("phase") or "ANALYZING").upper()
    if phase not in {"ANALYZING", "TOOL_ACTIVITY", "CONVERGING", "SUBMITTING"}:
        phase = "ANALYZING"
    submit_attempt_count = _limited_non_negative(source.get("submitAttemptCount"), 3)
    schema_failure_count = _limited_non_negative(source.get("schemaFailureCount"), 3)
    output_repair_exhausted = bool(source.get("outputRepairExhausted"))
    output_termination_requested = bool(source.get("outputTerminationRequested"))
    failure_chain: list[dict[str, Any]] = []
    if schema_failure_count:
        failure_chain.append(
            {"code": "REVIEW_SCHEMA_INVALID", "count": schema_failure_count}
        )
    if output_repair_exhausted:
        failure_chain.append(
            {"code": "AGENT_REVIEW_SCHEMA_RETRY_EXHAUSTED", "count": 1}
        )
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
        "submitAttemptCount": submit_attempt_count,
        "schemaFailureCount": schema_failure_count,
        "lastSchemaFailures": _safe_schema_failures(
            source.get("lastSchemaFailures")
        ),
        "outputRepairExhausted": output_repair_exhausted,
        "outputTerminationRequested": output_termination_requested,
        "failureChain": failure_chain,
        "reviewBudget": _safe_review_budget(source.get("reviewBudget")),
        "topPathSummaries": _safe_path_summaries(source.get("topPathSummaries"), 20),
        "events": events,
    }


def _safe_schema_failures(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    allowed_reasons = {
        "REQUIRED",
        "TYPE",
        "ENUM",
        "UNSAFE_PATH",
        "PATH_OUTSIDE_CHANGED_FILES",
        "LINE_RANGE",
        "LENGTH",
        "CARD_SHAPE",
    }
    failures: list[dict[str, str]] = []
    for raw in value[:5]:
        if not isinstance(raw, dict):
            continue
        reason_code = str(raw.get("reasonCode") or "")
        field = str(raw.get("field") or "")[:120]
        if reason_code not in allowed_reasons or not re.fullmatch(
            r"\$|[A-Za-z][A-Za-z0-9]*(?:\[\d+\]|\.[A-Za-z][A-Za-z0-9]*)*",
            field,
        ):
            continue
        failures.append({"reasonCode": reason_code, "field": field})
    return failures


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


def _worker_pool_supports(worker_pool: dict[str, Any], runtime_type: str) -> bool:
    nodes = worker_pool.get("nodes") if isinstance(worker_pool, dict) else None
    if not isinstance(nodes, list):
        return False
    return any(
        isinstance(node, dict)
        and node.get("online") is True
        and str(node.get("state") or "IDLE").upper() != "DRAINING"
        and worker_supports(node.get("capabilities"), runtime_type)
        for node in nodes
    )


def _decrypt_runtime_api_key(record: AgentReviewSettings, runtime_type: str) -> str:
    if normalize_runtime_type(runtime_type) == CUSTOM_RUNTIME:
        return decrypt_api_key(record.custom_api_key_ciphertext)
    return decrypt_api_key(record.api_key_ciphertext)


def _decrypt_runtime_code_api_key(
    db: Session,
    settings: AgentReviewSettings,
    runtime_code: str,
) -> str:
    normalized = str(runtime_code or DEFAULT_RUNTIME).strip().upper()
    if normalized in RUNTIME_TYPES:
        runtime = db.get(AgentReviewRuntime, normalized)
        if runtime is None:
            return _decrypt_runtime_api_key(settings, normalized)
    else:
        runtime = db.get(AgentReviewRuntime, normalized)
    if runtime is None:
        raise AppError(
            "AGENT_RUNTIME_NOT_FOUND",
            f"Agent Runtime no longer exists: {normalized}",
            409,
        )
    if not runtime.enabled:
        raise AppError(
            "AGENT_RUNTIME_DISABLED",
            f"Agent Runtime is disabled: {normalized}",
            409,
        )
    try:
        return decrypt_api_key(runtime.api_key_ciphertext)
    except AppError as exception:
        raise AppError(
            "AGENT_RUNTIME_CREDENTIAL_UNAVAILABLE",
            f"Agent Runtime credential is unavailable: {normalized}",
            409,
        ) from exception


def _assert_selected_runtime_ready(
    db: Session,
    runtime_code: str,
    *,
    require_worker: bool,
) -> None:
    runtime = _get_agent_runtime(db, runtime_code)
    if not runtime.enabled:
        raise AppError("AGENT_RUNTIME_DISABLED", f"Agent Runtime is disabled: {runtime.runtime_code}", 409)
    if runtime.runtime_code == DEFAULT_RUNTIME:
        _assert_runtime_ready(
            db,
            get_agent_settings_record(db),
            DEFAULT_RUNTIME,
            require_worker=require_worker,
        )
        return
    _assert_runtime_protocol_available(
        runtime.protocol,
        agent_worker_pool(db),
        require_worker=require_worker,
    )
    _assert_runtime_configuration_complete(runtime)
    _decrypt_runtime_code_api_key(db, get_agent_settings_record(db), runtime.runtime_code)


def _fail_unclaimable_runtime_job(
    job: CodeQualitySchedulerJob,
    run: AgentReviewRun,
    failure_code: str,
    failure_message: str,
    now: datetime,
) -> None:
    message = _bounded(failure_message, 512)
    job.status = "FAILED"
    job.error_message = failure_code
    job.finished_at = now
    job.updated_at = now
    run.status = "FAILED"
    run.effective_engine = "STANDARD_FALLBACK"
    run.failure_code = _bounded(failure_code, 64)
    run.failure_message = message
    run.finished_at = now
    run.updated_at = now


def _assert_runtime_ready(
    db: Session,
    record: AgentReviewSettings,
    runtime_type: str,
    *,
    require_worker: bool,
) -> None:
    normalized = normalize_runtime_type(runtime_type)
    _decrypt_runtime_api_key(record, normalized)
    if normalized == CUSTOM_RUNTIME:
        if not record.custom_base_url or not record.custom_model:
            raise AppError(
                "AGENT_CUSTOM_CONFIG_INCOMPLETE",
                "自定义 OpenAI Responses Agent 配置不完整",
                409,
            )
        normalize_custom_base_url(record.custom_base_url)
        if str(record.custom_reasoning_effort or "high") not in CUSTOM_REASONING_EFFORTS:
            raise AppError(
                "AGENT_CUSTOM_CONFIG_INCOMPLETE",
                "自定义 OpenAI Responses Agent 推理强度无效",
                409,
            )
        if require_worker and not _worker_pool_supports(
            agent_worker_pool(db), CUSTOM_RUNTIME
        ):
            raise AppError(
                "AGENT_REVIEW_UNAVAILABLE",
                "没有支持自定义 Responses Agent 的在线 Worker",
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
    selected_runtime_missing = "selected_runtime_code" not in columns
    definitions = {
        "runtime_type": "VARCHAR(32) NOT NULL DEFAULT 'CLAUDE_CODE_DEEPSEEK'",
        "selected_runtime_code": "VARCHAR(40) NOT NULL DEFAULT 'CLAUDE_CODE_DEEPSEEK'",
        "custom_display_name": "VARCHAR(64) NULL",
        "custom_base_url": "VARCHAR(1024) NULL",
        "custom_model": "VARCHAR(128) NULL",
        "custom_reasoning_effort": "VARCHAR(16) NULL",
        "custom_tls_verify": "BOOLEAN NOT NULL DEFAULT TRUE",
        "custom_api_key_ciphertext": "TEXT NULL",
        "custom_api_key_fingerprint": "VARCHAR(32) NULL",
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
    if selected_runtime_missing:
        db.execute(
            text(
                "UPDATE code_quality_agent_settings "
                "SET selected_runtime_code = CASE "
                "WHEN runtime_type = 'OPENAI_RESPONSES_CUSTOM' "
                "THEN 'OPENAI_RESPONSES_CUSTOM' "
                "ELSE 'CLAUDE_CODE_DEEPSEEK' END"
            )
        )
        db.flush()


def _ensure_worker_columns(db: Session, inspector) -> None:
    columns = {
        column["name"]
        for column in inspector.get_columns("code_quality_agent_workers")
    }
    definitions = {
        "worker_version": "VARCHAR(64) NULL",
        "cli_version": "VARCHAR(64) NULL",
        "capabilities_json": "TEXT NULL",
        "responses_runner_version": "VARCHAR(64) NULL",
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


def _ensure_run_columns(db: Session, inspector) -> None:
    columns = {column["name"] for column in inspector.get_columns("agent_review_runs")}
    definitions = {
        "runner_type": "VARCHAR(32) NOT NULL DEFAULT 'CLAUDE_CODE'",
        "provider": "VARCHAR(32) NOT NULL DEFAULT 'DEEPSEEK'",
    }
    for name, definition in definitions.items():
        _add_column(db, columns, "agent_review_runs", name, definition)


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
    return _worker_time_is_online(
        record.last_worker_heartbeat_at,
        utc_now() - timedelta(seconds=AGENT_WORKER_ONLINE_SECONDS),
    )


def _worker_time_is_online(value: Any, cutoff: datetime) -> bool:
    try:
        return isinstance(value, datetime) and value >= cutoff
    except (OverflowError, TypeError, ValueError):
        return False


def _safe_format_worker_time(value: Any) -> str | None:
    return format_datetime(value) if isinstance(value, datetime) else None


def _empty_agent_queue_metrics(
    worker_pool: dict[str, Any],
    *,
    legacy_heartbeat: object | None,
) -> dict[str, Any]:
    return {
        "queued": 0,
        "running": 0,
        "expiredLease": 0,
        "oldestQueuedSeconds": 0,
        **_queue_capacity_metrics(
            worker_pool,
            legacy_heartbeat=legacy_heartbeat,
        ),
    }


def _queue_capacity_metrics(
    worker_pool: dict[str, Any],
    *,
    legacy_heartbeat: object | None,
) -> dict[str, Any]:
    online_capacity = _non_negative(worker_pool.get("onlineCapacity"))
    busy_capacity = min(
        _non_negative(worker_pool.get("busyCapacity")),
        online_capacity,
    )
    return {
        "onlineCapacity": online_capacity,
        "busyCapacity": busy_capacity,
        "utilizationPercent": _utilization_percent(
            busy_capacity,
            online_capacity,
        ),
        "drainingWorkers": _non_negative(worker_pool.get("drainingCount")),
        "lastWorkerHeartbeatAt": (
            worker_pool.get("lastHeartbeatAt")
            or _safe_format_worker_time(legacy_heartbeat)
        ),
    }


def _utilization_percent(busy_capacity: Any, online_capacity: Any) -> int:
    online = _non_negative(online_capacity)
    if online <= 0:
        return 0
    busy = min(_non_negative(busy_capacity), online)
    return min(max((busy * 100 + online // 2) // online, 0), 100)


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
