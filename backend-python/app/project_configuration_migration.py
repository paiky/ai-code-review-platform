from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import create_engine_for_url
from app.core.json_utils import read_json_array
from app.notification.models import NotificationWebhook, ProjectNotificationWebhook
from app.project_integration.models import (
    Project,
    ProjectAiReviewModel,
    ProjectGroup,
    ProjectGroupAiReviewModel,
    ProjectReviewSettings,
    ProjectTargetConfig,
)
from app.project_integration.repository import (
    DEFAULT_PUSH_REVIEW_POLICY,
    TARGET_TYPE_DEFAULTS,
    make_ai_review_model_key,
    normalize_target_type,
)


AUTO_TARGET_CONFIG_DESCRIPTIONS = {
    "自动识别创建的端类型配置",
    "路径映射创建的端类型配置",
}


class MigrationBlockedError(RuntimeError):
    """Raised when preflight finds data that needs manual resolution."""


@dataclass(frozen=True)
class MigrationIssue:
    code: str
    message: str
    project_id: int | None = None
    blocking: bool = True
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProjectMigrationAudit:
    projects_scanned: int
    target_types: dict[int, str]
    issues: tuple[MigrationIssue, ...]
    duplicate_webhook_ids: dict[int, int]

    @property
    def blocking_issues(self) -> tuple[MigrationIssue, ...]:
        return tuple(item for item in self.issues if item.blocking)

    @property
    def is_ready(self) -> bool:
        return not self.blocking_issues

    def to_dict(self) -> dict[str, Any]:
        return {
            "projectsScanned": self.projects_scanned,
            "targetTypes": self.target_types,
            "ready": self.is_ready,
            "blockingIssueCount": len(self.blocking_issues),
            "issues": [asdict(item) for item in self.issues],
            "duplicateWebhookIds": self.duplicate_webhook_ids,
        }


@dataclass(frozen=True)
class EffectiveConfigComparison:
    project_id: int
    matches: bool
    legacy: dict[str, Any]
    migrated: dict[str, Any]
    differences: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "projectId": self.project_id,
            "matches": self.matches,
            "legacy": self.legacy,
            "migrated": self.migrated,
            "differences": list(self.differences),
        }


@dataclass(frozen=True)
class ProjectMigrationBackfill:
    dry_run: bool
    projects_processed: int
    settings_created: int
    models_created: int
    configurations_created: int
    webhook_relations_created: int
    effective_configurations: tuple[EffectiveConfigComparison, ...]

    @property
    def effective_configurations_match(self) -> bool:
        return all(item.matches for item in self.effective_configurations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dryRun": self.dry_run,
            "projectsProcessed": self.projects_processed,
            "settingsCreated": self.settings_created,
            "modelsCreated": self.models_created,
            "configurationsCreated": self.configurations_created,
            "webhookRelationsCreated": self.webhook_relations_created,
            "effectiveConfigurationsMatch": self.effective_configurations_match,
            "effectiveConfigurations": [
                item.to_dict() for item in self.effective_configurations
            ],
        }


