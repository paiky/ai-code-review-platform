from __future__ import annotations

from datetime import datetime
from threading import Lock
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import inspect, or_, select, text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.json_utils import format_datetime
from app.notification.models import NotificationWebhook
from app.project_integration.models import Project, ProjectGroup


_WEBHOOK_SCHEMA_LOCK = Lock()
_WEBHOOK_SCHEMA_ENSURED_ENGINE_IDS: set[int] = set()


def ensure_webhook_schema(db: Session) -> None:
    engine_id = id(db.get_bind())
    if engine_id in _WEBHOOK_SCHEMA_ENSURED_ENGINE_IDS:
        return
    with _WEBHOOK_SCHEMA_LOCK:
        if engine_id in _WEBHOOK_SCHEMA_ENSURED_ENGINE_IDS:
            return
        connection = db.connection()
        inspector = inspect(connection)
        if not inspector.has_table("notification_webhooks"):
            NotificationWebhook.__table__.create(connection, checkfirst=True)
            _add_index_if_missing(
                db,
                "notification_webhooks",
                "idx_notification_webhooks_group_channel_enabled",
                "project_group_id, channel, enabled, status",
            )
            db.flush()
            _WEBHOOK_SCHEMA_ENSURED_ENGINE_IDS.add(engine_id)
            return
        columns = {column["name"] for column in inspector.get_columns("notification_webhooks")}
        project_group_added = False
        if "project_group_id" not in columns:
            db.execute(text("ALTER TABLE notification_webhooks ADD COLUMN project_group_id BIGINT NULL"))
            columns.add("project_group_id")
            project_group_added = True
        if "enabled" not in columns:
            db.execute(
                text("ALTER TABLE notification_webhooks ADD COLUMN enabled BOOLEAN NOT NULL DEFAULT TRUE")
            )
            columns.add("enabled")
        if project_group_added:
            default_group_id = default_project_group_id(db)
            db.execute(
                text(
                    "UPDATE notification_webhooks "
                    "SET project_group_id = :group_id "
                    "WHERE project_group_id IS NULL"
                ),
                {"group_id": default_group_id},
            )
        _add_index_if_missing(
            db,
            "notification_webhooks",
            "idx_notification_webhooks_group_channel_enabled",
            "project_group_id, channel, enabled, status",
        )
        db.flush()
        _WEBHOOK_SCHEMA_ENSURED_ENGINE_IDS.add(engine_id)


def _add_index_if_missing(db: Session, table_name: str, index_name: str, columns_sql: str) -> None:
    inspector = inspect(db.connection())
    existing = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name in existing:
        return
    db.execute(text(f"CREATE INDEX {index_name} ON {table_name} ({columns_sql})"))


def default_project_group_id(db: Session) -> int:
    from app.project_integration.repository import ensure_project_config_schema

    ensure_project_config_schema(db)
    group = db.scalars(select(ProjectGroup).where(ProjectGroup.group_code == "default")).first()
    if group is not None:
        return int(group.id)
    now = datetime.now()
    group = ProjectGroup(
        group_name="默认项目组",
        group_code="default",
        default_provider_code=None,
        ai_review_enabled=True,
        trigger_on_manual=True,
        trigger_on_mr=True,
        trigger_on_push=False,
        trigger_only_when_risk_matched=False,
        auto_fix_preview_enabled=False,
        auto_fix_preview_severities='["CRITICAL"]',
        push_branch_patterns='["master"]',
        push_min_changed_files=10,
        push_min_diff_bytes=30000,
        push_min_commit_count=3,
        push_max_changed_files=-1,
        push_max_diff_bytes=-1,
        push_debounce_seconds=300,
        status="ENABLED",
        description="系统默认项目组",
        created_at=now,
        updated_at=now,
    )
    db.add(group)
    db.flush()
    return int(group.id)


def list_webhooks(db: Session, project_group_id: int | None = None) -> list[NotificationWebhook]:
    ensure_webhook_schema(db)
    group_id = default_project_group_id(db) if project_group_id is None else int(project_group_id)
    query = select(NotificationWebhook).where(NotificationWebhook.channel == "DINGTALK")
    if group_id == default_project_group_id(db):
        query = query.where(
            or_(
                NotificationWebhook.project_group_id == group_id,
                NotificationWebhook.project_group_id.is_(None),
            )
        )
    else:
        query = query.where(NotificationWebhook.project_group_id == group_id)
    return db.scalars(query.order_by(NotificationWebhook.id.asc())).all()


def list_enabled_webhooks(db: Session, project_group_id: int | None = None) -> list[NotificationWebhook]:
    ensure_webhook_schema(db)
    group_id = default_project_group_id(db) if project_group_id is None else int(project_group_id)
    query = (
        select(NotificationWebhook)
        .where(NotificationWebhook.channel == "DINGTALK")
        .where(NotificationWebhook.enabled.is_(True))
        .where(NotificationWebhook.status == "ENABLED")
    )
    if group_id == default_project_group_id(db):
        query = query.where(
            or_(
                NotificationWebhook.project_group_id == group_id,
                NotificationWebhook.project_group_id.is_(None),
            )
        )
    else:
        query = query.where(NotificationWebhook.project_group_id == group_id)
    return db.scalars(query.order_by(NotificationWebhook.id.asc())).all()


