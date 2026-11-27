import argparse
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import logging
import signal
from threading import Event
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.code_quality.models import CodeQualityModelProvider
from app.core.database import SessionLocal
from app.review_quality.governance_execution import execute
from app.review_quality.governance_models import GovernanceRun
from app.review_quality.governance_queue import claim_next, configured_provider_code, governance_enabled, heartbeat


LOG = logging.getLogger(__name__)


def run_once(owner: str, stopping: Event) -> bool:
    with SessionLocal() as db:
        claim = claim_next(db, owner)
    if claim is None:
        return False
    stopped = Event()
    with ThreadPoolExecutor(max_workers=1) as executor:
        task = executor.submit(execute, claim, stopped)
        while True:
            try:
                task.result(timeout=5)
                return True
            except TimeoutError:
                if task.done():
                    task.result()
                if stopping.is_set():
                    stopped.set()
                    return True
                try:
                    with SessionLocal() as db:
                        if not heartbeat(db, claim):
                            stopped.set()
                            return True
                except SQLAlchemyError:
                    stopped.set()
                    raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the review quality governance worker")
    parser.add_argument("--healthcheck", action="store_true")
    args = parser.parse_args()
    if not governance_enabled() or not configured_provider_code():
        return 1
    if args.healthcheck:
        try:
            with SessionLocal() as db:
                db.scalar(select(GovernanceRun.id).limit(1))
                if db.scalar(select(CodeQualityModelProvider.id).where(
                    CodeQualityModelProvider.provider_code == configured_provider_code(),
                    CodeQualityModelProvider.enabled.is_(True),
                )) is None:
                    return 1
        except SQLAlchemyError:
            return 1
        return 0
    logging.basicConfig(level=logging.INFO)
    stopping = Event()
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    owner = str(uuid4())
    while not stopping.is_set():
        try:
            if run_once(owner, stopping):
                continue
        except SQLAlchemyError as exc:
            LOG.warning("Governance queue unavailable (%s)", type(exc).__name__)
        stopping.wait(3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
