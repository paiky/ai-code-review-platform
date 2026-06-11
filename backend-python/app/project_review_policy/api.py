from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import ok
from app.project_review_policy.service import (
    list_project_review_policies_response,
    set_project_review_policy_enabled_response,
    update_project_review_policy_response,
)


project_policy_project_router = APIRouter(prefix="/api/projects", tags=["project-review-policies"])
project_policy_router = APIRouter(prefix="/api/project-review-policies", tags=["project-review-policies"])


@project_policy_project_router.get("/{project_id}/review-policies")
async def list_project_review_policies(
    project_id: int,
    enabled: bool | None = None,
    policy_type: str | None = Query(default=None, alias="policyType"),
    risk_type: str | None = Query(default=None, alias="riskType"),
    db: Session = Depends(get_db),
) -> dict:
    return ok(
        list_project_review_policies_response(
            db,
            project_id,
            enabled=enabled,
            policy_type=policy_type,
            risk_type=risk_type,
        )
    )


@project_policy_router.put("/{policy_id}")
async def update_project_review_policy(policy_id: int, request: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    return ok(update_project_review_policy_response(db, policy_id, request))


@project_policy_router.put("/{policy_id}/enabled")
async def set_project_review_policy_enabled(policy_id: int, request: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    return ok(set_project_review_policy_enabled_response(db, policy_id, request))
