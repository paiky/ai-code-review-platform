from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.json_utils import format_datetime
from app.notification.models import NotificationWebhook


def ensure_webhook_schema(db: Session) -> None:
    connection = db.connection()
    inspector = inspect(connection)
    if not inspector.has_table("notification_webhooks"):
        NotificationWebhook.__table__.create(connection, checkfirst=True)
        return
    columns = {column["name"] for column in inspector.get_columns("notification_webhooks")}
    if "enabled" not in columns:
        db.execute(
            text("ALTER TABLE notification_webhooks ADD COLUMN enabled BOOLEAN NOT NULL DEFAULT TRUE")
        )
    db.flush()


def list_webhooks(db: Session) -> list[NotificationWebhook]:
    ensure_webhook_schema(db)
    return db.scalars(
        select(NotificationWebhook)
        .where(NotificationWebhook.channel == "DINGTALK")
        .order_by(NotificationWebhook.id.asc())
    ).all()


def list_enabled_webhooks(db: Session) -> list[NotificationWebhook]:
    ensure_webhook_schema(db)
    return db.scalars(
        select(NotificationWebhook)
        .where(NotificationWebhook.channel == "DINGTALK")
        .where(NotificationWebhook.enabled.is_(True))
        .where(NotificationWebhook.status == "ENABLED")
        .order_by(NotificationWebhook.id.asc())
    ).all()


def webhook_to_dict(record: NotificationWebhook) -> dict[str, Any]:
    return {
        "id": record.id,
        "name": record.name,
        "channel": record.channel,
        "webhookUrl": record.webhook_url,
        "webhookMasked": mask_webhook(record.webhook_url),
        "enabled": bool(record.enabled) and record.status == "ENABLED",
        "status": record.status,
        "updatedAt": format_datetime(record.updated_at),
    }


def upsert_webhooks(db: Session, webhook_requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ensure_webhook_schema(db)
    existing_records = {record.id: record for record in list_webhooks(db)}
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
    return [webhook_to_dict(record) for record in list_webhooks(db)]


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
