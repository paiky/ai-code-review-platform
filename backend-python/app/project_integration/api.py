from typing import Any

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import ok
from app.project_integration.repository import list_enabled_projects
from app.project_integration.service import handle_gitlab_webhook


router = APIRouter(prefix="/api/projects", tags=["projects"])
webhook_router = APIRouter(prefix="/api/webhooks/gitlab", tags=["gitlab-webhooks"])


@router.get("")
async def list_projects(db: Session = Depends(get_db)) -> dict:
    return ok(list_enabled_projects(db))


@webhook_router.post("/merge-request")
async def receive_gitlab_webhook(
    payload: dict[str, Any],
    gitlab_event: str | None = Header(default=None, alias="X-Gitlab-Event"),
    db: Session = Depends(get_db),
) -> dict:
    return ok(handle_gitlab_webhook(db, gitlab_event, payload))
