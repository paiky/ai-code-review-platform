from datetime import datetime
from fnmatch import fnmatchcase
import json
from threading import Lock
from typing import Any

from sqlalchemy import Select, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.json_utils import page_response
from app.core.errors import AppError
from app.core.json_utils import read_json, read_json_array
from app.project_integration.models import Project, ProjectGroup, ProjectTargetConfig, TargetTypePathMapping


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

PATH_DETECTION_RULES = [
    ("APP_IOS", ["ios/**", "**/*.swift", "**/*.m", "**/*.mm", "Podfile"]),
    ("APP_ANDROID", ["android/**", "**/*.kt", "**/*.kts", "build.gradle", "settings.gradle", "**/*.gradle"]),
    ("WEB_PC", ["frontend/**", "web/**", "src/**/*.tsx", "src/**/*.jsx", "src/**/*.vue", "package.json"]),
    ("BACKEND", ["src/main/java/**", "src/main/resources/**", "src/*.java", "src/**/*.java", "pom.xml", "backend-python/**", "backend/**"]),
]
PATH_MAPPING_TARGET_TYPES = {target_type for target_type, _patterns in PATH_DETECTION_RULES}
SYSTEM_DETECTED_TARGET_CONFIG_DESCRIPTIONS = {"自动识别创建的端类型配置", "路径映射创建的端类型配置"}

_SCHEMA_LOCK = Lock()
_SCHEMA_ENSURED_ENGINE_IDS: set[int] = set()


def ensure_project_config_schema(db: Session) -> None:
    engine_id = id(db.get_bind())
    if engine_id in _SCHEMA_ENSURED_ENGINE_IDS:
        return
    with _SCHEMA_LOCK:
        if engine_id in _SCHEMA_ENSURED_ENGINE_IDS:
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
            _add_column_if_missing(db, group_columns, "project_groups", "push_branch_patterns", "TEXT NULL")
            _add_column_if_missing(db, group_columns, "project_groups", "push_min_changed_files", "INT NULL DEFAULT 10")
            _add_column_if_missing(db, group_columns, "project_groups", "push_min_diff_bytes", "INT NULL DEFAULT 30000")
            _add_column_if_missing(db, group_columns, "project_groups", "push_min_commit_count", "INT NULL DEFAULT 3")
            _add_column_if_missing(db, group_columns, "project_groups", "push_max_changed_files", "INT NULL DEFAULT -1")
            _add_column_if_missing(db, group_columns, "project_groups", "push_max_diff_bytes", "INT NULL DEFAULT -1")
            _add_column_if_missing(db, group_columns, "project_groups", "push_debounce_seconds", "INT NULL DEFAULT 300")
        if not inspector.has_table("target_type_path_mappings"):
            TargetTypePathMapping.__table__.create(connection, checkfirst=True)
        if not inspector.has_table("project_target_configs"):
            ProjectTargetConfig.__table__.create(connection, checkfirst=True)
        project_columns = {column["name"] for column in inspector.get_columns("projects")} if inspector.has_table("projects") else set()
        _add_column_if_missing(db, project_columns, "projects", "group_id", "BIGINT NULL")
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
        "supportedTargetTypes": read_json_array(project.supported_target_types) or ["BACKEND"],
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
    include_disabled: bool = False,
) -> dict:
    ensure_project_config_schema(db)
    _ensure_default_project_group(db)
    db.commit()
    stmt: Select[tuple[Project]] = select(Project)
    if not include_disabled:
        stmt = stmt.where(Project.status == "ENABLED")
    if group_id is not None:
        stmt = stmt.where(Project.group_id == group_id)
    if target_type:
        stmt = stmt.where(Project.supported_target_types.like(f"%{target_type}%"))
    stmt = stmt.order_by(Project.id.desc())
    items = [project_to_dict(project) for project in db.scalars(stmt).all()]
    total_stmt = select(func.count()).select_from(Project)
    if not include_disabled:
        total_stmt = total_stmt.where(Project.status == "ENABLED")
    if group_id is not None:
        total_stmt = total_stmt.where(Project.group_id == group_id)
    if target_type:
        total_stmt = total_stmt.where(Project.supported_target_types.like(f"%{target_type}%"))
    total = db.scalar(total_stmt) or 0
    return page_response(items, 1, len(items), total)


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
        supported_target_types=json.dumps(target_types, ensure_ascii=False),
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
        supported_target_types=json.dumps(detected_types, ensure_ascii=False),
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
    _create_detected_target_configs(db, project, detected_types)
    return project