def audit_project_configuration_migration(db: Session) -> ProjectMigrationAudit:
    projects = db.scalars(select(Project).order_by(Project.id.asc())).all()
    webhooks = db.scalars(
        select(NotificationWebhook)
        .where(NotificationWebhook.channel == "DINGTALK")
        .order_by(NotificationWebhook.id.asc())
    ).all()
    issues: list[MigrationIssue] = []
    target_types: dict[int, str] = {}
    duplicate_webhook_ids: dict[int, int] = {}
    canonical_webhooks: dict[str, NotificationWebhook] = {}

    for webhook in webhooks:
        normalized_url = str(webhook.webhook_url or "").strip()
        if not normalized_url:
            issues.append(
                MigrationIssue(
                    code="EMPTY_WEBHOOK_URL",
                    message="Webhook URL is empty and cannot be migrated",
                    blocking=True,
                    details={"webhookId": webhook.id},
                )
            )
            continue
        existing = canonical_webhooks.get(normalized_url)
        if existing is None:
            canonical_webhooks[normalized_url] = webhook
            continue
        duplicate_webhook_ids[int(webhook.id)] = int(existing.id)
        issues.append(
            MigrationIssue(
                code="DUPLICATE_WEBHOOK_URL",
                message="Duplicate webhook URL will be merged to the earliest resource",
                blocking=False,
                details={
                    "webhookId": webhook.id,
                    "canonicalWebhookId": existing.id,
                    "urlSuffix": normalized_url[-4:],
                },
            )
        )
        if bool(webhook.enabled) and not bool(existing.enabled):
            canonical_webhooks[normalized_url] = webhook

    for project in projects:
        configs = db.scalars(
            select(ProjectTargetConfig)
            .where(ProjectTargetConfig.project_id == project.id)
            .order_by(ProjectTargetConfig.id.asc())
        ).all()
        target_type, target_issue = _resolve_project_target_type(project, configs)
        if target_issue is not None:
            issues.append(target_issue)
        elif target_type is not None:
            target_types[int(project.id)] = target_type

        group = db.get(ProjectGroup, project.group_id) if project.group_id else None
        if project.group_id and group is None:
            issues.append(
                MigrationIssue(
                    code="MISSING_PROJECT_GROUP",
                    message="Project references a project group that does not exist",
                    project_id=int(project.id),
                    details={"groupId": project.group_id},
                )
            )
        elif group is not None and str(group.status).upper() != "ENABLED":
            issues.append(
                MigrationIssue(
                    code="DISABLED_PROJECT_GROUP",
                    message="Project is bound to a disabled project group",
                    project_id=int(project.id),
                    details={"groupId": group.id, "status": group.status},
                )
            )

        enabled_configs = [item for item in configs if bool(item.enabled)]
        manual_configs = [
            item
            for item in enabled_configs
            if item.description not in AUTO_TARGET_CONFIG_DESCRIPTIONS
        ]
        if len(manual_configs) > 1:
            issues.append(
                MigrationIssue(
                    code="MULTIPLE_MANUAL_TARGET_TYPES",
                    message="Project has multiple manually enabled target configurations",
                    project_id=int(project.id),
                    details={"targetTypes": [item.target_type for item in manual_configs]},
                )
            )

        if target_type is None:
            continue
        selected_config = next(
            (
                item
                for item in enabled_configs
                if normalize_target_type(item.target_type) == target_type
            ),
            None,
        )
        profile_code = _effective_profile(project, group, selected_config, target_type)
        if not profile_code:
            issues.append(
                MigrationIssue(
                    code="MISSING_REVIEW_PROFILE",
                    message="Project has no effective Review Profile for the selected target type",
                    project_id=int(project.id),
                    details={"targetType": target_type},
                )
            )

        group_models = _group_models(db, group)
        provider_code = _effective_provider(project, group, selected_config, group_models)
        if not provider_code:
            issues.append(
                MigrationIssue(
                    code="MISSING_REVIEW_PROVIDER",
                    message="Project has no effective Review Provider or model",
                    project_id=int(project.id),
                    details={"targetType": target_type},
                )
            )
        if (
            selected_config is not None
            and selected_config.provider_code
            and group_models
            and selected_config.provider_code
            not in {str(item.provider_code).strip() for item in group_models}
        ):
            issues.append(
                MigrationIssue(
                    code="PROJECT_PROVIDER_GROUP_MODEL_CONFLICT",
                    message="Project target Provider overrides the project group model list",
                    project_id=int(project.id),
                    blocking=False,
                    details={
                        "targetProviderCode": selected_config.provider_code,
                        "groupProviderCodes": sorted(
                            {str(item.provider_code).strip() for item in group_models}
                        ),
                    },
                )
            )

    return ProjectMigrationAudit(
        projects_scanned=len(projects),
        target_types=target_types,
        issues=tuple(issues),
        duplicate_webhook_ids=duplicate_webhook_ids,
    )