def webhook_to_dict(record: NotificationWebhook) -> dict[str, Any]:
    return {
        "id": record.id,
        "projectGroupId": record.project_group_id,
        "name": record.name,
        "channel": record.channel,
        "webhookUrl": record.webhook_url,
        "webhookMasked": mask_webhook(record.webhook_url),
        "enabled": bool(record.enabled) and record.status == "ENABLED",
        "status": record.status,
        "updatedAt": format_datetime(record.updated_at),
    }


def upsert_webhooks(
    db: Session,
    webhook_requests: list[dict[str, Any]],
    project_group_id: int | None = None,
) -> list[dict[str, Any]]:
    ensure_webhook_schema(db)
    group_id = default_project_group_id(db) if project_group_id is None else int(project_group_id)
    group = db.get(ProjectGroup, group_id)
    if group is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project group not found: {group_id}", 404)
    existing_records = {record.id: record for record in list_webhooks(db, group_id)}
    retained_ids: set[int] = set()
    seen_enabled_urls: set[str] = set()
    now = datetime.now()

    for item in webhook_requests:
        channel = str(item.get("channel") or "DINGTALK").strip().upper()
        if channel != "DINGTALK":
            raise AppError("VALIDATION_ERROR", "Only DINGTALK webhooks are supported", 400)
        name = str(item.get("name") or "").strip()
        webhook_url = str(item.get("webhookUrl") or "").strip()
        enabled = bool(item.get("enabled", True))
        if not name:
            raise AppError("VALIDATION_ERROR", "Webhook name is required", 400)
        validate_webhook_url(webhook_url)
        normalized_url = webhook_url.lower()
        if enabled and normalized_url in seen_enabled_urls:
            raise AppError("VALIDATION_ERROR", "Duplicate enabled DingTalk webhook URL", 400)
        if enabled:
            seen_enabled_urls.add(normalized_url)

        record_id = item.get("id")
        if record_id is None:
            db.add(
                NotificationWebhook(
                    project_group_id=group_id,
                    name=name,
                    channel="DINGTALK",
                    webhook_url=webhook_url,
                    secret_ref=None,
                    status="ENABLED" if enabled else "DISABLED",
                    enabled=enabled,
                    created_at=now,
                    updated_at=now,
                )
            )
            continue

        try:
            numeric_id = int(record_id)
        except (TypeError, ValueError):
            raise AppError("VALIDATION_ERROR", f"Invalid webhook id: {record_id}", 400) from None
        record = existing_records.get(numeric_id)
        if record is None:
            raise AppError("VALIDATION_ERROR", f"Webhook not found: {numeric_id}", 400)
        retained_ids.add(numeric_id)
        record.project_group_id = group_id
        record.name = name
        record.channel = "DINGTALK"
        record.webhook_url = webhook_url
        record.enabled = enabled
        record.status = "ENABLED" if enabled else "DISABLED"
        record.updated_at = now

    for record_id, record in existing_records.items():
        if record_id not in retained_ids:
            db.delete(record)

    db.flush()
    return [webhook_to_dict(record) for record in list_webhooks(db, group_id)]


def project_group_webhooks_to_dict(db: Session, project_group_id: int) -> list[dict[str, Any]]:
    return [webhook_to_dict(record) for record in list_webhooks(db, project_group_id)]


def enabled_webhooks_for_task(db: Session, task_id: int) -> list[NotificationWebhook]:
    ensure_webhook_schema(db)
    project_group_id = _task_project_group_id(db, task_id)
    return list_enabled_webhooks(db, project_group_id)


def has_any_enabled_webhook_for_task(db: Session, task_id: int | None = None) -> bool:
    if task_id is None:
        return bool(list_enabled_webhooks(db, default_project_group_id(db)))
    return bool(enabled_webhooks_for_task(db, task_id))


def _task_project_group_id(db: Session, task_id: int) -> int:
    project_id = db.scalar(text("SELECT project_id FROM review_tasks WHERE id = :task_id"), {"task_id": task_id})
    if project_id is None:
        return default_project_group_id(db)
    project = db.get(Project, int(project_id))
    return int(project.group_id) if project and project.group_id else default_project_group_id(db)


def validate_webhook_url(value: str) -> None:
    if not value:
        raise AppError("VALIDATION_ERROR", "Webhook URL is required", 400)
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise AppError("VALIDATION_ERROR", "Webhook URL must start with http:// or https://", 400)


def mask_webhook(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    if len(text) <= 16:
        return "****"
    return f"{text[:12]}...{text[-4:]}"
