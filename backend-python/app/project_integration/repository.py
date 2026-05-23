from datetime import datetime
from fnmatch import fnmatchcase
import json
from threading import Lock

from sqlalchemy import Select, func, inspect, select, text
from sqlalchemy.orm import Session

from app.core.json_utils import page_response
from app.core.errors import AppError
from app.core.json_utils import read_json_array
from app.project_integration.models import Project, ProjectGroup, ProjectTargetConfig


TARGET_TYPE_DEFAULTS = {
    "BACKEND": {
        "templateCode": "backend-default",
        "profileCode": "backend-default-ai-review",
        "pathPatterns": ["backend-python/**", "backend/**", "src/main/**", "src/test/**", "pom.xml", "requirements*.txt"],
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
        "profileCode": "backend-default-ai-review",
        "pathPatterns": ["**/*"],
        "reminderCardEnabled": False,
    },
}

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
        if not inspector.has_table("project_groups"):
            ProjectGroup.__table__.create(connection, checkfirst=True)
        if not inspector.has_table("project_target_configs"):
            ProjectTargetConfig.__table__.create(connection, checkfirst=True)
        project_columns = {column["name"] for column in inspector.get_columns("projects")} if inspector.has_table("projects") else set()
        _add_column_if_missing(db, project_columns, "projects", "group_id", "BIGINT NULL")
        _add_column_if_missing(db, project_columns, "projects", "supported_target_types", "TEXT NULL")
        task_columns = {column["name"] for column in inspector.get_columns("review_tasks")} if inspector.has_table("review_tasks") else set()
        _add_column_if_missing(db, task_columns, "review_tasks", "target_type", "VARCHAR(32) NULL")
        _add_column_if_missing(db, task_columns, "review_tasks", "target_types_json", "TEXT NULL")
        _add_column_if_missing(db, task_columns, "review_tasks", "code_quality_profile_code", "VARCHAR(64) NULL")
        result_columns = {column["name"] for column in inspector.get_columns("review_results")} if inspector.has_table("review_results") else set()
        _add_column_if_missing(db, result_columns, "review_results", "target_type", "VARCHAR(32) NULL")
        _add_column_if_missing(db, result_columns, "review_results", "reminder_card_enabled", "BOOLEAN NULL")
        db.flush()
        _SCHEMA_ENSURED_ENGINE_IDS.add(engine_id)


def _add_column_if_missing(db: Session, columns: set[str], table_name: str, column_name: str, definition: str) -> None:
    if column_name in columns:
        return
    db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"))
    columns.add(column_name)
    db.flush()


def _ensure_default_project_group(db: Session) -> ProjectGroup:
    group = db.scalars(select(ProjectGroup).where(ProjectGroup.group_code == "default")).first()
    if group is None:
        now = datetime.now()
        group = ProjectGroup(
            group_name="默认项目组",
            group_code="default",
            default_provider_code=None,
            status="ENABLED",
            description="系统默认项目组",
            created_at=now,
            updated_at=now,
        )
        db.add(group)
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
        "defaultTemplateCode": project.default_template_code,
        "defaultCodeQualityProfileCode": project.default_code_quality_profile_code,
        "defaultCodeQualityProviderCode": project.default_code_quality_provider_code,
        "status": project.status,
    }


def list_enabled_projects(
    db: Session,
    group_id: int | None = None,
    target_type: str | None = None,
) -> dict:
    ensure_project_config_schema(db)
    _ensure_default_project_group(db)
    db.commit()
    stmt: Select[tuple[Project]] = select(Project).where(Project.status == "ENABLED")
    if group_id is not None:
        stmt = stmt.where(Project.group_id == group_id)
    if target_type:
        stmt = stmt.where(Project.supported_target_types.like(f"%{target_type}%"))
    stmt = stmt.order_by(Project.id.desc())
    items = [project_to_dict(project) for project in db.scalars(stmt).all()]
    total_stmt = select(func.count()).select_from(Project).where(Project.status == "ENABLED")
    if group_id is not None:
        total_stmt = total_stmt.where(Project.group_id == group_id)
    if target_type:
        total_stmt = total_stmt.where(Project.supported_target_types.like(f"%{target_type}%"))
    total = db.scalar(total_stmt) or 0
    return page_response(items, 1, len(items), total)


def find_project_by_id(db: Session, project_id: int) -> Project | None:
    ensure_project_config_schema(db)
    return db.get(Project, project_id)


def find_project_by_git_project_id(db: Session, git_project_id: str) -> Project | None:
    ensure_project_config_schema(db)
    return db.scalars(
        select(Project).where(Project.git_provider == "GITLAB", Project.git_project_id == git_project_id)
    ).first()


