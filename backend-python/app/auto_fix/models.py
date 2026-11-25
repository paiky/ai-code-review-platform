from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import DATETIME, MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


ID = BigInteger().with_variant(Integer, "sqlite")
ACTIVATION_TIME = DateTime().with_variant(DATETIME(fsp=6), "mysql")
SNAPSHOT_TEXT = Text().with_variant(MEDIUMTEXT(), "mysql")


class AutoFixSettings(Base):
    __tablename__ = "code_quality_auto_fix_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    enabled_at: Mapped[object | None] = mapped_column(ACTIVATION_TIME)
    updated_at: Mapped[object] = mapped_column(ACTIVATION_TIME, nullable=False)
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False)


class FixRun(Base):
    __tablename__ = "code_quality_fix_runs"
    __table_args__ = (
        UniqueConstraint("project_id", "source_mr_iid", "developer_sha", name="uk_fix_run_mr_sha"),
        UniqueConstraint("project_id", "developer_branch", "active_slot", name="uk_fix_run_active_branch"),
        Index("idx_fix_run_task_review", "source_task_id", "source_review_key", "id"),
        Index("idx_fix_run_due", "status", "next_at", "id"),
    )

    id: Mapped[int] = mapped_column(ID, primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_task_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_mr_iid: Mapped[str] = mapped_column(String(32), nullable=False)
    source_review_key: Mapped[str] = mapped_column(String(64), nullable=False)
    source_review_version: Mapped[str] = mapped_column(String(128), nullable=False)
    inputs_json: Mapped[str] = mapped_column(SNAPSHOT_TEXT, nullable=False)
    enabled_at: Mapped[object] = mapped_column(ACTIVATION_TIME, nullable=False)
    base_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    developer_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    developer_branch: Mapped[str] = mapped_column(String(255, collation="utf8mb4_bin").with_variant(String(255), "sqlite"), nullable=False)
    active_slot: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    step: Mapped[str | None] = mapped_column(String(24))
    reason_code: Mapped[str | None] = mapped_column(String(64))
    reason: Mapped[str | None] = mapped_column(String(512))
    cancel_requested_at: Mapped[object | None] = mapped_column(DateTime)
    mr_iid: Mapped[str | None] = mapped_column(String(32))
    mr_url: Mapped[str | None] = mapped_column(String(1024))
    project_url: Mapped[str | None] = mapped_column(String(1024))
    merge_sha: Mapped[str | None] = mapped_column(String(64))
    merged_at: Mapped[object | None] = mapped_column(DateTime)
    notification_json: Mapped[str | None] = mapped_column(Text)
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_until: Mapped[object | None] = mapped_column(DateTime)
    next_at: Mapped[object] = mapped_column(DateTime, nullable=False)
    failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[object] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[object] = mapped_column(DateTime, nullable=False)


class FixRound(Base):
    __tablename__ = "code_quality_fix_rounds"

    run_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    number: Mapped[int] = mapped_column(Integer, primary_key=True)
    input_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    commit_sha: Mapped[str | None] = mapped_column(String(64))
    pushed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_task_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    review_key: Mapped[str | None] = mapped_column(String(64))
    review_version: Mapped[str | None] = mapped_column(String(128))
    critical_count: Mapped[int | None] = mapped_column(Integer)
    findings_json: Mapped[str | None] = mapped_column(SNAPSHOT_TEXT)
    created_at: Mapped[object] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[object | None] = mapped_column(DateTime)
