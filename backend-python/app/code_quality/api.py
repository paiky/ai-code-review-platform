from fastapi import APIRouter, Depends
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


@review_router.put("/settings")
async def update_settings(request: dict, db: Session = Depends(get_db)) -> dict:
    return ok(service.update_settings(db, request))


@review_router.post("/tasks/{task_id}/retry")
async def retry(task_id: int, db: Session = Depends(get_db)) -> dict:
    return ok(service.retry_review_task(db, task_id))


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
async def rendered_prompt(profile_code: str, db: Session = Depends(get_db)) -> dict:
    return ok(service.rendered_prompt(db, profile_code))


@profile_router.post("/{profile_code}/reset-default-prompt")
async def reset_default_prompt(profile_code: str, db: Session = Depends(get_db)) -> dict:
    return ok(service.reset_default_prompt_response(db, profile_code))


@provider_router.get("")
async def list_providers(db: Session = Depends(get_db)) -> dict:
    return ok(service.list_provider_response(db))


@provider_router.put("/{provider_code}")
async def update_provider(provider_code: str, request: dict, db: Session = Depends(get_db)) -> dict:
    return ok(service.update_provider_response(db, provider_code, request))


@provider_router.post("/{provider_code}/set-default")
async def set_default_provider(provider_code: str, db: Session = Depends(get_db)) -> dict:
    return ok(service.set_default_provider_response(db, provider_code))
