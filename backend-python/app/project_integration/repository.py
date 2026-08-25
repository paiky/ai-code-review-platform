from datetime import datetime
from fnmatch import fnmatchcase
import hashlib
import json
import re
from threading import Lock
from typing import Any

from sqlalchemy import Select, func, inspect, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.json_utils import page_response
from app.core.errors import AppError
from app.core.json_utils import read_json, read_json_array
from app.project_integration.models import (
    Project,
    ProjectGroup,
    ProjectGroupAiReviewModel,
    ProjectAiReviewModel,
    ProjectReviewSettings,
    ProjectTargetConfig,
    TargetTypePathMapping,
)


TARGET_TYPE_DEFAULTS = {
    "BACKEND": {
        "templateCode": "backend-default",
        "profileCode": "backend-default-ai-review",
        "pathPatterns": ["backend-python/**", "backend/**", "src/main/**", "src/test/**", "src/*.java", "src/**/*.java", "pom.xml", "requirements*.txt"],
        "reminderCardEnabled": True,
    },
    "WEB_PC": {
        "templateCode": "frontend-default",
        "profileCode": "web-pc-default-ai-review",
        "pathPatterns": ["frontend/**", "web/**", "src/**/*.tsx", "src/**/*.jsx", "src/**/*.vue"],
        "reminderCardEnabled": False,
    },
    "APP_IOS": {
        "templateCode": "frontend-default",
        "profileCode": "app-ios-default-ai-review",
        "pathPatterns": ["ios/**", "**/*.swift", "**/*.m", "**/*.mm"],
        "reminderCardEnabled": False,
    },
    "APP_ANDROID": {
        "templateCode": "frontend-default",
        "profileCode": "app-android-default-ai-review",
        "pathPatterns": ["android/**", "**/*.kt", "**/*.kts", "**/*.gradle"],
        "reminderCardEnabled": False,
    },
    "APP_CROSS_PLATFORM": {
        "templateCode": "frontend-default",
        "profileCode": "app-cross-platform-default-ai-review",
        "pathPatterns": ["flutter/**", "rn/**", "miniapp/**", "**/*.dart"],
        "reminderCardEnabled": False,
    },
    "GENERAL": {
        "templateCode": "general-default",
        "profileCode": None,
        "pathPatterns": ["**/*"],
        "reminderCardEnabled": False,
    },
}

DEFAULT_PUSH_REVIEW_POLICY = {
    "pushBranchPatterns": ["master"],
    "pushMinChangedFiles": 10,
    "pushMinDiffBytes": 30000,
    "pushMinCommitCount": 3,
    "pushMaxChangedFiles": -1,
    "pushMaxDiffBytes": -1,
    "pushDebounceSeconds": 300,
}
DEFAULT_GROUP_AI_REVIEW_POLICY = {
    "reviewEngine": "AGENT",
    "agentSourceExportAllowed": True,
    "aiReviewEnabled": True,
    "triggerOnManual": True,
    "triggerOnMr": True,
    "triggerOnPush": True,
    "triggerOnlyWhenRiskMatched": False,
    "autoFixPreviewEnabled": True,
    "autoFixPreviewSeverities": ["CRITICAL"],
}

PATH_DETECTION_RULES = [
    ("APP_IOS", ["ios/**", "**/*.swift", "**/*.m", "**/*.mm", "Podfile"]),
    ("APP_ANDROID", ["android/**", "**/*.kt", "**/*.kts", "build.gradle", "settings.gradle", "**/*.gradle"]),
    ("WEB_PC", ["frontend/**", "web/**", "src/**/*.tsx", "src/**/*.jsx", "src/**/*.vue", "package.json"]),
    ("BACKEND", ["src/main/java/**", "src/main/resources/**", "src/*.java", "src/**/*.java", "pom.xml", "backend-python/**", "backend/**"]),
]
PATH_MAPPING_TARGET_TYPES = {target_type for target_type, _patterns in PATH_DETECTION_RULES}
SYSTEM_DETECTED_TARGET_CONFIG_DESCRIPTIONS = {
    "自动识别创建的端类型配置",
    "路径映射创建的端类型配置",
    "恢复自动识别的端类型配置",
}

_SCHEMA_LOCK = Lock()
_SCHEMA_ENSURED_ENGINE_IDS: set[int] = set()


def ensure_project_config_schema(db: Session) -> None:
    engine_id = id(db.get_bind())
    if engine_id in _SCHEMA_ENSURED_ENGINE_IDS:
        _ensure_project_group_ai_review_model_schema(db)
        _ensure_project_ai_review_model_schema(db)
        _ensure_project_review_settings_schema(db)
        return
    with _SCHEMA_LOCK:
        if engine_id in _SCHEMA_ENSURED_ENGINE_IDS:
            _ensure_project_group_ai_review_model_schema(db)
            _ensure_project_ai_review_model_schema(db)
            _ensure_project_review_settings_schema(db)
            return
        connection = db.connection()
        inspector = inspect(connection)
        project_groups_created = False
        if not inspector.has_table("project_groups"):
            ProjectGroup.__table__.create(connection, checkfirst=True)
            project_groups_created = True
        if not project_groups_created:
            group_columns = {column["name"] for column in inspector.get_columns("project_groups")} if inspector.has_table("project_groups") else set()
            _add_column_if_missing(db, group_columns, "project_groups", "default_code_quality_profile_code", "VARCHAR(64) NULL")
            _add_column_if_missing(db, group_columns, "project_groups", "default_provider_code", "VARCHAR(64) NULL")
            _add_column_if_missing(db, group_columns, "project_groups", "review_engine", "VARCHAR(32) NOT NULL DEFAULT 'AGENT'")
            _add_column_if_missing(db, group_columns, "project_groups", "agent_source_export_allowed", "BOOLEAN NOT NULL DEFAULT TRUE")
            _add_column_if_missing(db, group_columns, "project_groups", "ai_review_enabled", "BOOLEAN NOT NULL DEFAULT TRUE")
            _add_column_if_missing(db, group_columns, "project_groups", "trigger_on_manual", "BOOLEAN NOT NULL DEFAULT TRUE")
            _add_column_if_missing(db, group_columns, "project_groups", "trigger_on_mr", "BOOLEAN NOT NULL DEFAULT TRUE")
            _add_column_if_missing(db, group_columns, "project_groups", "trigger_on_push", "BOOLEAN NOT NULL DEFAULT FALSE")
            _add_column_if_missing(db, group_columns, "project_groups", "trigger_only_when_risk_matched", "BOOLEAN NOT NULL DEFAULT FALSE")
            _add_column_if_missing(db, group_columns, "project_groups", "auto_fix_preview_enabled", "BOOLEAN NOT NULL DEFAULT FALSE")
            _add_column_if_missing(db, group_columns, "project_groups", "auto_fix_preview_severities", "TEXT NULL")
            _add_column_if_missing(db, group_columns, "project_groups", "push_branch_patterns", "TEXT NULL")
            _add_column_if_missing(db, group_columns, "project_groups", "push_min_changed_files", "INT NULL DEFAULT 10")
            _add_column_if_missing(db, group_columns, "project_groups", "push_min_diff_bytes", "INT NULL DEFAULT 30000")
            _add_column_if_missing(db, group_columns, "project_groups", "push_min_commit_count", "INT NULL DEFAULT 3")
            _add_column_if_missing(db, group_columns, "project_groups", "push_max_changed_files", "INT NULL DEFAULT -1")
            _add_column_if_missing(db, group_columns, "project_groups", "push_max_diff_bytes", "INT NULL DEFAULT -1")
            _add_column_if_missing(db, group_columns, "project_groups", "push_debounce_seconds", "INT NULL DEFAULT 300")
        if not inspector.has_table("target_type_path_mappings"):
            TargetTypePathMapping.__table__.create(connection, checkfirst=True)
        _ensure_project_group_ai_review_model_schema(db, inspector)
        _ensure_project_ai_review_model_schema(db, inspector)
        if not inspector.has_table("project_target_configs"):
            ProjectTargetConfig.__table__.create(connection, checkfirst=True)
        _ensure_project_review_settings_schema(db, inspector)
        project_columns = {column["name"] for column in inspector.get_columns("projects")} if inspector.has_table("projects") else set()
        _add_column_if_missing(db, project_columns, "projects", "group_id", "BIGINT NULL")
        _add_column_if_missing(db, project_columns, "projects", "target_type", "VARCHAR(32) NULL")
        _add_column_if_missing(db, project_columns, "projects", "default_code_quality_profile_code", "VARCHAR(64) NULL")
        _ensure_nullable_column(db, inspector, "projects", "default_code_quality_profile_code", "VARCHAR(64)")
        _add_column_if_missing(db, project_columns, "projects", "supported_target_types", "TEXT NULL")
        _add_column_if_missing(db, project_columns, "projects", "detected_target_types", "TEXT NULL")
        _add_column_if_missing(db, project_columns, "projects", "target_detection_json", "TEXT NULL")
        task_columns = {column["name"] for column in inspector.get_columns("review_tasks")} if inspector.has_table("review_tasks") else set()
        _add_column_if_missing(db, task_columns, "review_tasks", "target_type", "VARCHAR(32) NULL")
        _add_column_if_missing(db, task_columns, "review_tasks", "target_types_json", "TEXT NULL")
        _add_column_if_missing(db, task_columns, "review_tasks", "code_quality_profile_code", "VARCHAR(64) NULL")
        result_columns = {column["name"] for column in inspector.get_columns("review_results")} if inspector.has_table("review_results") else set()
        _add_column_if_missing(db, result_columns, "review_results", "target_type", "VARCHAR(32) NULL")
        _add_column_if_missing(db, result_columns, "review_results", "reminder_card_enabled", "BOOLEAN NULL")
        db.flush()
        _ensure_default_target_type_path_mappings(db)
        _SCHEMA_ENSURED_ENGINE_IDS.add(engine_id)


def _ensure_project_group_ai_review_model_schema(db: Session, inspector=None) -> None:
    inspector = inspector or inspect(db.connection())
    if not inspector.has_table("project_group_ai_review_models"):
        ProjectGroupAiReviewModel.__table__.create(db.connection(), checkfirst=True)
        db.flush()



def _ensure_project_ai_review_model_schema(db: Session, inspector=None) -> None:
    inspector = inspector or inspect(db.connection())
    if not inspector.has_table("project_ai_review_models"):
        ProjectAiReviewModel.__table__.create(db.connection(), checkfirst=True)
        db.flush()


def _ensure_project_review_settings_schema(db: Session, inspector=None) -> None:
    inspector = inspector or inspect(db.connection())
    if not inspector.has_table("project_review_settings"):
        ProjectReviewSettings.__table__.create(db.connection(), checkfirst=True)
        db.flush()

def _add_column_if_missing(db: Session, columns: set[str], table_name: str, column_name: str, definition: str) -> None:
    if column_name in columns:
        return
    db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"))
    columns.add(column_name)
    db.flush()


