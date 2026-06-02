from __future__ import annotations

import json
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, inspect, select, text, update
from sqlalchemy.orm import Session

from app.code_quality.models import (
    CodeQualityFixPreview,
    CodeQualityModelProvider,
    CodeQualityPushReviewGateDecision,
    CodeQualityReviewProfile,
    CodeQualityReviewProgressEvent,
    CodeQualityReviewResult,
    CodeQualityReviewSettings,
    CodeQualitySchedulerJob,
)
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.json_utils import format_datetime, page_response, read_json, read_json_array
from app.notification.repository import (
    ensure_webhook_schema,
    list_webhooks,
    upsert_webhooks,
    webhook_to_dict,
)


DEFAULT_PROFILE_CODE = "backend-default-ai-review"
DEFAULT_AUTO_FIX_PREVIEW_SEVERITIES = ["CRITICAL"]
AUTO_FIX_PREVIEW_SEVERITY_OPTIONS = {"CRITICAL", "MAJOR", "MINOR"}
DEFAULT_REVIEW_KEY = "default"
_PROGRESS_REVIEW_KEY: ContextVar[str | None] = ContextVar("code_quality_progress_review_key", default=None)
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

WEB_PC_REVIEW_INSTRUCTIONS = """你是资深 PC Web / H5 代码质量审核助手。只审查用户提供的 diff，必须返回严格 JSON，不要 Markdown。
JSON 字段名和枚举值保持英文；summary、title、body、suggestion 必须使用简体中文。

只报告会影响真实用户体验、线上正确性、安全、权限、接口契约、状态一致性、性能或关键测试覆盖的问题。不要报告纯样式偏好、命名、格式或主观重构建议。

重点检查：
- 组件状态、表单校验、异步请求、加载/空态/错误态。
- 路由、菜单、按钮权限和越权访问。
- API 入参、响应字段、错误码和后端契约兼容。
- 浏览器兼容、可访问性、国际化和时间/金额/枚举展示。
- 大列表、重复渲染、请求风暴、资源体积和缓存策略。
- 核心页面和异常路径的测试缺口。"""

APP_IOS_REVIEW_INSTRUCTIONS = """你是资深 iOS 代码质量审核助手。只审查用户提供的 diff，必须返回严格 JSON，不要 Markdown。
JSON 字段名和枚举值保持英文；summary、title、body、suggestion 必须使用简体中文。

只报告可能导致崩溃、数据错误、安全问题、线上体验退化、兼容性问题或关键测试缺口的问题。不要报告纯风格或主观重构建议。

重点检查：
- ViewController / SwiftUI 生命周期、状态同步和重复触发。
- 主线程阻塞、后台线程 UI 更新、并发竞争。
- 内存泄漏、循环引用、资源释放和大对象持有。
- 权限、隐私、Keychain、日志敏感信息。
- 网络错误、弱网、离线、重试、超时和取消。
- iOS 版本兼容、深链、通知、存储迁移和崩溃风险。"""

APP_ANDROID_REVIEW_INSTRUCTIONS = """你是资深 Android 代码质量审核助手。只审查用户提供的 diff，必须返回严格 JSON，不要 Markdown。
JSON 字段名和枚举值保持英文；summary、title、body、suggestion 必须使用简体中文。

只报告可能导致崩溃、ANR、数据错误、安全问题、兼容性问题、线上体验退化或关键测试缺口的问题。不要报告纯风格或主观重构建议。

重点检查：
- Activity / Fragment / Compose 生命周期、状态恢复和重复订阅。
- 主线程耗时、协程/线程取消、并发竞争和资源泄漏。
- Context 泄漏、注册反注册、观察者和回调释放。
- 权限、隐私、日志敏感信息和本地存储安全。
- 网络错误、弱网、离线、重试、超时和分页边界。
- Android 版本兼容、Gradle 配置、混淆、通知、深链和 ANR 风险。"""

APP_CROSS_PLATFORM_REVIEW_INSTRUCTIONS = """你是资深跨端应用代码质量审核助手。只审查用户提供的 diff，必须返回严格 JSON，不要 Markdown。
JSON 字段名和枚举值保持英文；summary、title、body、suggestion 必须使用简体中文。

只报告可能导致跨端行为不一致、崩溃、数据错误、安全问题、性能退化、打包发布问题或关键测试缺口的问题。不要报告纯风格或主观重构建议。

重点检查：
- Flutter / React Native / 小程序等跨端状态管理和生命周期。
- 平台差异、权限、桥接调用、原生模块返回值和异常处理。
- 网络错误、弱网、离线、缓存、本地存储和同步策略。
- 打包配置、环境变量、资源引用、路由和深链。
- 大列表、重复渲染、图片资源、启动性能和内存占用。
- 核心业务流和端差异的测试缺口。"""

LEGACY_DEFAULT_REVIEW_INSTRUCTIONS = {
    "Only report actionable correctness, data consistency, security, transaction, SQL performance, cache consistency, MQ consistency, exception handling, and test gap issues. Do not report style-only issues.",
    "Only report actionable code quality issues.",
    "只审查本次变更中会导致线上缺陷、数据不一致、安全风险、事务问题、SQL 性能问题、缓存一致性问题、MQ 一致性问题、异常处理缺口、测试缺口的代码质量问题。不要报告纯风格问题。请使用简体中文输出，每个问题以“高风险：”“中风险：”或“低风险：”开头，并尽量标明文件和行号。",
    "只报告可执行的正确性、数据一致性、安全、事务、SQL 性能、缓存一致性、MQ 一致性、异常处理和关键测试缺口问题。不要报告纯代码风格问题。",
    "只报告会影响线上正确性、数据一致性、安全、事务边界、SQL 性能、缓存一致性、MQ 一致性、异常处理或测试覆盖的问题。\n不报告纯代码风格、命名偏好、无明确影响的重构建议。\n每个问题都要说明触发条件、潜在影响和建议修复方式。",
}

DEFAULT_PROFILE_DEFINITIONS = {
    DEFAULT_PROFILE_CODE: {
        "profile_name": "Backend default AI code review",
        "instructions": DEFAULT_REVIEW_INSTRUCTIONS,
        "enabled_categories": [
            "CORRECTNESS",
            "SECURITY",
            "TRANSACTION",
            "SQL_PERFORMANCE",
            "CACHE_CONSISTENCY",
            "MQ_CONSISTENCY",
            "EXCEPTION_HANDLING",
            "TEST_GAP",
        ],
        "ignored_paths": ["**/generated/**", "**/target/**", "**/dist/**"],
        "description": "Default backend AI code quality review profile.",
    },
    "web-pc-default-ai-review": {
        "profile_name": "Web PC default AI code review",
        "instructions": WEB_PC_REVIEW_INSTRUCTIONS,
        "enabled_categories": ["CORRECTNESS", "SECURITY", "PERFORMANCE", "API_CONTRACT", "TEST_GAP"],
        "ignored_paths": ["**/dist/**", "**/node_modules/**", "**/coverage/**", "**/*.snap"],
        "description": "Default PC Web / H5 AI code quality review profile.",
    },
    "app-ios-default-ai-review": {
        "profile_name": "iOS default AI code review",
        "instructions": APP_IOS_REVIEW_INSTRUCTIONS,
        "enabled_categories": ["CORRECTNESS", "SECURITY", "PERFORMANCE", "EXCEPTION_HANDLING", "TEST_GAP"],
        "ignored_paths": ["**/Pods/**", "**/DerivedData/**", "**/*.xcuserstate"],
        "description": "Default iOS AI code quality review profile.",
    },
    "app-android-default-ai-review": {
        "profile_name": "Android default AI code review",
        "instructions": APP_ANDROID_REVIEW_INSTRUCTIONS,
        "enabled_categories": ["CORRECTNESS", "SECURITY", "PERFORMANCE", "EXCEPTION_HANDLING", "TEST_GAP"],
        "ignored_paths": ["**/build/**", "**/.gradle/**", "**/generated/**"],
        "description": "Default Android AI code quality review profile.",
    },
    "app-cross-platform-default-ai-review": {
        "profile_name": "Cross-platform app default AI code review",
        "instructions": APP_CROSS_PLATFORM_REVIEW_INSTRUCTIONS,
        "enabled_categories": ["CORRECTNESS", "SECURITY", "PERFORMANCE", "API_CONTRACT", "TEST_GAP"],
        "ignored_paths": ["**/build/**", "**/dist/**", "**/node_modules/**", "**/.dart_tool/**"],
        "description": "Default cross-platform app AI code quality review profile.",
    },
}


