from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import ok
from app.review_quality_acceptance import service


router = APIRouter(prefix="/api/review-quality/acceptance-gates", tags=["review-quality-acceptance"])


@router.post("")
async def create_acceptance_gate(request: dict, db: Session = Depends(get_db)) -> dict:
    return ok(service.create_acceptance_gate_response(db, request))


@router.get("")
async def list_acceptance_gates(
    project_id: int | None = Query(default=None, alias="projectId"),
    change_type: str | None = Query(default=None, alias="changeType"),
    status: str | None = None,
    provider: str | None = None,
    profile: str | None = None,
    risk_type: str | None = Query(default=None, alias="riskType"),
    page_no: int = Query(default=1, alias="pageNo", ge=1),
    page_size: int = Query(default=20, alias="pageSize", ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    return ok(
        service.list_acceptance_gate_response(
            db,
            project_id=project_id,
            change_type=change_type,
            status=status,
            provider=provider,
            profile=profile,
            risk_type=risk_type,
            page_no=page_no,
            page_size=page_size,
        )
    )


@router.get("/{gate_id}")
async def get_acceptance_gate(gate_id: int, db: Session = Depends(get_db)) -> dict:
    return ok(service.get_acceptance_gate_response(db, gate_id))


@router.put("/{gate_id}")
async def update_acceptance_gate(gate_id: int, request: dict, db: Session = Depends(get_db)) -> dict:
    return ok(service.update_acceptance_gate_response(db, gate_id, request))