def _ensure_nullable_column(
    db: Session,
    inspector,
    table_name: str,
    column_name: str,
    column_type: str,
) -> None:
    column = next(
        (
            item
            for item in inspector.get_columns(table_name)
            if item.get("name") == column_name
        ),
        None,
    )
    if column is None or column.get("nullable", True):
        return
    if db.get_bind().dialect.name != "mysql":
        return
    db.execute(text(f"ALTER TABLE {table_name} MODIFY COLUMN {column_name} {column_type} NULL"))
    db.flush()


def _default_path_mapping_rows() -> list[dict[str, Any]]:
    return [
        {
            "targetType": target_type,
            "pathPatterns": list(patterns),
            "enabled": True,
            "sortOrder": index * 10,
            "description": "系统默认端类型路径映射",
        }
        for index, (target_type, patterns) in enumerate(PATH_DETECTION_RULES, start=1)
    ]


def _ensure_default_target_type_path_mappings(db: Session) -> None:
    existing = db.scalars(select(TargetTypePathMapping)).all()
    existing_by_type = {mapping.target_type: mapping for mapping in existing}
    now = datetime.now()
    for row in _default_path_mapping_rows():
        if row["targetType"] in existing_by_type:
            continue
        db.add(
            TargetTypePathMapping(
                target_type=row["targetType"],
                path_patterns=json.dumps(row["pathPatterns"], ensure_ascii=False),
                enabled=bool(row["enabled"]),
                sort_order=int(row["sortOrder"]),
                description=row["description"],
                created_at=now,
                updated_at=now,
            )
        )
    for mapping in existing:
        if mapping.target_type not in PATH_MAPPING_TARGET_TYPES and mapping.enabled:
            mapping.enabled = False
            mapping.updated_at = now
    db.flush()


def _ensure_default_project_group(db: Session) -> ProjectGroup:
    group = db.scalars(select(ProjectGroup).where(ProjectGroup.group_code == "default")).first()
    if group is None:
        now = datetime.now()
        group = ProjectGroup(
            group_name="默认通用项目组",
            group_code="default",
            default_code_quality_profile_code=None,
            default_provider_code=None,
            **_ai_review_policy_columns({}),
            **_push_policy_columns({}),
            status="ENABLED",
            description="系统默认项目组",
            created_at=now,
            updated_at=now,
        )
        db.add(group)
        db.flush()
    elif group.group_name == "默认项目组":
        group.group_name = "默认通用项目组"
        group.updated_at = datetime.now()
        db.flush()
    db.execute(text("UPDATE projects SET group_id = :group_id WHERE group_id IS NULL"), {"group_id": group.id})
    return group


def project_to_dict(project: Project) -> dict:
    group = None
    session = Session.object_session(project)
    if session and project.group_id:
        group = session.get(ProjectGroup, project.group_id)
    return {
        "id": project.id,
        "groupId": project.group_id,
        "groupName": group.group_name if group else None,
        "name": project.name,
        "gitProvider": project.git_provider,
        "gitProjectId": project.git_project_id,
        "repositoryUrl": project.repository_url,
        "targetType": effective_project_target_type(project),
        "supportedTargetTypes": [effective_project_target_type(project)],
        "detectedTargetTypes": read_json_array(project.detected_target_types),
        "targetDetection": read_json(project.target_detection_json, None),
        "defaultTemplateCode": project.default_template_code,
        "defaultCodeQualityProfileCode": project.default_code_quality_profile_code,
        "defaultCodeQualityProviderCode": project.default_code_quality_provider_code,
        "status": project.status,
    }


def list_enabled_projects(
    db: Session,
    group_id: int | None = None,
    target_type: str | None = None,
    keyword: str | None = None,
    notification_status: str | None = None,
    review_status: str | None = None,
    page_no: int | None = None,
    page_size: int | None = None,
    include_disabled: bool = False,
) -> dict:
    from app.code_quality.repository import ensure_defaults
    from app.notification.repository import ensure_webhook_schema

    ensure_project_config_schema(db)
    ensure_webhook_schema(db)
    ensure_defaults(db)
    _ensure_default_project_group(db)
    db.commit()

    stmt: Select[tuple[Project]] = select(Project)
    if not include_disabled:
        stmt = stmt.where(Project.status == "ENABLED")
    if group_id is not None:
        stmt = stmt.where(Project.group_id == group_id)
    if target_type:
        stmt = stmt.where(Project.target_type == normalize_target_type(target_type))
    normalized_keyword = str(keyword or "").strip().lower()
    if normalized_keyword:
        search_value = f"%{normalized_keyword}%"
        stmt = stmt.where(
            or_(
                func.lower(Project.name).like(search_value),
                func.lower(Project.git_project_id).like(search_value),
                func.lower(Project.repository_url).like(search_value),
            )
        )

    projects = db.scalars(stmt.order_by(Project.id.desc())).all()
    items = _project_list_items(db, projects)
    normalized_notification_status = str(notification_status or "").strip().upper()
    if normalized_notification_status:
        if normalized_notification_status == "HEALTH_WARNING":
            items = [item for item in items if item["healthWarning"]]
        else:
            items = [
                item
                for item in items
                if item["notificationStatus"] == normalized_notification_status
            ]
    normalized_review_status = str(review_status or "").strip().upper()
    if normalized_review_status:
        items = [
            item
            for item in items
            if item["reviewStatus"] == normalized_review_status
        ]

    total = len(items)
    paging_requested = page_no is not None or page_size is not None
    safe_page_no = max(int(page_no or 1), 1)
    if not paging_requested:
        return page_response(items, safe_page_no, len(items), total)
    safe_page_size = min(max(int(page_size or 20), 1), 100)
    start = (safe_page_no - 1) * safe_page_size
    return page_response(
        items[start : start + safe_page_size],
        safe_page_no,
        safe_page_size,
        total,
    )


def _project_list_items(db: Session, projects: list[Project]) -> list[dict[str, Any]]:
    if not projects:
        return []

    from app.code_quality.models import (
        CodeQualityModelProvider,
        CodeQualityReviewProfile,
        CodeQualityReviewSettings,
    )
    from app.notification.models import (
        NotificationWebhook,
        ProjectNotificationWebhook,
    )
    from app.notification.repository import mask_webhook

    project_ids = [int(project.id) for project in projects]
    current_target_types = {
        int(project.id): effective_project_target_type(project)
        for project in projects
    }
    configs = db.scalars(
        select(ProjectTargetConfig).where(
            ProjectTargetConfig.project_id.in_(project_ids),
            ProjectTargetConfig.enabled.is_(True),
        )
    ).all()
    config_by_project: dict[int, ProjectTargetConfig] = {}
    for config in configs:
        project_id = int(config.project_id)
        if config.target_type == current_target_types[project_id]:
            config_by_project[project_id] = config

    settings_by_project = {
        int(settings.project_id): settings
        for settings in db.scalars(
            select(ProjectReviewSettings).where(
                ProjectReviewSettings.project_id.in_(project_ids)
            )
        ).all()
    }
    models_by_project: dict[int, list[ProjectAiReviewModel]] = {}
    project_models = db.scalars(
        select(ProjectAiReviewModel)
        .where(
            ProjectAiReviewModel.project_id.in_(project_ids),
            ProjectAiReviewModel.enabled.is_(True),
        )
        .order_by(
            ProjectAiReviewModel.project_id.asc(),
            ProjectAiReviewModel.sort_order.asc(),
            ProjectAiReviewModel.id.asc(),
        )
    ).all()
    for model in project_models:
        models_by_project.setdefault(int(model.project_id), []).append(model)

    webhook_rows = db.execute(
        select(ProjectNotificationWebhook, NotificationWebhook)
        .join(
            NotificationWebhook,
            NotificationWebhook.id == ProjectNotificationWebhook.webhook_id,
        )
        .where(
            ProjectNotificationWebhook.project_id.in_(project_ids),
            ProjectNotificationWebhook.enabled.is_(True),
        )
        .order_by(
            ProjectNotificationWebhook.project_id.asc(),
            NotificationWebhook.id.asc(),
        )
    ).all()
    webhooks_by_project: dict[
        int,
        list[tuple[ProjectNotificationWebhook, NotificationWebhook]],
    ] = {}
    for relation, webhook in webhook_rows:
        webhooks_by_project.setdefault(int(relation.project_id), []).append(
            (relation, webhook)
        )

    profile_code_by_project = {
        int(project.id): _project_list_profile_code(
            project,
            config_by_project.get(int(project.id)),
        )
        for project in projects
    }
    profile_codes = {
        profile_code
        for profile_code in profile_code_by_project.values()
        if profile_code
    }
    profiles_by_code = (
        {
            profile.profile_code: profile
            for profile in db.scalars(
                select(CodeQualityReviewProfile).where(
                    CodeQualityReviewProfile.profile_code.in_(profile_codes)
                )
            ).all()
        }
        if profile_codes
        else {}
    )

    settings_record = db.get(CodeQualityReviewSettings, 1)
    default_provider_code = (
        _blank_to_none(settings_record.default_provider_code)
        if settings_record is not None
        else None
    )
    provider_codes = {
        str(config.provider_code).upper()
        for config in configs
        if _blank_to_none(config.provider_code)
    }
    provider_codes.update(
        str(model.provider_code).upper()
        for model in project_models
        if _blank_to_none(model.provider_code)
    )
    provider_codes.update(
        str(profile.provider_code).upper()
        for profile in profiles_by_code.values()
        if _blank_to_none(profile.provider_code)
    )
    if default_provider_code:
        provider_codes.add(default_provider_code.upper())
    providers_by_code = (
        {
            provider.provider_code.upper(): provider
            for provider in db.scalars(
                select(CodeQualityModelProvider).where(
                    CodeQualityModelProvider.provider_code.in_(provider_codes)
                )
            ).all()
        }
        if provider_codes
        else {}
    )

    items = []
    for project in projects:
        project_id = int(project.id)
        config = config_by_project.get(project_id)
        profile_code = profile_code_by_project[project_id]
        profile = profiles_by_code.get(profile_code)
        profile_available = bool(
            profile is not None
            and profile.enabled
            and profile.status == "ENABLED"
        )
        review_model_names = _project_review_model_names(
            config,
            models_by_project.get(project_id, []),
            profile,
            default_provider_code,
            providers_by_code,
        )
        webhook_summary = _project_webhook_summary(
            webhooks_by_project.get(project_id, []),
            mask_webhook,
        )
        settings = settings_by_project.get(project_id)
        item = project_to_dict(project)
        item.update(
            {
                "reviewProfileCode": profile_code,
                "reviewModelNames": review_model_names,
                "triggerOnMr": (
                    bool(settings.trigger_on_mr)
                    if settings is not None
                    else True
                ),
                "triggerOnPush": (
                    bool(settings.trigger_on_push)
                    if settings is not None
                    else False
                ),
                "reviewStatus": (
                    "CONFIGURED"
                    if profile_available and review_model_names
                    else "UNCONFIGURED"
                ),
                **webhook_summary,
            }
        )
        items.append(item)
    return items


def _project_list_profile_code(
    project: Project,
    config: ProjectTargetConfig | None,
) -> str | None:
    if config is not None and _blank_to_none(config.code_quality_profile_code):
        return _blank_to_none(config.code_quality_profile_code)
    defaults = TARGET_TYPE_DEFAULTS.get(
        effective_project_target_type(project),
        TARGET_TYPE_DEFAULTS["GENERAL"],
    )
    return _blank_to_none(defaults.get("profileCode"))


