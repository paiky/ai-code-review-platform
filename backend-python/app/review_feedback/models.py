from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


ID_TYPE = BigInteger().with_variant(Integer, "sqlite")


class ReviewItemFeedback(Base):
    __tablename__ = "review_item_feedbacks"
    __table_args__ = (
        UniqueConstraint("task_id", "source_type", "item_fingerprint", name="uk_review_item_feedback_task_source_item"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    task_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    item_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    card_id: Mapped[str | None] = mapped_column(String(128))
    risk_id: Mapped[str | None] = mapped_column(String(128))
    review_key: Mapped[str | None] = mapped_column(String(64))
    finding_index: Mapped[int | None] = mapped_column(Integer)
    risk_type: Mapped[str | None] = mapped_column(String(64))
    risk_title: Mapped[str | None] = mapped_column(String(255))
    original_risk_level: Mapped[str | None] = mapped_column(String(32))
    feedback_type: Mapped[str] = mapped_column(String(64), nullable=False)
    reason_type: Mapped[str | None] = mapped_column(String(64))
    reason_text: Mapped[str | None] = mapped_column(Text)
    suggest_as_project_rule: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="PENDING")
    admin_comment: Mapped[str | None] = mapped_column(Text)
    item_snapshot_json: Mapped[str | None] = mapped_column(Text)
    operator_name: Mapped[str | None] = mapped_column(String(128))
    operator_username: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[object | None] = mapped_column(DateTime)
    updated_at: Mapped[object | None] = mapped_column(DateTime)