def update_project_target_detection(
    db: Session,
    project: Project,
    project_name: str | None,
    changed_files: list[dict[str, Any]] | None,
) -> Project:
    detection = detect_project_target_types(db, changed_files or [])
    _store_target_detection(project, detection)
    existing_configs = db.scalars(
        select(ProjectTargetConfig).where(ProjectTargetConfig.project_id == project.id)
    ).all()
    auto_created = existing_configs and all(config.description in SYSTEM_DETECTED_TARGET_CONFIG_DESCRIPTIONS for config in existing_configs)
    can_rebuild_auto_configs = not existing_configs or auto_created
    if can_rebuild_auto_configs:
        detected_types = detection.get("targetTypes") or ["BACKEND"]
        primary = detected_types[0]
        defaults = TARGET_TYPE_DEFAULTS.get(primary, TARGET_TYPE_DEFAULTS["BACKEND"])
        for config in existing_configs:
            db.delete(config)
        if existing_configs:
            db.flush()
        project.supported_target_types = json.dumps(detected_types, ensure_ascii=False)
        project.default_template_code = defaults["templateCode"]
        project.default_code_quality_profile_code = defaults["profileCode"]
        _create_detected_target_configs(db, project, detected_types)
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
        "dingtalkWebhooks": dingtalk_webhooks,
        "enabledDingtalkWebhookCount": len([item for item in dingtalk_webhooks if item.get("enabled")]),
        "status": group.status,
        "description": group.description,
        **push_policy_to_dict(group),
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
    _update_group_push_policy(group, request)
    if "status" in request:
        _assert_default_group_can_keep_status(group, request["status"])
        group.status = request["status"]
    if "description" in request:
        group.description = _blank_to_none(request.get("description"))
    if "dingtalkWebhooks" in request:
        from app.notification.repository import upsert_webhooks

        upsert_webhooks(db, request.get("dingtalkWebhooks") or [], int(group.id))
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


def get_project_group_push_policy(db: Session, project: Project) -> dict[str, Any]:
    ensure_project_config_schema(db)
    group = db.get(ProjectGroup, project.group_id) if project.group_id else None
    if group is None:
        group = _ensure_default_project_group(db)
    return push_policy_to_dict(group)


def resolve_project_review_profile_code(db: Session, project: Project, target_type: str | None) -> str | None:
    ensure_project_config_schema(db)
    group = db.get(ProjectGroup, project.group_id) if project.group_id else None
    if group is None:
        group = _ensure_default_project_group(db)
    group_profile = _blank_to_none(group.default_code_quality_profile_code)
    if group_profile:
        return group_profile
    normalized_target_type = normalize_target_type(target_type)
    if group.group_code == "default" and normalized_target_type != "GENERAL":
        defaults = TARGET_TYPE_DEFAULTS.get(normalized_target_type, TARGET_TYPE_DEFAULTS["GENERAL"])
        return defaults.get("profileCode")
    return None


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
            enabled=bool(request.get("enabled", True)),
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
        if "enabled" in request:
            config.enabled = bool(request["enabled"])
        if "description" in request:
            config.description = _blank_to_none(request.get("description"))
        elif config.description in SYSTEM_DETECTED_TARGET_CONFIG_DESCRIPTIONS:
            config.description = "手动维护的端类型配置"
        config.updated_at = now
    _sync_project_supported_target_types(db, project)
    db.commit()
    return target_config_to_dict(config)