def _project_review_model_names(
    config: ProjectTargetConfig | None,
    project_models: list[ProjectAiReviewModel],
    profile,
    default_provider_code: str | None,
    providers_by_code: dict[str, Any],
) -> list[str]:
    provider_codes: list[tuple[str, str | None, str | None]] = []
    if config is not None and _blank_to_none(config.provider_code):
        provider_codes.append((str(config.provider_code), None, None))
    elif project_models:
        provider_codes.extend(
            (
                str(model.provider_code),
                _blank_to_none(model.model_name),
                _blank_to_none(model.display_name),
            )
            for model in project_models
        )
    else:
        profile_provider_code = (
            _blank_to_none(profile.provider_code)
            if profile is not None
            else None
        )
        resolved_provider_code = profile_provider_code or default_provider_code
        if resolved_provider_code:
            provider_codes.append(
                (
                    resolved_provider_code,
                    _blank_to_none(profile.model) if profile is not None else None,
                    None,
                )
            )

    names: list[str] = []
    for provider_code, model_name, display_name in provider_codes:
        provider = providers_by_code.get(provider_code.upper())
        if provider is None or not provider.enabled:
            continue
        name = (
            display_name
            or model_name
            or _blank_to_none(provider.model_name)
            or provider.provider_name
        )
        if name and name not in names:
            names.append(name)
    return names


def _project_webhook_summary(
    rows: list[tuple[Any, Any]],
    mask_webhook,
) -> dict[str, Any]:
    webhooks = []
    enabled_webhooks = []
    for _relation, webhook in rows:
        enabled = bool(webhook.enabled) and webhook.status == "ENABLED"
        item = {
            "id": int(webhook.id),
            "name": webhook.name,
            "enabled": enabled,
            "status": webhook.status,
            "webhookMasked": mask_webhook(webhook.webhook_url),
            "lastTestStatus": webhook.last_test_status,
        }
        webhooks.append(item)
        if enabled:
            enabled_webhooks.append(item)
    if not webhooks:
        notification_status = "UNCONFIGURED"
    elif enabled_webhooks:
        notification_status = "CONFIGURED"
    else:
        notification_status = "ABNORMAL"
    return {
        "notificationStatus": notification_status,
        "healthWarning": any(
            item["lastTestStatus"] == "FAILED"
            for item in enabled_webhooks
        ),
        "webhooks": webhooks,
    }


def create_project(db: Session, request: dict) -> dict:
    ensure_project_config_schema(db)
    name = str(request.get("name") or "").strip()
    git_provider = str(request.get("gitProvider") or "GITLAB").strip().upper()
    git_project_id = str(request.get("gitProjectId") or "").strip()
    if not name:
        raise AppError("VALIDATION_ERROR", "name is required", 400)
    if not git_project_id:
        raise AppError("VALIDATION_ERROR", "gitProjectId is required", 400)
    existing = db.scalars(
        select(Project).where(Project.git_provider == git_provider, Project.git_project_id == git_project_id)
    ).first()
    if existing is not None:
        raise AppError("VALIDATION_ERROR", f"Project already exists: {git_provider}/{git_project_id}", 400)
    group_id = request.get("groupId")
    group = db.get(ProjectGroup, int(group_id)) if group_id is not None else _ensure_default_project_group(db)
    if group is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project group not found: {group_id}", 404)
    if group.status != "ENABLED":
        raise AppError("VALIDATION_ERROR", f"Project group is disabled: {group_id}", 400)
    target_types = _requested_target_types(request)
    primary = target_types[0]
    defaults = TARGET_TYPE_DEFAULTS.get(primary, TARGET_TYPE_DEFAULTS["BACKEND"])
    now = datetime.now()
    project = Project(
        group_id=group.id,
        name=name,
        git_provider=git_provider,
        git_project_id=git_project_id,
        repository_url=_blank_to_none(request.get("repositoryUrl")),
        target_type=primary,
        supported_target_types=json.dumps([primary], ensure_ascii=False),
        detected_target_types=None,
        target_detection_json=None,
        default_template_code=request.get("defaultTemplateCode") or defaults["templateCode"],
        default_code_quality_profile_code=request.get("defaultCodeQualityProfileCode") or defaults["profileCode"],
        default_code_quality_provider_code=_blank_to_none(request.get("defaultCodeQualityProviderCode")),
        dingtalk_webhook_id=None,
        status=request.get("status") or "ENABLED",
        description=_blank_to_none(request.get("description")) or "Manually created before GitLab webhook",
        created_at=now,
        updated_at=now,
    )
    db.add(project)
    db.flush()
    _create_default_project_review_settings(db, project)
    _create_manual_target_configs(db, project, target_types)
    db.commit()
    return project_to_dict(project)


def find_project_by_id(db: Session, project_id: int) -> Project | None:
    ensure_project_config_schema(db)
    return db.get(Project, project_id)


def find_project_by_git_project_id(db: Session, git_project_id: str) -> Project | None:
    ensure_project_config_schema(db)
    return db.scalars(
        select(Project).where(Project.git_provider == "GITLAB", Project.git_project_id == git_project_id)
    ).first()


def upsert_gitlab_project(
    db: Session,
    git_project_id: str,
    project_name: str,
    repository_url: str | None,
    changed_files: list[dict[str, Any]] | None = None,
) -> Project:
    ensure_project_config_schema(db)
    now = datetime.now()
    detection = detect_project_target_types(db, changed_files or [])
    project = find_project_by_git_project_id(db, git_project_id)
    if project:
        project.name = project_name
        project.repository_url = repository_url
        project.status = "ENABLED"
        _store_target_detection(project, detection)
        _get_or_create_project_review_settings(db, project)
        project.updated_at = now
        db.flush()
        return project

    detected_types = detection.get("targetTypes") or ["BACKEND"]
    primary = detected_types[0]
    defaults = TARGET_TYPE_DEFAULTS.get(primary, TARGET_TYPE_DEFAULTS["BACKEND"])
    project = Project(
        group_id=_ensure_default_project_group(db).id,
        name=project_name,
        git_provider="GITLAB",
        git_project_id=git_project_id,
        repository_url=repository_url,
        target_type=primary,
        supported_target_types=json.dumps([primary], ensure_ascii=False),
        detected_target_types=json.dumps(detected_types, ensure_ascii=False),
        target_detection_json=json.dumps(detection, ensure_ascii=False),
        default_template_code=defaults["templateCode"],
        default_code_quality_profile_code=defaults["profileCode"],
        default_code_quality_provider_code=None,
        dingtalk_webhook_id=None,
        status="ENABLED",
        description="Auto-created from GitLab webhook",
        created_at=now,
        updated_at=now,
    )
    db.add(project)
    db.flush()
    _create_default_project_review_settings(db, project)
    _create_detected_target_configs(db, project, [primary])
    return project


def update_project_target_detection(
    db: Session,
    project: Project,
    project_name: str | None,
    changed_files: list[dict[str, Any]] | None,
) -> Project:
    previous_detection = read_json(project.target_detection_json, {}) or {}
    existing_configs = db.scalars(
        select(ProjectTargetConfig).where(ProjectTargetConfig.project_id == project.id)
    ).all()
    can_complete_initial_detection = (
        effective_project_target_type(project) == "GENERAL"
        and not any(
            evidence.get("source") != "FALLBACK"
            for evidence in previous_detection.get("evidences") or []
            if isinstance(evidence, dict)
        )
        and existing_configs
        and all(
            config.description in SYSTEM_DETECTED_TARGET_CONFIG_DESCRIPTIONS
            for config in existing_configs
        )
    )
    detection = detect_project_target_types(db, changed_files or [])
    _store_target_detection(project, detection)
    detected_types = detection.get("targetTypes") or ["GENERAL"]
    primary = normalize_target_type(detected_types[0])
    if can_complete_initial_detection and primary != "GENERAL":
        defaults = TARGET_TYPE_DEFAULTS.get(primary, TARGET_TYPE_DEFAULTS["GENERAL"])
        for config in existing_configs:
            db.delete(config)
        db.flush()
        _set_project_supported_target_type(db, project, primary)
        project.default_template_code = defaults["templateCode"]
        project.default_code_quality_profile_code = defaults["profileCode"]
        _create_detected_target_configs(db, project, [primary])
    project.updated_at = datetime.now()
    db.flush()
    return project


def list_project_groups(db: Session) -> dict:
    ensure_project_config_schema(db)
    _ensure_default_project_group(db)
    db.commit()
    groups = db.scalars(select(ProjectGroup).where(ProjectGroup.status == "ENABLED").order_by(ProjectGroup.id.asc())).all()
    return page_response([project_group_to_dict(group) for group in groups], 1, len(groups), len(groups))


def project_group_to_dict(group: ProjectGroup) -> dict:
    session = Session.object_session(group)
    dingtalk_webhooks = []
    if session is not None:
        from app.notification.repository import project_group_webhooks_to_dict

        dingtalk_webhooks = project_group_webhooks_to_dict(session, int(group.id))
    return {
        "id": group.id,
        "groupCode": group.group_code,
        "groupName": group.group_name,
        "defaultCodeQualityProfileCode": group.default_code_quality_profile_code,
        "defaultProviderCode": group.default_provider_code,
        "reviewEngine": "AGENT",
        "agentSourceExportAllowed": True,
        "aiReviewModels": list_project_group_ai_review_models(session, int(group.id), include_fallback=True)
        if session is not None
        else [],
        "dingtalkWebhooks": dingtalk_webhooks,
        "enabledDingtalkWebhookCount": len([item for item in dingtalk_webhooks if item.get("enabled")]),
        "status": group.status,
        "description": group.description,
        **ai_review_policy_to_dict(group),
        **push_policy_to_dict(group),
    }


def list_project_group_ai_review_models(
    db: Session | None,
    group_id: int,
    *,
    include_fallback: bool = True,
) -> list[dict[str, Any]]:
    if db is None:
        return []
    _ensure_project_group_ai_review_model_schema(db)
    group = db.get(ProjectGroup, group_id)
    records = db.scalars(
        select(ProjectGroupAiReviewModel)
        .where(ProjectGroupAiReviewModel.group_id == group_id)
        .order_by(ProjectGroupAiReviewModel.sort_order.asc(), ProjectGroupAiReviewModel.id.asc())
    ).all()
    items = [project_group_ai_review_model_to_dict(record) for record in records]
    if items or not include_fallback or group is None or not _blank_to_none(group.default_provider_code):
        return items
    provider_code = _blank_to_none(group.default_provider_code)
    review_key = make_ai_review_model_key(provider_code or "default", None, 0)
    return [
        {
            "id": None,
            "groupId": group_id,
            "reviewKey": review_key,
            "providerCode": provider_code,
            "modelName": None,
            "displayName": provider_code,
            "enabled": True,
            "sortOrder": 10,
            "fallback": True,
        }
    ]


def project_group_ai_review_model_to_dict(record: ProjectGroupAiReviewModel) -> dict[str, Any]:
    return {
        "id": record.id,
        "groupId": record.group_id,
        "reviewKey": record.review_key,
        "providerCode": record.provider_code,
        "modelName": record.model_name,
        "displayName": record.display_name,
        "enabled": bool(record.enabled),
        "sortOrder": int(record.sort_order or 0),
    }


