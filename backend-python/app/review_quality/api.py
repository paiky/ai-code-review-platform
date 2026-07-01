from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import ok
from app.review_quality import service


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
