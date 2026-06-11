from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


ID_TYPE = BigInteger().with_variant(Integer, "sqlite")


class ProjectReviewPolicy(Base):
    __tablename__ = "project_review_policies"
    __table_args__ = (
        Index("idx_project_review_policies_project_enabled", "project_id", "enabled"),
        Index("idx_project_review_policies_project_risk_type", "project_id", "risk_type"),
        Index("idx_project_review_policies_source_feedback", "source_feedback_id"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    policy_type: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_type: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_feedback_id: Mapped[int | None] = mapped_column(BigInteger)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[object | None] = mapped_column(DateTime)
    updated_at: Mapped[object | None] = mapped_column(DateTime)