def create_project_group(db: Session, request: dict) -> dict:
    ensure_project_config_schema(db)
    now = datetime.now()
    group_name = str(request.get("groupName") or request.get("name") or "").strip()
    group_code = _blank_to_none(request.get("groupCode"))
    if not group_name:
        raise AppError("VALIDATION_ERROR", "groupName is required", 400)
    if not group_code:
        raise AppError("VALIDATION_ERROR", "groupCode is required", 400)
    _assert_group_code_available(db, group_code)
    group = ProjectGroup(
        group_name=group_name,
        group_code=group_code,
        default_code_quality_profile_code=_blank_to_none(request.get("defaultCodeQualityProfileCode")),
        default_provider_code=_blank_to_none(request.get("defaultProviderCode")),
        **_ai_review_policy_columns(request),
        **_push_policy_columns(request),
        status=request.get("status") or "ENABLED",
        description=_blank_to_none(request.get("description")),
        created_at=now,
        updated_at=now,
    )
    db.add(group)
    try:
        if "dingtalkWebhooks" in request:
            from app.notification.repository import upsert_webhooks

            db.flush()
            upsert_webhooks(db, request.get("dingtalkWebhooks") or [], int(group.id))
        if "aiReviewModels" in request:
            db.flush()
            _replace_project_group_ai_review_models(db, group, request.get("aiReviewModels") or [])
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError("VALIDATION_ERROR", f"Project group code already exists: {group_code}", 400) from exc
    return project_group_to_dict(group)


def update_project_group(db: Session, group_id: int, request: dict) -> dict:
    ensure_project_config_schema(db)
    group = db.get(ProjectGroup, group_id)
    if group is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project group not found: {group_id}", 404)
    if "groupName" in request or "name" in request:
        group.group_name = str(request.get("groupName") or request.get("name") or "").strip()
        if not group.group_name:
            raise AppError("VALIDATION_ERROR", "groupName is required", 400)
    if "groupCode" in request:
        next_code = _blank_to_none(request.get("groupCode"))
        if not next_code:
            raise AppError("VALIDATION_ERROR", "groupCode is required", 400)
        _assert_default_group_code_not_changed(group, next_code)
        _assert_group_code_available(db, next_code, exclude_group_id=group.id)
        group.group_code = next_code
    if "defaultProviderCode" in request:
        group.default_provider_code = _blank_to_none(request.get("defaultProviderCode"))
    if "defaultCodeQualityProfileCode" in request:
        group.default_code_quality_profile_code = _blank_to_none(request.get("defaultCodeQualityProfileCode"))
    _update_group_ai_review_policy(group, request)
    _update_group_push_policy(group, request)
    if "status" in request:
        _assert_default_group_can_keep_status(group, request["status"])
        group.status = request["status"]
    if "description" in request:
        group.description = _blank_to_none(request.get("description"))
    if "dingtalkWebhooks" in request:
        from app.notification.repository import upsert_webhooks

        upsert_webhooks(db, request.get("dingtalkWebhooks") or [], int(group.id))
    if "aiReviewModels" in request:
        _replace_project_group_ai_review_models(db, group, request.get("aiReviewModels") or [])
    group.updated_at = datetime.now()
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError("VALIDATION_ERROR", f"Project group code already exists: {group.group_code}", 400) from exc
    return project_group_to_dict(group)


def list_target_type_path_mappings(db: Session) -> list[dict[str, Any]]:
    ensure_project_config_schema(db)
    mappings = db.scalars(
        select(TargetTypePathMapping)
        .where(TargetTypePathMapping.target_type.in_(PATH_MAPPING_TARGET_TYPES))
        .order_by(TargetTypePathMapping.sort_order.asc(), TargetTypePathMapping.id.asc())
    ).all()
    return [target_type_path_mapping_to_dict(mapping) for mapping in mappings]


def update_target_type_path_mappings(db: Session, request: dict[str, Any]) -> list[dict[str, Any]]:
    ensure_project_config_schema(db)
    items = request.get("items") if isinstance(request, dict) else None
    if not isinstance(items, list):
        raise AppError("VALIDATION_ERROR", "items must be a list", 400)
    existing_by_type = {
        mapping.target_type: mapping
        for mapping in db.scalars(select(TargetTypePathMapping)).all()
    }
    now = datetime.now()
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise AppError("VALIDATION_ERROR", "items must contain mapping objects", 400)
        target_type = normalize_target_type(item.get("targetType"))
        if target_type not in PATH_MAPPING_TARGET_TYPES:
            raise AppError("VALIDATION_ERROR", f"{target_type} does not support path mapping", 400)
        if target_type in seen:
            raise AppError("VALIDATION_ERROR", f"Duplicate target type mapping: {target_type}", 400)
        seen.add(target_type)
        path_patterns = item.get("pathPatterns") or []
        if not isinstance(path_patterns, list):
            raise AppError("VALIDATION_ERROR", "pathPatterns must be a list", 400)
        mapping = existing_by_type.get(target_type)
        if mapping is None:
            mapping = TargetTypePathMapping(
                target_type=target_type,
                path_patterns=json.dumps(path_patterns, ensure_ascii=False),
                enabled=bool(item.get("enabled", True)),
                sort_order=int(item.get("sortOrder") if item.get("sortOrder") is not None else (index + 1) * 10),
                description=_blank_to_none(item.get("description")),
                created_at=now,
                updated_at=now,
            )
            db.add(mapping)
        else:
            mapping.path_patterns = json.dumps(path_patterns, ensure_ascii=False)
            mapping.enabled = bool(item.get("enabled", True))
            mapping.sort_order = int(item.get("sortOrder") if item.get("sortOrder") is not None else mapping.sort_order)
            mapping.description = _blank_to_none(item.get("description"))
            mapping.updated_at = now
    for target_type, mapping in existing_by_type.items():
        if target_type not in PATH_MAPPING_TARGET_TYPES and mapping.enabled:
            mapping.enabled = False
            mapping.updated_at = now
    db.commit()
    return list_target_type_path_mappings(db)


def target_type_path_mapping_to_dict(mapping: TargetTypePathMapping) -> dict[str, Any]:
    return {
        "id": mapping.id,
        "targetType": mapping.target_type,
        "pathPatterns": read_json_array(mapping.path_patterns),
        "enabled": bool(mapping.enabled),
        "sortOrder": int(mapping.sort_order or 0),
        "description": mapping.description,
    }


def _create_default_project_review_settings(db: Session, project: Project) -> ProjectReviewSettings:
    now = datetime.now()
    settings = ProjectReviewSettings(
        project_id=int(project.id),
        trigger_on_mr=True,
        trigger_on_push=False,
        trigger_only_when_risk_matched=False,
        auto_fix_preview_enabled=False,
        auto_fix_preview_severities=json.dumps(["MAJOR"], ensure_ascii=False),
        push_branch_patterns=json.dumps(DEFAULT_PUSH_REVIEW_POLICY["pushBranchPatterns"], ensure_ascii=False),
        push_min_changed_files=int(DEFAULT_PUSH_REVIEW_POLICY["pushMinChangedFiles"]),
        push_min_diff_bytes=int(DEFAULT_PUSH_REVIEW_POLICY["pushMinDiffBytes"]),
        push_min_commit_count=int(DEFAULT_PUSH_REVIEW_POLICY["pushMinCommitCount"]),
        push_max_changed_files=int(DEFAULT_PUSH_REVIEW_POLICY["pushMaxChangedFiles"]),
        push_max_diff_bytes=int(DEFAULT_PUSH_REVIEW_POLICY["pushMaxDiffBytes"]),
        push_debounce_seconds=int(DEFAULT_PUSH_REVIEW_POLICY["pushDebounceSeconds"]),
        created_at=now,
        updated_at=now,
    )
    db.add(settings)
    return settings


def _get_or_create_project_review_settings(db: Session, project: Project) -> ProjectReviewSettings:
    ensure_project_config_schema(db)
    settings = db.get(ProjectReviewSettings, int(project.id))
    if settings is None:
        settings = _create_default_project_review_settings(db, project)
        db.flush()
    return settings


def project_review_settings_response(db: Session, project_id: int) -> dict[str, Any]:
    project = find_project_by_id(db, project_id)
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {project_id}", 404)
    settings = _get_or_create_project_review_settings(db, project)
    db.commit()
    return project_review_settings_to_dict(settings)


def update_project_review_settings(db: Session, project_id: int, request: dict[str, Any]) -> dict[str, Any]:
    project = find_project_by_id(db, project_id)
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {project_id}", 404)
    settings = _get_or_create_project_review_settings(db, project)
    _apply_project_review_settings(settings, request)
    db.commit()
    return project_review_settings_to_dict(settings)


def _apply_project_review_settings(
    settings: ProjectReviewSettings,
    request: dict[str, Any],
) -> None:
    bool_fields = {
        "triggerOnMr": "trigger_on_mr",
        "triggerOnPush": "trigger_on_push",
        "triggerOnlyWhenRiskMatched": "trigger_only_when_risk_matched",
        "autoFixPreviewEnabled": "auto_fix_preview_enabled",
    }
    for json_field, column_name in bool_fields.items():
        if json_field in request and request[json_field] is not None:
            setattr(settings, column_name, bool(request[json_field]))
    if request.get("autoFixPreviewSeverities") is not None:
        settings.auto_fix_preview_severities = json.dumps(
            _normalize_auto_fix_preview_severities(request["autoFixPreviewSeverities"]),
            ensure_ascii=False,
        )
    if request.get("pushBranchPatterns") is not None:
        settings.push_branch_patterns = json.dumps(
            _normalize_branch_patterns(request["pushBranchPatterns"]),
            ensure_ascii=False,
        )
    int_fields = {
        "pushMinChangedFiles": "push_min_changed_files",
        "pushMinDiffBytes": "push_min_diff_bytes",
        "pushMinCommitCount": "push_min_commit_count",
        "pushMaxChangedFiles": "push_max_changed_files",
        "pushMaxDiffBytes": "push_max_diff_bytes",
        "pushDebounceSeconds": "push_debounce_seconds",
    }
    for json_field, column_name in int_fields.items():
        if json_field in request and request[json_field] is not None:
            setattr(settings, column_name, int(request[json_field]))
    settings.updated_at = datetime.now()


def get_project_push_policy(db: Session, project: Project) -> dict[str, Any]:
    return project_review_settings_to_dict(_get_or_create_project_review_settings(db, project))


def get_project_review_policy(db: Session, project: Project) -> dict[str, Any]:
    return {
        "reviewEngine": "AGENT",
        "agentSourceExportAllowed": True,
        "aiReviewEnabled": True,
        "triggerOnManual": True,
        **project_review_settings_to_dict(_get_or_create_project_review_settings(db, project)),
    }


