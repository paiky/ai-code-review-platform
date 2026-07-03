from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


ID_TYPE = BigInteger().with_variant(Integer, "sqlite")


class ReviewQualityAcceptanceGate(Base):
    __tablename__ = "review_quality_acceptance_gates"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    change_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(64))
    profile: Mapped[str | None] = mapped_column(String(64))
    risk_type: Mapped[str | None] = mapped_column(String(64))
    evaluation_case_ids_json: Mapped[str | None] = mapped_column(Text)
    evaluation_run_ids_json: Mapped[str | None] = mapped_column(Text)
    rule_gap_summary_json: Mapped[str | None] = mapped_column(Text)
    admission_json: Mapped[str | None] = mapped_column(Text)
    exit_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[object | None] = mapped_column(DateTime)
    updated_at: Mapped[object | None] = mapped_column(DateTime)
