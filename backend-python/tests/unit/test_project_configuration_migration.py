import json

import pytest

from app.notification.models import NotificationWebhook, ProjectNotificationWebhook
from app.project_configuration_migration import (
    MigrationBlockedError,
    audit_project_configuration_migration,
    backfill_project_configuration,
)
from app.project_integration.models import (
    Project,
    ProjectGroup,
    ProjectGroupAiReviewModel,
    ProjectReviewSettings,
    ProjectTargetConfig,
)
from app.migrate import split_sql_statements


def _project(**overrides):
    values = {
        "id": 1,
        "group_id": 1,
        "name": "demo",
        "git_provider": "GITLAB",
        "git_project_id": "101",
        "repository_url": "https://gitlab.example/demo",
        "supported_target_types": json.dumps(["WEB_PC"]),
        "detected_target_types": json.dumps(["WEB_PC"]),
        "default_template_code": "frontend-default",
        "default_code_quality_profile_code": None,
        "default_code_quality_provider_code": None,
        "status": "ENABLED",
    }
    values.update(overrides)
    return Project(**values)


def _group(**overrides):
    values = {
        "id": 1,
        "group_name": "web",
        "group_code": "web",
        "default_code_quality_profile_code": "web-profile",
        "default_provider_code": "DEEPSEEK",
        "trigger_on_mr": False,
        "trigger_on_push": True,
        "trigger_only_when_risk_matched": True,
        "auto_fix_preview_enabled": True,
        "auto_fix_preview_severities": json.dumps(["MAJOR"]),
        "push_branch_patterns": json.dumps(["develop"]),
        "push_min_changed_files": 4,
        "push_min_diff_bytes": 1200,
        "push_min_commit_count": 2,
        "push_max_changed_files": -1,
        "push_max_diff_bytes": -1,
        "push_debounce_seconds": 60,
        "status": "ENABLED",
    }
    values.update(overrides)
    return ProjectGroup(**values)


def _target_config(**overrides):
    values = {
        "id": 1,
        "project_id": 1,
        "target_type": "WEB_PC",
        "template_code": "frontend-default",
        "code_quality_profile_code": "old-profile",
        "provider_code": None,
        "path_patterns": json.dumps(["frontend/**"]),
        "reminder_card_enabled": False,
        "enabled": True,
        "description": "手动维护的端类型配置",
    }
    values.update(overrides)
    return ProjectTargetConfig(**values)


def _webhook(webhook_id, url, *, enabled=True, project_group_id=1):
    return NotificationWebhook(
        id=webhook_id,
        project_group_id=project_group_id,
        name=f"webhook-{webhook_id}",
        channel="DINGTALK",
        webhook_url=url,
        status="ENABLED" if enabled else "DISABLED",
        enabled=enabled,
    )


def test_audit_reports_ambiguous_manual_target_types_as_blocking(db_session):
    db_session.add(_group())
    db_session.add(_project(supported_target_types=json.dumps(["WEB_PC", "BACKEND"])))
    db_session.add_all(
        [
            _target_config(id=1, target_type="WEB_PC"),
            _target_config(id=2, target_type="BACKEND"),
        ]
    )
    db_session.commit()

    report = audit_project_configuration_migration(db_session)

    assert report.is_ready is False
    assert {item.code for item in report.blocking_issues} >= {
        "MULTIPLE_MANUAL_TARGET_TYPES",
    }
    with pytest.raises(MigrationBlockedError):
        backfill_project_configuration(db_session, audit=report)