def project_review_settings_to_dict(settings: ProjectReviewSettings) -> dict[str, Any]:
    return {
        "projectId": int(settings.project_id),
        "source": "PROJECT",
        "triggerOnMr": bool(settings.trigger_on_mr),
        "triggerOnPush": bool(settings.trigger_on_push),
        "triggerOnlyWhenRiskMatched": bool(settings.trigger_only_when_risk_matched),
        "autoFixPreviewEnabled": bool(settings.auto_fix_preview_enabled),
        "autoFixPreviewSeverities": read_json_array(settings.auto_fix_preview_severities) or ["MAJOR"],
        "pushBranchPatterns": (
            read_json_array(settings.push_branch_patterns)
            or list(DEFAULT_PUSH_REVIEW_POLICY["pushBranchPatterns"])
        ),
        "pushMinChangedFiles": _policy_int(settings.push_min_changed_files, "pushMinChangedFiles"),
        "pushMinDiffBytes": _policy_int(settings.push_min_diff_bytes, "pushMinDiffBytes"),
        "pushMinCommitCount": _policy_int(settings.push_min_commit_count, "pushMinCommitCount"),
        "pushMaxChangedFiles": _policy_int(settings.push_max_changed_files, "pushMaxChangedFiles"),
        "pushMaxDiffBytes": _policy_int(settings.push_max_diff_bytes, "pushMaxDiffBytes"),
        "pushDebounceSeconds": _policy_int(settings.push_debounce_seconds, "pushDebounceSeconds"),
    }


def resolve_project_review_profile_code(db: Session, project: Project, target_type: str | None) -> str | None:
    ensure_project_config_schema(db)
    normalized_target_type = normalize_target_type(target_type or effective_project_target_type(project))
    config = db.scalars(
        select(ProjectTargetConfig).where(
            ProjectTargetConfig.project_id == project.id,
            ProjectTargetConfig.target_type == normalized_target_type,
            ProjectTargetConfig.enabled.is_(True),
        )
    ).first()
    if config is not None and _blank_to_none(config.code_quality_profile_code):
        return _blank_to_none(config.code_quality_profile_code)
    defaults = TARGET_TYPE_DEFAULTS.get(normalized_target_type, TARGET_TYPE_DEFAULTS["GENERAL"])
    return defaults.get("profileCode")


def push_policy_to_dict(group: ProjectGroup | None) -> dict[str, Any]:
    return {
        "pushBranchPatterns": read_json_array(getattr(group, "push_branch_patterns", None)) or list(DEFAULT_PUSH_REVIEW_POLICY["pushBranchPatterns"]),
        "pushMinChangedFiles": _policy_int(getattr(group, "push_min_changed_files", None), "pushMinChangedFiles"),
        "pushMinDiffBytes": _policy_int(getattr(group, "push_min_diff_bytes", None), "pushMinDiffBytes"),
        "pushMinCommitCount": _policy_int(getattr(group, "push_min_commit_count", None), "pushMinCommitCount"),
        "pushMaxChangedFiles": _policy_int(getattr(group, "push_max_changed_files", None), "pushMaxChangedFiles"),
        "pushMaxDiffBytes": _policy_int(getattr(group, "push_max_diff_bytes", None), "pushMaxDiffBytes"),
        "pushDebounceSeconds": _policy_int(getattr(group, "push_debounce_seconds", None), "pushDebounceSeconds"),
    }


def ai_review_policy_to_dict(group: ProjectGroup | None) -> dict[str, Any]:
    return {
        "reviewEngine": "AGENT",
        "agentSourceExportAllowed": True,
        "aiReviewEnabled": True,
        "triggerOnManual": True,
        "triggerOnMr": _policy_bool(getattr(group, "trigger_on_mr", None), "triggerOnMr"),
        "triggerOnPush": _policy_bool(getattr(group, "trigger_on_push", None), "triggerOnPush"),
        "triggerOnlyWhenRiskMatched": _policy_bool(
            getattr(group, "trigger_only_when_risk_matched", None),
            "triggerOnlyWhenRiskMatched",
        ),
        "autoFixPreviewEnabled": _policy_bool(getattr(group, "auto_fix_preview_enabled", None), "autoFixPreviewEnabled"),
        "autoFixPreviewSeverities": read_json_array(getattr(group, "auto_fix_preview_severities", None))
        or list(DEFAULT_GROUP_AI_REVIEW_POLICY["autoFixPreviewSeverities"]),
    }


def update_project_group_binding(db: Session, project_id: int, request: dict) -> dict:
    project = find_project_by_id(db, project_id)
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {project_id}", 404)
    group_id = request.get("groupId")
    group = db.get(ProjectGroup, int(group_id)) if group_id is not None else None
    if group_id is not None and group is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project group not found: {group_id}", 404)
    if group is not None and group.status != "ENABLED":
        raise AppError("VALIDATION_ERROR", f"Project group is disabled: {group_id}", 400)
    project.group_id = group.id if group else None
    project.updated_at = datetime.now()
    db.commit()
    return project_to_dict(project)


def list_project_target_configs(db: Session, project_id: int) -> list[dict]:
    project = find_project_by_id(db, project_id)
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {project_id}", 404)
    configs = db.scalars(
        select(ProjectTargetConfig)
        .where(ProjectTargetConfig.project_id == project_id)
        .order_by(ProjectTargetConfig.target_type.asc())
    ).all()
    if not configs:
        return [_default_target_config_response(project)]
    return [target_config_to_dict(config) for config in configs]


def ambiguous_auto_detected_target_types(db: Session, project: Project) -> list[str]:
    if _blank_to_none(project.target_type):
        return []
    target_types = read_json_array(project.detected_target_types)
    if len(target_types) <= 1:
        return []
    configs = db.scalars(
        select(ProjectTargetConfig).where(ProjectTargetConfig.project_id == project.id)
    ).all()
    if configs and not all(config.description in SYSTEM_DETECTED_TARGET_CONFIG_DESCRIPTIONS for config in configs):
        return []
    return target_types


def upsert_project_target_config(db: Session, project_id: int, target_type: str, request: dict) -> dict:
    project = find_project_by_id(db, project_id)
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {project_id}", 404)
    if db.scalar(select(func.count()).select_from(ProjectTargetConfig).where(ProjectTargetConfig.project_id == project_id)) == 0:
        ensure_default_target_configs(db, project)
    normalized = normalize_target_type(target_type)
    defaults = TARGET_TYPE_DEFAULTS.get(normalized, TARGET_TYPE_DEFAULTS["GENERAL"])
    config = find_target_config(db, project_id, normalized)
    now = datetime.now()
    if config is None:
        config = ProjectTargetConfig(
            project_id=project_id,
            target_type=normalized,
            template_code=request.get("templateCode") or defaults["templateCode"],
            code_quality_profile_code=request.get("codeQualityProfileCode") or defaults["profileCode"],
            provider_code=_blank_to_none(request.get("providerCode")),
            path_patterns=json.dumps(request.get("pathPatterns") or defaults["pathPatterns"], ensure_ascii=False),
            reminder_card_enabled=bool(request.get("reminderCardEnabled", defaults["reminderCardEnabled"])),
            enabled=True,
            description=_blank_to_none(request.get("description")) or "手动维护的端类型配置",
            created_at=now,
            updated_at=now,
        )
        db.add(config)
    else:
        if "templateCode" in request:
            config.template_code = request["templateCode"]
        if "codeQualityProfileCode" in request:
            config.code_quality_profile_code = request["codeQualityProfileCode"]
        if "providerCode" in request:
            config.provider_code = _blank_to_none(request.get("providerCode"))
        if "pathPatterns" in request:
            config.path_patterns = json.dumps(request.get("pathPatterns") or [], ensure_ascii=False)
        if "reminderCardEnabled" in request:
            config.reminder_card_enabled = bool(request["reminderCardEnabled"])
        config.enabled = True
        if "description" in request:
            config.description = _blank_to_none(request.get("description"))
        elif config.description in SYSTEM_DETECTED_TARGET_CONFIG_DESCRIPTIONS:
            config.description = "手动维护的端类型配置"
        config.updated_at = now
    for existing in db.scalars(
        select(ProjectTargetConfig).where(ProjectTargetConfig.project_id == project_id)
    ).all():
        existing.enabled = existing is config
        existing.updated_at = now
    _set_project_supported_target_type(db, project, normalized)
    db.commit()
    return target_config_to_dict(config)


def ensure_default_target_configs(db: Session, project: Project) -> None:
    target_type = effective_project_target_type(project)
    existing_configs = db.scalars(
        select(ProjectTargetConfig).where(ProjectTargetConfig.project_id == project.id)
    ).all()
    selected = next((config for config in existing_configs if config.target_type == target_type), None)
    if selected is None:
        defaults = TARGET_TYPE_DEFAULTS.get(target_type, TARGET_TYPE_DEFAULTS["GENERAL"])
        now = datetime.now()
        selected = ProjectTargetConfig(
            project_id=project.id,
            target_type=target_type,
            template_code=project.default_template_code or defaults["templateCode"],
            code_quality_profile_code=project.default_code_quality_profile_code or defaults["profileCode"],
            provider_code=project.default_code_quality_provider_code,
            path_patterns=json.dumps(defaults["pathPatterns"], ensure_ascii=False),
            reminder_card_enabled=bool(defaults["reminderCardEnabled"]),
            enabled=True,
            description="单端类型默认配置",
            created_at=now,
            updated_at=now,
        )
        db.add(selected)
        existing_configs.append(selected)
    for config in existing_configs:
        config.enabled = config is selected
    _set_project_supported_target_type(db, project, target_type)
    db.flush()


def find_target_config(db: Session, project_id: int, target_type: str) -> ProjectTargetConfig | None:
    ensure_project_config_schema(db)
    return db.scalars(
        select(ProjectTargetConfig)
        .where(ProjectTargetConfig.project_id == project_id, ProjectTargetConfig.target_type == normalize_target_type(target_type))
    ).first()


def resolve_project_target_config(
    db: Session,
    project: Project,
    changed_files: list[dict] | None,
    requested_target_type: str | None = None,
    requested_target_types: list[str] | None = None,
) -> dict:
    del changed_files, requested_target_type, requested_target_types
    ensure_default_target_configs(db, project)
    primary = effective_project_target_type(project)
    config = db.scalars(
        select(ProjectTargetConfig).where(
            ProjectTargetConfig.project_id == project.id,
            ProjectTargetConfig.target_type == primary,
            ProjectTargetConfig.enabled.is_(True),
        )
    ).first()
    defaults = TARGET_TYPE_DEFAULTS.get(primary, TARGET_TYPE_DEFAULTS["GENERAL"])
    return {
        "targetType": primary,
        "targetTypes": [primary],
        "templateCode": (config.template_code if config else None) or defaults["templateCode"],
        "profileCode": resolve_project_review_profile_code(db, project, primary),
        "providerCode": config.provider_code if config else None,
        "reminderCardEnabled": _reminder_card_enabled(primary, config, defaults),
    }


def target_config_to_dict(config: ProjectTargetConfig) -> dict:
    return {
        "id": config.id,
        "projectId": config.project_id,
        "targetType": config.target_type,
        "templateCode": config.template_code,
        "codeQualityProfileCode": config.code_quality_profile_code,
        "providerCode": config.provider_code,
        "pathPatterns": read_json_array(config.path_patterns),
        "reminderCardEnabled": _reminder_card_enabled(
            config.target_type,
            config,
            TARGET_TYPE_DEFAULTS.get(config.target_type, TARGET_TYPE_DEFAULTS["GENERAL"]),
        ),
        "enabled": bool(config.enabled),
        "description": config.description,
    }


