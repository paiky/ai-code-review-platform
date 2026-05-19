from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import inspect, select, text, update
from sqlalchemy.orm import Session

from app.code_quality.models import (
    CodeQualityModelProvider,
    CodeQualityReviewProfile,
    CodeQualityReviewProgressEvent,
    CodeQualityReviewResult,
    CodeQualityReviewSettings,
)
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.json_utils import format_datetime, page_response, read_json_array


DEFAULT_PROFILE_CODE = "backend-default-ai-review"
DEFAULT_REVIEW_INSTRUCTIONS = """你是资深后端代码质量审核助手。只审查用户提供的 diff，必须返回严格 JSON，不要 Markdown。
JSON 字段名和枚举值保持英文；summary、title、body、suggestion 必须使用简体中文。

审查原则：
1. 只审查本次 diff 新增或修改引入的问题，不报告历史存量问题。
2. 只报告会影响线上正确性、数据一致性、安全、事务边界、SQL 性能、缓存一致性、MQ 一致性、异常处理或关键测试覆盖的问题。
3. 不报告纯代码风格、命名偏好、格式、注释、主观重构或没有明确线上影响的建议。
4. 不要猜测 diff 外部代码、调用方行为或未提供的配置；缺少证据时不要报告，除非潜在影响很高且必须人工确认。
5. 每个 finding 都必须说明：为什么它由本次变更引入、具体触发条件、潜在影响、建议修复方式。

重点检查：
- 正确性：条件分支、边界值、空值、状态流转、幂等、重复提交、并发竞争。
- 事务与一致性：多表写入、远程调用、消息/缓存副作用、异常回滚、部分成功。
- SQL 与数据访问：索引命中、慢查询、分页、批量操作、更新/删除条件、N+1、结果兼容。
- 缓存：key 兼容、TTL、失效路径、数据库与缓存写入顺序、降级与旧数据清理。
- MQ：发送时机、事务一致性、重复消费、顺序、重试、死信、消息结构兼容。
- 安全：鉴权、越权、输入校验、注入、敏感信息泄露、日志暴露。
- 异常与观测：异常吞掉、错误码误导、补偿缺失、关键日志和监控缺口。
- 测试缺口：当本次变更涉及核心业务分支、数据一致性或高风险边界时，指出缺少的关键测试。"""

LEGACY_DEFAULT_REVIEW_INSTRUCTIONS = {
    "Only report actionable correctness, data consistency, security, transaction, SQL performance, cache consistency, MQ consistency, exception handling, and test gap issues. Do not report style-only issues.",
    "Only report actionable code quality issues.",
    "只审查本次变更中会导致线上缺陷、数据不一致、安全风险、事务问题、SQL 性能问题、缓存一致性问题、MQ 一致性问题、异常处理缺口、测试缺口的代码质量问题。不要报告纯风格问题。请使用简体中文输出，每个问题以“高风险：”“中风险：”或“低风险：”开头，并尽量标明文件和行号。",
    "只报告可执行的正确性、数据一致性、安全、事务、SQL 性能、缓存一致性、MQ 一致性、异常处理和关键测试缺口问题。不要报告纯代码风格问题。",
    "只报告会影响线上正确性、数据一致性、安全、事务边界、SQL 性能、缓存一致性、MQ 一致性、异常处理或测试覆盖的问题。\n不报告纯代码风格、命名偏好、无明确影响的重构建议。\n每个问题都要说明触发条件、潜在影响和建议修复方式。",
}


