from __future__ import annotations

from datetime import datetime
from threading import Lock
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import func, inspect, or_, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.json_utils import format_datetime, page_response
from app.notification.models import NotificationWebhook, ProjectNotificationWebhook
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
        trigger_on_push=True,
        trigger_only_when_risk_matched=False,
        auto_fix_preview_enabled=True,
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
    project_id = db.scalar(text("SELECT project_id FROM review_tasks WHERE id = :task_id"), {"task_id": task_id})
    if project_id is not None:
        records = db.scalars(
            select(NotificationWebhook)
            .join(
                ProjectNotificationWebhook,
                ProjectNotificationWebhook.webhook_id == NotificationWebhook.id,
            )
            .where(ProjectNotificationWebhook.project_id == int(project_id))
            .where(ProjectNotificationWebhook.enabled.is_(True))
            .where(NotificationWebhook.channel == "DINGTALK")
            .where(NotificationWebhook.enabled.is_(True))
            .where(NotificationWebhook.status == "ENABLED")
            .order_by(NotificationWebhook.id.asc())
        ).all()
        if records or not get_settings().project_notification_group_fallback_enabled:
            return records
    if not get_settings().project_notification_group_fallback_enabled:
        return []
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


def notification_webhook_to_dict(
    record: NotificationWebhook,
    *,
    project_count: int = 0,
) -> dict[str, Any]:
    return {
        "id": record.id,
        "name": record.name,
        "channel": record.channel,
        "description": record.description,
        "enabled": bool(record.enabled) and record.status == "ENABLED",
        "status": record.status,
        "webhookMasked": mask_webhook(record.webhook_url),
        "lastTestStatus": record.last_test_status,
        "lastTestAt": format_datetime(record.last_test_at),
        "lastTestMessage": record.last_test_message,
        "projectCount": int(project_count),
        "updatedAt": format_datetime(record.updated_at),
    }


def _notification_webhook_project_counts(db: Session, webhook_ids: list[int]) -> dict[int, int]:
    if not webhook_ids:
        return {}
    rows = db.execute(
        select(
            ProjectNotificationWebhook.webhook_id,
            func.count(ProjectNotificationWebhook.project_id),
        )
        .where(ProjectNotificationWebhook.webhook_id.in_(webhook_ids))
        .where(ProjectNotificationWebhook.enabled.is_(True))
        .group_by(ProjectNotificationWebhook.webhook_id)
    ).all()
    return {int(webhook_id): int(count) for webhook_id, count in rows}


