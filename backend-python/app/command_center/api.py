from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.command_center import service
from app.core.database import get_db
from app.core.response import ok


router = APIRouter(prefix="/api/command-center", tags=["command-center"])


@router.get("/runtime")
async def get_command_center_runtime(
    window_hours: int = Query(default=24, alias="windowHours", ge=1, le=168),
    active_limit: int = Query(default=20, alias="activeLimit", ge=1, le=50),
    alert_limit: int = Query(default=20, alias="alertLimit", ge=1, le=50),
    project_id: int | None = Query(default=None, alias="projectId", ge=1),
    group_id: int | None = Query(default=None, alias="groupId", ge=1),
    db: Session = Depends(get_db),
) -> dict:
    snapshot = service.get_runtime_snapshot(
        db,
        window_hours=window_hours,
        active_limit=active_limit,
        alert_limit=alert_limit,
        project_id=project_id,
        group_id=group_id,
    )
    return ok(snapshot.model_dump(by_alias=True, mode="json"))


@router.get("/governance")
async def get_command_center_governance(
    window_hours: int = Query(default=24, alias="windowHours", ge=1, le=168),
    project_id: int | None = Query(default=None, alias="projectId", ge=1),
    group_id: int | None = Query(default=None, alias="groupId", ge=1),
    db: Session = Depends(get_db),
) -> dict:
    snapshot = service.get_governance_snapshot(
        db,
        window_hours=window_hours,
        project_id=project_id,
        group_id=group_id,
    )
    return ok(snapshot.model_dump(by_alias=True, mode="json"))
