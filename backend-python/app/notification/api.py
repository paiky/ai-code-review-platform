from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import ok
from app.notification.repository import (
    create_notification_webhook,
    delete_notification_webhook,
    list_notification_webhook_projects,
    list_notification_webhooks,
    preview_project_notification_webhooks,
    update_notification_webhook,
    update_project_notification_webhooks,
)
from app.notification.schemas import (
    NotificationWebhookCreateRequest,
    NotificationWebhookUpdateRequest,
    ProjectNotificationWebhookBatchRequest,
)
from app.notification.service import test_saved_notification_webhook


router = APIRouter(prefix="/api/notification-webhooks", tags=["notification-webhooks"])
project_router = APIRouter(prefix="/api/projects/notification-webhooks", tags=["project-notification-webhooks"])


@router.get("")
async def find_notification_webhooks(
    keyword: str | None = Query(default=None),
    status: str | None = Query(default=None),
    last_test_status: str | None = Query(default=None, alias="lastTestStatus"),
    page_no: int = Query(default=1, alias="pageNo", ge=1),
    page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return ok(
        list_notification_webhooks(
            db,
            keyword=keyword,
            status=status,
            last_test_status=last_test_status,
            page_no=page_no,
            page_size=page_size,
        )
    )


@router.post("")
async def create_notification_webhook_record(
    request: NotificationWebhookCreateRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    result = create_notification_webhook(db, request.model_dump(by_alias=True))
    db.commit()
    return ok(result)


@router.put("/{webhook_id}")
async def update_notification_webhook_record(
    webhook_id: int,
    request: NotificationWebhookUpdateRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    result = update_notification_webhook(
        db,
        webhook_id,
        request.model_dump(by_alias=True, exclude_unset=True),
    )
    db.commit()
    return ok(result)


@router.delete("/{webhook_id}")
async def delete_notification_webhook_record(webhook_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    delete_notification_webhook(db, webhook_id)
    db.commit()
    return ok({"deleted": True, "webhookId": webhook_id})


@router.post("/{webhook_id}/test")
async def test_notification_webhook_record(webhook_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    result = test_saved_notification_webhook(db, webhook_id)
    db.commit()
    return ok(result)


@router.get("/{webhook_id}/projects")
async def find_notification_webhook_projects(webhook_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(list_notification_webhook_projects(db, webhook_id))


@project_router.post("/batch/preview")
async def preview_project_notification_webhook_batch(
    request: ProjectNotificationWebhookBatchRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return ok(preview_project_notification_webhooks(db, request.model_dump(by_alias=True)))


@project_router.put("/batch")
async def update_project_notification_webhook_batch(
    request: ProjectNotificationWebhookBatchRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    result = update_project_notification_webhooks(db, request.model_dump(by_alias=True))
    db.commit()
    return ok(result)