def list_project_ai_review_models(
    db: Session,
    project_id: int,
    *,
    enabled_only: bool = False,
) -> list[dict[str, Any]]:
    ensure_project_config_schema(db)
    stmt = select(ProjectAiReviewModel).where(ProjectAiReviewModel.project_id == project_id)
    if enabled_only:
        stmt = stmt.where(ProjectAiReviewModel.enabled.is_(True))
    records = db.scalars(
        stmt.order_by(ProjectAiReviewModel.sort_order.asc(), ProjectAiReviewModel.id.asc())
    ).all()
    return [project_ai_review_model_to_dict(record) for record in records]


def project_ai_review_model_to_dict(record: ProjectAiReviewModel) -> dict[str, Any]:
    return {
        "id": record.id,
        "projectId": record.project_id,
        "reviewKey": record.review_key,
        "providerCode": record.provider_code,
        "modelName": record.model_name,
        "displayName": record.display_name,
        "enabled": bool(record.enabled),
        "sortOrder": int(record.sort_order),
    }


def project_configuration_response(db: Session, project_id: int) -> dict[str, Any]:
    project = find_project_by_id(db, project_id)
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {project_id}", 404)
    settings = _get_or_create_project_review_settings(db, project)
    db.commit()
    return _project_configuration_to_dict(db, project, settings)


def update_project_configuration(
    db: Session,
    project_id: int,
    request: dict[str, Any],
) -> dict[str, Any]:
    project = find_project_by_id(db, project_id)
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {project_id}", 404)
    try:
        target_type = normalize_target_type(request["targetType"])
        target_request = request["targetConfig"]
        template_code = str(target_request["templateCode"]).strip()
        profile_code = _blank_to_none(target_request.get("codeQualityProfileCode"))
        provider_code = _blank_to_none(target_request.get("providerCode"))
        provider_code = provider_code.upper() if provider_code else None
        model_requests = request.get("aiReviewModels") or []
        webhook_ids = list(dict.fromkeys(int(value) for value in request.get("webhookIds") or []))
        _validate_project_configuration(
            db,
            target_type,
            target_request,
            model_requests,
            webhook_ids,
        )
        now = datetime.now()
        configs = db.scalars(
            select(ProjectTargetConfig).where(ProjectTargetConfig.project_id == project_id)
        ).all()
        config = next((item for item in configs if item.target_type == target_type), None)
        if config is None:
            config = ProjectTargetConfig(
                project_id=project_id,
                target_type=target_type,
                template_code=template_code,
                code_quality_profile_code=profile_code,
                provider_code=provider_code,
                path_patterns=json.dumps(
                    _normalize_path_patterns(target_request.get("pathPatterns")),
                    ensure_ascii=False,
                ),
                reminder_card_enabled=bool(target_request["reminderCardEnabled"]),
                enabled=True,
                description="项目综合配置维护",
                created_at=now,
                updated_at=now,
            )
            db.add(config)
            configs.append(config)
        else:
            config.template_code = template_code
            config.code_quality_profile_code = profile_code
            config.provider_code = provider_code
            config.path_patterns = json.dumps(
                _normalize_path_patterns(target_request.get("pathPatterns")),
                ensure_ascii=False,
            )
            config.reminder_card_enabled = bool(target_request["reminderCardEnabled"])
            config.description = "项目综合配置维护"
            config.updated_at = now
        for item in configs:
            item.enabled = item is config
            item.updated_at = now
        _set_project_supported_target_type(db, project, target_type)
        project.default_template_code = config.template_code
        project.default_code_quality_profile_code = config.code_quality_profile_code
        project.default_code_quality_provider_code = config.provider_code
        settings = _get_or_create_project_review_settings(db, project)
        _apply_project_review_settings(settings, request["reviewSettings"])
        _replace_project_ai_review_models(db, project, model_requests)
        _replace_project_notification_webhooks(db, project, webhook_ids)
        project.updated_at = now
        db.commit()
        return _project_configuration_to_dict(db, project, settings)
    except Exception:
        db.rollback()
        raise


def _project_configuration_to_dict(
    db: Session,
    project: Project,
    settings: ProjectReviewSettings,
) -> dict[str, Any]:
    from app.notification.models import ProjectNotificationWebhook

    target_type = effective_project_target_type(project)
    config = db.scalars(
        select(ProjectTargetConfig).where(
            ProjectTargetConfig.project_id == project.id,
            ProjectTargetConfig.target_type == target_type,
            ProjectTargetConfig.enabled.is_(True),
        )
    ).first()
    webhook_ids = [
        int(value)
        for value in db.scalars(
            select(ProjectNotificationWebhook.webhook_id)
            .where(
                ProjectNotificationWebhook.project_id == project.id,
                ProjectNotificationWebhook.enabled.is_(True),
            )
            .order_by(ProjectNotificationWebhook.webhook_id.asc())
        ).all()
    ]
    return {
        "projectId": int(project.id),
        "targetType": target_type,
        "targetTypes": [target_type],
        "targetConfig": (
            target_config_to_dict(config)
            if config is not None
            else _default_target_config_response(project)
        ),
        "aiReviewModels": list_project_ai_review_models(db, int(project.id)),
        "reviewSettings": project_review_settings_to_dict(settings),
        "webhookIds": webhook_ids,
    }


def project_configuration_defaults_response(
    target_type: str,
) -> dict[str, Any]:
    normalized_target_type = normalize_target_type(target_type)
    return {
        "targetType": normalized_target_type,
        "targetConfig": _target_configuration_defaults(normalized_target_type),
    }


def project_target_type_auto_detection_preview(
    db: Session,
    project_id: int,
) -> dict[str, Any]:
    project = find_project_by_id(db, project_id)
    if project is None:
        raise AppError(
            "RESOURCE_NOT_FOUND",
            f"Project not found: {project_id}",
            404,
        )
    detection, detected_target_types, evidence_version = (
        _project_target_detection_state(project)
    )
    detected_target_type = detected_target_types[0]
    current_target_type = effective_project_target_type(project)
    current_config = db.scalars(
        select(ProjectTargetConfig).where(
            ProjectTargetConfig.project_id == project.id,
            ProjectTargetConfig.target_type == current_target_type,
            ProjectTargetConfig.enabled.is_(True),
        )
    ).first()
    current_target_config = (
        target_config_to_dict(current_config)
        if current_config is not None
        else _default_target_config_response(project)
    )
    target_config = _target_configuration_defaults(detected_target_type)
    changes = []
    for field in (
        "targetType",
        "templateCode",
        "codeQualityProfileCode",
        "providerCode",
        "pathPatterns",
        "reminderCardEnabled",
    ):
        before = (
            current_target_type
            if field == "targetType"
            else current_target_config.get(field)
        )
        after = (
            detected_target_type
            if field == "targetType"
            else target_config.get(field)
        )
        if before != after:
            changes.append(
                {
                    "field": field,
                    "before": before,
                    "after": after,
                }
            )
    return {
        "projectId": int(project.id),
        "currentTargetType": current_target_type,
        "detectedTargetType": detected_target_type,
        "detectedTargetTypes": detected_target_types,
        "evidences": detection["evidences"],
        "evidenceUpdatedAt": detection.get("updatedAt"),
        "evidenceVersion": evidence_version,
        "currentTargetConfig": current_target_config,
        "targetConfig": target_config,
        "changes": changes,
    }


def apply_project_target_type_auto_detection(
    db: Session,
    project_id: int,
    request: dict[str, Any],
) -> dict[str, Any]:
    try:
        preview = project_target_type_auto_detection_preview(db, project_id)
        if request.get("evidenceVersion") != preview["evidenceVersion"]:
            raise AppError(
                "PROJECT_TARGET_DETECTION_STALE",
                "Project target detection evidence changed; refresh the preview",
                409,
            )
        target_type = normalize_target_type(request.get("targetType"))
        if target_type != preview["detectedTargetType"]:
            raise AppError(
                "PROJECT_TARGET_DETECTION_STALE",
                "Selected target type no longer matches current detection evidence",
                409,
            )

        project = find_project_by_id(db, project_id)
        if project is None:
            raise AppError(
                "RESOURCE_NOT_FOUND",
                f"Project not found: {project_id}",
                404,
            )
        defaults = TARGET_TYPE_DEFAULTS[target_type]
        configs = db.scalars(
            select(ProjectTargetConfig).where(
                ProjectTargetConfig.project_id == project.id
            )
        ).all()
        selected = next(
            (
                config
                for config in configs
                if config.target_type == target_type
            ),
            None,
        )
        now = datetime.now()
        if selected is None:
            selected = ProjectTargetConfig(
                project_id=project.id,
                target_type=target_type,
                template_code=defaults["templateCode"],
                code_quality_profile_code=defaults["profileCode"],
                provider_code=None,
                path_patterns=json.dumps(
                    defaults["pathPatterns"],
                    ensure_ascii=False,
                ),
                reminder_card_enabled=bool(defaults["reminderCardEnabled"]),
                enabled=True,
                description="恢复自动识别的端类型配置",
                created_at=now,
                updated_at=now,
            )
            db.add(selected)
            configs.append(selected)
        else:
            selected.template_code = defaults["templateCode"]
            selected.code_quality_profile_code = defaults["profileCode"]
            selected.provider_code = None
            selected.path_patterns = json.dumps(
                defaults["pathPatterns"],
                ensure_ascii=False,
            )
            selected.reminder_card_enabled = bool(
                defaults["reminderCardEnabled"]
            )
            selected.description = "恢复自动识别的端类型配置"
            selected.updated_at = now
        for config in configs:
            config.enabled = config is selected
            config.updated_at = now

        _set_project_supported_target_type(db, project, target_type)
        project.default_template_code = defaults["templateCode"]
        project.default_code_quality_profile_code = defaults["profileCode"]
        project.default_code_quality_provider_code = None
        project.updated_at = now
        settings = _get_or_create_project_review_settings(db, project)
        db.commit()
        return {
            "projectId": int(project.id),
            "appliedTargetType": target_type,
            "evidenceVersion": preview["evidenceVersion"],
            "configuration": _project_configuration_to_dict(
                db,
                project,
                settings,
            ),
        }
    except Exception:
        db.rollback()
        raise


def _target_configuration_defaults(target_type: str) -> dict[str, Any]:
    normalized_target_type = normalize_target_type(target_type)
    defaults = TARGET_TYPE_DEFAULTS.get(
        normalized_target_type,
        TARGET_TYPE_DEFAULTS["GENERAL"],
    )
    return {
        "targetType": normalized_target_type,
        "templateCode": defaults["templateCode"],
        "codeQualityProfileCode": defaults["profileCode"],
        "providerCode": None,
        "pathPatterns": list(defaults["pathPatterns"]),
        "reminderCardEnabled": bool(defaults["reminderCardEnabled"]),
    }


