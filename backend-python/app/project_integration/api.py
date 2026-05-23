from typing import Any

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import ok
from app.project_integration.repository import (
    create_project,
    create_project_group,
    list_enabled_projects,
    list_project_groups,
    list_project_target_configs,
    update_project_group,
    update_project_group_binding,
    upsert_project_target_config,
)
from app.project_integration.service import handle_gitlab_webhook


router = APIRouter(prefix="/api/projects", tags=["projects"])
webhook_router = APIRouter(prefix="/api/webhooks/gitlab", tags=["gitlab-webhooks"])


group_router = APIRouter(prefix="/api/project-groups", tags=["project-groups"])


@group_router.get("")
async def find_project_groups(db: Session = Depends(get_db)) -> dict:
    return ok(list_project_groups(db))


@group_router.post("")
async def create_group(request: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    return ok(create_project_group(db, request))


@group_router.put("/{group_id}")
async def update_group(group_id: int, request: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    return ok(update_project_group(db, group_id, request))


@router.get("")
async def list_projects(
    group_id: int | None = Query(default=None, alias="groupId"),
    target_type: str | None = Query(default=None, alias="targetType"),
    include_disabled: bool = Query(default=False, alias="includeDisabled"),
    db: Session = Depends(get_db),
) -> dict:
    return ok(list_enabled_projects(db, group_id=group_id, target_type=target_type, include_disabled=include_disabled))


@router.post("")
async def create_project_record(request: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    return ok(create_project(db, request))


@router.put("/{project_id}/group")
async def bind_project_group(project_id: int, request: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    return ok(update_project_group_binding(db, project_id, request))


@router.get("/{project_id}/target-configs")
async def find_project_target_configs(project_id: int, db: Session = Depends(get_db)) -> dict:
    return ok(list_project_target_configs(db, project_id))


@router.put("/{project_id}/target-configs/{target_type}")
async def update_project_target_config(
    project_id: int,
    target_type: str,
    request: dict[str, Any],
    db: Session = Depends(get_db),
) -> dict:
    return ok(upsert_project_target_config(db, project_id, target_type, request))


@webhook_router.post("/merge-request")
async def receive_gitlab_webhook(
    payload: dict[str, Any],
    gitlab_event: str | None = Header(default=None, alias="X-Gitlab-Event"),
    db: Session = Depends(get_db),
) -> dict:
    return ok(handle_gitlab_webhook(db, gitlab_event, payload))
