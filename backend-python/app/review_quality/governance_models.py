from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.review_quality.monitoring_models import ID_TYPE, TIMESTAMP


class GovernanceRun(Base):
    __tablename__ = "review_quality_governance_runs"
    __table_args__ = (
        UniqueConstraint("project_id", "evidence_key", name="uk_quality_governance_evidence"),
        Index("idx_quality_governance_claim", "status", "available_at", "id"),
        Index("idx_quality_governance_lease", "status", "lease_until", "id"),
        Index("idx_quality_governance_report", "project_id", "report_id", "id"),
        Index("idx_quality_governance_issue", "project_id", "issue_id", "id"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    report_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    issue_id: Mapped[int | None] = mapped_column(BigInteger)
    evidence_key: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    input_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    result_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    model_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(64))
    lease_until: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    error_code: Mapped[str | None] = mapped_column(String(64))
    available_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)


class GovernanceControl(Base):
    __tablename__ = "review_quality_governance_controls"

    issue_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    priority: Mapped[str | None] = mapped_column(String(16))
    conclusion: Mapped[str | None] = mapped_column(String(1000))


class GovernanceEvent(Base):
    __tablename__ = "review_quality_governance_events"
    __table_args__ = (Index("idx_quality_governance_event", "run_id", "id"),)

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False)