def list_notification_webhooks(
    db: Session,
    *,
    keyword: str | None = None,
    status: str | None = None,
    last_test_status: str | None = None,
    page_no: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    ensure_webhook_schema(db)
    records = db.scalars(
        select(NotificationWebhook)
        .where(NotificationWebhook.channel == "DINGTALK")
        .order_by(NotificationWebhook.id.desc())
    ).all()
    normalized_keyword = str(keyword or "").strip().casefold()
    normalized_status = str(status or "").strip().upper()
    normalized_test_status = str(last_test_status or "").strip().upper()
    filtered: list[NotificationWebhook] = []
    for record in records:
        masked = mask_webhook(record.webhook_url) or ""
        if normalized_keyword and not any(
            normalized_keyword in value.casefold()
            for value in (record.name or "", record.description or "", masked[-4:])
        ):
            continue
        if normalized_status and normalized_status != str(record.status or "").upper():
            continue
        if normalized_test_status and normalized_test_status != str(record.last_test_status or "").upper():
            continue
        filtered.append(record)
    safe_page_no = max(int(page_no or 1), 1)
    safe_page_size = min(max(int(page_size or 20), 1), 100)
    total = len(filtered)
    start = (safe_page_no - 1) * safe_page_size
    page = filtered[start : start + safe_page_size]
    counts = _notification_webhook_project_counts(db, [int(record.id) for record in page])
    return page_response(
        [notification_webhook_to_dict(record, project_count=counts.get(int(record.id), 0)) for record in page],
        safe_page_no,
        safe_page_size,
        total,
    )


def get_notification_webhook(db: Session, webhook_id: int) -> NotificationWebhook:
    ensure_webhook_schema(db)
    record = db.get(NotificationWebhook, int(webhook_id))
    if record is None or record.channel != "DINGTALK":
        raise AppError("RESOURCE_NOT_FOUND", f"Notification webhook not found: {webhook_id}", 404)
    return record


def _assert_webhook_url_available(db: Session, webhook_url: str, exclude_id: int | None = None) -> None:
    query = select(NotificationWebhook).where(
        NotificationWebhook.channel == "DINGTALK",
        NotificationWebhook.webhook_url == webhook_url,
    )
    if exclude_id is not None:
        query = query.where(NotificationWebhook.id != exclude_id)
    if db.scalars(query).first() is not None:
        raise AppError("VALIDATION_ERROR", "Duplicate DingTalk webhook URL", 400)


def create_notification_webhook(db: Session, request: dict[str, Any]) -> dict[str, Any]:
    ensure_webhook_schema(db)
    name = str(request.get("name") or "").strip()
    webhook_url = str(request.get("webhookUrl") or "").strip()
    if not name:
        raise AppError("VALIDATION_ERROR", "name is required", 400)
    validate_webhook_url(webhook_url)
    _assert_webhook_url_available(db, webhook_url)
    enabled = bool(request.get("enabled", True))
    now = datetime.now()
    record = NotificationWebhook(
        project_group_id=None,
        name=name,
        channel="DINGTALK",
        webhook_url=webhook_url,
        secret_ref=None,
        description=str(request.get("description") or "").strip() or None,
        last_test_status="UNTESTED",
        status="ENABLED" if enabled else "DISABLED",
        enabled=enabled,
        created_at=now,
        updated_at=now,
    )
    db.add(record)
    db.flush()
    return notification_webhook_to_dict(record)


def update_notification_webhook(db: Session, webhook_id: int, request: dict[str, Any]) -> dict[str, Any]:
    record = get_notification_webhook(db, webhook_id)
    if "name" in request:
        name = str(request.get("name") or "").strip()
        if not name:
            raise AppError("VALIDATION_ERROR", "name is required", 400)
        record.name = name
    if "webhookUrl" in request and request.get("webhookUrl") is not None:
        webhook_url = str(request.get("webhookUrl") or "").strip()
        validate_webhook_url(webhook_url)
        _assert_webhook_url_available(db, webhook_url, record.id)
        if webhook_url != record.webhook_url:
            record.last_test_status = "UNTESTED"
            record.last_test_at = None
            record.last_test_message = None
        record.webhook_url = webhook_url
    if "description" in request:
        record.description = str(request.get("description") or "").strip() or None
    if "enabled" in request:
        record.enabled = bool(request["enabled"])
        record.status = "ENABLED" if record.enabled else "DISABLED"
    record.updated_at = datetime.now()
    db.flush()
    counts = _notification_webhook_project_counts(db, [int(record.id)])
    return notification_webhook_to_dict(record, project_count=counts.get(int(record.id), 0))


def delete_notification_webhook(db: Session, webhook_id: int) -> None:
    record = get_notification_webhook(db, webhook_id)
    count = db.scalar(
        select(func.count())
        .select_from(ProjectNotificationWebhook)
        .where(ProjectNotificationWebhook.webhook_id == record.id)
    ) or 0
    if count:
        raise AppError(
            "VALIDATION_ERROR",
            f"Notification webhook is still associated with {int(count)} project(s)",
            400,
        )
    db.delete(record)
    db.flush()


def list_notification_webhook_projects(db: Session, webhook_id: int) -> list[dict[str, Any]]:
    get_notification_webhook(db, webhook_id)
    rows = db.execute(
        select(Project, ProjectNotificationWebhook)
        .join(ProjectNotificationWebhook, ProjectNotificationWebhook.project_id == Project.id)
        .where(ProjectNotificationWebhook.webhook_id == webhook_id)
        .where(ProjectNotificationWebhook.enabled.is_(True))
        .order_by(Project.id.asc())
    ).all()
    return [
        {
            "id": project.id,
            "name": project.name,
            "status": project.status,
            "enabled": project.status == "ENABLED",
        }
        for project, _relation in rows
    ]


def _normalize_batch_request(request: dict[str, Any]) -> tuple[list[int], list[int], str]:
    try:
        project_ids = list(dict.fromkeys(int(item) for item in request.get("projectIds") or []))
        webhook_ids = list(dict.fromkeys(int(item) for item in request.get("webhookIds") or []))
    except (TypeError, ValueError):
        raise AppError("VALIDATION_ERROR", "projectIds and webhookIds must contain numeric ids", 400) from None
    mode = str(request.get("mode") or "REPLACE").strip().upper()
    if mode not in {"REPLACE", "ADD", "REMOVE"}:
        raise AppError("VALIDATION_ERROR", "mode must be REPLACE, ADD or REMOVE", 400)
    if not project_ids:
        raise AppError("VALIDATION_ERROR", "projectIds must not be empty", 400)
    return project_ids, webhook_ids, mode


def _batch_notification_webhook_diff(
    db: Session,
    project_ids: list[int],
    webhook_ids: list[int],
    mode: str,
) -> dict[str, Any]:
    projects = db.scalars(select(Project).where(Project.id.in_(project_ids))).all()
    found_project_ids = {int(project.id) for project in projects}
    missing_projects = sorted(set(project_ids) - found_project_ids)
    if missing_projects:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {missing_projects[0]}", 404)
    if webhook_ids:
        found_webhook_ids = {
            int(item.id)
            for item in db.scalars(
                select(NotificationWebhook).where(
                    NotificationWebhook.id.in_(webhook_ids),
                    NotificationWebhook.channel == "DINGTALK",
                )
            ).all()
        }
        missing_webhooks = sorted(set(webhook_ids) - found_webhook_ids)
        if missing_webhooks:
            raise AppError("RESOURCE_NOT_FOUND", f"Notification webhook not found: {missing_webhooks[0]}", 404)
    existing_rows = db.scalars(
        select(ProjectNotificationWebhook).where(
            ProjectNotificationWebhook.project_id.in_(project_ids),
            ProjectNotificationWebhook.enabled.is_(True),
        )
    ).all()
    existing = {int(row.project_id): set() for row in existing_rows}
    for row in existing_rows:
        existing.setdefault(int(row.project_id), set()).add(int(row.webhook_id))
    items = []
    for project_id in project_ids:
        before = sorted(existing.get(project_id, set()))
        if mode == "REPLACE":
            after_set = set(webhook_ids)
        elif mode == "ADD":
            after_set = set(before) | set(webhook_ids)
        else:
            after_set = set(before) - set(webhook_ids)
        after = sorted(after_set)
        items.append(
            {
                "projectId": project_id,
                "beforeWebhookIds": before,
                "afterWebhookIds": after,
                "addedWebhookIds": sorted(after_set - set(before)),
                "removedWebhookIds": sorted(set(before) - after_set),
            }
        )
    changed = [item for item in items if item["beforeWebhookIds"] != item["afterWebhookIds"]]
    return {
        "changedProjectCount": len(changed),
        "unchangedProjectCount": len(items) - len(changed),
        "items": items,
    }


def preview_project_notification_webhooks(db: Session, request: dict[str, Any]) -> dict[str, Any]:
    project_ids, webhook_ids, mode = _normalize_batch_request(request)
    return _batch_notification_webhook_diff(db, project_ids, webhook_ids, mode)


def update_project_notification_webhooks(db: Session, request: dict[str, Any]) -> dict[str, Any]:
    project_ids, webhook_ids, mode = _normalize_batch_request(request)
    diff = _batch_notification_webhook_diff(db, project_ids, webhook_ids, mode)
    target_by_project = {
        int(item["projectId"]): set(item["afterWebhookIds"])
        for item in diff["items"]
    }
    existing_rows = db.scalars(
        select(ProjectNotificationWebhook).where(
            ProjectNotificationWebhook.project_id.in_(project_ids)
        )
    ).all()
    now = datetime.now()
    for row in existing_rows:
        target_ids = target_by_project[int(row.project_id)]
        if int(row.webhook_id) not in target_ids:
            db.delete(row)
        else:
            row.enabled = True
            row.updated_at = now
    db.flush()
    existing_keys = {
        (int(row.project_id), int(row.webhook_id))
        for row in db.scalars(
            select(ProjectNotificationWebhook).where(
                ProjectNotificationWebhook.project_id.in_(project_ids)
            )
        ).all()
    }
    now = datetime.now()
    for project_id, targets in target_by_project.items():
        for webhook_id in targets:
            if (project_id, webhook_id) in existing_keys:
                continue
            db.add(
                ProjectNotificationWebhook(
                    project_id=project_id,
                    webhook_id=webhook_id,
                    enabled=True,
                    created_at=now,
                    updated_at=now,
                )
            )
    db.flush()
    return diff


def project_webhook_ids_for_task(db: Session, task_id: int) -> list[int]:
    project_id = db.scalar(text("SELECT project_id FROM review_tasks WHERE id = :task_id"), {"task_id": task_id})
    if project_id is None:
        return []
    return [
        int(value)
        for value in db.scalars(
            select(ProjectNotificationWebhook.webhook_id)
            .where(ProjectNotificationWebhook.project_id == int(project_id))
            .where(ProjectNotificationWebhook.enabled.is_(True))
            .order_by(ProjectNotificationWebhook.webhook_id.asc())
        ).all()
    ]

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
