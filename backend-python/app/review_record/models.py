from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


ID_TYPE = BigInteger().with_variant(Integer, "sqlite")


class ReviewTask(Base):
    __tablename__ = "review_tasks"
    __table_args__ = (
        Index("idx_review_tasks_cc_created", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(64), nullable=False)
    external_source_id: Mapped[str | None] = mapped_column(String(128))
    external_url: Mapped[str | None] = mapped_column(String(512))
    source_branch: Mapped[str | None] = mapped_column(String(255))
    target_branch: Mapped[str | None] = mapped_column(String(255))
    commit_sha: Mapped[str | None] = mapped_column(String(128))
    before_sha: Mapped[str | None] = mapped_column(String(128))
    after_sha: Mapped[str | None] = mapped_column(String(128))
    author_name: Mapped[str | None] = mapped_column(String(128))
    author_username: Mapped[str | None] = mapped_column(String(128))
    template_code: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(32))
    target_types_json: Mapped[str | None] = mapped_column(Text)
    code_quality_profile_code: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="NOT_TRIGGERED")
    risk_level: Mapped[str | None] = mapped_column(String(32))
    error_message: Mapped[str | None] = mapped_column(String(1024))
    started_at: Mapped[object | None] = mapped_column(DateTime)
    finished_at: Mapped[object | None] = mapped_column(DateTime)
    created_at: Mapped[object | None] = mapped_column(DateTime)
    updated_at: Mapped[object | None] = mapped_column(DateTime)


class ReviewResult(Base):
    __tablename__ = "review_results"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    task_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    template_code: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(32))
    reminder_card_enabled: Mapped[bool | None] = mapped_column(Boolean)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    risk_item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    change_analysis_json: Mapped[str] = mapped_column(Text, nullable=False)
    risk_card_json: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(String(1024))
    created_at: Mapped[object | None] = mapped_column(DateTime)
    updated_at: Mapped[object | None] = mapped_column(DateTime)


class NotificationRecord(Base):
    __tablename__ = "notification_records"
    __table_args__ = (
        Index(
            "idx_notification_records_cc_created_status_task",
            "created_at",
            "status",
            "task_id",
        ),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    task_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    result_id: Mapped[int | None] = mapped_column(BigInteger)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    target: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    request_digest: Mapped[str | None] = mapped_column(String(1024))
    response_body: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(String(1024))
    sent_at: Mapped[object | None] = mapped_column(DateTime)
    created_at: Mapped[object | None] = mapped_column(DateTime)
    updated_at: Mapped[object | None] = mapped_column(DateTime)