def test_backfill_is_idempotent_and_preserves_effective_configuration(db_session):
    db_session.add(_group())
    db_session.add(_project())
    db_session.add(
        _target_config()
    )
    db_session.add(
        ProjectGroupAiReviewModel(
            id=1,
            group_id=1,
            review_key="deepseek-default",
            provider_code="DEEPSEEK",
            model_name=None,
            display_name="DeepSeek",
            enabled=True,
            sort_order=10,
        )
    )
    db_session.add_all(
        [
            _webhook(1, "https://oapi.example/token"),
            _webhook(2, " https://oapi.example/token ", enabled=False),
        ]
    )
    db_session.commit()

    report = audit_project_configuration_migration(db_session)
    assert report.is_ready is True
    assert report.duplicate_webhook_ids == {2: 1}
    assert any(item.code == "DUPLICATE_WEBHOOK_URL" for item in report.issues)

    result = backfill_project_configuration(db_session, audit=report)
    assert result.settings_created == 1
    assert result.models_created == 1
    assert result.webhook_relations_created == 1
    assert result.effective_configurations_match is True

    project = db_session.get(Project, 1)
    settings = db_session.get(ProjectReviewSettings, 1)
    relation = db_session.query(ProjectNotificationWebhook).one()
    duplicate = db_session.get(NotificationWebhook, 2)
    assert project.target_type == "WEB_PC"
    assert json.loads(project.supported_target_types) == ["WEB_PC"]
    assert settings.trigger_on_mr is False
    assert settings.trigger_on_push is True
    assert settings.push_min_changed_files == 4
    assert relation.webhook_id == 1
    assert duplicate.enabled is False

    second = backfill_project_configuration(db_session)
    assert second.settings_created == 0
    assert second.models_created == 0
    assert second.webhook_relations_created == 0
    assert second.effective_configurations_match is True



def test_v54_bootstrap_contains_all_project_centric_foundation_objects():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    sql = (
        root
        / "backend-python/migrations/bootstrap_sql/"
        "V54__project_centric_review_configuration_foundation.sql"
    ).read_text(encoding="utf-8")
    statements = split_sql_statements(sql)

    assert len(statements) == 11
    assert "ADD COLUMN target_type VARCHAR(32)" in statements[0]
    assert "idx_projects_target_type_status" in statements[1]
    assert "last_test_status" in sql
    assert "CREATE TABLE IF NOT EXISTS project_review_settings" in sql
    assert "CREATE TABLE IF NOT EXISTS project_ai_review_models" in sql
    assert "CREATE TABLE IF NOT EXISTS project_notification_webhooks" in sql


def test_dry_run_does_not_write_project_foundation(db_session):
    db_session.add(_group())
    db_session.add(_project())
    db_session.add(_target_config())
    db_session.commit()

    result = backfill_project_configuration(db_session, dry_run=True)

    assert result.dry_run is True
    assert db_session.get(Project, 1).target_type is None
    assert db_session.get(ProjectReviewSettings, 1) is None
    assert db_session.query(ProjectNotificationWebhook).count() == 0



def test_v54_reconciles_runtime_added_columns_and_index(monkeypatch):
    from app.migrate import (
        MigrationFile,
        _migration_statement_already_satisfied,
    )

    class Inspector:
        def has_table(self, table_name):
            return table_name in {"projects", "notification_webhooks"}

        def get_columns(self, table_name):
            if table_name == "projects":
                return [
                    {"name": "target_type", "type": "VARCHAR(32)", "nullable": True},
                ]
            return [
                {"name": "project_group_id", "type": "BIGINT", "nullable": True},
                {
                    "name": "enabled",
                    "type": "BOOLEAN",
                    "nullable": False,
                    "default": "1",
                },
            ]

        def get_indexes(self, table_name):
            if table_name == "projects":
                return [{"name": "idx_projects_target_type_status"}]
            return []

    monkeypatch.setattr("app.migrate.inspect", lambda _connection: Inspector())
    migration = MigrationFile(54, "foundation", "V54.sql", "checksum", None)

    assert _migration_statement_already_satisfied(
        object(),
        migration,
        "ALTER TABLE projects ADD COLUMN target_type VARCHAR(32) NULL AFTER git_project_id",
    )
    assert _migration_statement_already_satisfied(
        object(),
        migration,
        "ALTER TABLE notification_webhooks "
        "ADD COLUMN enabled BOOLEAN NOT NULL DEFAULT TRUE",
    )
    assert _migration_statement_already_satisfied(
        object(),
        migration,
        "ALTER TABLE projects ADD INDEX "
        "idx_projects_target_type_status (target_type, status)",
    )
