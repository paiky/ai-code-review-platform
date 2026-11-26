from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import DATETIME, MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


ID_TYPE = BigInteger().with_variant(Integer, "sqlite")
TIMESTAMP = DateTime().with_variant(DATETIME(fsp=6), "mysql")
SNAPSHOT_TYPE = Text().with_variant(MEDIUMTEXT(), "mysql")


class MonitoringReport(Base):
    __tablename__ = "review_quality_monitor_reports"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "source", "idempotency_hash", name="uk_quality_monitor_request"
        ),
        Index("idx_quality_monitor_report_project", "project_id", "id"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    idempotency_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    start_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False)
    end_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_token: Mapped[str] = mapped_column(String(36), nullable=False)
    snapshot_json: Mapped[str | None] = mapped_column(SNAPSHOT_TYPE)
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)


class MonitoringIssue(Base):
    __tablename__ = "review_quality_monitor_issues"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "engine", "issue_type", "diagnostic_type", name="uk_quality_monitor_issue"
        ),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    engine: Mapped[str] = mapped_column(String(16), nullable=False)
    issue_type: Mapped[str] = mapped_column(String(64), nullable=False)
    diagnostic_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False)
    last_report_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    assignee: Mapped[str | None] = mapped_column(String(128))
    resolution: Mapped[str | None] = mapped_column(String(2048))
    acceptance_criteria: Mapped[str | None] = mapped_column(String(2048))
    evaluation_case_id: Mapped[int | None] = mapped_column(BigInteger)
    evaluation_run_id: Mapped[int | None] = mapped_column(BigInteger)
    closed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
