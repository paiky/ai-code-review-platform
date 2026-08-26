from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import ok
from app.review_quality import service
from app.review_quality.agent_observation import (
    export_agent_observation,
    get_agent_observation,
)


router = APIRouter(prefix="/api/review-quality", tags=["review-quality"])


@router.get("/dashboard")
async def get_review_quality_dashboard(
    project_id: int | None = Query(default=None, alias="projectId"),
    provider: str | None = None,
    profile: str | None = None,
    risk_type: str | None = Query(default=None, alias="riskType"),
    verdict: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    return ok(
        service.get_review_quality_dashboard(
            db,
            project_id=project_id,
            provider=provider,
            profile=profile,
            risk_type=risk_type,
            verdict=verdict,
        )
    )


@router.get("/agent-observation")
async def get_agent_review_observation(
    task_id: int | None = Query(default=None, alias="taskId"),
    project_id: int | None = Query(default=None, alias="projectId"),
    profile: str | None = None,
    start_at: str | None = Query(default=None, alias="startAt"),
    end_at: str | None = Query(default=None, alias="endAt"),
    synthetic_demo: bool = Query(default=False, alias="syntheticDemo"),
    db: Session = Depends(get_db),
) -> dict:
    return ok(
        get_agent_observation(
            db,
            task_id=task_id,
            project_id=project_id,
            profile=profile,
            start_at=start_at,
            end_at=end_at,
            synthetic_demo=synthetic_demo,
        )
    )


@router.post("/agent-observation/export")
async def export_agent_review_observation(
    request: dict,
    db: Session = Depends(get_db),
) -> dict:
    return ok(export_agent_observation(db, request))
