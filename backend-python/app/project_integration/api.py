from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import ok
from app.project_integration.repository import (
    apply_project_target_type_auto_detection,
    create_project,
    create_project_group,
    list_enabled_projects,
    list_project_groups,
    list_project_target_configs,
    list_target_type_path_mappings,
    project_configuration_defaults_response,
    project_configuration_response,
    project_target_type_auto_detection_preview,
    project_review_settings_response,
    update_project_configuration,
    update_project_group,
    update_project_group_binding,
    update_project_review_settings,
    update_target_type_path_mappings,
    upsert_project_target_config,
)
from app.project_integration.schemas import (
    ProjectConfigurationUpdateRequest,
    ProjectReviewSettingsUpdateRequest,
    ProjectTargetTypeAutoDetectionApplyRequest,
    TargetType,
)
from app.project_integration.service import handle_gitlab_webhook


router = APIRouter(prefix="/api/projects", tags=["projects"])
webhook_router = APIRouter(prefix="/api/webhooks/gitlab", tags=["gitlab-webhooks"])


group_router = APIRouter(prefix="/api/project-groups", tags=["project-groups"])
target_mapping_router = APIRouter(prefix="/api/target-type-path-mappings", tags=["target-type-path-mappings"])


@group_router.get("")
async def find_project_groups(db: Session = Depends(get_db)) -> dict:
    return ok(list_project_groups(db))


@group_router.post("")
async def create_group(request: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    return ok(create_project_group(db, request))


@group_router.put("/{group_id}")
async def update_group(group_id: int, request: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    return ok(update_project_group(db, group_id, request))


@target_mapping_router.get("")
async def find_target_type_path_mappings(db: Session = Depends(get_db)) -> dict:
    return ok(list_target_type_path_mappings(db))


@target_mapping_router.put("")
async def save_target_type_path_mappings(request: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    return ok(update_target_type_path_mappings(db, request))


@router.get("")
async def list_projects(
    group_id: int | None = Query(default=None, alias="groupId"),
    target_type: str | None = Query(default=None, alias="targetType"),
    keyword: str | None = Query(default=None),
    notification_status: Literal[
        "CONFIGURED",
        "UNCONFIGURED",
        "ABNORMAL",
        "HEALTH_WARNING",
    ]
    | None = Query(default=None, alias="notificationStatus"),
    review_status: Literal["CONFIGURED", "UNCONFIGURED"] | None = Query(
        default=None,
        alias="reviewStatus",
    ),
    page_no: int | None = Query(default=None, alias="pageNo", ge=1),
    page_size: int | None = Query(default=None, alias="pageSize", ge=1, le=100),
    include_disabled: bool = Query(default=False, alias="includeDisabled"),
    db: Session = Depends(get_db),
) -> dict:
    return ok(
        list_enabled_projects(
            db,
            group_id=group_id,
            target_type=target_type,
            keyword=keyword,
            notification_status=notification_status,
            review_status=review_status,
            page_no=page_no,
            page_size=page_size,
            include_disabled=include_disabled,
        )
    )


@router.post("")
async def create_project_record(request: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    return ok(create_project(db, request))


@router.get("/configuration-defaults")
async def get_project_configuration_defaults(
    target_type: TargetType = Query(alias="targetType"),
) -> dict:
    return ok(project_configuration_defaults_response(target_type))


@router.put("/{project_id}/group")
async def bind_project_group(project_id: int, request: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    return ok(update_project_group_binding(db, project_id, request))


@router.get("/{project_id}/configuration")
async def get_project_configuration(project_id: int, db: Session = Depends(get_db)) -> dict:
    return ok(project_configuration_response(db, project_id))


@router.put("/{project_id}/configuration")
async def save_project_configuration(
    project_id: int,
    request: ProjectConfigurationUpdateRequest,
    db: Session = Depends(get_db),
) -> dict:
    payload = request.model_dump(by_alias=True)
    return ok(update_project_configuration(db, project_id, payload))


@router.get("/{project_id}/target-type-auto-detection/preview")
async def preview_project_target_type_auto_detection(
    project_id: int,
    db: Session = Depends(get_db),
) -> dict:
    return ok(project_target_type_auto_detection_preview(db, project_id))


@router.put("/{project_id}/target-type-auto-detection")
async def restore_project_target_type_auto_detection(
    project_id: int,
    request: ProjectTargetTypeAutoDetectionApplyRequest,
    db: Session = Depends(get_db),
) -> dict:
    payload = request.model_dump(by_alias=True)
    return ok(apply_project_target_type_auto_detection(db, project_id, payload))


@router.get("/{project_id}/review-settings")
async def get_project_review_settings(project_id: int, db: Session = Depends(get_db)) -> dict:
    return ok(project_review_settings_response(db, project_id))


@router.put("/{project_id}/review-settings")
async def save_project_review_settings(
    project_id: int,
    request: ProjectReviewSettingsUpdateRequest,
    db: Session = Depends(get_db),
) -> dict:
    payload = request.model_dump(by_alias=True, exclude_unset=True)
    return ok(update_project_review_settings(db, project_id, payload))


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
