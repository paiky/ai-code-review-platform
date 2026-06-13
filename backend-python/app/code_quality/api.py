from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.code_quality import service
from app.core.database import get_db
from app.core.response import ok


review_router = APIRouter(prefix="/api/code-quality-reviews", tags=["code-quality-reviews"])
profile_router = APIRouter(
    prefix="/api/code-quality-review-profiles", tags=["code-quality-review-profiles"]
)
provider_router = APIRouter(
    prefix="/api/code-quality-review-providers", tags=["code-quality-review-providers"]
)


@review_router.post("/manual")
async def manual_review(request: dict, db: Session = Depends(get_db)) -> dict:
    return ok(service.create_manual_review(db, request))


@review_router.get("/settings")
async def get_settings(db: Session = Depends(get_db)) -> dict:
    return ok(service.get_settings_response(db))


@review_router.get("/job-queue")
async def get_job_queue(db: Session = Depends(get_db)) -> dict:
    return ok(service.get_job_queue_response(db))


@review_router.post("/job-queue/{job_id}/cancel")
async def cancel_job(job_id: int, db: Session = Depends(get_db)) -> dict:
    return ok(service.cancel_job_response(db, job_id))


@review_router.get("/failure-notifications")
async def get_failure_notifications(db: Session = Depends(get_db)) -> dict:
    return ok(service.get_failure_notifications_response(db))


@review_router.get("/rule-gaps")
async def get_rule_gaps(
    project_id: int | None = Query(default=None, alias="projectId"),
    gap_type: str | None = Query(default=None, alias="gapType"),
    signal: str | None = None,
    recent_days: int | None = Query(default=30, alias="recentDays", ge=1, le=3650),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict:
    return ok(
        service.get_rule_gap_dashboard_response(
            db,
            project_id=project_id,
            gap_type=gap_type,
            signal=signal,
            recent_days=recent_days,
            limit=limit,
        )
    )


@review_router.put("/settings")
async def update_settings(request: dict, db: Session = Depends(get_db)) -> dict:
    return ok(service.update_settings(db, request))


@review_router.post("/tasks/{task_id}/retry")
async def retry(task_id: int, request: dict | None = None, db: Session = Depends(get_db)) -> dict:
    return ok(service.retry_review_task(db, task_id, request))


@review_router.post("/tasks/{task_id}/cancel")
async def cancel_task_jobs(task_id: int, request: dict | None = None, db: Session = Depends(get_db)) -> dict:
    return ok(service.cancel_task_jobs_response(db, task_id, request))


@profile_router.get("")
async def list_profiles(db: Session = Depends(get_db)) -> dict:
    from app.code_quality.repository import list_enabled_profiles

    return ok(list_enabled_profiles(db))


@profile_router.get("/{profile_code}")
async def get_profile(profile_code: str, db: Session = Depends(get_db)) -> dict:
    return ok(service.get_profile_response(db, profile_code))


@profile_router.put("/{profile_code}")
async def update_profile(profile_code: str, request: dict, db: Session = Depends(get_db)) -> dict:
    return ok(service.update_profile_response(db, profile_code, request))


@profile_router.get("/{profile_code}/rendered-prompt")
async def rendered_prompt(
    profile_code: str,
    project_id: int | None = Query(default=None, alias="projectId"),
    db: Session = Depends(get_db),
) -> dict:
    return ok(service.rendered_prompt(db, profile_code, project_id=project_id))


@profile_router.post("/{profile_code}/reset-default-prompt")
async def reset_default_prompt(profile_code: str, db: Session = Depends(get_db)) -> dict:
    return ok(service.reset_default_prompt_response(db, profile_code))


@provider_router.get("")
async def list_providers(db: Session = Depends(get_db)) -> dict:
    return ok(service.list_provider_response(db))


@provider_router.put("/{provider_code}")
async def update_provider(provider_code: str, request: dict, db: Session = Depends(get_db)) -> dict:
    return ok(service.update_provider_response(db, provider_code, request))


@provider_router.post("/{provider_code}/test")
async def test_provider(provider_code: str, request: dict, db: Session = Depends(get_db)) -> dict:
    return ok(service.test_provider_response(db, provider_code, request))


@provider_router.post("/{provider_code}/set-default")
async def set_default_provider(provider_code: str, db: Session = Depends(get_db)) -> dict:
    return ok(service.set_default_provider_response(db, provider_code))
