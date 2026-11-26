from __future__ import annotations

import argparse
import json
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import SessionLocal
from app.core.errors import AppError
from app.project_integration.models import Project
from app.review_quality.monitoring import generate_monitoring_report, monitoring_enabled


_BEIJING_TZ = timezone(timedelta(hours=8), "Asia/Shanghai")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a scheduled review monitoring report for each project")
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        help="Beijing schedule date (YYYY-MM-DD), for retrying a missed run",
    )
    args = parser.parse_args(argv)
    today = datetime.now(_BEIJING_TZ).date()
    schedule_date = args.date or today
    if schedule_date.year < 1001 or schedule_date > today:
        parser.error("--date is outside the supported range")
    start_at = datetime.combine(schedule_date - timedelta(days=7), time.min, _BEIJING_TZ)
    end_at = datetime.combine(schedule_date, time.min, _BEIJING_TZ)
    try:
        with SessionLocal() as db:
            if not monitoring_enabled(db):
                print(json.dumps({"status": "DISABLED"}))
                return 0
            project_ids = list(db.scalars(select(Project.id).order_by(Project.id)))
    except SQLAlchemyError:
        print(json.dumps({"status": "FAILED", "errorCode": "MONITORING_DATABASE_ERROR"}))
        return 1

    failed = False
    for project_id in project_ids:
        try:
            with SessionLocal() as db:
                if not monitoring_enabled(db):
                    print(json.dumps({"status": "DISABLED"}))
                    break
                report = generate_monitoring_report(
                    db,
                    project_id=project_id,
                    start_at=start_at.astimezone(timezone.utc),
                    end_at=end_at.astimezone(timezone.utc),
                    idempotency_key=f"daily:{schedule_date.isoformat()}",
                    source="SCHEDULED",
                )
            outcome = {"reportId": report.id, "status": report.status, "errorCode": report.errorCode}
        except (AppError, SQLAlchemyError) as exc:
            outcome = {"status": "FAILED", "errorCode": exc.code if isinstance(exc, AppError) else "MONITORING_DATABASE_ERROR"}
        print(json.dumps({"projectId": project_id, **outcome}))
        failed |= outcome["status"] != "SUCCEEDED"
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