def upsert_gitlab_project(db: Session, git_project_id: str, project_name: str, repository_url: str | None) -> Project:
    ensure_project_config_schema(db)
    now = datetime.now()
    project = find_project_by_git_project_id(db, git_project_id)
    if project:
        project.name = project_name
        project.repository_url = repository_url
        project.status = "ENABLED"
        project.updated_at = now
        db.flush()
        return project

    project = Project(
        group_id=_ensure_default_project_group(db).id,
        name=project_name,
        git_provider="GITLAB",
        git_project_id=git_project_id,
        repository_url=repository_url,
        supported_target_types=json.dumps(["BACKEND"], ensure_ascii=False),
        default_template_code="backend-default",
        default_code_quality_profile_code="backend-default-ai-review",
        default_code_quality_provider_code=None,
        dingtalk_webhook_id=None,
        status="ENABLED",
        description="Auto-created from GitLab webhook",
        created_at=now,
        updated_at=now,
    )
    db.add(project)
    db.flush()
    return project


def list_project_groups(db: Session) -> dict:
    ensure_project_config_schema(db)
    _ensure_default_project_group(db)
    db.commit()
    groups = db.scalars(select(ProjectGroup).where(ProjectGroup.status == "ENABLED").order_by(ProjectGroup.id.asc())).all()
    return page_response([project_group_to_dict(group) for group in groups], 1, len(groups), len(groups))


def project_group_to_dict(group: ProjectGroup) -> dict:
    return {
        "id": group.id,
        "groupCode": group.group_code,
        "groupName": group.group_name,
        "defaultProviderCode": group.default_provider_code,
        "status": group.status,
        "description": group.description,
    }


def create_project_group(db: Session, request: dict) -> dict:
    ensure_project_config_schema(db)
    now = datetime.now()
    group = ProjectGroup(
        group_name=str(request.get("groupName") or request.get("name") or "").strip(),
        group_code=_blank_to_none(request.get("groupCode")),
        default_provider_code=_blank_to_none(request.get("defaultProviderCode")),
        status=request.get("status") or "ENABLED",
        description=_blank_to_none(request.get("description")),
        created_at=now,
        updated_at=now,
    )
    if not group.group_name:
        raise AppError("VALIDATION_ERROR", "groupName is required", 400)
    db.add(group)
    db.commit()
    return project_group_to_dict(group)


def update_project_group(db: Session, group_id: int, request: dict) -> dict:
    ensure_project_config_schema(db)
    group = db.get(ProjectGroup, group_id)
    if group is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project group not found: {group_id}", 404)
    if "groupName" in request or "name" in request:
        group.group_name = str(request.get("groupName") or request.get("name") or "").strip()
    if "groupCode" in request:
        group.group_code = _blank_to_none(request.get("groupCode"))
    if "defaultProviderCode" in request:
        group.default_provider_code = _blank_to_none(request.get("defaultProviderCode"))
    if "status" in request:
        group.status = request["status"]
    if "description" in request:
        group.description = _blank_to_none(request.get("description"))
    group.updated_at = datetime.now()
    db.commit()
    return project_group_to_dict(group)


def update_project_group_binding(db: Session, project_id: int, request: dict) -> dict:
    project = find_project_by_id(db, project_id)
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {project_id}", 404)
    group_id = request.get("groupId")
    group = db.get(ProjectGroup, int(group_id)) if group_id is not None else None
    if group_id is not None and group is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project group not found: {group_id}", 404)
    project.group_id = group.id if group else None
    project.updated_at = datetime.now()
    db.commit()
    return project_to_dict(project)


def list_project_target_configs(db: Session, project_id: int) -> list[dict]:
    project = find_project_by_id(db, project_id)
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {project_id}", 404)
    ensure_default_target_configs(db, project)
    configs = db.scalars(
        select(ProjectTargetConfig)
        .where(ProjectTargetConfig.project_id == project_id)
        .order_by(ProjectTargetConfig.target_type.asc())
    ).all()
    return [target_config_to_dict(config) for config in configs]


def upsert_project_target_config(db: Session, project_id: int, target_type: str, request: dict) -> dict:
    project = find_project_by_id(db, project_id)
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {project_id}", 404)
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
            description=_blank_to_none(request.get("description")),
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
        config.updated_at = now
    _sync_project_supported_target_types(db, project)
    db.commit()
    return target_config_to_dict(config)


def ensure_default_target_configs(db: Session, project: Project) -> None:
    existing = find_target_config(db, project.id, "BACKEND")
    if existing is None:
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
        "profileCode": (config.code_quality_profile_code if config else None) or defaults["profileCode"] or project.default_code_quality_profile_code,
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


def _path_matches(path: str, pattern: str) -> bool:
    normalized_path = path.replace("\\", "/")
    normalized_pattern = str(pattern or "").replace("\\", "/")
    return fnmatchcase(normalized_path, normalized_pattern)


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