def _project_target_detection_state(
    project: Project,
) -> tuple[dict[str, Any], list[str], str]:
    detection = read_json(project.target_detection_json, None)
    if not isinstance(detection, dict):
        raise AppError(
            "PROJECT_TARGET_DETECTION_UNAVAILABLE",
            "Project target detection evidence is unavailable",
            409,
        )
    evidences = [
        item
        for item in detection.get("evidences") or []
        if isinstance(item, dict)
    ]
    detected_target_types = []
    for value in detection.get("targetTypes") or []:
        normalized = str(value or "").strip().upper().replace("-", "_")
        if (
            normalized in TARGET_TYPE_DEFAULTS
            and normalized not in detected_target_types
        ):
            detected_target_types.append(normalized)
    if not evidences or not detected_target_types:
        raise AppError(
            "PROJECT_TARGET_DETECTION_UNAVAILABLE",
            "Project target detection evidence is incomplete",
            409,
        )
    canonical = json.dumps(
        detection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    evidence_version = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    normalized_detection = {
        **detection,
        "evidences": evidences,
        "targetTypes": detected_target_types,
    }
    return normalized_detection, detected_target_types, evidence_version


def _validate_project_configuration(
    db: Session,
    target_type: str,
    target_request: dict[str, Any],
    model_requests: list[dict[str, Any]],
    webhook_ids: list[int],
) -> None:
    from app.code_quality.models import CodeQualityModelProvider, CodeQualityReviewProfile
    from app.notification.models import NotificationWebhook
    from app.rule_template.models import RuleTemplate

    template_code = str(target_request.get("templateCode") or "").strip()
    template = db.scalars(
        select(RuleTemplate)
        .where(
            RuleTemplate.template_code == template_code,
            RuleTemplate.status == "ENABLED",
        )
        .order_by(RuleTemplate.version.desc())
    ).first()
    if template is None:
        raise AppError("VALIDATION_ERROR", f"Rule template is unavailable: {template_code}", 400)
    profile_code = _blank_to_none(target_request.get("codeQualityProfileCode"))
    if profile_code:
        profile = db.scalars(
            select(CodeQualityReviewProfile).where(
                CodeQualityReviewProfile.profile_code == profile_code,
                CodeQualityReviewProfile.enabled.is_(True),
                CodeQualityReviewProfile.status == "ENABLED",
            )
        ).first()
        if profile is None:
            raise AppError(
                "VALIDATION_ERROR",
                f"Code quality review profile is unavailable: {profile_code}",
                400,
            )
    _normalize_path_patterns(target_request.get("pathPatterns"))
    provider_codes = {
        value.upper()
        for value in [_blank_to_none(target_request.get("providerCode"))]
        if value
    }
    provider_codes.update(
        str(item.get("providerCode") or "").strip().upper()
        for item in model_requests
        if item.get("providerCode")
    )
    if provider_codes:
        providers = db.scalars(
            select(CodeQualityModelProvider).where(
                CodeQualityModelProvider.provider_code.in_(provider_codes),
                CodeQualityModelProvider.enabled.is_(True),
            )
        ).all()
        found_codes = {str(provider.provider_code).upper() for provider in providers}
        missing = sorted(provider_codes - found_codes)
        if missing:
            raise AppError("VALIDATION_ERROR", f"Model provider is unavailable: {missing[0]}", 400)
    if webhook_ids:
        webhooks = db.scalars(
            select(NotificationWebhook).where(
                NotificationWebhook.id.in_(webhook_ids),
                NotificationWebhook.channel == "DINGTALK",
            )
        ).all()
        found_webhook_ids = {int(webhook.id) for webhook in webhooks}
        missing_webhooks = sorted(set(webhook_ids) - found_webhook_ids)
        if missing_webhooks:
            raise AppError(
                "RESOURCE_NOT_FOUND",
                f"Notification webhook not found: {missing_webhooks[0]}",
                404,
            )
    if target_type != "BACKEND" and target_request.get("reminderCardEnabled"):
        raise AppError(
            "VALIDATION_ERROR",
            "reminderCardEnabled is only supported for BACKEND projects",
            400,
        )


def _replace_project_ai_review_models(
    db: Session,
    project: Project,
    raw_items: list[dict[str, Any]],
) -> None:
    for record in db.scalars(
        select(ProjectAiReviewModel).where(ProjectAiReviewModel.project_id == project.id)
    ).all():
        db.delete(record)
    db.flush()
    now = datetime.now()
    seen_keys: set[str] = set()
    seen_provider_models: set[tuple[str, str | None]] = set()
    for index, raw_item in enumerate(raw_items):
        provider_code = str(raw_item.get("providerCode") or "").strip().upper()
        model_name = _blank_to_none(raw_item.get("modelName"))
        provider_model = (provider_code, model_name)
        if provider_model in seen_provider_models:
            raise AppError(
                "VALIDATION_ERROR",
                f"Duplicate project AI Review provider/model: {provider_code}/{model_name or 'default'}",
                400,
            )
        seen_provider_models.add(provider_model)
        review_key = _blank_to_none(raw_item.get("reviewKey")) or make_ai_review_model_key(
            provider_code,
            model_name,
            index,
        )
        if review_key in seen_keys:
            raise AppError(
                "VALIDATION_ERROR",
                f"Duplicate project AI Review reviewKey: {review_key}",
                400,
            )
        seen_keys.add(review_key)
        db.add(
            ProjectAiReviewModel(
                project_id=project.id,
                review_key=review_key,
                provider_code=provider_code,
                model_name=model_name,
                display_name=_blank_to_none(raw_item.get("displayName")),
                enabled=bool(raw_item.get("enabled", True)),
                sort_order=int(raw_item.get("sortOrder") or 0),
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()


def _replace_project_notification_webhooks(
    db: Session,
    project: Project,
    webhook_ids: list[int],
) -> None:
    from app.notification.models import ProjectNotificationWebhook

    for record in db.scalars(
        select(ProjectNotificationWebhook).where(
            ProjectNotificationWebhook.project_id == project.id
        )
    ).all():
        db.delete(record)
    db.flush()
    now = datetime.now()
    for webhook_id in webhook_ids:
        db.add(
            ProjectNotificationWebhook(
                project_id=project.id,
                webhook_id=webhook_id,
                enabled=True,
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()


def _normalize_path_patterns(value: Any) -> list[str]:
    patterns = []
    for item in value if isinstance(value, list) else []:
        pattern = str(item or "").strip()
        if pattern and pattern not in patterns:
            patterns.append(pattern)
    if not patterns:
        raise AppError("VALIDATION_ERROR", "pathPatterns must contain at least one pattern", 400)
    return patterns


def _default_target_config_response(project: Project) -> dict:
    target_type = effective_project_target_type(project)
    defaults = TARGET_TYPE_DEFAULTS.get(target_type, TARGET_TYPE_DEFAULTS["GENERAL"])
    return {
        "id": None,
        "projectId": project.id,
        "targetType": target_type,
        "templateCode": project.default_template_code or defaults["templateCode"],
        "codeQualityProfileCode": project.default_code_quality_profile_code or defaults["profileCode"],
        "providerCode": project.default_code_quality_provider_code,
        "pathPatterns": defaults["pathPatterns"],
        "reminderCardEnabled": bool(defaults["reminderCardEnabled"]),
        "enabled": True,
        "description": "单端类型默认配置（未保存）",
    }


def _reminder_card_enabled(target_type: str, config: ProjectTargetConfig | None, defaults: dict[str, Any]) -> bool:
    if normalize_target_type(target_type) != "BACKEND":
        return False
    return bool(config.reminder_card_enabled) if config else bool(defaults.get("reminderCardEnabled"))


def effective_project_target_type(project: Project) -> str:
    if _blank_to_none(project.target_type):
        return normalize_target_type(project.target_type)
    legacy_types = read_json_array(project.supported_target_types)
    return normalize_target_type(legacy_types[0] if legacy_types else None)


def normalize_target_type(value: str | None) -> str:
    normalized = str(value or "BACKEND").strip().upper().replace("-", "_")
    return normalized if normalized in TARGET_TYPE_DEFAULTS else "GENERAL"


def _match_target_types(configs: list[ProjectTargetConfig], changed_files: list[dict]) -> list[str]:
    paths = [str(file.get("path") or file.get("newPath") or file.get("oldPath") or "") for file in changed_files if isinstance(file, dict)]
    matched: list[str] = []
    for config in configs:
        patterns = read_json_array(config.path_patterns)
        if any(_path_matches(path, pattern) for path in paths for pattern in patterns):
            matched.append(config.target_type)
    return matched


def detect_project_target_types(db: Session, changed_files: list[dict[str, Any]]) -> dict:
    evidences: list[dict[str, str]] = []
    matched: list[str] = []
    paths = [
        str(file.get("path") or file.get("newPath") or file.get("oldPath") or "")
        for file in changed_files
        if isinstance(file, dict)
    ]
    mappings = db.scalars(
        select(TargetTypePathMapping)
        .where(TargetTypePathMapping.enabled.is_(True))
        .where(TargetTypePathMapping.target_type.in_(PATH_MAPPING_TARGET_TYPES))
        .order_by(TargetTypePathMapping.sort_order.asc(), TargetTypePathMapping.id.asc())
    ).all()
    for mapping in mappings:
        target_type = mapping.target_type
        patterns = read_json_array(mapping.path_patterns)
        for path in paths:
            matched_pattern = next((pattern for pattern in patterns if _path_matches(path, pattern)), None)
            if not matched_pattern:
                continue
            _append_unique_target(matched, target_type)
            _append_target_detection_evidence(
                evidences,
                target_type=target_type,
                source="PATH_MAPPING",
                value=path,
                pattern=matched_pattern,
                reason=f"{path} matches path mapping {matched_pattern}",
            )
            break
    if not matched:
        matched = ["GENERAL"]
        evidences.append(
            {
                "targetType": "GENERAL",
                "source": "FALLBACK",
                "value": "",
                "pattern": "no path mapping matched",
                "reason": "no target type path mapping matched; fallback to GENERAL",
            }
        )
    return {
        "targetTypes": matched,
        "evidences": evidences,
        "updatedAt": datetime.now().isoformat(timespec="seconds"),
    }


def _append_target_detection_evidence(
    evidences: list[dict[str, str]],
    *,
    target_type: str,
    source: str,
    value: str,
    pattern: str,
    reason: str,
) -> None:
    if any(
        item.get("targetType") == target_type
        and item.get("value") == value
        and item.get("pattern") == pattern
        for item in evidences
    ):
        return
    evidences.append(
        {
            "targetType": target_type,
            "source": source,
            "value": value,
            "pattern": pattern,
            "reason": reason,
        }
    )


def make_ai_review_model_key(provider_code: str, model_name: str | None, index: int = 0) -> str:
    provider_part = _slug(provider_code or "provider")
    model_part = _slug(model_name or "default")
    base = f"{provider_part}-{model_part}".strip("-") or "default"
    if len(base) <= 48:
        return base
    digest = hashlib.sha1(f"{provider_code}:{model_name}:{index}".encode("utf-8")).hexdigest()[:10]
    return f"{base[:37].rstrip('-')}-{digest}"


def _slug(value: str | None) -> str:
    text_value = str(value or "").strip().lower()
    text_value = re.sub(r"[^a-z0-9]+", "-", text_value).strip("-")
    return text_value or "default"


def _replace_project_group_ai_review_models(
    db: Session,
    group: ProjectGroup,
    raw_items: list[dict[str, Any]],
) -> None:
    _ensure_project_group_ai_review_model_schema(db)
    for record in db.scalars(
        select(ProjectGroupAiReviewModel).where(ProjectGroupAiReviewModel.group_id == group.id)
    ).all():
        db.delete(record)
    # Flush deletes before inserting replacement rows, otherwise MySQL unique
    # constraints can see the old and new review_key values at the same time.
    db.flush()
    now = datetime.now()
    seen: set[str] = set()
    seen_provider_models: set[tuple[str, str | None]] = set()
    for index, raw_item in enumerate(raw_items or []):
        if not isinstance(raw_item, dict):
            raise AppError("VALIDATION_ERROR", "aiReviewModels must contain objects", 400)
        provider_code = _blank_to_none(raw_item.get("providerCode"))
        if not provider_code:
            raise AppError("VALIDATION_ERROR", "aiReviewModels.providerCode is required", 400)
        model_name = _blank_to_none(raw_item.get("modelName"))
        provider_model_key = (provider_code, model_name)
        if provider_model_key in seen_provider_models:
            continue
        seen_provider_models.add(provider_model_key)
        review_key = _blank_to_none(raw_item.get("reviewKey")) or make_ai_review_model_key(
            provider_code,
            model_name,
            index,
        )
        if review_key in seen:
            review_key = make_ai_review_model_key(provider_code, f"{model_name or 'default'}-{index + 1}", index)
        seen.add(review_key)
        db.add(
            ProjectGroupAiReviewModel(
                group_id=group.id,
                review_key=review_key,
                provider_code=provider_code,
                model_name=model_name,
                display_name=_blank_to_none(raw_item.get("displayName")),
                enabled=bool(raw_item.get("enabled", True)),
                sort_order=int(raw_item.get("sortOrder") if raw_item.get("sortOrder") is not None else (index + 1) * 10),
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()


def _path_matches(path: str, pattern: str) -> bool:
    normalized_path = path.replace("\\", "/")
    normalized_pattern = str(pattern or "").replace("\\", "/")
    return fnmatchcase(normalized_path, normalized_pattern)


def _sync_project_supported_target_types(db: Session, project: Project) -> None:
    _set_project_supported_target_type(db, project, effective_project_target_type(project))


def _set_project_supported_target_type(db: Session, project: Project, target_type: str) -> None:
    normalized = normalize_target_type(target_type)
    project.target_type = normalized
    project.supported_target_types = json.dumps([normalized], ensure_ascii=False)
    project.updated_at = datetime.now()
    db.flush()


def _blank_to_none(value) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


def _push_policy_columns(request: dict[str, Any]) -> dict[str, Any]:
    policy = {**DEFAULT_PUSH_REVIEW_POLICY, **{key: request[key] for key in DEFAULT_PUSH_REVIEW_POLICY if key in request}}
    return {
        "push_branch_patterns": json.dumps(policy["pushBranchPatterns"] or [], ensure_ascii=False),
        "push_min_changed_files": _int_or_default(policy.get("pushMinChangedFiles"), "pushMinChangedFiles"),
        "push_min_diff_bytes": _int_or_default(policy.get("pushMinDiffBytes"), "pushMinDiffBytes"),
        "push_min_commit_count": _int_or_default(policy.get("pushMinCommitCount"), "pushMinCommitCount"),
        "push_max_changed_files": _int_or_default(policy.get("pushMaxChangedFiles"), "pushMaxChangedFiles"),
        "push_max_diff_bytes": _int_or_default(policy.get("pushMaxDiffBytes"), "pushMaxDiffBytes"),
        "push_debounce_seconds": _int_or_default(policy.get("pushDebounceSeconds"), "pushDebounceSeconds"),
    }


def _ai_review_policy_columns(request: dict[str, Any]) -> dict[str, Any]:
    policy = {**DEFAULT_GROUP_AI_REVIEW_POLICY, **{key: request[key] for key in DEFAULT_GROUP_AI_REVIEW_POLICY if key in request}}
    return {
        "review_engine": "AGENT",
        "agent_source_export_allowed": True,
        "ai_review_enabled": True,
        "trigger_on_manual": True,
        "trigger_on_mr": bool(policy["triggerOnMr"]),
        "trigger_on_push": bool(policy["triggerOnPush"]),
        "trigger_only_when_risk_matched": bool(policy["triggerOnlyWhenRiskMatched"]),
        "auto_fix_preview_enabled": bool(policy["autoFixPreviewEnabled"]),
        "auto_fix_preview_severities": json.dumps(
            _normalize_auto_fix_preview_severities(policy.get("autoFixPreviewSeverities")),
            ensure_ascii=False,
        ),
    }


def _update_group_ai_review_policy(group: ProjectGroup, request: dict[str, Any]) -> None:
    fields = {
        "triggerOnMr": "trigger_on_mr",
        "triggerOnPush": "trigger_on_push",
        "triggerOnlyWhenRiskMatched": "trigger_only_when_risk_matched",
        "autoFixPreviewEnabled": "auto_fix_preview_enabled",
    }
    for json_field, column_name in fields.items():
        if json_field in request:
            setattr(group, column_name, bool(request[json_field]))
    group.review_engine = "AGENT"
    group.agent_source_export_allowed = True
    group.ai_review_enabled = True
    group.trigger_on_manual = True
    if "autoFixPreviewSeverities" in request:
        group.auto_fix_preview_severities = json.dumps(
            _normalize_auto_fix_preview_severities(request.get("autoFixPreviewSeverities")),
            ensure_ascii=False,
        )


def _update_group_push_policy(group: ProjectGroup, request: dict[str, Any]) -> None:
    if "pushBranchPatterns" in request:
        group.push_branch_patterns = json.dumps(request.get("pushBranchPatterns") or [], ensure_ascii=False)
    fields = {
        "pushMinChangedFiles": "push_min_changed_files",
        "pushMinDiffBytes": "push_min_diff_bytes",
        "pushMinCommitCount": "push_min_commit_count",
        "pushMaxChangedFiles": "push_max_changed_files",
        "pushMaxDiffBytes": "push_max_diff_bytes",
        "pushDebounceSeconds": "push_debounce_seconds",
    }
    for json_field, column_name in fields.items():
        if json_field in request:
            setattr(group, column_name, _int_or_default(request.get(json_field), json_field))


def _policy_int(value: Any, field: str) -> int:
    return _int_or_default(value, field)


def _policy_bool(value: Any, field: str) -> bool:
    if value is None:
        return bool(DEFAULT_GROUP_AI_REVIEW_POLICY[field])
    return bool(value)


def _normalize_auto_fix_preview_severities(value: Any) -> list[str]:
    allowed = {"CRITICAL", "MAJOR", "MINOR"}
    raw_values = value if isinstance(value, list) else []
    result: list[str] = []
    for item in raw_values:
        normalized = str(item or "").strip().upper()
        if normalized in allowed and normalized not in result:
            result.append(normalized)
    return result or list(DEFAULT_GROUP_AI_REVIEW_POLICY["autoFixPreviewSeverities"])


def _normalize_branch_patterns(value: Any) -> list[str]:
    raw_values = value if isinstance(value, list) else []
    result: list[str] = []
    for item in raw_values:
        normalized = str(item or "").strip()
        if normalized and normalized not in result:
            result.append(normalized)
    if not result:
        raise AppError("VALIDATION_ERROR", "pushBranchPatterns must contain at least one pattern", 400)
    return result


def _int_or_default(value: Any, field: str) -> int:
    if value is None:
        return int(DEFAULT_PUSH_REVIEW_POLICY[field])
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(DEFAULT_PUSH_REVIEW_POLICY[field])


def _store_target_detection(project: Project, detection: dict) -> None:
    project.detected_target_types = json.dumps(detection.get("targetTypes") or [], ensure_ascii=False)
    project.target_detection_json = json.dumps(detection, ensure_ascii=False)


def _create_detected_target_configs(db: Session, project: Project, detected_types: list[str]) -> None:
    single_target = len(detected_types) == 1
    now = datetime.now()
    for target_type in detected_types:
        normalized = normalize_target_type(target_type)
        defaults = TARGET_TYPE_DEFAULTS.get(normalized, TARGET_TYPE_DEFAULTS["GENERAL"])
        db.add(
            ProjectTargetConfig(
                project_id=project.id,
                target_type=normalized,
                template_code=defaults["templateCode"],
                code_quality_profile_code=defaults["profileCode"],
                provider_code=project.default_code_quality_provider_code,
                path_patterns=json.dumps(["**/*"] if single_target else defaults["pathPatterns"], ensure_ascii=False),
                reminder_card_enabled=bool(defaults["reminderCardEnabled"]),
                enabled=True,
                description="路径映射创建的端类型配置",
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()


def _create_manual_target_configs(db: Session, project: Project, target_types: list[str]) -> None:
    single_target = len(target_types) == 1
    now = datetime.now()
    for target_type in target_types:
        normalized = normalize_target_type(target_type)
        defaults = TARGET_TYPE_DEFAULTS.get(normalized, TARGET_TYPE_DEFAULTS["GENERAL"])
        db.add(
            ProjectTargetConfig(
                project_id=project.id,
                target_type=normalized,
                template_code=defaults["templateCode"],
                code_quality_profile_code=defaults["profileCode"],
                provider_code=project.default_code_quality_provider_code,
                path_patterns=json.dumps(["**/*"] if single_target else defaults["pathPatterns"], ensure_ascii=False),
                reminder_card_enabled=bool(defaults["reminderCardEnabled"]),
                enabled=True,
                description="手动预创建的端类型配置",
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()


def _requested_target_types(request: dict) -> list[str]:
    raw_values = request.get("targetTypes")
    if not isinstance(raw_values, list):
        raw_values = [request.get("targetType") or "BACKEND"]
    normalized: list[str] = []
    for value in raw_values:
        target_type = normalize_target_type(value)
        if target_type not in normalized:
            normalized.append(target_type)
    if len(normalized) > 1:
        raise AppError("VALIDATION_ERROR", "A project must have exactly one targetType", 400)
    return normalized or ["BACKEND"]


def _append_unique_target(targets: list[str], target_type: str) -> None:
    if target_type not in targets:
        targets.append(target_type)


def _assert_group_code_available(db: Session, group_code: str, exclude_group_id: int | None = None) -> None:
    stmt = select(ProjectGroup).where(ProjectGroup.group_code == group_code)
    if exclude_group_id is not None:
        stmt = stmt.where(ProjectGroup.id != exclude_group_id)
    existing = db.scalars(stmt).first()
    if existing is not None:
        raise AppError("VALIDATION_ERROR", f"Project group code already exists: {group_code}", 400)


def _assert_default_group_code_not_changed(group: ProjectGroup, next_code: str) -> None:
    if group.group_code == "default" and next_code != "default":
        raise AppError("VALIDATION_ERROR", "Default project group code cannot be changed", 400)


def _assert_default_group_can_keep_status(group: ProjectGroup, next_status: str) -> None:
    if group.group_code == "default" and next_status != "ENABLED":
        raise AppError("VALIDATION_ERROR", "Default project group cannot be disabled", 400)