def backfill_project_configuration(
    db: Session,
    *,
    audit: ProjectMigrationAudit | None = None,
    dry_run: bool = False,
) -> ProjectMigrationBackfill:
    report = audit or audit_project_configuration_migration(db)
    if report.blocking_issues:
        preview = "; ".join(
            f"{item.code} (project {item.project_id})" if item.project_id else item.code
            for item in report.blocking_issues[:10]
        )
        raise MigrationBlockedError(
            f"Project configuration migration is blocked by "
            f"{len(report.blocking_issues)} issue(s): {preview}"
        )

    projects = db.scalars(select(Project).order_by(Project.id.asc())).all()
    webhook_map = _canonical_webhook_map(db)
    settings_created = 0
    models_created = 0
    configurations_created = 0
    relations_created = 0
    comparisons: list[EffectiveConfigComparison] = []

    for project in projects:
        target_type = report.target_types.get(int(project.id))
        if target_type is None:
            raise MigrationBlockedError(
                f"Target type is missing from audit report for project {project.id}"
            )
        group = db.get(ProjectGroup, project.group_id) if project.group_id else None
        configs = db.scalars(
            select(ProjectTargetConfig)
            .where(ProjectTargetConfig.project_id == project.id)
            .order_by(ProjectTargetConfig.id.asc())
        ).all()
        selected_config = _select_target_config(configs, target_type)
        if selected_config is None:
            selected_config = _create_target_config(project, group, target_type)
            if not dry_run:
                db.add(selected_config)
            configurations_created += 1
        elif not dry_run and group is not None and group.default_code_quality_profile_code:
            selected_config.code_quality_profile_code = (
                group.default_code_quality_profile_code.strip()
            )

        for config in configs:
            if (
                not dry_run
                and config is not selected_config
                and bool(config.enabled)
                and config.description in AUTO_TARGET_CONFIG_DESCRIPTIONS
            ):
                config.enabled = False

        group_models = _group_models(db, group)
        legacy = _effective_config(project, group, selected_config, group_models, target_type)
        if not dry_run:
            project.target_type = target_type
            project.supported_target_types = json.dumps([target_type], ensure_ascii=False)
            project.updated_at = datetime.now()
            if _ensure_review_settings(db, project, group):
                settings_created += 1
            models_created += _upsert_project_models(db, project, group_models, group)
            relations_created += _upsert_project_webhooks(
                db,
                project,
                group,
                webhook_map,
                duplicate_ids=report.duplicate_webhook_ids,
            )
            db.flush()
        migrated = _effective_config_after_backfill(
            db,
            project,
            group,
            selected_config,
            group_models,
            target_type,
            dry_run=dry_run,
        )
        comparisons.append(_compare_effective_configs(int(project.id), legacy, migrated))

    if not dry_run:
        _disable_duplicate_webhooks(db, report.duplicate_webhook_ids)
        db.commit()

    return ProjectMigrationBackfill(
        dry_run=dry_run,
        projects_processed=len(projects),
        settings_created=settings_created,
        models_created=models_created,
        configurations_created=configurations_created,
        webhook_relations_created=relations_created,
        effective_configurations=tuple(comparisons),
    )


def _resolve_project_target_type(
    project: Project,
    configs: list[ProjectTargetConfig],
) -> tuple[str | None, MigrationIssue | None]:
    if project.target_type:
        return normalize_target_type(project.target_type), None

    enabled_configs = [item for item in configs if bool(item.enabled)]
    manual_configs = [
        item
        for item in enabled_configs
        if item.description not in AUTO_TARGET_CONFIG_DESCRIPTIONS
    ]
    if len(manual_configs) > 1:
        return None, None
    if len(manual_configs) == 1:
        return normalize_target_type(manual_configs[0].target_type), None

    supported_types = _normalized_target_types(project.supported_target_types)
    if len(supported_types) == 1:
        return supported_types[0], None
    if len(supported_types) > 1:
        return None, MigrationIssue(
            code="AMBIGUOUS_TARGET_TYPE",
            message="Project supported_target_types has multiple candidates",
            project_id=int(project.id),
            details={"supportedTargetTypes": supported_types},
        )

    detected_types = _normalized_target_types(project.detected_target_types)
    if len(detected_types) == 1:
        return detected_types[0], None
    if len(detected_types) > 1:
        return None, MigrationIssue(
            code="AMBIGUOUS_TARGET_TYPE",
            message="Project detected_target_types has multiple candidates",
            project_id=int(project.id),
            details={"detectedTargetTypes": detected_types},
        )
    return None, MigrationIssue(
        code="MISSING_TARGET_TYPE",
        message="Project has no deterministic target type candidate",
        project_id=int(project.id),
    )


