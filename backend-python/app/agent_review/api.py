import secrets

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.agent_review import service
from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import AppError
from app.core.response import ok


router = APIRouter(prefix="/internal/agent-review", tags=["internal-agent-review"])


def require_worker_token(
    x_agent_worker_token: str | None = Header(default=None, alias="X-Agent-Worker-Token"),
) -> None:
    expected = get_settings().agent_review_worker_token
    if not expected or not x_agent_worker_token or not secrets.compare_digest(expected, x_agent_worker_token):
        raise AppError("AGENT_WORKER_UNAUTHORIZED", "Agent Worker token is invalid", 401)


@router.post("/workers/heartbeat", dependencies=[Depends(require_worker_token)])
async def worker_heartbeat(request: dict, db: Session = Depends(get_db)) -> dict:
    return ok(service.worker_heartbeat(db, request))


@router.post("/jobs/claim", dependencies=[Depends(require_worker_token)])
async def claim(request: dict, db: Session = Depends(get_db)) -> dict:
    return ok(service.claim_job(db, request))


@router.post("/configuration-test/complete", dependencies=[Depends(require_worker_token)])
async def configuration_test_complete(request: dict, db: Session = Depends(get_db)) -> dict:
    return ok(service.complete_configuration_test(db, request))


@router.post("/jobs/{job_id}/heartbeat", dependencies=[Depends(require_worker_token)])
async def heartbeat(job_id: int, request: dict, db: Session = Depends(get_db)) -> dict:
    return ok(service.heartbeat_job(db, job_id, request))


@router.post("/jobs/{job_id}/complete", dependencies=[Depends(require_worker_token)])
async def complete(job_id: int, request: dict, db: Session = Depends(get_db)) -> dict:
    return ok(service.complete_job(db, job_id, request))


@router.post("/jobs/{job_id}/fail", dependencies=[Depends(require_worker_token)])
async def fail(job_id: int, request: dict, db: Session = Depends(get_db)) -> dict:
    return ok(service.fail_job(db, job_id, request))


@router.post("/jobs/{job_id}/cancelled", dependencies=[Depends(require_worker_token)])
async def cancelled(job_id: int, request: dict, db: Session = Depends(get_db)) -> dict:
    return ok(service.fail_job(db, job_id, {**request, "failureCode": "AGENT_CANCELLED"}))