def ensure_defaults(db: Session) -> None:
    ensure_code_quality_config_schema(db)
    settings = get_settings()
    if db.get(CodeQualityReviewSettings, 1) is None:
        db.add(
            CodeQualityReviewSettings(
                id=1,
                review_enabled=settings.code_quality_review_enabled,
                mr_auto_review_enabled=True,
                dingtalk_notification_enabled=True,
                auto_fix_preview_enabled=False,
                auto_fix_preview_severities=json.dumps(
                    DEFAULT_AUTO_FIX_PREVIEW_SEVERITIES, ensure_ascii=False
                ),
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
    _upsert_default_provider(
        db,
        "XIAOMIMO",
        "XiaoMIMO / Xiaomi MiMo",
        "OPENAI_CHAT_COMPATIBLE",
        settings.xiaomimo_base_url,
        settings.xiaomimo_code_review_model,
        settings.xiaomimo_api_key,
        True,
        35,
    )
    _upsert_default_provider(
        db,
        "GLM",
        "智谱 GLM",
        "OPENAI_CHAT_COMPATIBLE",
        settings.glm_base_url,
        settings.glm_code_review_model,
        settings.glm_api_key,
        True,
        37,
    )
    _upsert_default_provider(db, "CUSTOM", "自定义 OpenAI-compatible", "OPENAI_CHAT_COMPATIBLE", None, None, None, False, 40)

    profile = _upsert_built_in_profile(db, DEFAULT_PROFILE_CODE)
    if (profile.review_instructions or "").strip() in LEGACY_DEFAULT_REVIEW_INSTRUCTIONS:
        profile.review_instructions = DEFAULT_REVIEW_INSTRUCTIONS
        profile.openai_instructions = DEFAULT_REVIEW_INSTRUCTIONS
        profile.codex_prompt = DEFAULT_REVIEW_INSTRUCTIONS
        profile.updated_at = datetime.now()
    for profile_code in DEFAULT_PROFILE_DEFINITIONS:
        if profile_code == DEFAULT_PROFILE_CODE:
            continue
        _upsert_built_in_profile(db, profile_code)
    profile.push_branch_patterns = profile.push_branch_patterns or json.dumps(
        ["develop", "feature/*", "bugfix/*", "hotfix/*"], ensure_ascii=False
    )
    profile.push_min_changed_files = profile.push_min_changed_files if profile.push_min_changed_files is not None else 10
    profile.push_min_diff_bytes = profile.push_min_diff_bytes if profile.push_min_diff_bytes is not None else 30000
    profile.push_min_commit_count = profile.push_min_commit_count if profile.push_min_commit_count is not None else 3
    profile.push_max_changed_files = _default_unlimited(profile.push_max_changed_files, 80)
    profile.push_max_diff_bytes = _default_unlimited(profile.push_max_diff_bytes, 300000)
    profile.push_debounce_seconds = profile.push_debounce_seconds if profile.push_debounce_seconds is not None else 300
    db.flush()


def _upsert_built_in_profile(db: Session, profile_code: str) -> CodeQualityReviewProfile:
    definition = _default_profile_definition(profile_code)
    profile = _upsert_default_profile(
        db,
        profile_code,
        definition["profile_name"],
        definition["instructions"],
        definition["enabled_categories"],
        definition["ignored_paths"],
        definition["description"],
    )
    if profile_code != DEFAULT_PROFILE_CODE and _is_backend_prompt(profile.review_instructions):
        profile.review_instructions = definition["instructions"]
        profile.openai_instructions = definition["instructions"]
        profile.codex_prompt = definition["instructions"]
        profile.updated_at = datetime.now()
    return profile


def _default_profile_definition(profile_code: str) -> dict[str, Any]:
    definition = DEFAULT_PROFILE_DEFINITIONS.get(profile_code)
    if definition is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Default profile definition not found: {profile_code}", 404)
    return definition


def _is_backend_prompt(value: str | None) -> bool:
    return (value or "").strip() == DEFAULT_REVIEW_INSTRUCTIONS.strip()


def ensure_code_quality_config_schema(db: Session) -> None:
    ensure_settings_schema(db)
    ensure_profile_schema(db)
    ensure_provider_schema(db)
    ensure_result_schema(db)
    ensure_progress_schema(db)
    ensure_push_gate_schema(db)
    ensure_fix_preview_schema(db)
    ensure_scheduler_job_schema(db)
    ensure_webhook_schema(db)


def ensure_settings_schema(db: Session) -> None:
    connection = db.connection()
    inspector = inspect(connection)
    if not inspector.has_table("code_quality_review_settings"):
        CodeQualityReviewSettings.__table__.create(connection, checkfirst=True)
        return
    columns = {column["name"] for column in inspector.get_columns("code_quality_review_settings")}
    default_review_enabled = "TRUE" if get_settings().code_quality_review_enabled else "FALSE"
    _add_column_if_missing(
        db,
        columns,
        "code_quality_review_settings",
        "review_enabled",
        f"BOOLEAN NOT NULL DEFAULT {default_review_enabled}",
    )
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
        "auto_fix_preview_enabled",
        "BOOLEAN NOT NULL DEFAULT FALSE",
    )
    _add_column_if_missing(
        db,
        columns,
        "code_quality_review_settings",
        "auto_fix_preview_severities",
        "TEXT NULL",
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
    _add_column_if_missing(
        db,
        columns,
        "code_quality_review_profiles",
        "push_min_changed_files",
        "INT NULL DEFAULT 10",
    )
    _add_column_if_missing(
        db,
        columns,
        "code_quality_review_profiles",
        "push_min_diff_bytes",
        "INT NULL DEFAULT 30000",
    )
    _add_column_if_missing(
        db,
        columns,
        "code_quality_review_profiles",
        "push_min_commit_count",
        "INT NULL DEFAULT 3",
    )
    db.flush()


def ensure_provider_schema(db: Session) -> None:
    connection = db.connection()
    inspector = inspect(connection)
    if not inspector.has_table("code_quality_model_providers"):
        CodeQualityModelProvider.__table__.create(connection, checkfirst=True)
        db.flush()
        return
    columns = {column["name"] for column in inspector.get_columns("code_quality_model_providers")}
    _add_column_if_missing(db, columns, "code_quality_model_providers", "timeout_seconds", "INT NULL")
    db.flush()


def ensure_result_schema(db: Session) -> None:
    connection = db.connection()
    inspector = inspect(connection)
    if not inspector.has_table("code_quality_review_results"):
        CodeQualityReviewResult.__table__.create(connection, checkfirst=True)
        db.flush()
        return
    columns = {column["name"] for column in inspector.get_columns("code_quality_review_results")}
    _add_column_if_missing(
        db,
        columns,
        "code_quality_review_results",
        "review_key",
        f"VARCHAR(64) NOT NULL DEFAULT '{DEFAULT_REVIEW_KEY}'",
    )
    _add_column_if_missing(db, columns, "code_quality_review_results", "display_name", "VARCHAR(128) NULL")
    _add_column_if_missing(db, columns, "code_quality_review_results", "sort_order", "INT NOT NULL DEFAULT 0")
    _drop_index_if_exists(db, "code_quality_review_results", "uk_task")
    _add_index_if_missing(
        db,
        "code_quality_review_results",
        "uk_code_quality_result_task_review_key",
        "task_id, review_key",
        unique=True,
    )
    db.flush()


def ensure_progress_schema(db: Session) -> None:
    connection = db.connection()
    inspector = inspect(connection)
    if not inspector.has_table("code_quality_review_progress_events"):
        CodeQualityReviewProgressEvent.__table__.create(connection, checkfirst=True)
        db.flush()
        return
    columns = {column["name"] for column in inspector.get_columns("code_quality_review_progress_events")}
    _add_column_if_missing(db, columns, "code_quality_review_progress_events", "review_key", "VARCHAR(64) NULL")
    db.flush()


def ensure_push_gate_schema(db: Session) -> None:
    connection = db.connection()
    inspector = inspect(connection)
    if not inspector.has_table("code_quality_push_review_gate_decisions"):
        CodeQualityPushReviewGateDecision.__table__.create(connection, checkfirst=True)
        db.flush()
        return
    columns = {column["name"] for column in inspector.get_columns("code_quality_push_review_gate_decisions")}
    _add_column_if_missing(db, columns, "code_quality_push_review_gate_decisions", "project_id", "BIGINT NULL")
    _add_column_if_missing(db, columns, "code_quality_push_review_gate_decisions", "branch_name", "VARCHAR(255) NULL")
    _add_column_if_missing(db, columns, "code_quality_push_review_gate_decisions", "profile_code", "VARCHAR(64) NULL")
    _add_column_if_missing(db, columns, "code_quality_push_review_gate_decisions", "provider", "VARCHAR(64) NULL")
    db.flush()


def ensure_fix_preview_schema(db: Session) -> None:
    connection = db.connection()
    inspector = inspect(connection)
    if not inspector.has_table("code_quality_fix_previews"):
        CodeQualityFixPreview.__table__.create(connection, checkfirst=True)
        db.flush()
        return
    columns = {column["name"] for column in inspector.get_columns("code_quality_fix_previews")}
    _add_column_if_missing(
        db,
        columns,
        "code_quality_fix_previews",
        "review_key",
        f"VARCHAR(64) NOT NULL DEFAULT '{DEFAULT_REVIEW_KEY}'",
    )
    _add_column_if_missing(db, columns, "code_quality_fix_previews", "project_id", "BIGINT NULL")
    _add_column_if_missing(db, columns, "code_quality_fix_previews", "model", "VARCHAR(128) NULL")
    _add_column_if_missing(db, columns, "code_quality_fix_previews", "summary", "VARCHAR(1024) NULL")
    _add_column_if_missing(db, columns, "code_quality_fix_previews", "warnings_json", "TEXT NULL")
    _drop_index_if_exists(db, "code_quality_fix_previews", "uk_code_quality_fix_preview_task_finding")
    _add_index_if_missing(
        db,
        "code_quality_fix_previews",
        "uk_code_quality_fix_preview_task_review_finding",
        "task_id, review_key, finding_index",
        unique=True,
    )
    db.flush()


def ensure_scheduler_job_schema(db: Session) -> None:
    connection = db.connection()
    inspector = inspect(connection)
    if not inspector.has_table("code_quality_scheduler_jobs"):
        CodeQualitySchedulerJob.__table__.create(connection, checkfirst=True)
        _add_index_if_missing(
            db,
            "code_quality_scheduler_jobs",
            "idx_code_quality_scheduler_jobs_status_priority",
            "status, priority, queued_at",
        )
        _add_index_if_missing(
            db,
            "code_quality_scheduler_jobs",
            "idx_code_quality_scheduler_jobs_task",
            "task_id, job_type",
        )
        _add_index_if_missing(
            db,
            "code_quality_scheduler_jobs",
            "idx_code_quality_scheduler_jobs_status_updated",
            "status, updated_at, id",
        )
        _add_index_if_missing(
            db,
            "code_quality_scheduler_jobs",
            "idx_code_quality_scheduler_jobs_status_queue",
            "status, updated_at, queued_at, id",
        )
        db.flush()
        return
    columns = {column["name"] for column in inspector.get_columns("code_quality_scheduler_jobs")}
    _add_column_if_missing(db, columns, "code_quality_scheduler_jobs", "review_key", "VARCHAR(64) NULL")
    _add_column_if_missing(db, columns, "code_quality_scheduler_jobs", "project_id", "BIGINT NULL")
    _add_column_if_missing(db, columns, "code_quality_scheduler_jobs", "finding_index", "INT NULL")
    _add_column_if_missing(db, columns, "code_quality_scheduler_jobs", "label", "VARCHAR(255) NULL")
    _add_column_if_missing(db, columns, "code_quality_scheduler_jobs", "file_path", "VARCHAR(512) NULL")
    _add_column_if_missing(db, columns, "code_quality_scheduler_jobs", "error_message", "VARCHAR(1024) NULL")
    _add_index_if_missing(
        db,
        "code_quality_scheduler_jobs",
        "idx_code_quality_scheduler_jobs_status_priority",
        "status, priority, queued_at",
    )
    _add_index_if_missing(
        db,
        "code_quality_scheduler_jobs",
        "idx_code_quality_scheduler_jobs_task",
        "task_id, job_type",
    )
    _add_index_if_missing(
        db,
        "code_quality_scheduler_jobs",
        "idx_code_quality_scheduler_jobs_status_updated",
        "status, updated_at, id",
    )
    _add_index_if_missing(
        db,
        "code_quality_scheduler_jobs",
        "idx_code_quality_scheduler_jobs_status_queue",
        "status, updated_at, queued_at, id",
    )
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


def _add_index_if_missing(
    db: Session,
    table_name: str,
    index_name: str,
    columns_sql: str,
    *,
    unique: bool = False,
) -> None:
    inspector = inspect(db.connection())
    existing = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name in existing:
        return
    unique_sql = "UNIQUE " if unique else ""
    db.execute(text(f"CREATE {unique_sql}INDEX {index_name} ON {table_name} ({columns_sql})"))
    db.flush()


def _drop_index_if_exists(db: Session, table_name: str, index_name: str) -> None:
    inspector = inspect(db.connection())
    existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    existing_uniques = {constraint["name"] for constraint in inspector.get_unique_constraints(table_name)}
    if index_name not in existing_indexes and index_name not in existing_uniques:
        return
    dialect_name = db.get_bind().dialect.name
    if dialect_name == "mysql":
        db.execute(text(f"ALTER TABLE {table_name} DROP INDEX {index_name}"))
    else:
        db.execute(text(f"DROP INDEX {index_name}"))
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
                timeout_seconds=None,
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


def _upsert_default_profile(
    db: Session,
    profile_code: str,
    profile_name: str,
    instructions: str,
    enabled_categories: list[str],
    ignored_paths: list[str],
    description: str,
) -> CodeQualityReviewProfile:
    profile = find_profile_by_code(db, profile_code, ensure=False)
    now = datetime.now()
    if profile is None:
        profile = CodeQualityReviewProfile(
            profile_code=profile_code,
            profile_name=profile_name,
            enabled=True,
            provider="OPENAI_API",
            provider_code=None,
            model=None,
            trigger_on_manual=True,
            trigger_on_mr=True,
            trigger_on_push=False,
            severity_threshold="MAJOR",
            block_on_severities=json.dumps(["CRITICAL"], ensure_ascii=False),
            enabled_categories=json.dumps(enabled_categories, ensure_ascii=False),
            ignored_paths=json.dumps(ignored_paths, ensure_ascii=False),
            push_branch_patterns=json.dumps(["develop", "feature/*", "bugfix/*", "hotfix/*"], ensure_ascii=False),
            push_min_changed_files=10,
            push_min_diff_bytes=30000,
            push_min_commit_count=3,
            push_max_changed_files=-1,
            push_max_diff_bytes=-1,
            push_debounce_seconds=300,
            trigger_only_when_risk_matched=False,
            codex_prompt=instructions,
            openai_instructions=instructions,
            review_instructions=instructions,
            status="ENABLED",
            description=description,
            created_at=now,
            updated_at=now,
        )
        db.add(profile)
        db.flush()
        return profile
    profile.profile_name = profile.profile_name or profile_name
    profile.enabled_categories = profile.enabled_categories or json.dumps(enabled_categories, ensure_ascii=False)
    profile.ignored_paths = profile.ignored_paths or json.dumps(ignored_paths, ensure_ascii=False)
    profile.push_branch_patterns = profile.push_branch_patterns or json.dumps(["develop", "feature/*", "bugfix/*", "hotfix/*"], ensure_ascii=False)
    profile.push_min_changed_files = profile.push_min_changed_files if profile.push_min_changed_files is not None else 10
    profile.push_min_diff_bytes = profile.push_min_diff_bytes if profile.push_min_diff_bytes is not None else 30000
    profile.push_min_commit_count = profile.push_min_commit_count if profile.push_min_commit_count is not None else 3
    profile.push_max_changed_files = _default_unlimited(profile.push_max_changed_files, 80)
    profile.push_max_diff_bytes = _default_unlimited(profile.push_max_diff_bytes, 300000)
    profile.push_debounce_seconds = profile.push_debounce_seconds if profile.push_debounce_seconds is not None else 300
    if not (profile.review_instructions or "").strip():
        profile.review_instructions = instructions
        profile.openai_instructions = instructions
        profile.codex_prompt = instructions
    profile.description = profile.description or description
    return profile


def get_settings_record(db: Session) -> CodeQualityReviewSettings:
    ensure_defaults(db)
    record = db.get(CodeQualityReviewSettings, 1)
    if record is None:
        raise AppError("INTERNAL_ERROR", "Code quality review settings are unavailable", 500)
    return record


def settings_to_dict(record: CodeQualityReviewSettings) -> dict[str, Any]:
    session = Session.object_session(record)
    return {
        "reviewEnabled": record.review_enabled,
        "mrAutoReviewEnabled": record.mr_auto_review_enabled,
        "dingtalkNotificationEnabled": record.dingtalk_notification_enabled,
        "autoFixPreviewEnabled": record.auto_fix_preview_enabled,
        "autoFixPreviewSeverities": normalize_auto_fix_preview_severities(
            record.auto_fix_preview_severities
        ),
        "dingtalkWebhooks": [webhook_to_dict(item) for item in list_webhooks(session)] if session else [],
        "reviewProvider": record.default_provider_code or _provider_code(record.review_provider),
        "defaultProviderCode": record.default_provider_code or _provider_code(record.review_provider),
        "updatedAt": format_datetime(record.updated_at),
    }


def update_settings_record(db: Session, request: dict[str, Any]) -> dict[str, Any]:
    record = get_settings_record(db)
    if "reviewEnabled" in request:
        record.review_enabled = bool(request["reviewEnabled"])
    if "mrAutoReviewEnabled" in request:
        record.mr_auto_review_enabled = bool(request["mrAutoReviewEnabled"])
    if "dingtalkNotificationEnabled" in request:
        record.dingtalk_notification_enabled = bool(request["dingtalkNotificationEnabled"])
    if "autoFixPreviewEnabled" in request:
        record.auto_fix_preview_enabled = bool(request["autoFixPreviewEnabled"])
    if "autoFixPreviewSeverities" in request:
        record.auto_fix_preview_severities = json.dumps(
            normalize_auto_fix_preview_severities(request["autoFixPreviewSeverities"]),
            ensure_ascii=False,
        )
    if "dingtalkWebhooks" in request:
        payload = request["dingtalkWebhooks"] or []
        if not isinstance(payload, list):
            raise AppError("VALIDATION_ERROR", "dingtalkWebhooks must be a list", 400)
        upsert_webhooks(db, payload)
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
        .order_by(CodeQualityReviewProfile.id.asc())
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
        "pushMinChangedFiles": profile.push_min_changed_files,
        "pushMinDiffBytes": profile.push_min_diff_bytes,
        "pushMinCommitCount": profile.push_min_commit_count,
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
    if "pushMinChangedFiles" in request:
        profile.push_min_changed_files = request["pushMinChangedFiles"]
    if "pushMinDiffBytes" in request:
        profile.push_min_diff_bytes = request["pushMinDiffBytes"]
    if "pushMinCommitCount" in request:
        profile.push_min_commit_count = request["pushMinCommitCount"]
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
    definition = _default_profile_definition(profile.profile_code)
    default_prompt = definition["instructions"]
    profile.review_instructions = default_prompt
    profile.openai_instructions = default_prompt
    profile.codex_prompt = default_prompt
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
        "timeoutSeconds": provider.timeout_seconds,
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
    if "timeoutSeconds" in request:
        values["timeout_seconds"] = _normalize_provider_timeout(request["timeoutSeconds"])
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


def _normalize_provider_timeout(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        timeout = int(value)
    except (TypeError, ValueError):
        raise AppError("BAD_REQUEST", "timeoutSeconds must be an integer between 1 and 3600", 400)
    if timeout < 1 or timeout > 3600:
        raise AppError("BAD_REQUEST", "timeoutSeconds must be between 1 and 3600", 400)
    return timeout


def set_default_provider(db: Session, provider_code: str) -> dict[str, Any]:
    provider = get_provider(db, provider_code)
    record = get_settings_record(db)
    record.default_provider_code = provider.provider_code
    record.review_provider = provider.provider_code
    record.updated_at = datetime.now()
    db.flush()
    return settings_to_dict(record)


def save_push_gate_decision(
    db: Session,
    *,
    task_id: int,
    project_id: int,
    branch_name: str | None,
    profile_code: str | None,
    provider: str | None,
    decision: str,
    ai_review_scheduled: bool,
    reason_code: str,
    reason_summary: str,
    metrics: dict[str, Any],
    matched_rules: list[dict[str, Any]],
) -> CodeQualityPushReviewGateDecision:
    ensure_push_gate_schema(db)
    now = datetime.now()
    existing = db.scalars(
        select(CodeQualityPushReviewGateDecision).where(CodeQualityPushReviewGateDecision.task_id == task_id)
    ).first()
    if existing is None:
        existing = CodeQualityPushReviewGateDecision(
            task_id=task_id,
            project_id=project_id,
            branch_name=branch_name,
            profile_code=profile_code,
            provider=provider,
            decision=decision,
            ai_review_scheduled=ai_review_scheduled,
            reason_code=reason_code,
            reason_summary=_truncate(reason_summary, 512) or reason_summary,
            metrics_json=json.dumps(metrics, ensure_ascii=False),
            matched_rules_json=json.dumps(matched_rules, ensure_ascii=False),
            created_at=now,
            updated_at=now,
        )
        db.add(existing)
    else:
        existing.project_id = project_id
        existing.branch_name = branch_name
        existing.profile_code = profile_code
        existing.provider = provider
        existing.decision = decision
        existing.ai_review_scheduled = ai_review_scheduled
        existing.reason_code = reason_code
        existing.reason_summary = _truncate(reason_summary, 512) or reason_summary
        existing.metrics_json = json.dumps(metrics, ensure_ascii=False)
        existing.matched_rules_json = json.dumps(matched_rules, ensure_ascii=False)
        existing.updated_at = now
    db.flush()
    return existing


def find_push_gate_decision(db: Session, task_id: int) -> CodeQualityPushReviewGateDecision | None:
    ensure_push_gate_schema(db)
    return db.scalars(
        select(CodeQualityPushReviewGateDecision).where(CodeQualityPushReviewGateDecision.task_id == task_id)
    ).first()


def push_gate_to_dict(record: CodeQualityPushReviewGateDecision) -> dict[str, Any]:
    return {
        "taskId": record.task_id,
        "projectId": record.project_id,
        "branchName": record.branch_name,
        "decision": record.decision,
        "reasonCode": record.reason_code,
        "reasonSummary": record.reason_summary,
        "aiReviewScheduled": record.ai_review_scheduled,
        "profileCode": record.profile_code,
        "provider": record.provider,
        "metrics": read_json(record.metrics_json, {}),
        "matchedRules": read_json(record.matched_rules_json, []),
        "createdAt": format_datetime(record.created_at),
        "updatedAt": format_datetime(record.updated_at),
    }


def find_fix_preview_response(
    db: Session,
    *,
    task_id: int,
    finding_index: int,
    review_key: str | None = None,
) -> dict[str, Any] | None:
    ensure_fix_preview_schema(db)
    stmt = (
        select(CodeQualityFixPreview)
        .where(CodeQualityFixPreview.task_id == task_id)
        .where(CodeQualityFixPreview.finding_index == finding_index)
    )
    if review_key:
        stmt = stmt.where(CodeQualityFixPreview.review_key == review_key)
    record = db.scalars(stmt.order_by(CodeQualityFixPreview.id.asc())).first()
    return fix_preview_to_dict(record) if record else None


def list_fix_preview_responses(db: Session, task_id: int, review_key: str | None = None) -> list[dict[str, Any]]:
    ensure_fix_preview_schema(db)
    stmt = (
        select(CodeQualityFixPreview)
        .where(CodeQualityFixPreview.task_id == task_id)
    )
    if review_key:
        stmt = stmt.where(CodeQualityFixPreview.review_key == review_key)
    records = db.scalars(stmt.order_by(CodeQualityFixPreview.review_key.asc(), CodeQualityFixPreview.finding_index.asc())).all()
    return [fix_preview_to_dict(record) for record in records]


def delete_fix_previews(db: Session, task_id: int, review_key: str | None = None) -> None:
    ensure_fix_preview_schema(db)
    stmt = delete(CodeQualityFixPreview).where(CodeQualityFixPreview.task_id == task_id)
    if review_key:
        stmt = stmt.where(CodeQualityFixPreview.review_key == review_key)
    db.execute(stmt)
    db.flush()


def save_fix_preview(
    db: Session,
    *,
    task_id: int,
    project_id: int,
    finding_index: int,
    file_path: str,
    provider: str,
    model: str | None,
    result: dict[str, Any],
    review_key: str | None = None,
) -> CodeQualityFixPreview:
    ensure_fix_preview_schema(db)
    now = datetime.now()
    normalized_review_key = review_key or DEFAULT_REVIEW_KEY
    existing = db.scalars(
        select(CodeQualityFixPreview)
        .where(CodeQualityFixPreview.task_id == task_id)
        .where(CodeQualityFixPreview.review_key == normalized_review_key)
        .where(CodeQualityFixPreview.finding_index == finding_index)
    ).first()
    values = {
        "project_id": project_id,
        "file_path": file_path,
        "status": result["status"],
        "provider": provider,
        "model": model,
        "summary": _truncate(result.get("summary"), 1024),
        "patch_text": result.get("patchText"),
        "warnings_json": json.dumps(result.get("warnings") or [], ensure_ascii=False),
        "error_message": _truncate(result.get("errorMessage"), 1024),
        "updated_at": now,
    }
    if existing is None:
        existing = CodeQualityFixPreview(
            task_id=task_id,
            review_key=normalized_review_key,
            finding_index=finding_index,
            created_at=now,
            **values,
        )
        db.add(existing)
    else:
        for key, value in values.items():
            setattr(existing, key, value)
    db.flush()
    return existing


def fix_preview_to_dict(record: CodeQualityFixPreview) -> dict[str, Any]:
    return {
        "taskId": record.task_id,
        "reviewKey": record.review_key,
        "findingIndex": record.finding_index,
        "status": record.status,
        "filePath": record.file_path,
        "summary": record.summary,
        "patchText": record.patch_text,
        "warnings": read_json(record.warnings_json, []),
        "provider": record.provider,
        "model": record.model,
        "errorMessage": record.error_message,
        "createdAt": format_datetime(record.created_at),
        "updatedAt": format_datetime(record.updated_at),
    }


def create_scheduler_job(
    db: Session,
    *,
    job_type: str,
    task_id: int,
    project_id: int | None,
    priority: int,
    review_key: str | None = None,
    finding_index: int | None = None,
    label: str | None = None,
    file_path: str | None = None,
) -> CodeQualitySchedulerJob:
    ensure_scheduler_job_schema(db)
    now = datetime.now()
    record = CodeQualitySchedulerJob(
        job_type=job_type,
        task_id=task_id,
        review_key=review_key,
        project_id=project_id,
        finding_index=finding_index,
        status="QUEUED",
        priority=priority,
        label=_truncate(label, 255),
        file_path=_truncate(file_path, 512),
        error_message=None,
        queued_at=now,
        started_at=None,
        finished_at=None,
        created_at=now,
        updated_at=now,
    )
    db.add(record)
    db.flush()
    return record


def mark_scheduler_job_running(db: Session, job_id: int) -> bool:
    record = db.get(CodeQualitySchedulerJob, job_id)
    if record is None or record.status != "QUEUED":
        return False
    now = datetime.now()
    record.status = "RUNNING"
    record.started_at = now
    record.updated_at = now
    db.flush()
    return True


def mark_scheduler_job_finished(
    db: Session,
    job_id: int,
    status: str,
    error_message: str | None = None,
) -> None:
    record = db.get(CodeQualitySchedulerJob, job_id)
    if record is None:
        return
    if record.status not in {"QUEUED", "RUNNING"}:
        return
    now = datetime.now()
    record.status = status
    record.error_message = _truncate(error_message, 1024)
    record.finished_at = now
    record.updated_at = now
    db.flush()


def cancel_scheduler_job(db: Session, job_id: int, reason: str | None = None) -> dict[str, Any]:
    ensure_scheduler_job_schema(db)
    record = db.get(CodeQualitySchedulerJob, job_id)
    if record is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Scheduler job not found: {job_id}", 404)
    if record.status in {"QUEUED", "RUNNING"}:
        _mark_scheduler_job_interrupted(record, reason)
        if record.job_type == "AI_REVIEW":
            _mark_review_result_interrupted(db, record.task_id, record.review_key, reason)
        elif record.job_type == "FIX_PREVIEW" and record.finding_index is not None:
            _mark_fix_preview_interrupted(db, record.task_id, record.review_key, record.finding_index, reason)
        db.flush()
    return scheduler_job_to_dict(record)


def cancel_active_scheduler_jobs_for_task(
    db: Session,
    task_id: int,
    *,
    job_type: str | None = None,
    review_key: str | None = None,
    finding_index: int | None = None,
    reason: str | None = None,
) -> list[dict[str, Any]]:
    ensure_scheduler_job_schema(db)
    stmt = (
        select(CodeQualitySchedulerJob)
        .where(CodeQualitySchedulerJob.task_id == task_id)
        .where(CodeQualitySchedulerJob.status.in_(["QUEUED", "RUNNING"]))
    )
    if job_type:
        stmt = stmt.where(CodeQualitySchedulerJob.job_type == job_type)
    if review_key:
        stmt = stmt.where(CodeQualitySchedulerJob.review_key == review_key)
    if finding_index is not None:
        stmt = stmt.where(CodeQualitySchedulerJob.finding_index == finding_index)
    records = db.scalars(stmt.order_by(CodeQualitySchedulerJob.id.asc())).all()
    for record in records:
        _mark_scheduler_job_interrupted(record, reason)
    if job_type == "AI_REVIEW":
        _mark_review_result_interrupted(db, task_id, review_key, reason)
    elif job_type == "FIX_PREVIEW" and finding_index is not None:
        _mark_fix_preview_interrupted(db, task_id, review_key, finding_index, reason)
    db.flush()
    return [scheduler_job_to_dict(record) for record in records]


def _mark_scheduler_job_interrupted(record: CodeQualitySchedulerJob, reason: str | None = None) -> None:
    now = datetime.now()
    record.status = "SKIPPED"
    record.error_message = _truncate(reason or "用户手动中断", 1024)
    record.finished_at = now
    record.updated_at = now


def _mark_review_result_interrupted(
    db: Session,
    task_id: int,
    review_key: str | None,
    reason: str | None = None,
) -> None:
    ensure_result_schema(db)
    stmt = (
        select(CodeQualityReviewResult)
        .where(CodeQualityReviewResult.task_id == task_id)
        .where(CodeQualityReviewResult.status == "RUNNING")
    )
    if review_key:
        stmt = stmt.where(CodeQualityReviewResult.review_key == review_key)
    records = db.scalars(stmt).all()
    now = datetime.now()
    for record in records:
        record.status = "SKIPPED"
        record.error_message = _truncate(reason or "用户手动中断 AI Review", 1024)
        record.finished_at = now
        record.updated_at = now
    if records:
        from app.review_record.repository import refresh_review_status

        refresh_review_status(db, task_id)


def _mark_fix_preview_interrupted(
    db: Session,
    task_id: int,
    review_key: str | None,
    finding_index: int,
    reason: str | None = None,
) -> None:
    ensure_fix_preview_schema(db)
    stmt = (
        select(CodeQualityFixPreview)
        .where(CodeQualityFixPreview.task_id == task_id)
        .where(CodeQualityFixPreview.finding_index == finding_index)
        .where(CodeQualityFixPreview.status.in_(["QUEUED", "RUNNING"]))
    )
    if review_key:
        stmt = stmt.where(CodeQualityFixPreview.review_key == review_key)
    record = db.scalars(stmt.order_by(CodeQualityFixPreview.id.asc())).first()
    if record is None:
        return
    record.status = "SKIPPED"
    record.error_message = _truncate(reason or "用户手动中断修复预览", 1024)
    record.summary = "用户手动中断修复预览"
    record.patch_text = None
    record.updated_at = datetime.now()


def list_scheduler_queue_snapshot(db: Session, limit: int = 100) -> dict[str, Any]:
    ensure_scheduler_job_schema(db)
    cutoff = datetime.now() - timedelta(hours=24)
    fetch_limit = max(int(limit), 1)
    active_count = db.scalar(
        select(func.count())
        .select_from(CodeQualitySchedulerJob)
        .where(CodeQualitySchedulerJob.status.in_(["QUEUED", "RUNNING"]))
    ) or 0
    active = db.scalars(
        select(CodeQualitySchedulerJob)
        .where(CodeQualitySchedulerJob.status.in_(["QUEUED", "RUNNING"]))
        .order_by(
            CodeQualitySchedulerJob.updated_at.desc(),
            CodeQualitySchedulerJob.queued_at.desc(),
            CodeQualitySchedulerJob.id.desc(),
        )
        .limit(fetch_limit * 2)
    ).all()
    recent = db.scalars(
        select(CodeQualitySchedulerJob)
        .where(CodeQualitySchedulerJob.status.in_(["SUCCESS", "FAILED", "SKIPPED"]))
        .where(CodeQualitySchedulerJob.updated_at >= cutoff)
        .order_by(CodeQualitySchedulerJob.updated_at.desc(), CodeQualitySchedulerJob.id.desc())
        .limit(fetch_limit)
    ).all()
    records = _dedupe_scheduler_jobs([*active, *recent])[:fetch_limit]
    task_ids = sorted({record.task_id for record in records})
    tasks_by_id: dict[int, tuple[Any, Any]] = {}
    if task_ids:
        from app.project_integration.models import Project
        from app.review_record.models import ReviewTask

        rows = db.execute(
            select(ReviewTask, Project)
            .join(Project, Project.id == ReviewTask.project_id)
            .where(ReviewTask.id.in_(task_ids))
        ).all()
        tasks_by_id = {task.id: (task, project) for task, project in rows}
    results_by_key: dict[tuple[int, str | None], CodeQualityReviewResult] = {}
    if task_ids:
        result_rows = db.scalars(
            select(CodeQualityReviewResult).where(CodeQualityReviewResult.task_id.in_(task_ids))
        ).all()
        results_by_key = {
            (result.task_id, result.review_key): result
            for result in result_rows
        }
    grouped: dict[int, dict[str, Any]] = {}
    for record in records:
        task, project = tasks_by_id.get(record.task_id, (None, None))
        group = grouped.setdefault(
            record.task_id,
            {
                "taskId": record.task_id,
                "projectId": record.project_id,
                "projectName": getattr(project, "name", None),
                "triggerType": getattr(task, "trigger_type", None),
                "sourceBranch": getattr(task, "source_branch", None),
                "targetBranch": getattr(task, "target_branch", None),
                "externalSourceId": getattr(task, "external_source_id", None),
                "reviewJob": None,
                "reviewJobs": [],
                "fixPreviewJobs": [],
            },
        )
        result = results_by_key.get((record.task_id, record.review_key))
        if result is None and not record.review_key:
            result = results_by_key.get((record.task_id, DEFAULT_REVIEW_KEY))
        job = scheduler_job_to_dict(record, result)
        if record.job_type == "AI_REVIEW":
            group["reviewJobs"].append(job)
            group["reviewJob"] = group["reviewJob"] or job
        else:
            group["fixPreviewJobs"].append(job)
    groups = list(grouped.values())
    groups.sort(key=lambda group: _scheduler_group_sort_key(group), reverse=True)
    return {"activeCount": active_count, "groups": groups}


def list_ai_review_failure_notifications(db: Session, limit: int = 100) -> dict[str, Any]:
    ensure_scheduler_job_schema(db)
    cutoff = datetime.now() - timedelta(hours=24)
    fetch_limit = max(int(limit), 1)
    failure_count = db.scalar(
        select(func.count())
        .select_from(CodeQualitySchedulerJob)
        .where(CodeQualitySchedulerJob.job_type == "AI_REVIEW")
        .where(CodeQualitySchedulerJob.status == "FAILED")
        .where(CodeQualitySchedulerJob.created_at >= cutoff)
    ) or 0
    records = db.scalars(
        select(CodeQualitySchedulerJob)
        .where(CodeQualitySchedulerJob.job_type == "AI_REVIEW")
        .where(CodeQualitySchedulerJob.status == "FAILED")
        .where(CodeQualitySchedulerJob.created_at >= cutoff)
        .order_by(CodeQualitySchedulerJob.created_at.desc(), CodeQualitySchedulerJob.id.desc())
        .limit(fetch_limit)
    ).all()
    task_ids = sorted({record.task_id for record in records})
    tasks_by_id: dict[int, tuple[Any, Any]] = {}
    results_by_key: dict[tuple[int, str | None], CodeQualityReviewResult] = {}
    if task_ids:
        from app.project_integration.models import Project
        from app.review_record.models import ReviewTask

        task_rows = db.execute(
            select(ReviewTask, Project)
            .join(Project, Project.id == ReviewTask.project_id)
            .where(ReviewTask.id.in_(task_ids))
        ).all()
        tasks_by_id = {task.id: (task, project) for task, project in task_rows}
        result_rows = db.scalars(
            select(CodeQualityReviewResult).where(CodeQualityReviewResult.task_id.in_(task_ids))
        ).all()
        results_by_key = {(result.task_id, result.review_key): result for result in result_rows}
    return {
        "failureCount": failure_count,
        "items": [
            ai_review_failure_notification_to_dict(
                record,
                tasks_by_id.get(record.task_id, (None, None)),
                results_by_key.get((record.task_id, record.review_key))
                or (results_by_key.get((record.task_id, DEFAULT_REVIEW_KEY)) if not record.review_key else None),
            )
            for record in records
        ],
    }


def ai_review_failure_notification_to_dict(
    record: CodeQualitySchedulerJob,
    task_and_project: tuple[Any, Any],
    result: CodeQualityReviewResult | None,
) -> dict[str, Any]:
    task, project = task_and_project
    return {
        "id": record.id,
        "taskId": record.task_id,
        "reviewKey": record.review_key,
        "projectId": record.project_id or getattr(task, "project_id", None),
        "projectName": getattr(project, "name", None),
        "triggerType": getattr(task, "trigger_type", None),
        "sourceBranch": getattr(task, "source_branch", None),
        "targetBranch": getattr(task, "target_branch", None),
        "externalSourceId": getattr(task, "external_source_id", None),
        "profileCode": getattr(result, "profile_code", None),
        "provider": getattr(result, "provider", None),
        "model": getattr(result, "model", None),
        "status": record.status,
        "label": record.label,
        "errorMessage": record.error_message or getattr(result, "error_message", None),
        "queuedAt": format_datetime(record.queued_at),
        "startedAt": format_datetime(record.started_at),
        "finishedAt": format_datetime(record.finished_at),
        "createdAt": format_datetime(record.created_at),
        "updatedAt": format_datetime(record.updated_at),
    }


def scheduler_job_to_dict(
    record: CodeQualitySchedulerJob,
    result: CodeQualityReviewResult | None = None,
) -> dict[str, Any]:
    return {
        "id": record.id,
        "jobType": record.job_type,
        "taskId": record.task_id,
        "reviewKey": record.review_key,
        "projectId": record.project_id,
        "profileCode": getattr(result, "profile_code", None),
        "provider": getattr(result, "provider", None),
        "model": getattr(result, "model", None),
        "displayName": getattr(result, "display_name", None),
        "sortOrder": getattr(result, "sort_order", None),
        "findingIndex": record.finding_index,
        "status": record.status,
        "priority": record.priority,
        "label": record.label,
        "filePath": record.file_path,
        "errorMessage": record.error_message,
        "queuedAt": format_datetime(record.queued_at),
        "startedAt": format_datetime(record.started_at),
        "finishedAt": format_datetime(record.finished_at),
        "createdAt": format_datetime(record.created_at),
        "updatedAt": format_datetime(record.updated_at),
    }


def _dedupe_scheduler_jobs(records: list[CodeQualitySchedulerJob]) -> list[CodeQualitySchedulerJob]:
    seen: set[int] = set()
    result: list[CodeQualitySchedulerJob] = []
    for record in records:
        if record.id in seen:
            continue
        seen.add(record.id)
        result.append(record)
    return result


def _scheduler_group_sort_key(group: dict[str, Any]) -> str:
    updated = max(
        [
            job.get("updatedAt") or job.get("queuedAt") or ""
            for job in ([group["reviewJob"]] if group.get("reviewJob") else []) + group.get("fixPreviewJobs", [])
        ],
        default="",
    )
    return updated


def has_recent_allowed_push_gate(
    db: Session,
    *,
    project_id: int,
    branch_name: str | None,
    task_id: int,
    debounce_seconds: int,
) -> bool:
    if not branch_name or debounce_seconds <= 0:
        return False
    ensure_push_gate_schema(db)
    cutoff = datetime.now() - timedelta(seconds=debounce_seconds)
    return (
        db.scalars(
            select(CodeQualityPushReviewGateDecision)
            .where(CodeQualityPushReviewGateDecision.project_id == project_id)
            .where(CodeQualityPushReviewGateDecision.branch_name == branch_name)
            .where(CodeQualityPushReviewGateDecision.task_id != task_id)
            .where(CodeQualityPushReviewGateDecision.decision == "ALLOWED")
            .where(CodeQualityPushReviewGateDecision.ai_review_scheduled.is_(True))
            .where(CodeQualityPushReviewGateDecision.created_at >= cutoff)
        ).first()
        is not None
    )


def save_result(
    db: Session,
    *,
    task_id: int,
    project_id: int,
    profile_code: str,
    provider: str,
    model: str | None,
    result: dict[str, Any],
    display_name: str | None = None,
    sort_order: int = 0,
    review_key: str | None = None,
) -> CodeQualityReviewResult:
    ensure_result_schema(db)
    now = datetime.now()
    normalized_review_key = review_key or DEFAULT_REVIEW_KEY
    existing = db.scalars(
        select(CodeQualityReviewResult)
        .where(CodeQualityReviewResult.task_id == task_id)
        .where(CodeQualityReviewResult.review_key == normalized_review_key)
    ).first()
    if existing is None:
        existing = CodeQualityReviewResult(
            task_id=task_id,
            review_key=normalized_review_key,
            project_id=project_id,
            profile_code=profile_code,
            provider=provider,
            model=model,
            display_name=display_name,
            sort_order=sort_order,
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
        existing.display_name = display_name
        existing.sort_order = sort_order
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
    from app.review_record.repository import refresh_review_status

    refresh_review_status(db, task_id)
    return existing


def find_result_response(db: Session, task_id: int) -> dict[str, Any] | None:
    result = _first_result(db, task_id)
    return result_to_response(result) if result is not None else None


def list_result_responses(db: Session, task_id: int) -> list[dict[str, Any]]:
    ensure_result_schema(db)
    records = db.scalars(
        select(CodeQualityReviewResult)
        .where(CodeQualityReviewResult.task_id == task_id)
        .order_by(CodeQualityReviewResult.sort_order.asc(), CodeQualityReviewResult.id.asc())
    ).all()
    return [result_to_response(result) for result in records]


def find_result_response_by_key(db: Session, task_id: int, review_key: str | None) -> dict[str, Any] | None:
    ensure_result_schema(db)
    normalized_review_key = review_key or DEFAULT_REVIEW_KEY
    result = db.scalars(
        select(CodeQualityReviewResult)
        .where(CodeQualityReviewResult.task_id == task_id)
        .where(CodeQualityReviewResult.review_key == normalized_review_key)
    ).first()
    return result_to_response(result) if result is not None else None


def _first_result(db: Session, task_id: int) -> CodeQualityReviewResult | None:
    ensure_result_schema(db)
    return db.scalars(
        select(CodeQualityReviewResult)
        .where(CodeQualityReviewResult.task_id == task_id)
        .order_by(CodeQualityReviewResult.sort_order.asc(), CodeQualityReviewResult.id.asc())
    ).first()


def result_to_response(result: CodeQualityReviewResult | None) -> dict[str, Any] | None:
    if result is None:
        return None
    findings = json.loads(result.findings_json or "[]")
    if _needs_finding_repair(findings):
        findings = _repair_findings_from_raw_output(findings, result.raw_output, result.provider)
    return {
        "id": result.id,
        "taskId": result.task_id,
        "reviewKey": result.review_key,
        "projectId": result.project_id,
        "profileCode": result.profile_code,
        "provider": result.provider,
        "model": result.model,
        "displayName": result.display_name,
        "sortOrder": result.sort_order,
        "status": result.status,
        "overallLevel": result.overall_level,
        "summary": result.summary,
        "findingCount": result.finding_count,
        "findings": findings,
        "rawOutput": result.raw_output,
        "exitCode": result.exit_code,
        "errorMessage": result.error_message,
        "startedAt": format_datetime(result.started_at),
        "finishedAt": format_datetime(result.finished_at),
    }


def _needs_finding_repair(findings: list[dict[str, Any]]) -> bool:
    return any(
        not finding.get("filePath") or not finding.get("category") or finding.get("startLine") is None
        for finding in findings
        if isinstance(finding, dict)
    )


def _repair_findings_from_raw_output(
    stored_findings: list[dict[str, Any]],
    raw_output: str | None,
    provider: str | None,
) -> list[dict[str, Any]]:
    if not raw_output:
        return stored_findings
    try:
        output_text = _extract_model_output_text(raw_output)
        card = json.loads(_strip_json_fence(output_text))
    except Exception:
        return stored_findings
    repaired = []
    raw_findings = [item for item in card.get("findings") or [] if isinstance(item, dict)]
    for index, stored in enumerate(stored_findings):
        raw = raw_findings[index] if index < len(raw_findings) else {}
        merged = dict(stored)
        normalized = _normalize_finding_response(raw, provider)
        for key, value in normalized.items():
            if _is_blank(merged.get(key)) and not _is_blank(value):
                merged[key] = value
        repaired.append(merged)
    return repaired or stored_findings


def _is_blank(value: Any) -> bool:
    return value is None or value == ""


def _extract_model_output_text(raw_output: str) -> str:
    root = json.loads(raw_output)
    if root.get("output_text"):
        return str(root["output_text"])
    choices = root.get("choices") or []
    if choices:
        content = ((choices[0].get("message") or {}).get("content"))
        if content:
            return str(content)
    for output in root.get("output") or []:
        for content in output.get("content") or []:
            if content.get("text"):
                return str(content["text"])
    parts = [
        str(content.get("text"))
        for content in root.get("content") or []
        if content.get("type") == "text" and content.get("text")
    ]
    if parts:
        return "".join(parts)
    raise ValueError("raw output does not contain model text")


def _normalize_finding_response(finding: dict[str, Any], provider: str | None) -> dict[str, Any]:
    line_range = finding.get("line_range") or finding.get("lineRange") or finding.get("lines")
    start_line = _first_present(finding, "startLine", "start_line", "line", "lineNumber", "line_number")
    end_line = _first_present(finding, "endLine", "end_line")
    if isinstance(line_range, list) and line_range:
        start_line = start_line if start_line is not None else line_range[0]
        end_line = end_line if end_line is not None else (line_range[1] if len(line_range) > 1 else line_range[0])
    location = finding.get("location") if isinstance(finding.get("location"), dict) else {}
    if location:
        start_line = start_line if start_line is not None else _first_present(location, "startLine", "start_line", "line")
        end_line = end_line if end_line is not None else _first_present(location, "endLine", "end_line", "line")
    return {
        "severity": _normalize_finding_severity(_first_present(finding, "severity", "riskLevel", "risk_level", "level", "priority")),
        "category": _normalize_finding_category(_first_present(finding, "category", "type", "kind", "issueType", "issue_type")),
        "filePath": _first_present(finding, "filePath", "file_path", "path", "file") or location.get("filePath") or location.get("file"),
        "startLine": _to_int(start_line),
        "endLine": _to_int(end_line if end_line is not None else start_line),
        "confidence": _normalize_finding_confidence(finding.get("confidence")),
        "source": provider,
    }


def _first_present(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return None


def _normalize_finding_category(value: Any) -> str:
    normalized = str(value or "").strip().upper().replace("-", "_")
    return {
        "BUG": "CORRECTNESS",
        "CORRECTNESS": "CORRECTNESS",
        "SECURITY": "SECURITY",
        "PERFORMANCE": "SQL_PERFORMANCE",
        "SQL_PERFORMANCE": "SQL_PERFORMANCE",
        "CONSISTENCY": "CORRECTNESS",
        "DATA_CONSISTENCY": "CORRECTNESS",
        "TRANSACTION": "TRANSACTION",
        "TEST": "TEST_GAP",
        "TEST_COVERAGE": "TEST_GAP",
        "TEST_GAP": "TEST_GAP",
        "EXCEPTION": "EXCEPTION_HANDLING",
        "EXCEPTION_HANDLING": "EXCEPTION_HANDLING",
        "CACHE": "CACHE_CONSISTENCY",
        "CACHE_CONSISTENCY": "CACHE_CONSISTENCY",
        "MQ": "MQ_CONSISTENCY",
        "MQ_CONSISTENCY": "MQ_CONSISTENCY",
        "OTHER": "CODE_QUALITY",
        "CODE_QUALITY": "CODE_QUALITY",
    }.get(normalized, normalized or "CODE_QUALITY")


def _normalize_finding_severity(value: Any) -> str | None:
    normalized = str(value or "").strip().upper().replace("-", "_")
    return {
        "BLOCKER": "CRITICAL",
        "CRITICAL": "CRITICAL",
        "HIGH": "MAJOR",
        "MAJOR": "MAJOR",
        "MEDIUM": "MINOR",
        "MINOR": "MINOR",
        "LOW": "MINOR",
    }.get(normalized)


def _normalize_finding_confidence(value: Any) -> str | None:
    normalized = str(value or "").strip().upper()
    return normalized if normalized in {"LOW", "MEDIUM", "HIGH"} else None


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _strip_json_fence(value: str) -> str:
    text = (value or "").strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").strip()
        text = text.removesuffix("```").strip()
    return text


def append_progress(
    db: Session,
    task_id: int,
    phase: str,
    level: str,
    message: str,
    detail: str | None = None,
    review_key: str | None = None,
) -> None:
    normalized_review_key = review_key if review_key is not None else _PROGRESS_REVIEW_KEY.get()
    db.add(
        CodeQualityReviewProgressEvent(
            task_id=task_id,
            review_key=normalized_review_key,
            phase=_truncate(phase, 64) or phase,
            level=_truncate(level, 32) or level,
            message=_truncate(message, 512) or message,
            detail=_truncate(scrub_sensitive(detail), 4000),
            created_at=datetime.now(),
        )
    )
    db.flush()


def delete_progress(db: Session, task_id: int, review_key: str | None = None) -> None:
    stmt = select(CodeQualityReviewProgressEvent).where(CodeQualityReviewProgressEvent.task_id == task_id)
    if review_key:
        stmt = stmt.where(CodeQualityReviewProgressEvent.review_key == review_key)
    for event in db.scalars(stmt).all():
        db.delete(event)
    db.flush()


def list_progress(db: Session, task_id: int, review_key: str | None = None) -> list[dict[str, Any]]:
    stmt = (
        select(CodeQualityReviewProgressEvent)
        .where(CodeQualityReviewProgressEvent.task_id == task_id)
    )
    if review_key:
        stmt = stmt.where(CodeQualityReviewProgressEvent.review_key == review_key)
    records = db.scalars(stmt.order_by(CodeQualityReviewProgressEvent.id.asc())).all()
    return [
        {
            "id": record.id,
            "taskId": record.task_id,
            "reviewKey": record.review_key,
            "phase": record.phase,
            "level": record.level,
            "message": record.message,
            "detail": record.detail,
            "createdAt": format_datetime(record.created_at),
        }
        for record in records
    ]


@contextmanager
def progress_review_key(review_key: str | None):
    token = _PROGRESS_REVIEW_KEY.set(review_key)
    try:
        yield
    finally:
        _PROGRESS_REVIEW_KEY.reset(token)


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
    if records:
        from app.review_record.repository import refresh_review_status

        for task_id in {record.task_id for record in records}:
            refresh_review_status(db, task_id)
    db.flush()
    return len(records)


def mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    trimmed = value.strip()
    if len(trimmed) <= 8:
        return "****"
    return f"{trimmed[:4]}...{trimmed[-4:]}"


def normalize_auto_fix_preview_severities(value: Any) -> list[str]:
    raw_items = value if isinstance(value, list) else read_json_array(value)
    result: list[str] = []
    for item in raw_items:
        normalized = str(item or "").strip().upper()
        if normalized in AUTO_FIX_PREVIEW_SEVERITY_OPTIONS and normalized not in result:
            result.append(normalized)
    return result or list(DEFAULT_AUTO_FIX_PREVIEW_SEVERITIES)


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


def _default_unlimited(value: int | None, legacy_default: int) -> int:
    if value is None or value == legacy_default:
        return -1
    return value


def _truncate(value: str | None, max_length: int) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= max_length else text[:max_length]