def ensure_defaults(db: Session) -> None:
    ensure_code_quality_config_schema(db)
    settings = get_settings()
    if db.get(CodeQualityReviewSettings, 1) is None:
        db.add(
            CodeQualityReviewSettings(
                id=1,
                mr_auto_review_enabled=True,
                dingtalk_notification_enabled=True,
                review_provider=settings.code_quality_review_provider,
                default_provider_code=_provider_code(settings.code_quality_review_provider),
                openai_api_key=None,
                anthropic_api_key=None,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
        )

    _upsert_default_provider(
        db,
        "OPENAI",
        "OpenAI",
        "OPENAI_RESPONSES",
        settings.openai_responses_url,
        settings.openai_code_review_model,
        settings.openai_api_key,
        True,
        10,
    )
    _upsert_default_provider(
        db,
        "ANTHROPIC",
        "Anthropic / Claude",
        "ANTHROPIC_MESSAGES",
        settings.anthropic_messages_url,
        settings.anthropic_code_review_model,
        settings.anthropic_api_key,
        True,
        20,
    )
    _upsert_default_provider(
        db,
        "DEEPSEEK",
        "DeepSeek",
        "OPENAI_CHAT_COMPATIBLE",
        settings.deepseek_base_url,
        settings.deepseek_code_review_model,
        settings.deepseek_api_key,
        True,
        30,
    )
    _upsert_default_provider(db, "CUSTOM", "自定义 OpenAI-compatible", "OPENAI_CHAT_COMPATIBLE", None, None, None, False, 40)

    profile = find_profile_by_code(db, DEFAULT_PROFILE_CODE, ensure=False)
    if profile is None:
        db.add(
            CodeQualityReviewProfile(
                profile_code=DEFAULT_PROFILE_CODE,
                profile_name="Backend default AI code review",
                enabled=True,
                provider="OPENAI_API",
                provider_code=None,
                model=None,
                trigger_on_manual=True,
                trigger_on_mr=True,
                trigger_on_push=False,
                severity_threshold="MAJOR",
                block_on_severities=json.dumps(["CRITICAL"], ensure_ascii=False),
                enabled_categories=json.dumps(
                    [
                        "CORRECTNESS",
                        "SECURITY",
                        "TRANSACTION",
                        "SQL_PERFORMANCE",
                        "CACHE_CONSISTENCY",
                        "MQ_CONSISTENCY",
                        "EXCEPTION_HANDLING",
                        "TEST_GAP",
                    ],
                    ensure_ascii=False,
                ),
                ignored_paths=json.dumps(["**/generated/**", "**/target/**", "**/dist/**"], ensure_ascii=False),
                push_branch_patterns=json.dumps(["main", "develop", "release/*"], ensure_ascii=False),
                push_max_changed_files=30,
                push_max_diff_bytes=200000,
                push_debounce_seconds=300,
                trigger_only_when_risk_matched=True,
                codex_prompt=DEFAULT_REVIEW_INSTRUCTIONS,
                openai_instructions=DEFAULT_REVIEW_INSTRUCTIONS,
                review_instructions=DEFAULT_REVIEW_INSTRUCTIONS,
                status="ENABLED",
                description="Default backend AI code quality review profile.",
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
        )
    elif (profile.review_instructions or "").strip() in LEGACY_DEFAULT_REVIEW_INSTRUCTIONS:
        profile.review_instructions = DEFAULT_REVIEW_INSTRUCTIONS
        profile.openai_instructions = DEFAULT_REVIEW_INSTRUCTIONS
        profile.codex_prompt = DEFAULT_REVIEW_INSTRUCTIONS
        profile.updated_at = datetime.now()
    db.flush()


def ensure_code_quality_config_schema(db: Session) -> None:
    ensure_settings_schema(db)
    ensure_profile_schema(db)
    ensure_provider_schema(db)


def ensure_settings_schema(db: Session) -> None:
    connection = db.connection()
    inspector = inspect(connection)
    if not inspector.has_table("code_quality_review_settings"):
        CodeQualityReviewSettings.__table__.create(connection, checkfirst=True)
        return
    columns = {column["name"] for column in inspector.get_columns("code_quality_review_settings")}
    _add_column_if_missing(
        db,
        columns,
        "code_quality_review_settings",
        "dingtalk_notification_enabled",
        "BOOLEAN NOT NULL DEFAULT TRUE",
    )
    _add_column_if_missing(
        db,
        columns,
        "code_quality_review_settings",
        "review_provider",
        "VARCHAR(32) NOT NULL DEFAULT 'DEEPSEEK'",
    )
    _add_column_if_missing(
        db,
        columns,
        "code_quality_review_settings",
        "default_provider_code",
        "VARCHAR(64) NOT NULL DEFAULT 'DEEPSEEK'",
    )
    _add_column_if_missing(
        db,
        columns,
        "code_quality_review_settings",
        "openai_api_key",
        "VARCHAR(1024) NULL",
    )
    _add_column_if_missing(
        db,
        columns,
        "code_quality_review_settings",
        "anthropic_api_key",
        "VARCHAR(1024) NULL",
    )
    db.flush()


def ensure_profile_schema(db: Session) -> None:
    connection = db.connection()
    inspector = inspect(connection)
    if not inspector.has_table("code_quality_review_profiles"):
        CodeQualityReviewProfile.__table__.create(connection, checkfirst=True)
        return
    columns = {column["name"] for column in inspector.get_columns("code_quality_review_profiles")}
    _add_column_if_missing(
        db,
        columns,
        "code_quality_review_profiles",
        "provider_code",
        "VARCHAR(64) NULL",
    )
    _add_column_if_missing(
        db,
        columns,
        "code_quality_review_profiles",
        "review_instructions",
        "TEXT NULL",
    )
    db.flush()


def ensure_provider_schema(db: Session) -> None:
    connection = db.connection()
    inspector = inspect(connection)
    if not inspector.has_table("code_quality_model_providers"):
        CodeQualityModelProvider.__table__.create(connection, checkfirst=True)
        db.flush()
    db.flush()


def _add_column_if_missing(
    db: Session,
    columns: set[str],
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    if column_name in columns:
        return
    db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"))
    columns.add(column_name)
    db.flush()


def _upsert_default_provider(
    db: Session,
    provider_code: str,
    provider_name: str,
    provider_type: str,
    endpoint_url: str | None,
    model_name: str | None,
    api_key: str | None,
    enabled: bool,
    sort_order: int,
) -> None:
    provider = db.scalars(
        select(CodeQualityModelProvider).where(CodeQualityModelProvider.provider_code == provider_code)
    ).first()
    if provider is None:
        db.add(
            CodeQualityModelProvider(
                provider_code=provider_code,
                provider_name=provider_name,
                provider_type=provider_type,
                endpoint_url=_blank_to_none(endpoint_url),
                model_name=_blank_to_none(model_name),
                api_key=_blank_to_none(api_key),
                enabled=enabled,
                built_in=True,
                sort_order=sort_order,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
        )
        return
    provider.provider_name = provider_name
    provider.provider_type = provider_type
    provider.endpoint_url = provider.endpoint_url or _blank_to_none(endpoint_url)
    provider.model_name = provider.model_name or _blank_to_none(model_name)
    provider.api_key = provider.api_key or _blank_to_none(api_key)
    provider.built_in = True
    provider.sort_order = sort_order


def get_settings_record(db: Session) -> CodeQualityReviewSettings:
    ensure_defaults(db)
    record = db.get(CodeQualityReviewSettings, 1)
    if record is None:
        raise AppError("INTERNAL_ERROR", "Code quality review settings are unavailable", 500)
    return record


def settings_to_dict(record: CodeQualityReviewSettings) -> dict[str, Any]:
    return {
        "mrAutoReviewEnabled": record.mr_auto_review_enabled,
        "dingtalkNotificationEnabled": record.dingtalk_notification_enabled,
        "reviewProvider": record.default_provider_code or _provider_code(record.review_provider),
        "defaultProviderCode": record.default_provider_code or _provider_code(record.review_provider),
        "updatedAt": format_datetime(record.updated_at),
    }


def update_settings_record(db: Session, request: dict[str, Any]) -> dict[str, Any]:
    record = get_settings_record(db)
    if "mrAutoReviewEnabled" in request:
        record.mr_auto_review_enabled = bool(request["mrAutoReviewEnabled"])
    if "dingtalkNotificationEnabled" in request:
        record.dingtalk_notification_enabled = bool(request["dingtalkNotificationEnabled"])
    default_provider = request.get("defaultProviderCode") or request.get("reviewProvider")
    if default_provider is not None:
        provider = get_provider(db, str(default_provider).upper())
        record.default_provider_code = provider.provider_code
        record.review_provider = provider.provider_code
    record.updated_at = datetime.now()
    db.flush()
    return settings_to_dict(record)


def list_enabled_profiles(db: Session) -> dict[str, Any]:
    ensure_defaults(db)
    profiles = db.scalars(
        select(CodeQualityReviewProfile)
        .where(CodeQualityReviewProfile.enabled.is_(True), CodeQualityReviewProfile.status == "ENABLED")
        .order_by(CodeQualityReviewProfile.id.desc())
    ).all()
    items = [profile_to_dict(profile) for profile in profiles]
    return page_response(items, 1, len(items), len(items))


def find_profile_by_code(
    db: Session, profile_code: str, *, ensure: bool = True
) -> CodeQualityReviewProfile | None:
    if ensure:
        ensure_defaults(db)
    return db.scalars(
        select(CodeQualityReviewProfile).where(CodeQualityReviewProfile.profile_code == profile_code)
    ).first()


def get_profile(db: Session, profile_code: str) -> CodeQualityReviewProfile:
    profile = find_profile_by_code(db, profile_code)
    if profile is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Code quality review profile not found: {profile_code}", 404)
    return profile


def profile_to_dict(profile: CodeQualityReviewProfile) -> dict[str, Any]:
    provider_code = _provider_code(profile.provider_code or profile.provider)
    return {
        "id": profile.id,
        "profileCode": profile.profile_code,
        "profileName": profile.profile_name,
        "enabled": profile.enabled,
        "provider": provider_code,
        "providerCode": profile.provider_code,
        "model": profile.model,
        "triggerOnManual": profile.trigger_on_manual,
        "triggerOnMr": profile.trigger_on_mr,
        "triggerOnPush": profile.trigger_on_push,
        "severityThreshold": profile.severity_threshold,
        "blockOnSeverities": read_json_array(profile.block_on_severities),
        "enabledCategories": read_json_array(profile.enabled_categories),
        "ignoredPaths": read_json_array(profile.ignored_paths),
        "pushBranchPatterns": read_json_array(profile.push_branch_patterns),
        "pushMaxChangedFiles": profile.push_max_changed_files,
        "pushMaxDiffBytes": profile.push_max_diff_bytes,
        "pushDebounceSeconds": profile.push_debounce_seconds,
        "triggerOnlyWhenRiskMatched": profile.trigger_only_when_risk_matched,
        "codexPrompt": profile.codex_prompt,
        "openaiInstructions": profile.openai_instructions,
        "reviewInstructions": profile.review_instructions,
        "status": profile.status,
        "description": profile.description,
        "createdAt": format_datetime(profile.created_at),
        "updatedAt": format_datetime(profile.updated_at),
    }


def update_profile(db: Session, profile_code: str, request: dict[str, Any]) -> dict[str, Any]:
    profile = get_profile(db, profile_code)
    if "profileName" in request:
        profile.profile_name = request["profileName"]
    if "enabled" in request:
        profile.enabled = bool(request["enabled"])
    if "providerCode" in request:
        raw = request["providerCode"]
        profile.provider_code = _provider_code(raw) if raw else None
    if "model" in request:
        profile.model = _blank_to_none(request["model"])
    if "triggerOnManual" in request:
        profile.trigger_on_manual = bool(request["triggerOnManual"])
    if "triggerOnMr" in request:
        profile.trigger_on_mr = bool(request["triggerOnMr"])
    if "triggerOnPush" in request:
        profile.trigger_on_push = bool(request["triggerOnPush"])
    if "severityThreshold" in request:
        profile.severity_threshold = request["severityThreshold"]
    for json_field, column_name in (
        ("blockOnSeverities", "block_on_severities"),
        ("enabledCategories", "enabled_categories"),
        ("ignoredPaths", "ignored_paths"),
        ("pushBranchPatterns", "push_branch_patterns"),
    ):
        if json_field in request:
            setattr(profile, column_name, json.dumps(request[json_field] or [], ensure_ascii=False))
    if "pushMaxChangedFiles" in request:
        profile.push_max_changed_files = request["pushMaxChangedFiles"]
    if "pushMaxDiffBytes" in request:
        profile.push_max_diff_bytes = request["pushMaxDiffBytes"]
    if "pushDebounceSeconds" in request:
        profile.push_debounce_seconds = request["pushDebounceSeconds"]
    if "triggerOnlyWhenRiskMatched" in request:
        profile.trigger_only_when_risk_matched = bool(request["triggerOnlyWhenRiskMatched"])
    if "reviewInstructions" in request:
        profile.review_instructions = request["reviewInstructions"]
        profile.openai_instructions = request["reviewInstructions"]
    profile.updated_at = datetime.now()
    db.flush()
    return profile_to_dict(profile)


def reset_default_prompt(db: Session, profile_code: str) -> dict[str, Any]:
    profile = get_profile(db, profile_code)
    profile.review_instructions = DEFAULT_REVIEW_INSTRUCTIONS
    profile.openai_instructions = DEFAULT_REVIEW_INSTRUCTIONS
    profile.codex_prompt = DEFAULT_REVIEW_INSTRUCTIONS
    profile.updated_at = datetime.now()
    db.flush()
    return profile_to_dict(profile)


def list_provider_responses(db: Session) -> list[dict[str, Any]]:
    settings = get_settings_record(db)
    providers = db.scalars(
        select(CodeQualityModelProvider).order_by(
            CodeQualityModelProvider.sort_order.asc(), CodeQualityModelProvider.id.asc()
        )
    ).all()
    return [
        provider_to_response(provider, settings.default_provider_code)
        for provider in providers
    ]


def get_provider(db: Session, provider_code: str) -> CodeQualityModelProvider:
    ensure_defaults(db)
    provider = db.scalars(
        select(CodeQualityModelProvider).where(CodeQualityModelProvider.provider_code == provider_code.upper())
    ).first()
    if provider is None:
        raise AppError("BAD_REQUEST", f"Model provider not found: {provider_code}", 400)
    return provider


def provider_to_response(
    provider: CodeQualityModelProvider,
    default_provider_code: str,
) -> dict[str, Any]:
    return {
        "providerCode": provider.provider_code,
        "providerName": provider.provider_name,
        "providerType": provider.provider_type,
        "endpointUrl": provider.endpoint_url,
        "modelName": provider.model_name,
        "enabled": provider.enabled,
        "builtIn": provider.built_in,
        "defaultProvider": provider.provider_code == default_provider_code,
        "apiKeyConfigured": bool(provider.api_key),
        "apiKeyMasked": mask_secret(provider.api_key),
        "updatedAt": format_datetime(provider.updated_at),
    }


def update_provider(db: Session, provider_code: str, request: dict[str, Any]) -> list[dict[str, Any]]:
    if not request:
        raise AppError("BAD_REQUEST", "At least one provider setting is required", 400)
    provider = get_provider(db, provider_code)
    values: dict[str, Any] = {}
    if request.get("providerName"):
        values["provider_name"] = str(request["providerName"]).strip()
    if "endpointUrl" in request:
        values["endpoint_url"] = _blank_to_none(request["endpointUrl"])
    if "modelName" in request:
        values["model_name"] = _blank_to_none(request["modelName"])
    if request.get("clearApiKey") is True:
        values["api_key"] = None
    elif "apiKey" in request:
        values["api_key"] = _blank_to_none(request["apiKey"])
    if "enabled" in request:
        values["enabled"] = bool(request["enabled"])
    values["updated_at"] = datetime.now()
    db.execute(
        update(CodeQualityModelProvider)
        .where(CodeQualityModelProvider.provider_code == provider.provider_code)
        .values(**values)
    )
    db.flush()
    db.expire_all()
    return list_provider_responses(db)


def set_default_provider(db: Session, provider_code: str) -> dict[str, Any]:
    provider = get_provider(db, provider_code)
    record = get_settings_record(db)
    record.default_provider_code = provider.provider_code
    record.review_provider = provider.provider_code
    record.updated_at = datetime.now()
    db.flush()
    return settings_to_dict(record)


def save_result(
    db: Session,
    *,
    task_id: int,
    project_id: int,
    profile_code: str,
    provider: str,
    model: str | None,
    result: dict[str, Any],
) -> CodeQualityReviewResult:
    now = datetime.now()
    existing = db.scalars(
        select(CodeQualityReviewResult).where(CodeQualityReviewResult.task_id == task_id)
    ).first()
    if existing is None:
        existing = CodeQualityReviewResult(
            task_id=task_id,
            project_id=project_id,
            profile_code=profile_code,
            provider=provider,
            model=model,
            status=result["status"],
            overall_level=result.get("overallLevel"),
            summary=_truncate(result.get("summary"), 1024),
            finding_count=len(result.get("findings") or []),
            findings_json=json.dumps(result.get("findings") or [], ensure_ascii=False),
            raw_output=result.get("rawOutput"),
            exit_code=result.get("exitCode"),
            error_message=_truncate(result.get("errorMessage"), 1024),
            started_at=result.get("startedAt"),
            finished_at=result.get("finishedAt"),
            created_at=now,
            updated_at=now,
        )
        db.add(existing)
    else:
        existing.project_id = project_id
        existing.profile_code = profile_code
        existing.provider = provider
        existing.model = model
        existing.status = result["status"]
        existing.overall_level = result.get("overallLevel")
        existing.summary = _truncate(result.get("summary"), 1024)
        existing.finding_count = len(result.get("findings") or [])
        existing.findings_json = json.dumps(result.get("findings") or [], ensure_ascii=False)
        existing.raw_output = result.get("rawOutput")
        existing.exit_code = result.get("exitCode")
        existing.error_message = _truncate(result.get("errorMessage"), 1024)
        existing.started_at = result.get("startedAt")
        existing.finished_at = result.get("finishedAt")
        existing.updated_at = now
    db.flush()
    return existing


def find_result_response(db: Session, task_id: int) -> dict[str, Any] | None:
    result = db.scalars(
        select(CodeQualityReviewResult).where(CodeQualityReviewResult.task_id == task_id)
    ).first()
    if result is None:
        return None
    return {
        "taskId": result.task_id,
        "projectId": result.project_id,
        "profileCode": result.profile_code,
        "provider": result.provider,
        "model": result.model,
        "status": result.status,
        "overallLevel": result.overall_level,
        "summary": result.summary,
        "findingCount": result.finding_count,
        "findings": json.loads(result.findings_json or "[]"),
        "rawOutput": result.raw_output,
        "exitCode": result.exit_code,
        "errorMessage": result.error_message,
        "startedAt": format_datetime(result.started_at),
        "finishedAt": format_datetime(result.finished_at),
    }


def append_progress(
    db: Session,
    task_id: int,
    phase: str,
    level: str,
    message: str,
    detail: str | None = None,
) -> None:
    db.add(
        CodeQualityReviewProgressEvent(
            task_id=task_id,
            phase=_truncate(phase, 64) or phase,
            level=_truncate(level, 32) or level,
            message=_truncate(message, 512) or message,
            detail=_truncate(scrub_sensitive(detail), 4000),
            created_at=datetime.now(),
        )
    )
    db.flush()


def delete_progress(db: Session, task_id: int) -> None:
    for event in db.scalars(
        select(CodeQualityReviewProgressEvent).where(CodeQualityReviewProgressEvent.task_id == task_id)
    ).all():
        db.delete(event)
    db.flush()


def list_progress(db: Session, task_id: int) -> list[dict[str, Any]]:
    records = db.scalars(
        select(CodeQualityReviewProgressEvent)
        .where(CodeQualityReviewProgressEvent.task_id == task_id)
        .order_by(CodeQualityReviewProgressEvent.id.asc())
    ).all()
    return [
        {
            "id": record.id,
            "taskId": record.task_id,
            "phase": record.phase,
            "level": record.level,
            "message": record.message,
            "detail": record.detail,
            "createdAt": format_datetime(record.created_at),
        }
        for record in records
    ]


def mark_stale_running_as_failed(db: Session, timeout_seconds: int) -> int:
    cutoff = datetime.now() - timedelta(seconds=max(timeout_seconds, 60))
    records = db.scalars(
        select(CodeQualityReviewResult)
        .where(CodeQualityReviewResult.status == "RUNNING")
        .where(CodeQualityReviewResult.updated_at < cutoff)
    ).all()
    for record in records:
        record.status = "FAILED"
        record.error_message = (
            "AI Review was interrupted or timed out before backend startup. Please retry it manually."
        )
        record.finished_at = datetime.now()
        record.updated_at = datetime.now()
    db.flush()
    return len(records)


def mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    trimmed = value.strip()
    if len(trimmed) <= 8:
        return "****"
    return f"{trimmed[:4]}...{trimmed[-4:]}"


def scrub_sensitive(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value)
    for marker in ("Authorization", "apiKey", "api_key", "token", "secret", "password", "x-api-key"):
        text = _mask_after_marker(text, marker)
    return text


def _mask_after_marker(text: str, marker: str) -> str:
    lower = text.lower()
    marker_lower = marker.lower()
    start = 0
    while True:
        index = lower.find(marker_lower, start)
        if index < 0:
            return text
        colon = text.find(":", index)
        equals = text.find("=", index)
        separator = min([pos for pos in (colon, equals) if pos >= 0], default=-1)
        if separator < 0:
            start = index + len(marker)
            continue
        end = separator + 1
        while end < len(text) and text[end] in " \t'\"":
            end += 1
        value_end = end
        while value_end < len(text) and text[value_end] not in ", \n\r\t'\"}":
            value_end += 1
        text = text[:end] + "****" + text[value_end:]
        lower = text.lower()
        start = end + 4


def _provider_code(value: str | None) -> str:
    normalized = (value or "DEEPSEEK").strip().upper()
    return {
        "OPENAI_API": "OPENAI",
        "ANTHROPIC_API": "ANTHROPIC",
        "CODEX_CLI": "DEEPSEEK",
    }.get(normalized, normalized)


def _blank_to_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _truncate(value: str | None, max_length: int) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= max_length else text[:max_length]