def ensure_default_target_configs(db: Session, project: Project) -> None:
    existing_configs = db.scalars(
        select(ProjectTargetConfig).where(ProjectTargetConfig.project_id == project.id)
    ).all()
    if not existing_configs:
        defaults = TARGET_TYPE_DEFAULTS["BACKEND"]
        now = datetime.now()
        db.add(
            ProjectTargetConfig(
                project_id=project.id,
                target_type="BACKEND",
                template_code=project.default_template_code or defaults["templateCode"],
                code_quality_profile_code=project.default_code_quality_profile_code or defaults["profileCode"],
                provider_code=project.default_code_quality_provider_code,
                path_patterns=json.dumps(defaults["pathPatterns"], ensure_ascii=False),
                reminder_card_enabled=True,
                enabled=True,
                description="默认后端端类型配置",
                created_at=now,
                updated_at=now,
            )
        )
        db.flush()
    _sync_project_supported_target_types(db, project)


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
    ensure_default_target_configs(db, project)
    configs = [
        config for config in db.scalars(
            select(ProjectTargetConfig)
            .where(ProjectTargetConfig.project_id == project.id, ProjectTargetConfig.enabled.is_(True))
            .order_by(ProjectTargetConfig.id.asc())
        ).all()
    ]
    requested = [normalize_target_type(value) for value in (requested_target_types or []) if value]
    if requested_target_type:
        requested = [normalize_target_type(requested_target_type), *[value for value in requested if value != normalize_target_type(requested_target_type)]]
    matched_types = requested or _match_target_types(configs, changed_files or [])
    if not matched_types:
        matched_types = ["BACKEND"]
    primary = matched_types[0]
    config = next((item for item in configs if item.target_type == primary), None)
    defaults = TARGET_TYPE_DEFAULTS.get(primary, TARGET_TYPE_DEFAULTS["GENERAL"])
    return {
        "targetType": primary,
        "targetTypes": matched_types,
        "templateCode": (config.template_code if config else None) or defaults["templateCode"] or project.default_template_code,
        "profileCode": resolve_project_review_profile_code(db, project, primary),
        "providerCode": (config.provider_code if config else None) or project.default_code_quality_provider_code,
        "reminderCardEnabled": bool(config.reminder_card_enabled) if config else bool(defaults["reminderCardEnabled"]),
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
        "reminderCardEnabled": bool(config.reminder_card_enabled),
        "enabled": bool(config.enabled),
        "description": config.description,
    }


def _default_target_config_response(project: Project) -> dict:
    defaults = TARGET_TYPE_DEFAULTS["BACKEND"]
    return {
        "id": None,
        "projectId": project.id,
        "targetType": "BACKEND",
        "templateCode": project.default_template_code or defaults["templateCode"],
        "codeQualityProfileCode": project.default_code_quality_profile_code or defaults["profileCode"],
        "providerCode": project.default_code_quality_provider_code,
        "pathPatterns": defaults["pathPatterns"],
        "reminderCardEnabled": True,
        "enabled": True,
        "description": "默认后端端类型配置（未保存）",
    }


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


def _path_matches(path: str, pattern: str) -> bool:
    normalized_path = path.replace("\\", "/")
    normalized_pattern = str(pattern or "").replace("\\", "/")
    return fnmatchcase(normalized_path, normalized_pattern) or fnmatchcase(normalized_path, f"**/{normalized_pattern}")


def _sync_project_supported_target_types(db: Session, project: Project) -> None:
    types = [
        config.target_type
        for config in db.scalars(
            select(ProjectTargetConfig)
            .where(ProjectTargetConfig.project_id == project.id, ProjectTargetConfig.enabled.is_(True))
            .order_by(ProjectTargetConfig.id.asc())
        ).all()
    ]
    project.supported_target_types = json.dumps(types or ["BACKEND"], ensure_ascii=False)
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