def _normalized_target_types(value: Any) -> list[str]:
    result: list[str] = []
    for item in read_json_array(value):
        normalized = normalize_target_type(str(item))
        if normalized not in result:
            result.append(normalized)
    return result


def _select_target_config(
    configs: list[ProjectTargetConfig],
    target_type: str,
) -> ProjectTargetConfig | None:
    return next(
        (
            item
            for item in configs
            if bool(item.enabled) and normalize_target_type(item.target_type) == target_type
        ),
        None,
    )


def _create_target_config(
    project: Project,
    group: ProjectGroup | None,
    target_type: str,
) -> ProjectTargetConfig:
    defaults = TARGET_TYPE_DEFAULTS.get(target_type, TARGET_TYPE_DEFAULTS["GENERAL"])
    profile = (
        (group.default_code_quality_profile_code or "").strip()
        if group is not None and group.default_code_quality_profile_code
        else project.default_code_quality_profile_code
        or defaults.get("profileCode")
    )
    return ProjectTargetConfig(
        project_id=int(project.id),
        target_type=target_type,
        template_code=project.default_template_code or defaults["templateCode"],
        code_quality_profile_code=profile,
        provider_code=(project.default_code_quality_provider_code or "").strip() or None,
        path_patterns=json.dumps(defaults["pathPatterns"], ensure_ascii=False),
        reminder_card_enabled=bool(defaults.get("reminderCardEnabled")),
        enabled=True,
        description="项目化迁移创建的端类型配置",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


def _ensure_review_settings(
    db: Session,
    project: Project,
    group: ProjectGroup | None,
) -> bool:
    existing = db.get(ProjectReviewSettings, int(project.id))
    if existing is not None:
        return False
    now = datetime.now()
    db.add(
        ProjectReviewSettings(
            project_id=int(project.id),
            trigger_on_mr=bool(group.trigger_on_mr) if group is not None else True,
            trigger_on_push=bool(group.trigger_on_push) if group is not None else False,
            trigger_only_when_risk_matched=(
                bool(group.trigger_only_when_risk_matched) if group is not None else False
            ),
            auto_fix_preview_enabled=(
                bool(group.auto_fix_preview_enabled) if group is not None else False
            ),
            auto_fix_preview_severities=(
                group.auto_fix_preview_severities
                if group is not None
                else json.dumps(["MAJOR"])
            ),
            push_branch_patterns=(
                group.push_branch_patterns
                if group is not None and group.push_branch_patterns
                else json.dumps(
                    DEFAULT_PUSH_REVIEW_POLICY["pushBranchPatterns"],
                    ensure_ascii=False,
                )
            ),
            push_min_changed_files=_policy_value(
                group.push_min_changed_files if group is not None else None,
                "pushMinChangedFiles",
            ),
            push_min_diff_bytes=_policy_value(
                group.push_min_diff_bytes if group is not None else None,
                "pushMinDiffBytes",
            ),
            push_min_commit_count=_policy_value(
                group.push_min_commit_count if group is not None else None,
                "pushMinCommitCount",
            ),
            push_max_changed_files=_policy_value(
                group.push_max_changed_files if group is not None else None,
                "pushMaxChangedFiles",
            ),
            push_max_diff_bytes=_policy_value(
                group.push_max_diff_bytes if group is not None else None,
                "pushMaxDiffBytes",
            ),
            push_debounce_seconds=_policy_value(
                group.push_debounce_seconds if group is not None else None,
                "pushDebounceSeconds",
            ),
            created_at=now,
            updated_at=now,
        )
    )
    return True


def _policy_value(value: int | None, key: str) -> int:
    if value is not None:
        return int(value)
    return int(DEFAULT_PUSH_REVIEW_POLICY[key])



def _group_models(db: Session, group: ProjectGroup | None) -> list[ProjectGroupAiReviewModel]:
    if group is None:
        return []
    return db.scalars(
        select(ProjectGroupAiReviewModel)
        .where(ProjectGroupAiReviewModel.group_id == group.id)
        .order_by(ProjectGroupAiReviewModel.sort_order.asc(), ProjectGroupAiReviewModel.id.asc())
    ).all()


def _upsert_project_models(
    db: Session,
    project: Project,
    group_models: list[ProjectGroupAiReviewModel],
    group: ProjectGroup | None,
) -> int:
    source_models = list(group_models)
    if not source_models and group is not None and group.default_provider_code:
        source_models = [
            ProjectGroupAiReviewModel(
                group_id=int(group.id),
                review_key=make_ai_review_model_key(group.default_provider_code, None, 0),
                provider_code=group.default_provider_code,
                model_name=None,
                display_name=group.default_provider_code,
                enabled=True,
                sort_order=10,
            )
        ]
    created = 0
    existing = {
        item.review_key: item
        for item in db.scalars(
            select(ProjectAiReviewModel).where(ProjectAiReviewModel.project_id == project.id)
        ).all()
    }
    now = datetime.now()
    for source in source_models:
        record = existing.get(source.review_key)
        if record is None:
            db.add(
                ProjectAiReviewModel(
                    project_id=int(project.id),
                    review_key=source.review_key,
                    provider_code=source.provider_code,
                    model_name=source.model_name,
                    display_name=source.display_name,
                    enabled=bool(source.enabled),
                    sort_order=int(source.sort_order or 0),
                    created_at=now,
                    updated_at=now,
                )
            )
            created += 1
            continue
        record.provider_code = source.provider_code
        record.model_name = source.model_name
        record.display_name = source.display_name
        record.enabled = bool(source.enabled)
        record.sort_order = int(source.sort_order or 0)
        record.updated_at = now
    db.flush()
    return created


def _canonical_webhook_map(db: Session) -> dict[int, NotificationWebhook]:
    canonical: dict[str, NotificationWebhook] = {}
    by_id: dict[int, NotificationWebhook] = {}
    for webhook in db.scalars(
        select(NotificationWebhook)
        .where(NotificationWebhook.channel == "DINGTALK")
        .order_by(NotificationWebhook.id.asc())
    ).all():
        key = str(webhook.webhook_url or "").strip()
        if key and key not in canonical:
            canonical[key] = webhook
        by_id[int(webhook.id)] = canonical.get(key, webhook)
    return by_id


def _upsert_project_webhooks(
    db: Session,
    project: Project,
    group: ProjectGroup | None,
    webhook_map: dict[int, NotificationWebhook],
    *,
    duplicate_ids: dict[int, int],
) -> int:
    if group is None:
        return 0
    conditions = [NotificationWebhook.project_group_id == group.id]
    if group.group_code == "default":
        conditions.append(NotificationWebhook.project_group_id.is_(None))
    source_records = db.scalars(
        select(NotificationWebhook)
        .where(NotificationWebhook.channel == "DINGTALK")
        .where(or_(*conditions))
        .order_by(NotificationWebhook.id.asc())
    ).all()
    existing_ids = {
        int(item.webhook_id)
        for item in db.scalars(
            select(ProjectNotificationWebhook).where(
                ProjectNotificationWebhook.project_id == project.id
            )
        ).all()
    }
    created = 0
    now = datetime.now()
    for source in source_records:
        canonical_id = duplicate_ids.get(int(source.id), int(source.id))
        canonical = webhook_map.get(canonical_id)
        if canonical is None or canonical_id in existing_ids:
            continue
        db.add(
            ProjectNotificationWebhook(
                project_id=int(project.id),
                webhook_id=canonical_id,
                enabled=bool(source.enabled),
                created_at=now,
                updated_at=now,
            )
        )
        existing_ids.add(canonical_id)
        created += 1
    return created


def _disable_duplicate_webhooks(
    db: Session,
    duplicate_ids: dict[int, int],
) -> None:
    if not duplicate_ids:
        return
    records = db.scalars(
        select(NotificationWebhook).where(
            NotificationWebhook.id.in_(list(duplicate_ids))
        )
    ).all()
    for record in records:
        record.enabled = False
        record.status = "DISABLED"
        record.last_test_message = (
            f"Merged into webhook {duplicate_ids[int(record.id)]} during project migration"
        )


def _effective_config(
    project: Project,
    group: ProjectGroup | None,
    config: ProjectTargetConfig | None,
    group_models: list[ProjectGroupAiReviewModel],
    target_type: str,
) -> dict[str, Any]:
    defaults = TARGET_TYPE_DEFAULTS.get(target_type, TARGET_TYPE_DEFAULTS["GENERAL"])
    return {
        "targetType": target_type,
        "templateCode": (
            config.template_code
            if config is not None and config.template_code
            else project.default_template_code or defaults["templateCode"]
        ),
        "profileCode": _effective_profile(project, group, config, target_type),
        "providerCode": _effective_provider(project, group, config, group_models),
        "reviewKeys": _effective_review_keys(group, group_models),
        "triggerOnMr": bool(group.trigger_on_mr) if group is not None else True,
        "triggerOnPush": bool(group.trigger_on_push) if group is not None else False,
        "triggerOnlyWhenRiskMatched": (
            bool(group.trigger_only_when_risk_matched) if group is not None else False
        ),
        "pushGate": _push_gate(group),
    }


def _push_gate(group: ProjectGroup | None) -> dict[str, int]:
    return {
        key: _policy_value(getattr(group, field, None) if group is not None else None, key)
        for key, field in (
            ("pushMinChangedFiles", "push_min_changed_files"),
            ("pushMinDiffBytes", "push_min_diff_bytes"),
            ("pushMinCommitCount", "push_min_commit_count"),
            ("pushMaxChangedFiles", "push_max_changed_files"),
            ("pushMaxDiffBytes", "push_max_diff_bytes"),
            ("pushDebounceSeconds", "push_debounce_seconds"),
        )
    }


def _effective_review_keys(
    group: ProjectGroup | None,
    group_models: list[ProjectGroupAiReviewModel],
) -> list[str]:
    keys = [item.review_key for item in group_models if bool(item.enabled)]
    if keys or group is None or not group.default_provider_code:
        return keys
    return [make_ai_review_model_key(group.default_provider_code, None, 0)]



def _effective_config_after_backfill(
    db: Session,
    project: Project,
    group: ProjectGroup | None,
    config: ProjectTargetConfig | None,
    group_models: list[ProjectGroupAiReviewModel],
    target_type: str,
    *,
    dry_run: bool,
) -> dict[str, Any]:
    settings = db.get(ProjectReviewSettings, int(project.id))
    project_models = db.scalars(
        select(ProjectAiReviewModel)
        .where(ProjectAiReviewModel.project_id == project.id)
        .order_by(ProjectAiReviewModel.sort_order.asc(), ProjectAiReviewModel.id.asc())
    ).all()
    if dry_run:
        settings_values = _settings_preview(group)
        model_keys = _effective_review_keys(group, group_models)
        provider_code = _effective_provider(project, group, config, group_models)
    else:
        settings_values = settings
        model_keys = [item.review_key for item in project_models if bool(item.enabled)]
        provider_code = _effective_provider_after_backfill(
            project,
            config,
            project_models,
            group,
        )
    defaults = TARGET_TYPE_DEFAULTS.get(target_type, TARGET_TYPE_DEFAULTS["GENERAL"])
    return {
        "targetType": project.target_type or target_type,
        "templateCode": (
            config.template_code
            if config is not None and config.template_code
            else project.default_template_code or defaults["templateCode"]
        ),
        "profileCode": (
            config.code_quality_profile_code
            if config is not None
            else _effective_profile(project, group, config, target_type)
        ),
        "providerCode": provider_code,
        "reviewKeys": model_keys,
        "triggerOnMr": (
            bool(settings_values.trigger_on_mr)
            if hasattr(settings_values, "trigger_on_mr")
            else bool(settings_values["triggerOnMr"])
        ),
        "triggerOnPush": (
            bool(settings_values.trigger_on_push)
            if hasattr(settings_values, "trigger_on_push")
            else bool(settings_values["triggerOnPush"])
        ),
        "triggerOnlyWhenRiskMatched": (
            bool(settings_values.trigger_only_when_risk_matched)
            if hasattr(settings_values, "trigger_only_when_risk_matched")
            else bool(settings_values["triggerOnlyWhenRiskMatched"])
        ),
        "pushGate": (
            _settings_push_gate(settings_values)
            if hasattr(settings_values, "push_min_changed_files")
            else settings_values["pushGate"]
        ),
    }


def _settings_preview(group: ProjectGroup | None) -> dict[str, Any]:
    return {
        "triggerOnMr": bool(group.trigger_on_mr) if group is not None else True,
        "triggerOnPush": bool(group.trigger_on_push) if group is not None else False,
        "triggerOnlyWhenRiskMatched": (
            bool(group.trigger_only_when_risk_matched) if group is not None else False
        ),
        "pushGate": _push_gate(group),
    }


def _settings_push_gate(settings: ProjectReviewSettings) -> dict[str, int]:
    return {
        "pushMinChangedFiles": int(settings.push_min_changed_files),
        "pushMinDiffBytes": int(settings.push_min_diff_bytes),
        "pushMinCommitCount": int(settings.push_min_commit_count),
        "pushMaxChangedFiles": int(settings.push_max_changed_files),
        "pushMaxDiffBytes": int(settings.push_max_diff_bytes),
        "pushDebounceSeconds": int(settings.push_debounce_seconds),
    }


def _effective_provider_after_backfill(
    project: Project,
    config: ProjectTargetConfig | None,
    project_models: list[ProjectAiReviewModel],
    group: ProjectGroup | None,
) -> str | None:
    if config is not None and config.provider_code:
        return config.provider_code.strip() or None
    if project.default_code_quality_provider_code:
        return project.default_code_quality_provider_code.strip() or None
    for model in project_models:
        if model.enabled and model.provider_code:
            return model.provider_code.strip() or None
    return group.default_provider_code.strip() if group and group.default_provider_code else None


def _compare_effective_configs(
    project_id: int,
    legacy: dict[str, Any],
    migrated: dict[str, Any],
) -> EffectiveConfigComparison:
    differences = tuple(
        key
        for key in sorted(set(legacy) | set(migrated))
        if legacy.get(key) != migrated.get(key)
    )
    return EffectiveConfigComparison(
        project_id=project_id,
        matches=not differences,
        legacy=legacy,
        migrated=migrated,
        differences=differences,
    )


def _effective_profile(
    project: Project,
    group: ProjectGroup | None,
    config: ProjectTargetConfig | None,
    target_type: str,
) -> str | None:
    if group is not None and group.default_code_quality_profile_code:
        return group.default_code_quality_profile_code.strip() or None
    if config is not None and config.code_quality_profile_code:
        return config.code_quality_profile_code.strip() or None
    if project.default_code_quality_profile_code:
        return project.default_code_quality_profile_code.strip() or None
    return TARGET_TYPE_DEFAULTS.get(target_type, TARGET_TYPE_DEFAULTS["GENERAL"]).get("profileCode")


def _effective_provider(
    project: Project,
    group: ProjectGroup | None,
    config: ProjectTargetConfig | None,
    group_models: list[ProjectGroupAiReviewModel],
) -> str | None:
    if config is not None and config.provider_code:
        return config.provider_code.strip() or None
    if project.default_code_quality_provider_code:
        return project.default_code_quality_provider_code.strip() or None
    if group is not None and group.default_provider_code:
        return group.default_provider_code.strip() or None
    for model in group_models:
        if model.enabled and model.provider_code:
            return model.provider_code.strip() or None
    return None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Audit or backfill project-centric Review configuration"
    )
    parser.add_argument("action", choices=("audit", "backfill"))
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args(argv)
    engine = create_engine_for_url(get_settings().database_url)
    try:
        with Session(engine) as db:
            if arguments.action == "audit":
                result = audit_project_configuration_migration(db)
                print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
                return
            result = backfill_project_configuration(db, dry_run=arguments.dry_run)
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

