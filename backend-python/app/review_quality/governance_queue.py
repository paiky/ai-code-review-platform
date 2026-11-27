from dataclasses import dataclass
from datetime import datetime, timedelta
import os

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.core.json_utils import utc_now
from app.review_quality.governance_models import GovernanceControl, GovernanceEvent, GovernanceRun
from app.review_quality.monitoring import monitoring_enabled


LEASE = timedelta(seconds=45)
MAX_ATTEMPTS = 3
MAX_MODEL_CALLS = 4
ACTIVE = ("QUEUED", "RUNNING", "PAUSED")


@dataclass(frozen=True)
class Claim:
    run_id: int
    owner: str
    attempt: int


def governance_enabled() -> bool:
    return os.getenv("REVIEW_QUALITY_GOVERNANCE_ENABLED", "").lower() == "true"


def configured_provider_code() -> str:
    return os.getenv("REVIEW_QUALITY_GOVERNANCE_PROVIDER", "").strip().upper()


def add_event(db: Session, run: GovernanceRun, kind: str, details: dict | None = None) -> None:
    db.add(GovernanceEvent(run_id=run.id, kind=kind, details=details or {}, created_at=utc_now()))


def transition(run: GovernanceRun, status: str, now: datetime) -> None:
    run.status = status
    run.updated_at = now
    run.lease_owner = None
    run.lease_until = None
    run.finished_at = None if status in ACTIVE else now


def claim_next(db: Session, owner: str) -> Claim | None:
    if not governance_enabled() or not monitoring_enabled(db):
        return None
    now = utc_now()
    priority = func.coalesce(
        select(GovernanceControl.priority).where(GovernanceControl.issue_id == GovernanceRun.issue_id).scalar_subquery(),
        GovernanceRun.input_json["issue"]["priority"].as_string(),
    )
    # The plain lock works on MySQL 5.7. Expired claims remain eligible after a crash.
    run = db.scalar(
        select(GovernanceRun).where(or_(
            and_(GovernanceRun.status == "QUEUED", GovernanceRun.available_at <= now),
            and_(GovernanceRun.status == "RUNNING", GovernanceRun.lease_until <= now),
        )).order_by(
            case((priority == "HIGH", 0), (priority == "MEDIUM", 1), else_=2),
            GovernanceRun.available_at, GovernanceRun.id,
        ).limit(1).with_for_update()
    )
    if run is None:
        return None
    if run.attempt >= MAX_ATTEMPTS:
        transition(run, "FAILED", now)
        run.error_code = "LEASE_ATTEMPTS_EXHAUSTED"
        add_event(db, run, "FAILED", {"errorCode": run.error_code})
        db.commit()
        return None
    recovered = run.status == "RUNNING"
    run.status = "RUNNING"
    run.attempt += 1
    run.lease_owner = owner
    run.lease_until = now + LEASE
    run.updated_at = now
    run.error_code = None
    claim = Claim(run.id, owner, run.attempt)
    add_event(db, run, "RECLAIMED" if recovered else "CLAIMED", {"attempt": claim.attempt})
    db.commit()
    return claim


def lock_claim(db: Session, claim: Claim) -> GovernanceRun | None:
    if not governance_enabled() or not monitoring_enabled(db):
        return None
    run = db.scalar(select(GovernanceRun).where(GovernanceRun.id == claim.run_id).with_for_update())
    if (
        run is None or run.status != "RUNNING" or run.lease_owner != claim.owner
        or run.attempt != claim.attempt or run.lease_until <= utc_now()
    ):
        return None
    return run


def heartbeat(db: Session, claim: Claim) -> bool:
    run = lock_claim(db, claim)
    if run is None:
        return False
    run.lease_until = utc_now() + LEASE
    db.commit()
    return True


def finish(db: Session, claim: Claim, error_code: str | None = None, *, retry: bool = False) -> bool:
    run = lock_claim(db, claim)
    if run is None:
        return False
    now = utc_now()
    if error_code and retry and run.attempt < MAX_ATTEMPTS:
        transition(run, "QUEUED", now)
        run.available_at = now + timedelta(seconds=15 * run.attempt)
        kind = "RETRY_QUEUED"
    else:
        kind = "FAILED" if error_code else "SUCCEEDED"
        transition(run, kind, now)
    run.error_code = error_code
    add_event(db, run, kind, {"errorCode": error_code} if error_code else None)
    db.commit()
    return True
